"""A registered worker reads the stored config of its host over HTTP on both backends."""

from uuid import UUID, uuid4

import pytest

from integration.api.test_workspace_routes import PLATFORM, created, host, workspace
from integration.api.test_workspace_routes import world as world
from security.api.harness import BASE, TestClient
from skm.bootstrap.composition import _settings_registry
from skm.bootstrap.plugins import PluginSchema, merged_schemas, plugin_settings_view
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.settings.domain.entry import ConfigEntryId, EntryOp, new_entry
from skm.modules.settings.ports import ConfigEntryRepository, ConfigGenerationCounter
from skm.platform.config.effective import values_digest
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.sources.cli_overrides import InvocationOverrides, cli_layers
from skm.platform.config.store import ConfigStore, EmptyPackConfigSource, PackConfigSource, ScopeTree
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.platform.config.test_resolver import SECRET_REF, leaf

SECRET_KEY = "plugins.probe.credential"
SECRET = "secret://env/WORKER_CREDENTIAL"


@pytest.fixture
def client(world):
    api = create_app(
        world.core,
        route_table=build_route_table(MODULE_IDS),
        registry=world.core.bus._registry,
        no_background=True,
    )
    with TestClient(api, base_url=BASE, headers=world.headers) as http:
        yield http


@pytest.fixture
def worker(client):
    ws, host_id = workspace(client), host(client)
    registration = created(
        client.post(
            f"/api/v1/workspaces/{ws}/workers",
            json={
                "host_id": host_id,
                "display_name": "config reader",
                "capabilities": {
                    "platform": PLATFORM,
                    "runtimes": [],
                    "isolation_profiles": ["worktree"],
                    "max_concurrency": 1,
                    "labels": [],
                    "skm_version": "2.0.0",
                },
            },
        )
    )
    return host_id, {"Authorization": "Bearer " + registration["token_secret"]}


def server_loader(schemas):
    # The built-in host sections have no secret key. Register one using the plugin schema path.
    urn = "urn:skm:probe:settings:v1"
    credential = leaf(
        {"$ref": SECRET_REF}, chain="host", levels=["instance", "host"], sensitivity="secret", portable=False
    )
    document: JsonObject = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": urn,
        "type": "object",
        "additionalProperties": False,
        "x-skm-section": {"id": "plugins.probe", "owner": "probe", "title": "Probe"},
        "x-skm-codegen": {"python": {"kind": "settings_view"}},
        "properties": {"credential": credential},
    }
    merged = merged_schemas(schemas, [PluginSchema("probe", urn, "settings.v1.json", document)])
    registry = _settings_registry(merged, {urn: plugin_settings_view(merged, urn)})
    invocation = cli_layers(registry, InvocationOverrides(sets=("logging.level=debug",)))
    return ConfigLoader(registry, EmptyPackConfigSource(), invocation)


def test_worker_reads_stored_host_chain_and_instance_plugins(world, client, worker, monkeypatch):
    host_id, headers = worker
    target = ScopeRef(ScopeKind.HOST, ScopeId(UUID(host_id)))
    loader = server_loader(world.core.schemas)
    monkeypatch.setattr(world.core.bus, "_config", loader)
    path = f"/api/v1/worker/hosts/{host_id}/config"
    defaults = client.get(path, headers=headers)
    assert defaults.status_code == 200, defaults.text
    assert SECRET_KEY not in defaults.json()["values"]
    assert SECRET_KEY not in defaults.json()["invalid"]

    meta = world.meta()
    with world.core.uow_factory(meta) as uow:
        instance = ScopeRef(ScopeKind.INSTANCE, uow.repo(ScopeRegistry).instance().id)
        entries = uow.repo(ConfigEntryRepository)
        counter = uow.repo(ConfigGenerationCounter)
        rows: tuple[tuple[ScopeRef, str, JsonValue], ...] = (
            (instance, "logging.level", "info"),
            (target, "logging.level", "warning"),
            (instance, "worker.capacity", 2),
            (target, "worker.capacity", 3),
            (instance, "worker.labels", ["inherited"]),
            (target, SECRET_KEY, SECRET),
            (target, "worker.claim.poll_ms", -1),  # invalid but admitted key
            (instance, "plugins.allowed", ["probe", "optional"]),
            (instance, "plugins.required", ["probe"]),
        )
        for scope, key, value in rows:
            entries.add(
                new_entry(
                    entry_id=ConfigEntryId(uuid4()),
                    scope=scope,
                    key=key,
                    op=EntryOp.SET,
                    value=value,
                    locked=False,
                    reason="",
                    actor=world.owner.principal_id,
                    now=meta.received_at,
                )
            )
            counter.increment()
        generation = counter.current()
        pack_generation = uow.repo(PackConfigSource).generation()
        uow.commit()

    with world.core.uow_factory(world.meta(), readonly=True) as uow:
        serving_config = loader.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), target)
        assert serving_config.get("logging.level") == "debug"

    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    values = result["values"]
    assert result["host_id"] == host_id
    assert (result["generation"], result["pack_generation"]) == (generation, pack_generation)
    assert result["digest"] == values_digest(values)
    assert values["worker.capacity"] == 3
    excluded = {"logging.level", "worker.labels", SECRET_KEY}
    assert values.keys().isdisjoint(excluded)
    assert set(result["invalid"]).isdisjoint(excluded)
    assert "worker.claim.poll_ms" in result["invalid"]
    assert values.keys().isdisjoint(result["invalid"])
    assert values.keys().isdisjoint({"plugins.allowed", "plugins.required", "execution.review.max_rounds"})
    assert result["plugins"] == {"allowed": ["probe", "optional"], "required": ["probe"]}


def test_worker_config_refuses_foreign_host_and_human(client, worker):
    host_id, headers = worker
    other = created(client.post("/api/v1/hosts", json={"name": "other", "platform": PLATFORM}))
    foreign = client.get(f"/api/v1/worker/hosts/{other['host_id']}/config", headers=headers)
    human = client.get(f"/api/v1/worker/hosts/{host_id}/config")
    for response in (foreign, human):
        assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")
    missing = client.get(f"/api/v1/worker/hosts/{uuid4()}/config", headers=headers)
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
