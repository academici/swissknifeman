"""Real PostgreSQL composition; cache application wiring, recreate all rows before each test."""

from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import psycopg
import pytest

from contracts.context.harness import MutableBuiltinPacks, _profile_toml, _spec_doc, core_pack
from contracts.execution._worker_protocol_support import claim
from contracts.execution.harness import PEPPER, ExecSide, _FixedPepper, _publish_revision
from contracts.extensions.harness import pack_payload
from fakes.clock import FrozenClock
from fakes.ids import SequentialIds
from fixtures.execution.runtime import read_only_profile_layer
from integration.artifacts.test_upload_flow import OWNER_ID, add_file_dto, dispatch_new, seed_principals
from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.application_bus.client import SkmClient
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import ResourceVersionId, WorkerId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.public import RbacAuthorizer, Role, TokenPepperSource, authenticate_token
from skm.modules.extensions import public as extensions
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.planning.generated.commands import CreatePlan
from skm.modules.runtimes.domain.capability import StaticCapabilityCatalog
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.ports import CapabilityCatalog, HostRuntimeRepository
from skm.modules.workspace.generated.commands import HostArch, HostOs, RegisterHostDefsHostPlatform
from skm.modules.workspace.generated.documents import WorkerCapabilities
from skm.modules.workspace.generated.results import RegisterWorkerResult
from skm.modules.workspace.public import (
    AttachRepository,
    CreateProject,
    CreateWorkspace,
    RegisterHost,
    RegisterRepository,
    RegisterWorker,
)
from skm.platform.config.bootstrap import BootstrapConfig, load_bootstrap
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.tokens.heuristic import HeuristicTokenEstimator
from support.pg import clean_test_database, pg_session, test_database
from support.seed import SEED
from unit.execution.application._support import ROOT, set_setting

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
SYSTEM = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")


@dataclass(frozen=True)
class _CachedApplication:
    app: App
    boot: BootstrapConfig
    clock: FrozenClock
    estimator: HeuristicTokenEstimator
    dsn: str


class _Cache:
    value: _CachedApplication | None = None


@dataclass
class RecoverySide(ExecSide):
    root: Path
    boot: BootstrapConfig
    secret: str
    system: SkmClient


CATALOG = """schema = "urn:skm:runtimes:model-catalog:v1"
catalog_version = "1.3.0"
[runtimes.fake]
class_selectors = { economy = ["fake-b"], implementation = ["fake-b"], frontier = ["fake-a"] }
effort_selectors = { low = "low", medium = "medium", high = "high", xhigh = "xhigh" }
[[runtimes.fake.models]]
id = "fake-a"
display_name = "Synthetic A"
classes = ["economy", "implementation", "frontier"]
suited_roles = ["executor", "reviewer", "triager", "registrar", "advisor"]
context_window_tokens = 128000
patterns = []
status = "confirmed"
verified_at = "2026-11-17"
source = "https://example.invalid/synthetic"
notes = "No live capability evidence"
[runtimes.fake.models.pricing]
input_per_mtok_usd = "1.00"
output_per_mtok_usd = "2.00"
currency = "USD"
verified_at = "2026-11-17"
source = "https://example.invalid/synthetic"
[[runtimes.fake.models]]
id = "fake-b"
display_name = "Synthetic B"
classes = ["economy", "implementation", "frontier"]
suited_roles = ["executor", "reviewer", "triager", "registrar", "advisor"]
context_window_tokens = 128000
patterns = []
status = "confirmed"
verified_at = "2026-11-17"
source = "https://example.invalid/synthetic"
notes = "Bounded rework route"
[runtimes.fake.models.pricing]
input_per_mtok_usd = "1.00"
output_per_mtok_usd = "2.00"
currency = "USD"
verified_at = "2026-11-17"
source = "https://example.invalid/synthetic"
"""


