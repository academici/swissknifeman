"""Project settings refuse machine-operator keys, including previously stored values."""

from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from security.api.harness import BASE, TestClient, World, make_world
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.settings.domain.entry import ConfigEntryId, EntryOp, new_entry
from skm.modules.settings.domain.history import ChangeKind, history_record
from skm.modules.settings.ports import ConfigEntryRepository, ConfigHistoryRepository
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

_PREFIX = "/api/v1/config"
_BLOCKED: Mapping[str, JsonValue] = {
    "runtimes.binaries": {"codex": "/synthetic/machine/path"},
    "runtimes.credentials.copy": {"codex": True},
    "runtimes.codex.allow_full_access": True,
    "runtimes.claude_code.allow_skip_permissions": True,
}
_LOCAL_PATH = "/synthetic/machine/path"


def seed_machine_entries(
    uow: UnitOfWork,
    scope: ScopeRef,
    actor: PrincipalId,
    now: datetime,
    values: Mapping[str, JsonValue],
) -> None:
    """Plant stale rows through storage ports so the public writes need not accept them."""
    for key, value in values.items():
        row = new_entry(
            entry_id=ConfigEntryId(uuid4()),
            scope=scope,
            key=key,
            op=EntryOp.SET,
            value=value,
            locked=False,
            reason="synthetic stale data",
            actor=actor,
            now=now,
        )
        uow.repo(ConfigEntryRepository).add(row)
        uow.repo(ConfigHistoryRepository).append(
            history_record(
                record_id=uuid4(),
                before=None,
                after=row,
                kind=ChangeKind.CREATED,
                actor=actor,
                request_id=None,
                reason="synthetic stale data",
                generation=1,
                now=now,
            )
        )


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def project(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[tuple[World, TestClient]]:
    dsn = request.getfixturevalue("clean_test_database").dsn if request.param == "postgres" else None
    world = make_world(tmp_path, database=dsn)
    table = build_route_table(("access", "settings"))
    registry = world.core.bus._registry
    try:
        with TestClient(
            create_app(world.core, route_table=table, registry=registry, no_background=True),
            base_url=BASE,
            headers=world.headers,
        ) as client:
            yield world, client
    finally:
        world.core.close()


def _denied(response: Any) -> None:
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "CONFIG_SCOPE_NOT_ALLOWED"
    assert response.json()["details"]["reason"] == "machine_owned"
    assert _LOCAL_PATH not in response.text


def test_project_set_and_import_refuse_machine_keys(project: tuple[World, TestClient]) -> None:
    world, client = project
    for key, value in _BLOCKED.items():
        path = f"{_PREFIX}/entries/instance/{key}"
        _denied(client.put(path, json={"value": value, "reason": "fixture", "confirmed": True}))
        _denied(client.request("DELETE", path, json={"reason": "fixture", "confirmed": True}))
        for action in ("unset", "lock", "unlock"):
            _denied(client.post(f"{path}/{action}", json={"reason": "fixture", "confirmed": True}))

    document = {"schema": "urn:skm:settings:document:v1", "runtimes": {"binaries": {"codex": _LOCAL_PATH}}}
    for dry_run in (True, False):
        _denied(
            client.post(
                f"{_PREFIX}/import",
                json={
                    "scope": {"level": "instance"},
                    "format": "json",
                    "document": document,
                    "reason": "fixture",
                    "dry_run": dry_run,
                },
            )
        )
    with world.core.uow_factory(world.meta(), readonly=True) as uow:
        entries = uow.repo(ConfigEntryRepository).entries_of_scope(world.core.instance_id)
        assert not (set(entries) & _BLOCKED.keys())
        assert (
            not uow.repo(ConfigHistoryRepository)
            .list(scope_id=world.core.instance_id, key=None, after=None, limit=100)
            .items
        )


def test_project_reads_and_replace_import_hide_stale_machine_inputs(
    project: tuple[World, TestClient],
) -> None:
    world, client = project
    instance = ScopeId(world.core.instance_id)
    host = ScopeId(uuid4())
    with world.core.uow_factory(world.meta()) as uow:
        uow.repo(ScopeRegistry).create(host, ScopeKind.HOST, parent=instance, workspace_id=None)
        seed_machine_entries(
            uow,
            ScopeRef(ScopeKind.INSTANCE, instance),
            cast("PrincipalId", world.owner.principal_id),
            world.core.clock.now(),
            _BLOCKED,
        )
        uow.commit()

    _denied(client.get(f"{_PREFIX}/entries/instance/runtimes.binaries"))
    _denied(client.get(f"{_PREFIX}/history", params={"key": "runtimes.binaries"}))
    _denied(client.get(f"{_PREFIX}/explain", params={"scope": f"host:{host}", "key": "runtimes.binaries"}))

    for key, value in (("runtimes.allowed", ["codex"]), ("plugins.allowed", ["a01.fixture"])):
        result = client.put(
            f"{_PREFIX}/entries/instance/{key}",
            json={"value": value, "reason": "test policy", "confirmed": True},
        )
        assert result.status_code == 200, result.text
        assert result.json()["entry"]["value"] == value

    for route, params in (
        ("entries", {"scope": "instance", "limit": 2}),
        ("history", {"scope": "instance", "limit": 2}),
        ("effective", {"scope": f"host:{host}"}),
        ("schema", {"section": "runtimes"}),
        ("export", {"scope": "instance", "format": "json"}),
    ):
        result = client.get(f"{_PREFIX}/{route}", params=params)
        assert result.status_code == 200, result.text
        assert _LOCAL_PATH not in result.text
        assert all(key not in result.text for key in _BLOCKED)
        if route == "schema":
            assert "binaries" not in result.json()["sections"][0]["schema"]["properties"]
        elif route in ("entries", "history"):
            assert {row["key"] for row in result.json()["items"]} == {"plugins.allowed", "runtimes.allowed"}

    exported = result.json()
    imported = client.post(
        f"{_PREFIX}/import",
        json={
            "scope": {"level": "instance"},
            "format": "json",
            "mode": "replace",
            "document": exported["document"],
            "expected_entries_digest": exported["digest"],
            "reason": "fixture",
            "confirmed": True,
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["entries_digest_after"] == exported["digest"]
    assert _LOCAL_PATH not in imported.text
    with world.core.uow_factory(world.meta(), readonly=True) as uow:
        entries = uow.repo(ConfigEntryRepository).entries_of_scope(instance)
        assert entries["runtimes.binaries"].value == _BLOCKED["runtimes.binaries"]
