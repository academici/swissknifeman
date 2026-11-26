"""PostgreSQL integration tests for overlay resolution and ``PostgresPackConfigSource`` (P09.03).

Covers PostgreSQL ``build_app`` composition, cycle-free ``extensions.packs.*`` resolution, layer precedence,
equal-priority tie-breaking, declared vs undeclared ``[[overrides]]``, disabled pack isolation, frozen run
``PackPins`` / ``FrozenConfig``, and ``settings.explain_config`` provenance.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

import psycopg
import pytest

from contracts.extensions.harness import FakeEstimator
from fakes.clock import FrozenClock
from skm.adapters.postgres.extensions.pack_config_source import PostgresPackConfigSource
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.adapters.resources.pack_reader import FilesystemPackReader
from skm.application_bus.client import SkmClient
from skm.bootstrap import composition
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.gateways import GatewayTable
from skm.kernel.generated.defs import ScopeRefDto
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.extensions import public as extensions_public
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.override_rules import can_override
from skm.modules.extensions.domain.pack import PackTrust
from skm.modules.extensions.domain.payload import PackPayload
from skm.modules.extensions.generated.commands import InstallPack, SyncBuiltinPacks
from skm.modules.extensions.generated.documents import PackPayload as PackPayloadDto
from skm.modules.extensions.generated.documents import PackPayloadFilesItem
from skm.modules.extensions.generated.queries import (
    GetResourceVersion,
    ListResources,
    ResolveResource,
)
from skm.modules.extensions.generated.queries import ResourceKind as QueryResourceKind
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.policy.module import MODULE as POLICY
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.settings.generated.queries import ExplainConfig, ExplainConfigDefsScopeRef
from skm.modules.settings.module import MODULE as SETTINGS
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.effective import EffectiveConfig, FrozenConfig
from skm.platform.config.store import ConfigStore, EmptyPackConfigSource, PackConfigSource, ScopeTree
from support.pg import TestDatabase, clean_test_database, pg_session, test_database
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]

pytestmark = pytest.mark.pg

ROOT = Path(__file__).resolve().parents[3]
PACKS_ROOT = ROOT / "resources" / "packs"
EXAMPLE_OVERLAY_DIR = ROOT / "tests" / "fixtures" / "overlays" / "example"
NOW = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)


@dataclass
class PgPackEnv:
    app: App
    dsn: str
    tmp_path: Path
    actor: Actor
    client: SkmClient
    workspace_id: WorkspaceId
    project_id: ProjectId
    plan_id: ScopeId
    run_id: ScopeId

    def effective(self, scope: ScopeRef | None, *, frozen: FrozenConfig | None = None) -> EffectiveConfig:
        meta = RequestMeta("req_eff_" + "0" * 22, Surface.CLI, None, NOW)
        with self.app.uow_factory(meta, readonly=True) as uow:
            return self.app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), scope, frozen=frozen)


def _payload_dto(payload: PackPayload) -> PackPayloadDto:
    files = tuple(
        PackPayloadFilesItem(path=f.path, content_b64=base64.b64encode(f.content).decode("ascii"))
        for f in payload.files
    )
    return PackPayloadDto(manifest_text=payload.manifest_text, files=files)


def _overlay_payload(
    slug: str,
    *,
    version: str = "1.0.0",
    priority: int = 100,
    config_lines: str = "",
    overrides_toml: str = "",
    prompt_key: str = "shared/work_policy",
    prompt_body: str = "Overlay prompt body.",
) -> PackPayloadDto:
    manifest = (
        f'schema = "urn:skm:extensions:pack:v1"\nslug = "{slug}"\nversion = "{version}"\n'
        f'title = "Overlay {slug}"\ndescription = "Test operator overlay {slug}."\n'
        f'publisher = "operator"\ntrust = "operator"\npriority = {priority}\n'
        f'license = "Apache-2.0"\nrequires_skm = ">=0.1.0,<1"\n{config_lines}\n{overrides_toml}\n'
    )
    prompt_text = (
        '+++\nschema = "urn:skm:extensions:prompt-block:v1"\n'
        f'block_type = "task_contract"\nvariables = []\n+++\n{prompt_body}\n'
    )
    b64 = base64.b64encode(prompt_text.encode("utf-8")).decode("ascii")
    return PackPayloadDto(
        manifest_text=manifest,
        files=(PackPayloadFilesItem(path=f"prompts/{prompt_key}.md", content_b64=b64),),
    )


def _open_pg_app(dsn: str, tmp_path: Path, *, invocation: JsonObject | None = None) -> App:
    clock = FrozenClock(NOW)
    state_root = tmp_path / f"app_{abs(hash(json.dumps(invocation or {}, sort_keys=True)))}"
    state_root.mkdir(parents=True, exist_ok=True)
    env = {"SKM_DATABASE_URL": dsn}
    bs = replace(
        load_bootstrap(None, env, state_root),
        instance_id=SEED.instance_id,
        database_application_name="skm-pack-config-test",
        database_pool_min_size=0,
        database_pool_max_size=3,
        database_pool_timeout_seconds=5,
    )
    gateways = GatewayTable(
        {TokenEstimator: FakeEstimator(), BuiltinPacks: PackagedBuiltinPacks(PACKS_ROOT)},
        "control_plane_gateway",
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        gateways=gateways,
        instance_id=SEED.instance_id,
    )
    return build_app(
        bs, surface=Surface.CLI, environ=env, invocation=invocation or {}, backend="postgres", overrides=ov
    )


@pytest.fixture
def pg_env(clean_test_database: TestDatabase, tmp_path: Path) -> Iterator[PgPackEnv]:
    app = _open_pg_app(clean_test_database.dsn, tmp_path)
    try:
        plan_id = ScopeId(UUID("01900000-0000-7000-8000-000000000101"))
        run_id = ScopeId(UUID("01900000-0000-7000-8000-000000000102"))
        with app.uow_factory(RequestMeta("req_seed_" + "1" * 21, Surface.CLI, None, NOW)) as uow:
            owner = new_principal(
                principal_id=SEED.principal_id,
                kind=PrincipalKind.HUMAN,
                display_name="owner",
                created_by=None,
                now=NOW,
            )
            uow.repo(PrincipalRepository).add(owner)
            uow.repo(MembershipRepository).upsert(
                Membership(SEED.instance_id, SEED.principal_id, Role.OWNER, None, NOW)
            )
            uow.commit()

        actor, client = SEED.actor(), app.client(actor=SEED.actor(), surface=Surface.CLI)
        ws_res: Any = client.dispatch(CreateWorkspace(slug="main", title="Main"))
        proj_res: Any = client.dispatch(
            CreateProject(workspace_id=ws_res.workspace_id, slug="app", title="App")
        )
        ws, proj = WorkspaceId(ws_res.workspace_id), ProjectId(proj_res.project_id)
        with app.uow_factory(RequestMeta("req_scopes_" + "2" * 19, Surface.CLI, None, NOW)) as uow:
            scopes = uow.repo(ScopeRegistry)
            scopes.create(plan_id, ScopeKind.PLAN, parent=ScopeId(proj), workspace_id=ws)
            scopes.create(run_id, ScopeKind.RUN, parent=plan_id, workspace_id=ws)
            uow.commit()

        yield PgPackEnv(app, clean_test_database.dsn, tmp_path, actor, client, ws, proj, plan_id, run_id)
    finally:
        app.close()


def _ask(client: SkmClient, query: object) -> Any:
    return client.ask(query)


def _set_value(
    client: SkmClient,
    level: Literal["instance", "workspace", "project", "plan", "run"],
    scope_id: UUID,
    key: str,
    value: Any,
) -> None:
    scope = SetValueDefsScopeRef(level=level, scope_id=scope_id)
    client.dispatch(SetValue(scope=scope, key=key, value=value, reason="integration test"))


def _install_example(client: SkmClient) -> None:
    example_dto = _payload_dto(FilesystemPackReader().read_dir(str(EXAMPLE_OVERLAY_DIR)))
    client.dispatch(
        InstallPack(payload=example_dto, origin_label="path:fixtures/overlays/example", trust="operator")
    )


def test_postgres_composition_wires_pack_config_source_and_preserves_empty_when_disabled(
    pg_env: PgPackEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = RequestMeta("req_comp_" + "3" * 21, Surface.CLI, None, NOW)
    with pg_env.app.uow_factory(meta, readonly=True) as uow:
        repo_source = uow.repo(PackConfigSource)
        assert isinstance(repo_source, PostgresPackConfigSource)
        assert repo_source.generation() == 0

    pg_env.client.dispatch(SyncBuiltinPacks())
    with pg_env.app.uow_factory(meta, readonly=True) as uow:
        assert uow.repo(PackConfigSource).generation() > 0

    monkeypatch.setattr(composition, "MANIFESTS", (ACCESS, SETTINGS, WORKSPACE, POLICY))
    no_ext_app = _open_pg_app(pg_env.dsn, pg_env.tmp_path / "no_ext")
    try:
        with no_ext_app.uow_factory(meta, readonly=True) as uow:
            disabled_source = uow.repo(PackConfigSource)
            assert isinstance(disabled_source, EmptyPackConfigSource)
            assert disabled_source.generation() == 0
            eff = no_ext_app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
            assert eff.pack_generation == 0
    finally:
        no_ext_app.close()


def test_no_config_cycle_when_resolving_pack_selection_keys(pg_env: PgPackEnv) -> None:
    pg_env.client.dispatch(SyncBuiltinPacks())
    _install_example(pg_env.client)

    tampered_pack_id = UUID("01900000-0000-7000-8000-000000000201")
    tampered_ver_id = UUID("01900000-0000-7000-8000-000000000202")
    tampered_manifest = json.dumps(
        {
            "schema": "urn:skm:extensions:pack:v1",
            "slug": "self-cycle",
            "version": "1.0.0",
            "title": "Self Cycle Pack",
            "description": "Attempts to mutate extensions.packs.* inside pack config.",
            "publisher": "operator",
            "trust": "operator",
            "priority": 900,
            "license": "Apache-2.0",
            "requires_skm": ">=0.1.0,<1",
            "config": {
                "extensions.packs.enabled": ["example-overlay", "self-cycle"],
                "extensions.packs.priority": {"core": 999},
                "context.report.top_sources": 42,
            },
            "exclusive_groups": [],
            "overrides": [],
        }
    )
    digest = "sha256:" + "c" * 64
    with psycopg.connect(pg_env.dsn) as conn:
        conn.execute(
            "INSERT INTO skm_extensions.packs (id, slug, title, publisher, trust, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (tampered_pack_id, "self-cycle", "Self Cycle Pack", "operator", "operator", NOW),
        )
        conn.execute(
            "INSERT INTO skm_extensions.pack_versions "
            "(id, pack_id, version, version_major, version_minor, version_patch, prerelease, digest, "
            "manifest, priority, state, origin, installed_at, installed_by) "
            "VALUES (%s, %s, '1.0.0', 1, 0, 0, NULL, %s, %s::jsonb, 900, 'active', "
            "'path:tampered/self-cycle', %s, %s)",
            (tampered_ver_id, tampered_pack_id, digest, tampered_manifest, NOW, SEED.principal_id),
        )
        conn.commit()

    ws_ref = ScopeRef(ScopeKind.WORKSPACE, ScopeId(pg_env.workspace_id))
    proj_ref = ScopeRef(ScopeKind.PROJECT, ScopeId(pg_env.project_id))
    eff_disabled = pg_env.effective(ws_ref)
    assert eff_disabled.get("extensions.packs.enabled") == ["core"]
    assert eff_disabled.get("context.report.top_sources") == 5
    assert eff_disabled.get("context.skills.budget_tokens") == 8000

    _set_value(pg_env.client, "workspace", pg_env.workspace_id, "extensions.packs.enabled", ["self-cycle"])
    eff_enabled = pg_env.effective(ws_ref)
    assert eff_enabled.get("context.report.top_sources") == 42
    assert set(cast("list[str]", eff_enabled.get("extensions.packs.enabled"))) == {"core", "self-cycle"}
    assert eff_enabled.get("extensions.packs.priority") == {}
    assert eff_enabled.get("context.skills.budget_tokens") == 8000

    _set_value(pg_env.client, "project", pg_env.project_id, "extensions.packs.enabled", ["example-overlay"])
    proj_eff = pg_env.effective(proj_ref)
    expected_packs = {"core", "example-overlay", "self-cycle"}
    assert set(cast("list[str]", proj_eff.get("extensions.packs.enabled"))) == expected_packs
    assert proj_eff.get("context.skills.budget_tokens") == 12000
    assert proj_eff.get("context.report.top_sources") == 42


def test_layer_precedence_with_example_overlay_fixture(pg_env: PgPackEnv) -> None:
    ws_ref = ScopeRef(ScopeKind.WORKSPACE, ScopeId(pg_env.workspace_id))
    proj_ref = ScopeRef(ScopeKind.PROJECT, ScopeId(pg_env.project_id))

    before = pg_env.effective(proj_ref)
    assert before.get("execution.debug.enabled") is False
    assert before.get("context.skills.budget_tokens") == 8000

    pg_env.client.dispatch(SyncBuiltinPacks())
    _install_example(pg_env.client)
    _set_value(
        pg_env.client, "workspace", pg_env.workspace_id, "extensions.packs.enabled", ["example-overlay"]
    )

    inst_eff = pg_env.effective(None)
    assert inst_eff.get("context.skills.budget_tokens") == 8000
    assert inst_eff.get("execution.debug.enabled") is False

    ws_eff = pg_env.effective(ws_ref)
    assert ws_eff.get("context.skills.budget_tokens") == 12000
    assert ws_eff.get("context.budget.supporting") == 36000
    assert ws_eff.get("context.report.top_sources") == 8
    assert ws_eff.get("execution.debug.enabled") is True
    intensity = cast("Mapping[str, str]", ws_eff.get("execution.work_policy.role_intensity"))
    assert intensity["executor"] == "heavy"
    assert intensity["scout"] == "medium"

    _set_value(pg_env.client, "project", pg_env.project_id, "context.skills.budget_tokens", 14000)
    _set_value(pg_env.client, "project", pg_env.project_id, "execution.debug.enabled", False)
    proj_eff = pg_env.effective(proj_ref)
    assert proj_eff.get("context.skills.budget_tokens") == 14000
    assert proj_eff.get("execution.debug.enabled") is False

    inv_app = _open_pg_app(
        pg_env.dsn, pg_env.tmp_path / "inv_prec", invocation={"set": ["execution.debug.enabled=true"]}
    )
    try:
        meta_prec = RequestMeta("req_prec_" + "5" * 21, Surface.CLI, None, NOW)
        with inv_app.uow_factory(meta_prec, readonly=True) as uow:
            inv_eff = inv_app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), proj_ref)
            assert inv_eff.get("execution.debug.enabled") is True
            assert inv_eff.get("context.skills.budget_tokens") == 14000
    finally:
        inv_app.close()


def test_deterministic_tie_break_and_instance_priority_override(pg_env: PgPackEnv) -> None:
    pg_env.client.dispatch(SyncBuiltinPacks())
    override_block = (
        '[[overrides]]\nkind = "prompt_block"\nkey = "shared/work_policy"\nreason = "Tie-break."\n'
    )
    alpha = _overlay_payload(
        "overlay-alpha",
        priority=100,
        config_lines='[config]\n"context.skills.budget_tokens" = 10000',
        overrides_toml=override_block,
        prompt_body="Alpha prompt body.",
    )
    beta = _overlay_payload(
        "overlay-beta",
        priority=100,
        config_lines='[config]\n"context.skills.budget_tokens" = 11000',
        overrides_toml=override_block,
        prompt_body="Beta prompt body.",
    )
    pg_env.client.dispatch(InstallPack(payload=beta, origin_label="path:overlays/beta", trust="operator"))
    pg_env.client.dispatch(InstallPack(payload=alpha, origin_label="path:overlays/alpha", trust="operator"))
    _set_value(
        pg_env.client,
        "workspace",
        pg_env.workspace_id,
        "extensions.packs.enabled",
        ["overlay-beta", "overlay-alpha"],
    )

    ws_ref = ScopeRef(ScopeKind.WORKSPACE, ScopeId(pg_env.workspace_id))
    for _ in range(3):
        assert pg_env.effective(ws_ref).get("context.skills.budget_tokens") == 11000

    resolved_equal = _ask(
        pg_env.client,
        ResolveResource(
            kind=QueryResourceKind.PROMPT_BLOCK,
            key="shared/work_policy",
            scope=ScopeRefDto(kind="workspace", id=pg_env.workspace_id),
        ),
    )
    assert resolved_equal.candidates[0].pack == "overlay-alpha"
    assert resolved_equal.candidates[0].reason == "chosen"

    _set_value(
        pg_env.client,
        "instance",
        SEED.instance_id,
        "extensions.packs.priority",
        {"overlay-alpha": 250, "overlay-beta": 100},
    )
    assert pg_env.effective(ws_ref).get("context.skills.budget_tokens") == 10000


def test_resource_overrides_declared_wins_and_undeclared_rejected(pg_env: PgPackEnv) -> None:
    pg_env.client.dispatch(SyncBuiltinPacks())
    _install_example(pg_env.client)
    _set_value(
        pg_env.client, "workspace", pg_env.workspace_id, "extensions.packs.enabled", ["example-overlay"]
    )

    ws_decision = _ask(
        pg_env.client,
        ResolveResource(
            kind=QueryResourceKind.PROMPT_BLOCK,
            key="shared/work_policy",
            scope=ScopeRefDto(kind="workspace", id=pg_env.workspace_id),
        ),
    )
    assert ws_decision.chosen is not None
    body_view = _ask(
        pg_env.client,
        GetResourceVersion(resource_version_id=ws_decision.chosen.resource_version_id, include_bodies=True),
    )
    assert body_view.bodies is not None
    assert "Operator overlay work policy" in body_view.bodies["work_policy.md"]

    inst_decision = _ask(
        pg_env.client,
        ResolveResource(
            kind=QueryResourceKind.PROMPT_BLOCK,
            key="shared/work_policy",
            scope=ScopeRefDto(kind="instance", id=SEED.instance_id),
        ),
    )
    assert inst_decision.candidates[0].pack == "core"

    undeclared = _overlay_payload("undeclared-overlay", priority=150, prompt_body="Undeclared override.")
    with pytest.raises(Conflict) as exc_info:
        pg_env.client.dispatch(
            InstallPack(payload=undeclared, origin_label="path:overlays/undeclared", trust="operator")
        )
    assert exc_info.value.code is ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED
    assert exc_info.value.details["kind"] == "prompt_block"
    assert exc_info.value.details["key"] == "shared/work_policy"

    with pytest.raises(Conflict) as holder_exc:
        can_override(
            PackTrust.THIRD_PARTY,
            PackTrust.THIRD_PARTY,
            declared={(ResourceKind.PROMPT_BLOCK, "shared/custom")},
            kind=ResourceKind.PROMPT_BLOCK,
            key="shared/custom",
            holder_trusts=(PackTrust.OPERATOR,),
        )
    assert holder_exc.value.code is ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED
    assert holder_exc.value.details["owner_trust"] == "operator"


def test_disabled_pack_isolation_for_config_and_resources(pg_env: PgPackEnv) -> None:
    pg_env.client.dispatch(SyncBuiltinPacks())
    dormant = _overlay_payload(
        "dormant-overlay",
        priority=500,
        config_lines='[config]\n"context.skills.budget_tokens" = 16000',
        prompt_key="shared/dormant_only",
        prompt_body="Should stay invisible while pack is disabled.",
    )
    pg_env.client.dispatch(
        InstallPack(payload=dormant, origin_label="path:overlays/dormant", trust="operator")
    )

    ws_ref = ScopeRef(ScopeKind.WORKSPACE, ScopeId(pg_env.workspace_id))
    eff = pg_env.effective(ws_ref)
    assert eff.get("context.skills.budget_tokens") == 8000

    meta_iso = RequestMeta("req_iso_" + "6" * 22, Surface.CLI, None, NOW)
    with pg_env.app.uow_factory(meta_iso, readonly=True) as uow, pytest.raises(NotFound):
        extensions_public.resolve_resource(uow, ResourceKind.PROMPT_BLOCK, "shared/dormant_only", config=eff)

    listed = _ask(
        pg_env.client,
        ListResources(
            kind=QueryResourceKind.PROMPT_BLOCK,
            scope=ScopeRefDto(kind="workspace", id=pg_env.workspace_id),
        ),
    )
    assert all(item.key != "shared/dormant_only" for item in listed.items)


def test_frozen_run_pins_and_frozen_config_survive_later_overlay_installs_and_upgrades(
    pg_env: PgPackEnv,
) -> None:
    pg_env.client.dispatch(SyncBuiltinPacks())
    run_ref = ScopeRef(ScopeKind.RUN, pg_env.run_id)

    with pg_env.app.uow_factory(
        RequestMeta("req_run1_" + "7" * 21, Surface.CLI, None, NOW), readonly=True
    ) as uow:
        initial_eff = pg_env.app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), run_ref)
        pins_run1 = extensions_public.pinned_pack_versions(uow, config=initial_eff)
        frozen_run1 = initial_eff.freeze(initial_eff.registry)
        initial_prompt = extensions_public.resolve_resource(
            uow, ResourceKind.PROMPT_BLOCK, "shared/work_policy", config=initial_eff, pins=pins_run1
        )

    _install_example(pg_env.client)
    _set_value(
        pg_env.client, "workspace", pg_env.workspace_id, "extensions.packs.enabled", ["example-overlay"]
    )

    override_block = '[[overrides]]\nkind = "prompt_block"\nkey = "shared/work_policy"\nreason = "Upgrade."\n'
    example_v2 = _overlay_payload(
        "example-overlay",
        version="1.1.0",
        priority=100,
        config_lines='[config]\n"context.skills.budget_tokens" = 15000\n"context.report.top_sources" = 9',
        overrides_toml=override_block,
        prompt_body="Upgraded 1.1.0 operator work policy.",
    )
    pg_env.client.dispatch(
        InstallPack(payload=example_v2, origin_label="path:overlays/example-v2", trust="operator")
    )

    with pg_env.app.uow_factory(
        RequestMeta("req_chk_" + "8" * 22, Surface.CLI, None, NOW), readonly=True
    ) as uow:
        run1_eff = pg_env.app.config.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), run_ref, frozen=frozen_run1
        )
        assert run1_eff.get("context.skills.budget_tokens") == 8000
        pinned_prompt = extensions_public.resolve_resource(
            uow, ResourceKind.PROMPT_BLOCK, "shared/work_policy", config=run1_eff, pins=pins_run1
        )
        assert pinned_prompt.resource_version_id == initial_prompt.resource_version_id
        assert pinned_prompt.digest == initial_prompt.digest

        fresh_eff = pg_env.app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), run_ref)
        pins_run2 = extensions_public.pinned_pack_versions(uow, config=fresh_eff)
        assert fresh_eff.get("context.skills.budget_tokens") == 15000
        fresh_prompt = extensions_public.resolve_resource(
            uow, ResourceKind.PROMPT_BLOCK, "shared/work_policy", config=fresh_eff, pins=pins_run2
        )
        assert fresh_prompt.resource_version_id != initial_prompt.resource_version_id


def test_explain_config_reports_pack_layers_priorities_and_generation(pg_env: PgPackEnv) -> None:
    pg_env.client.dispatch(SyncBuiltinPacks())
    _install_example(pg_env.client)
    _set_value(
        pg_env.client, "workspace", pg_env.workspace_id, "extensions.packs.enabled", ["example-overlay"]
    )
    _set_value(pg_env.client, "project", pg_env.project_id, "context.budget.supporting", 42000)

    explained = _ask(
        pg_env.client,
        ExplainConfig(
            scope=ExplainConfigDefsScopeRef(level="project", scope_id=pg_env.project_id),
            keys=("context.skills.budget_tokens", "context.budget.supporting"),
        ),
    )
    report = explained.to_json()
    assert cast("int", report["pack_generation"]) > 0

    pack_chain = [
        (item["pack_id"], item["pack_priority"])
        for item in cast("list[dict[str, Any]]", report["chain"])
        if item["level"] == "pack"
    ]
    assert pack_chain == [("core", 0), ("example-overlay", 100)]

    def _traces(entry: dict[str, Any]) -> list[tuple[Any, Any, Any]]:
        return [(c["layer"]["level"], c["layer"].get("pack_id"), c["status"]) for c in entry["contributions"]]

    by_key = {item["key"]: item for item in cast("list[dict[str, Any]]", report["keys"])}
    skills_report = by_key["context.skills.budget_tokens"]
    assert skills_report["value"] == 12000
    assert skills_report["winner"] == {"level": "pack", "pack_id": "example-overlay", "pack_priority": 100}
    assert ("pack", "core", "shadowed") in _traces(skills_report)
    assert ("pack", "example-overlay", "winner") in _traces(skills_report)

    supporting_report = by_key["context.budget.supporting"]
    assert supporting_report["value"] == 42000
    assert supporting_report["winner"]["level"] == "project"
    assert ("pack", "core", "shadowed") in _traces(supporting_report)
    assert ("pack", "example-overlay", "shadowed") in _traces(supporting_report)