def _pack():
    files = {f.path: f.content.decode() for f in core_pack("1.3.0").files}
    files["workflows/reviewed-development.toml"] = (
        (ROOT / "tests/fixtures/corpus/examples/execution/workflows/quick-fix.toml")
        .read_text()
        .replace('id = "quick-fix"', 'id = "reviewed-development"')
    )
    files["runtimes/models.toml"] = CATALOG
    for role in ("executor", "reviewer", "triager", "registrar"):
        files[f"agent-profiles/{role}.toml"] = _profile_toml(role, "1.3.0")
        if role != "executor":
            files[f"agent-profiles/{role}.toml"] = files[f"agent-profiles/{role}.toml"].replace(
                'policy_profile = "workspace-contained"', 'policy_profile = "read-only"'
            )
            files[f"agent-profiles/{role}.toml"] += read_only_profile_layer()
    files["agent-profiles/executor.toml"] = files["agent-profiles/executor.toml"].replace(
        'model_class = "implementation"', 'model_class = "economy"'
    )
    return pack_payload("core", "1.3.0", files=files)


def _application(request, root, dsn) -> _CachedApplication:
    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT clock_timestamp()").fetchone()
        assert row is not None
        (now,) = row
    if (current := _Cache.value) is not None:
        assert current.dsn == dsn
        current.app.config.clear_cache()
        current.clock.set(now)
        return current
    clock, estimator = FrozenClock(now), HeuristicTokenEstimator()
    fake = FakeRuntime(
        state_dir=root / "state",
        scenario=ROOT / "tests/fixtures/runtimes/fake/review-green.toml",
        allow_pgroup_best_effort=True,
    )
    boot = replace(
        load_bootstrap(None, {"SKM_DATABASE_URL": dsn}, root),
        instance_id=SEED.instance_id,
        database_pool_min_size=0,
        database_pool_max_size=8,
    )
    app = build_app(
        boot,
        surface=Surface.CLI,
        environ={},
        invocation={},
        backend="postgres",
        overrides=CompositionOverrides(
            RbacAuthorizer(clock),
            StoredScopeChain(),
            clock=clock,
            instance_id=SEED.instance_id,
            gateways=GatewayTable(
                {
                    BuiltinPacks: MutableBuiltinPacks(_pack()),
                    TokenEstimator: estimator,
                    TokenPepperSource: _FixedPepper(),
                    CapabilityCatalog: StaticCapabilityCatalog({"fake": fake.capabilities()}, {}),
                },
                "control_plane_gateway",
            ),
        ),
    )
    current = _CachedApplication(app, boot, clock, estimator, dsn)
    _Cache.value = current

    def close():
        app.close()
        _Cache.value = None

    request.session.addfinalizer(close)
    return current


