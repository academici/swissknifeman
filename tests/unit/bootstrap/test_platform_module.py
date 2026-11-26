"""``PLATFORM_MANIFEST``, ``platform.migration_status`` and the migrator DSN (kernel-platform §5.6, K21).

No database: the handler runs over a fake ``SchemaVersionReader`` in a fake unit of work, so every state of
the chain against the history is a plain table. The registry check builds the real manifest against the
packaged schemas. The migrator DSN comes from bootstrap files in ``tmp_path`` and an explicit environment.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from skm.application_bus.context import QueryContext
from skm.application_bus.platform.doctor import DOCTOR
from skm.application_bus.platform.migrations import (
    MIGRATION_STATUS,
    AppliedMigration,
    PackagedMigration,
    SchemaVersionReader,
    handle,
)
from skm.application_bus.platform.outbox import LIST_DEAD_OUTBOX, RETRY_OUTBOX
from skm.application_bus.platform.storage import REPAIR_STORAGE_SAFE, VERIFY_STORAGE, StorageInspector
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.platform_module import PLATFORM_MANIFEST, resolve_migrator_dsn
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, InternalError, PreconditionFailed, ValidationFailed
from skm.kernel.ports_uow import Isolation
from skm.platform.generated.commands import RetryOutbox
from skm.platform.generated.queries import ListDeadOutbox, MigrationStatus
from skm.platform.generated.results import MigrationStatusResult
from skm.platform.schema.registry import SchemaRegistry

AT = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def packaged(*numbers: int, changed: Sequence[int] = ()) -> list[PackagedMigration]:
    return [
        PackagedMigration(n, f"{n:04d}_core_m{n}.sql", f"sha256:{'b' if n in changed else 'a'}{n}")
        for n in numbers
    ]


def applied(*numbers: int) -> list[AppliedMigration]:
    return [AppliedMigration(n, f"{n:04d}_core_m{n}.sql", f"sha256:a{n}", AT) for n in numbers]


class FakeReader:
    def __init__(self, chain: list[PackagedMigration], history: list[AppliedMigration]) -> None:
        self._chain, self._history = chain, history

    def packaged(self) -> list[PackagedMigration]:
        return self._chain

    def applied(self) -> list[AppliedMigration]:
        return self._history


def status(chain: list[PackagedMigration], history: list[AppliedMigration]) -> MigrationStatusResult:
    seen: list[type[object]] = []

    def repo(port: type[object]) -> object:
        seen.append(port)
        return FakeReader(chain, history)

    result = handle(
        MigrationStatus(), cast("QueryContext", SimpleNamespace()), cast("Any", SimpleNamespace(repo=repo))
    )
    assert seen == [SchemaVersionReader]  # the one read-only port, nothing else
    return result


def states(result: MigrationStatusResult) -> list[tuple[int, str]]:
    return [(item.version, item.state) for item in result.migrations]


# --- registration ---------------------------------------------------------------------------------


def test_manifest_registers_doctor_migration_status_and_outbox_but_no_apply() -> None:
    assert PLATFORM_MANIFEST.queries == (DOCTOR, MIGRATION_STATUS, LIST_DEAD_OUTBOX, VERIFY_STORAGE)
    assert PLATFORM_MANIFEST.commands == (RETRY_OUTBOX, REPAIR_STORAGE_SAFE)
    assert PLATFORM_MANIFEST.repository_ports == (SchemaVersionReader, StorageInspector)
    assert getattr(SchemaVersionReader, "__skm_port_kind__", None) == "repository"
    names = {getattr(spec, "name", "") for spec in PLATFORM_MANIFEST.queries} | {
        getattr(spec, "name", "") for spec in PLATFORM_MANIFEST.commands
    }
    assert "platform.migration_status" in names
    assert "platform.apply_migrations" not in names


def test_migration_status_is_an_instance_scoped_read_only_storage_query() -> None:
    assert MIGRATION_STATUS.name == "platform.migration_status"
    assert MIGRATION_STATUS.permission == "admin.storage"
    assert MIGRATION_STATUS.permission in PLATFORM_MANIFEST.permissions
    assert MIGRATION_STATUS.scope_of is None
    assert MIGRATION_STATUS.isolation is Isolation.REPEATABLE_READ
    assert MIGRATION_STATUS.internal is False
    assert MIGRATION_STATUS.dto is MigrationStatus
    assert MIGRATION_STATUS.result is MigrationStatusResult


def test_manifest_passes_the_bus_registry_and_routes_the_query() -> None:
    registry = BusRegistry.build(
        (PLATFORM_MANIFEST,),
        schemas=SchemaRegistry.load_default(),
        permission_catalog=PLATFORM_MANIFEST.permissions,
        disabled_modules=frozenset(),
    )
    assert registry.query(MigrationStatus) is MIGRATION_STATUS
    assert registry.query(ListDeadOutbox) is LIST_DEAD_OUTBOX
    assert registry.command(RetryOutbox) is RETRY_OUTBOX
    # Migrations are applied by the migrator, never routed: the name is an unregistered query.
    with pytest.raises(InternalError) as caught:
        registry.query(cast("Any", type("ApplyMigrations", (), {})))
    assert caught.value.code is ErrorCode.INTERNAL_ERROR
    assert caught.value.details == {"kind": "query", "name": "ApplyMigrations"}


# --- the handler ----------------------------------------------------------------------------------


def test_every_migration_applied_is_ok() -> None:
    result = status(packaged(1, 2, 3), applied(1, 2, 3))
    assert (result.known_version, result.db_version, result.state) == (3, 3, "ok")
    assert states(result) == [(1, "applied"), (2, "applied"), (3, "applied")]
    assert all(item.applied_at == AT for item in result.migrations)
    assert [item.name for item in result.migrations] == [
        "0001_core_m1.sql",
        "0002_core_m2.sql",
        "0003_core_m3.sql",
    ]


def test_pending_tail_means_not_migrated_and_has_no_timestamp() -> None:
    result = status(packaged(1, 2, 3), applied(1))
    assert (result.known_version, result.db_version, result.state) == (3, 1, "not_migrated")
    assert states(result) == [(1, "applied"), (2, "pending"), (3, "pending")]
    assert [item.applied_at for item in result.migrations] == [AT, None, None]


@pytest.mark.parametrize("chain", [packaged(1, 2), []])
def test_empty_history_is_not_migrated(chain: list[PackagedMigration]) -> None:
    result = status(chain, [])
    assert (result.db_version, result.state) == (0, "not_migrated")
    assert all(item.state == "pending" for item in result.migrations)


def test_a_changed_file_is_modified_and_a_foreign_row_is_unknown_and_newer_database_is_too_new() -> None:
    result = status(packaged(1, 2, changed=(2,)), applied(1, 2, 3))
    assert (result.known_version, result.db_version, result.state) == (2, 3, "too_new")
    assert states(result) == [(1, "applied"), (2, "modified"), (3, "unknown")]
    assert result.migrations[2].name == "0003_core_m3.sql"  # the history name, the file is not packaged


def test_checksums_are_compared_but_never_returned() -> None:
    document = status(packaged(1, changed=(1,)), applied(1)).to_json()
    assert "sha256" not in str(document)
    assert document["migrations"][0]["state"] == "modified"


# --- the migrator's DSN ---------------------------------------------------------------------------


def bootstrap(tmp_path: Path, body: str) -> str:
    path = tmp_path / "bootstrap.toml"
    head = 'schema = "urn:skm:config:bootstrap:v1"\ninstance_id = "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c11"\n'
    path.write_text(head + body, encoding="utf-8")
    return str(path)


def dsn(tmp_path: Path, explicit: str | None = None, path: str | None = None, **environ: str) -> Any:
    return resolve_migrator_dsn(explicit, bootstrap_path=path, instance=None, environ=environ, home=tmp_path)


def test_explicit_database_url_wins_and_needs_no_bootstrap(tmp_path: Path) -> None:
    target = dsn(tmp_path, "postgresql://skm_migrator:s3cretpass@db/skm")  # no bootstrap anywhere
    assert target.dsn == "postgresql://skm_migrator:s3cretpass@db/skm"
    assert "s3cretpass" in target.secrets
    assert "s3cretpass" not in repr(target)


def test_a_key_value_dsn_registers_its_password_on_its_own(tmp_path: Path) -> None:
    # A password echoed alone (a prompt, a tool's error) is masked only if it was registered by itself.
    target = dsn(tmp_path, "host=db dbname=skm user=skm_migrator password='pw x1'")
    assert "pw x1" in target.secrets
    encoded = dsn(tmp_path, "postgresql://skm_migrator:p%40ss@db/skm")
    assert {"p%40ss", "p@ss"} <= set(encoded.secrets)


def test_bootstrap_migrator_url_precedes_database_url(tmp_path: Path) -> None:
    path = bootstrap(
        tmp_path,
        '[access]\nmode = "embedded"\n[database]\nurl = "secret://env/APP_DSN"\nmigrator_url = "secret://env/MIGRATOR_DSN"\n',
    )
    target = dsn(
        tmp_path,
        None,
        path,
        APP_DSN="postgresql://skm_app:pw1@db/skm",
        MIGRATOR_DSN="postgresql://skm_migrator:pw2xxxxx@db/skm",
    )
    assert target.dsn == "postgresql://skm_migrator:pw2xxxxx@db/skm"
    assert "pw2xxxxx" in target.secrets


def test_database_url_is_the_fallback_when_no_migrator_url_is_configured(tmp_path: Path) -> None:
    path = bootstrap(tmp_path, '[access]\nmode = "embedded"\n[database]\nurl = "secret://env/APP_DSN"\n')
    assert (
        dsn(tmp_path, None, path, APP_DSN="postgresql://skm_app:pw1@db/skm").dsn
        == "postgresql://skm_app:pw1@db/skm"
    )


def test_explicit_url_beats_the_bootstrap(tmp_path: Path) -> None:
    path = bootstrap(
        tmp_path,
        '[access]\nmode = "embedded"\n[database]\nurl = "secret://env/APP_DSN"\nmigrator_url = "secret://env/MIGRATOR_DSN"\n',
    )
    assert (
        dsn(tmp_path, "postgresql://flag@db/x", path, MIGRATOR_DSN="postgresql://env@db/y").dsn
        == "postgresql://flag@db/x"
    )


def test_http_profile_without_a_dsn_is_refused_with_a_hint_and_no_api_call(tmp_path: Path) -> None:
    path = bootstrap(
        tmp_path,
        '[access]\nmode = "http"\n[api]\nendpoint = "https://skm.example.test/api/v1"\ncredential = "secret://env/SKM_API_TOKEN"\n',
    )
    with pytest.raises(CapabilityUnavailable) as caught:
        dsn(tmp_path, None, path)
    assert caught.value.code == ErrorCode.CAPABILITY_UNAVAILABLE
    assert "--database-url" in str(caught.value.details["hint"])


def test_a_missing_bootstrap_is_the_bootstrap_missing_precondition(tmp_path: Path) -> None:
    with pytest.raises(PreconditionFailed) as caught:
        dsn(tmp_path)
    assert caught.value.code == ErrorCode.BOOTSTRAP_MISSING


def test_an_unresolvable_secret_reference_does_not_leak(tmp_path: Path) -> None:
    path = bootstrap(
        tmp_path,
        '[access]\nmode = "embedded"\n[database]\nurl = "secret://env/APP_DSN"\nmigrator_url = "secret://env/NOPE_DSN"\n',
    )
    with pytest.raises(ValidationFailed) as caught:
        dsn(tmp_path, None, path)
    assert caught.value.details["reason"] == "secret_unresolved"