@pytest.fixture
def recovery(request, tmp_path, tmp_path_factory, clean_test_database):
    """Only wiring is reused. clean_test_database truncates every mutable row before reseeding."""
    from contracts.execution._client_execution import ClientWorker, model_snapshot

    shared_root = tmp_path_factory.getbasetemp() / "m3-app"
    shared_root.mkdir(exist_ok=True)
    cache = _application(request, shared_root, clean_test_database.dsn)
    app, clock = cache.app, cache.clock
    owner = seed_principals(
        app,
        "postgres",
        people=(
            (OWNER_ID, PrincipalKind.HUMAN, "owner"),
            (SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"),
        ),
        roles=((SEED.instance_id, OWNER_ID, Role.OWNER), (SEED.instance_id, SYSTEM_PRINCIPAL_ID, Role.OWNER)),
    )
    client = app.client(actor=owner, surface=Surface.CLI)
    dispatch_new(client, SyncBuiltinPacks())
    ws = dispatch_new(client, CreateWorkspace("m3", "M3")).workspace_id
    project = dispatch_new(client, CreateProject(ws, "m3", "M3")).project_id
    repository = dispatch_new(
        client, RegisterRepository(ws, "M3", "https://example.invalid/m3.git", None)
    ).repository_id
    dispatch_new(client, AttachRepository(project, repository, mount_name="repo", role="primary"))
    platform = RegisterHostDefsHostPlatform(HostOs.LINUX, HostArch.X86_64)
    host1 = dispatch_new(client, RegisterHost("m3-one", platform)).host_id
    host2 = dispatch_new(client, RegisterHost("m3-two", platform)).host_id
    caps = WorkerCapabilities.from_json(
        {
            "runtimes": ["fake", "codex_cli"],
            "isolation_profiles": ["worktree", "landlock"],
            "max_concurrency": 4,
            "labels": ["linux"],
            "platform": {"os": "linux", "arch": "x86_64"},
            "skm_version": "2.0.0",
        }
    )
    registered = client.dispatch(RegisterWorker(ws, host1, "recovery-worker", caps))
    assert isinstance(registered, RegisterWorkerResult)
    worker_id = WorkerId(registered.worker_id)
    files = []
    for content in (b"Artifact 1\n", b"Artifact 2\n"):
        blob = client.upload_blob(ws, (content,), size=len(content), media_type="text/markdown")
        files.append(dispatch_new(client, add_file_dto(ws, project, blob)).file_version_id)
    plan = dispatch_new(client, CreatePlan(project, "M3 plan")).plan_id
    rev1 = _publish_revision(app, client, owner, clock, plan, _spec_doc(files[0]), "empty")
    rev2 = _publish_revision(app, client, owner, clock, plan, {"goal": "M3 recovery"}, "current")
    with app.uow_factory(RequestMeta("req_" + "a" * 26, Surface.CLI, None, clock.now())) as uow:
        actor = authenticate_token(uow, registered.token_secret, pepper=PEPPER, now=clock.now())
        cfg = app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.PLAN, plan))
        profile = extensions.resolve_resource(
            uow, extensions.ResourceKind.AGENT_PROFILE, "executor", config=cfg
        )
        uow.repo(HostRuntimeRepository).upsert(
            RuntimeInstallation(
                host1,
                "fake",
                "0.1.0",
                "/synthetic/fake",
                AuthState.OK,
                clock.now(),
                {
                    "executable_sha256": "sha256:" + "a" * 64,
                    "verification_key": "sha256:" + "b" * 64,
                    "adapter_version": "0.1.0",
                },
            )
        )
        uow.commit()
    worker_client = app.client(actor=actor, surface=Surface.WORKER)
    side = RecoverySide(
        "postgres",
        app,
        clock,
        owner,
        owner,
        client,
        client,
        worker_client,
        ws,
        project,
        repository,
        ws,
        project,
        plan,
        rev1,
        host1,
        host2,
        worker_id,
        worker_id,
        plan,
        rev1,
        rev2,
        plan,
        rev2,
        files[0],
        files[1],
        ResourceVersionId(profile.resource_version_id),
        cache.estimator,
        clean_test_database.dsn,
        SequentialIds(start=5000),
        tmp_path,
        cache.boot,
        registered.token_secret,
        app.client(actor=SYSTEM, surface=Surface.BACKGROUND),
    )
    for key, value in {
        "runtimes.allowed": ["fake"],
        "runtimes.preference": ["fake"],
        "runtimes.config_isolation.required": False,
        "runtimes.role_routing": {
            role: {"runtime": "fake"} for role in ("executor", "reviewer", "triager", "registrar")
        },
        "execution.advisor.enabled": False,
        "execution.lease.renew_every_seconds": 5,
        "runtimes.admission.bounded_fix.resume": "never",
    }.items():
        set_setting(side, key, value)
    worker = ClientWorker(worker_client, worker_id, host1, ws, registered.token_secret)
    dispatch_new(worker.client, model_snapshot(worker, clock.now(), ("fake-a", "fake-b")))
    return side


def recovery_claim(side: RecoverySide, *, key: str | None = None):
    """Offer the runtime published by the recovery worker's authenticated snapshot."""
    return claim(side, key=key, runtime_id="fake")


def expire(side, *, seconds=121):
    """Advance host facts and age the authoritative server lease, without waiting for wall time."""
    side.clock.advance(timedelta(seconds=seconds))
    with psycopg.connect(side.dsn) as conn:
        conn.execute(
            "UPDATE skm_execution.assignment_leases "
            "SET last_heartbeat_at=clock_timestamp()-interval '2 seconds', "
            "expires_at=clock_timestamp()-interval '1 second'"
        )
    return system_dispatch(side, "expire_leases")


def system_dispatch(side, name, **payload):
    dto = side.app.bus._registry.command_by_name("execution." + name).dto
    return side.system.dispatch(dto.from_json({"limit": 100, **payload}))
