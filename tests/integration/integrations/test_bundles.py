"""End-to-end integration tests for integration bundles and pure-data agent packs (P10.06)."""

from __future__ import annotations

import base64
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.extensions.harness import FakeEstimator
from fakes.clock import FrozenClock
from skm.adapters.checkout_fs.local import LocalCheckoutFs
from skm.adapters.integrations.registry import default_target_registry
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.adapters.resources.pack_reader import FilesystemPackReader
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext, HostServices
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel import actor, cancel, gateways, ids, ports_uow, scopes, tokens
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, Forbidden, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.modules.access import ports as acc_ports
from skm.modules.access import public as acc_pub
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.extensions import ports as ext_ports
from skm.modules.extensions.application.candidate import DEFAULT_ALLOWED_LICENSES, build_candidate
from skm.modules.extensions.domain import compat as ext_compat
from skm.modules.extensions.domain import digest_rules as ext_dig
from skm.modules.extensions.domain import keys as ext_keys
from skm.modules.extensions.domain import resource as ext_res
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import PackTrust
from skm.modules.extensions.domain.payload import PackPayload
from skm.modules.extensions.generated import commands as ext_cmd
from skm.modules.extensions.generated import documents as ext_doc
from skm.modules.integrations import ports as int_ports
from skm.modules.integrations.domain import bundle as bdom
from skm.modules.integrations.domain.ownership import Ownership
from skm.modules.integrations.domain.projection import ApplyOutcome, ProjectionPlan, ProjectionState
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated import queries as gen_q
from skm.modules.integrations.generated import views as gen_v
from skm.modules.integrations.host.apply_projection import apply_projection
from skm.modules.integrations.host.detect_drift import detect_drift
from skm.modules.integrations.host.plan_projection import plan_projection
from skm.modules.integrations.host.registry import HOST_OPERATIONS
from skm.modules.integrations.host.remove_projection import remove_projection
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.workspace import public as ws_pub
from skm.modules.workspace.generated.commands import HostArch, HostOs, RegisterHostDefsHostPlatform
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.logging.logger import get_logger
from support.seed import SEED

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKS_ROOT = REPO_ROOT / "resources" / "packs"
AGENT_PACKS_SLOT = PACKS_ROOT / "agent-packs-local"
GOLDEN_ROOT = REPO_ROOT / "tests" / "golden" / "integrations" / "bundles"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
OWNER_ID = ids.PrincipalId(UUID("01900000-0000-7000-8000-0000000000e1"))
VIEWER_ID = ids.PrincipalId(UUID("01900000-0000-7000-8000-0000000000e2"))
_TOK_A = ("axioma", "azguard", "botkit", "academici", "perplexity-web", "memster", "chatom")
_TOK_B = ("swissknifeman", "vostrikov", "{{", "<!-- pack:if")
_TOK_C = ("agent-pack.lock.json", "settings.fragment.json")
FORBIDDEN_TOKENS = (*_TOK_A, *_TOK_B, *_TOK_C)
BUNDLE_GOLDENS: tuple[tuple[TargetId, str, str], ...] = (
    (TargetId.CLAUDE_CODE, ".claude/agents/team-code-auditor.md", "claude_code/team-code-auditor.md"),
    (TargetId.CLAUDE_CODE, ".claude/agents/team-reviewer.md", "claude_code/team-reviewer.md"),
    (TargetId.CLAUDE_CODE, ".claude/rules/common.md", "claude_code/common-rule.md"),
    (TargetId.CLAUDE_CODE, ".claude/workflows/dev-loop.js", "claude_code/dev-loop.js"),
    (TargetId.CODEX, ".codex/agents/team-code-auditor.toml", "codex/team-code-auditor.toml"),
    (TargetId.CODEX, ".codex/agents/team-reviewer.toml", "codex/team-reviewer.toml"),
    (TargetId.CURSOR, ".cursor/agents/team-code-auditor.md", "cursor/team-code-auditor.md"),
    (TargetId.CURSOR, ".cursor/agents/team-reviewer.md", "cursor/team-reviewer.md"),
    (TargetId.CURSOR, ".cursor/rules/common.mdc", "cursor/common-rule.mdc"),
    (TargetId.GROK, ".grok/rules/common.md", "claude_code/common-rule.md"),
    (TargetId.GROK, ".grok/workflows/dev-loop.js", "claude_code/dev-loop.js"),
)


class _NullHome:
    def read(self, logical: Any) -> bytes | None:
        return None


class _ForbiddenRunner:
    def run(self, *args: object, **kwargs: object) -> Any:
        raise AssertionError(f"HostCommandRunner must never execute: {args}")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _payload_dto(payload: PackPayload) -> ext_doc.PackPayload:
    items = tuple(
        ext_doc.PackPayloadFilesItem(path=f.path, content_b64=_b64(f.content)) for f in payload.files
    )
    return ext_doc.PackPayload(manifest_text=payload.manifest_text, files=items)


def _bundle_doc(
    key: str,
    *,
    version: str = "1.0.0",
    targets: Sequence[str] = ("claude_code",),
    agents: Sequence[Mapping[str, str]] = (),
    skills: Sequence[Mapping[str, str]] = (),
    assets: Sequence[Mapping[str, str]] = (),
) -> dict[str, JsonValue]:
    top: dict[str, JsonValue] = {"schema": "urn:skm:integrations:bundle:v1", "key": key, "version": version}
    meta: dict[str, JsonValue] = {"title": f"Bundle {key}", "description": f"Test bundle {key}."}
    body: dict[str, JsonValue] = {
        "targets": list[JsonValue](targets),
        "agents": [dict[str, JsonValue](a) for a in agents],
        "skills": [dict[str, JsonValue](s) for s in skills],
    }
    return {**top, **meta, **body, "assets": [dict[str, JsonValue](a) for a in assets]}


def _resolve_path(
    raw_path: str,
    *,
    target: TargetId = TargetId.CLAUDE_CODE,
    surface: bdom.BundleAssetSurface = bdom.BundleAssetSurface.RULES,
    own: Ownership = Ownership.MANAGED_FILE,
) -> str:
    return bdom.resolve_bundle_asset_path(
        raw_path=raw_path, target=target, surface=surface, pack_prefix="skm", ownership=own
    )


def _host_gateways(checkout_dir: Path, state_dir: Path) -> gateways.GatewayTable:
    fs = LocalCheckoutFs(checkout_dir, state_dir=state_dir, lock_timeout_seconds=0.1)
    table = {
        int_ports.IntegrationTargetRegistry: default_target_registry(),
        int_ports.CheckoutFs: fs,
        int_ports.UserHomeReader: _NullHome(),
        int_ports.HostCommandRunner: _ForbiddenRunner(),
        tokens.TokenEstimator: FakeEstimator(),
    }
    return gateways.GatewayTable(table, "host_gateway")


@dataclass
class _BundleEnv:
    app: App
    client: SkmClient
    services: HostServices
    ctx: HostContext
    checkout_dir: Path
    workspace_id: ids.WorkspaceId
    project_id: ids.ProjectId
    host_id: ids.HostId
    binding_id: ws_pub.CheckoutBindingId

    def run_cmd(self, cmd: object) -> Any:
        return self.client.dispatch(cmd, idempotency_key=self.client.new_idempotency_key())

    def set_cfg(self, level: Any, scope_id: Any, key: str, value: Any) -> None:
        scope = SetValueDefsScopeRef(level=level, scope_id=scope_id)
        self.run_cmd(SetValue(scope=scope, key=key, value=value, confirmed=True))

    def plan(self, target: TargetId = TargetId.CLAUDE_CODE) -> ProjectionPlan:
        return plan_projection(self.ctx, project_id=self.project_id, targets=(target,))[0]

    def apply(self, target: TargetId = TargetId.CLAUDE_CODE) -> ApplyOutcome:
        plans = plan_projection(self.ctx, project_id=self.project_id, targets=(target,))
        return apply_projection(self.ctx, plans)[0]

    def drift(self, target: TargetId = TargetId.CLAUDE_CODE) -> Mapping[str, Any]:
        return detect_drift(self.ctx, project_id=self.project_id, targets=(target,))[0]

    def remove(self, target: TargetId = TargetId.CLAUDE_CODE) -> ApplyOutcome:
        return remove_projection(self.ctx, project_id=self.project_id, target=target, restore_pre_image=True)

    def desired(self, target: Any = "claude_code") -> gen_v.DesiredProjectionView:
        pid, bid = self.project_id, self.binding_id
        res = self.client.ask(
            gen_q.GetDesiredProjection(project_id=pid, checkout_binding_id=bid, target=target)
        )
        assert isinstance(res, gen_v.DesiredProjectionView)
        return res

    def applied(self, target: Any = "claude_code") -> gen_v.AppliedStateView:
        pid, bid = self.project_id, self.binding_id
        res = self.client.ask(gen_q.GetAppliedState(project_id=pid, checkout_binding_id=bid, target=target))
        assert isinstance(res, gen_v.AppliedStateView)
        return res

    def install_migrated(self, *slugs: str) -> None:
        reader = FilesystemPackReader()
        for slug in slugs:
            dto = _payload_dto(reader.read_dir(str(AGENT_PACKS_SLOT / slug)))
            cmd = ext_cmd.InstallPack(
                payload=dto, origin_label=f"path:{slug}", trust="third_party", allow_quarantine=False
            )
            assert self.run_cmd(cmd).status in {"installed", "already_installed"}

    def seed_bundle_in_core(
        self, key: str, manifest: Mapping[str, JsonValue], *, bodies: Mapping[str, bytes] | None = None
    ) -> ids.ResourceVersionId:
        raw_b = {"bundle.toml": b"# seeded\n", **(bodies or {})}
        files = tuple(
            ext_res.ResourceFile(path, len(body), ext_dig.file_digest(body), "text/plain")
            for path, body in raw_b.items()
        )
        ok = ext_compat.CompatStatus.OK
        checks = tuple(ext_compat.CompatCheck(c, ok, "ok") for c in ext_compat.CompatCheckId)
        compat = ext_compat.CompatReport(checks, ext_compat.CompatVerdict.CLEAN)
        kind = ResourceKind.INTEGRATION_BUNDLE
        meta = ports_uow.RequestMeta("req_" + "2" * 26, ports_uow.Surface.CLI, None, NOW)
        with self.app.uow_factory(meta) as uow:
            cv = next(v for v in uow.repo(ext_ports.PackRepository).list_versions() if v.slug == "core")
            resources = uow.repo(ext_ports.ResourceRepository)
            res = resources.find(kind, key)
            if res is None:
                rid = ext_keys.ResourceId(UUID(int=abs(hash(("res", key))) % (1 << 120)))
                res = ext_res.Resource(rid, kind, key, cv.pack_id, NOW)
                resources.add(res)
            rv_id = ids.ResourceVersionId(UUID(int=abs(hash(("rv", key))) % (1 << 120)))
            pvid = ext_keys.PackVersionId(cv.version_id)
            sem, dig = ext_keys.SemVer.parse("1.0.0"), ext_dig.resource_digest(raw_b)
            rv = ext_res.ResourceVersion(
                rv_id, res.id, kind, key, pvid, sem, dig, dict(manifest), files, 0, compat, NOW
            )
            resources.add_version(rv, raw_b)
            uow.commit()
            return rv_id


@pytest.fixture
def bundle_env(tmp_path: Path) -> Iterator[_BundleEnv]:
    clock = FrozenClock(NOW)
    db_env = {"SKM_DATABASE_URL": "postgresql://127.0.0.1:5432/mem"}
    raw_bs = load_bootstrap(None, db_env, tmp_path / "boot")
    bs = replace(raw_bs, instance_id=SEED.instance_id, database_pool_min_size=0, database_pool_max_size=2)
    cp_map = {
        ext_ports.BuiltinPacks: PackagedBuiltinPacks(PACKS_ROOT),
        ext_ports.PackReader: FilesystemPackReader(),
        tokens.TokenEstimator: FakeEstimator(),
    }
    cp_gw = gateways.GatewayTable(cp_map, "control_plane_gateway")
    authz = acc_pub.RbacAuthorizer(clock)
    ov = CompositionOverrides(
        authorizer=authz, scopes=StoredScopeChain(), clock=clock, instance_id=SEED.instance_id, gateways=cp_gw
    )
    surf, env_vars = ports_uow.Surface.CLI, {"GITHUB_TOKEN": "ghp_DO_NOT_RESOLVE"}
    app = build_app(bs, surface=surf, environ=env_vars, invocation={}, backend=None, overrides=ov)
    try:
        with app.uow_factory(ports_uow.RequestMeta("req_" + "1" * 26, surf, None, NOW)) as uow:
            uow.repo(scopes.ScopeRegistry).create(
                SEED.instance_id, scopes.ScopeKind.INSTANCE, parent=None, workspace_id=None
            )
            principals = ((OWNER_ID, "owner", acc_pub.Role.OWNER), (VIEWER_ID, "viewer", acc_pub.Role.VIEWER))
            h_kind = actor.PrincipalKind.HUMAN
            for pid, name, role in principals:
                pr = new_principal(principal_id=pid, kind=h_kind, display_name=name, created_by=None, now=NOW)
                uow.repo(acc_ports.PrincipalRepository).add(pr)
                uow.repo(acc_ports.MembershipRepository).upsert(
                    Membership(SEED.instance_id, pid, role, None, NOW)
                )
            uow.commit()
        client = app.client(actor=actor.Actor(OWNER_ID, actor.PrincipalKind.HUMAN, "owner"), surface=surf)
        disp = lambda cmd: cast("Any", client.dispatch(cmd, idempotency_key=client.new_idempotency_key()))  # noqa: E731
        disp(ext_cmd.SyncBuiltinPacks())
        ws_id = ids.WorkspaceId(disp(ws_pub.CreateWorkspace(slug="ws", title="WS")).workspace_id)
        proj_id = ids.ProjectId(
            disp(ws_pub.CreateProject(workspace_id=ws_id, slug="demo", title="Demo")).project_id
        )
        plat = RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64)
        host_id = ids.HostId(disp(ws_pub.RegisterHost(name="dev", platform=plat)).host_id)
        repo_cmd = ws_pub.RegisterRepository(ws_id, "repo", "https://github.com/org/skm.git", None)
        repo_id = disp(repo_cmd).repository_id
        disp(ws_pub.AttachRepository(project_id=proj_id, repository_id=repo_id, mount_name="main"))
        co = tmp_path / "checkout"
        (co / ".git").mkdir(parents=True, exist_ok=True)
        bind_cmd = ws_pub.BindCheckout(
            repo_id, host_id, str(co), str(co), ("github.com/org/skm",), "a" * 40, False, NOW
        )
        b_id = ws_pub.CheckoutBindingId(disp(bind_cmd).binding_id)
        hgw = _host_gateways(co, tmp_path / "host-state")
        ops = {s.name: s for s in HOST_OPERATIONS}
        services = HostServices(host_id=host_id, surface=surf, gateways=hgw, host_config=dict, operations=ops)
        ctx = services.context(
            client=client, cancel=cancel.CancelSource().token, log=get_logger("test.bundles")
        )
        yield _BundleEnv(app, client, services, ctx, co, ws_id, proj_id, host_id, b_id)
    finally:
        app.close()


def test_migrated_agent_packs_neutral_compat_clean_and_installable(bundle_env: _BundleEnv) -> None:
    assert len(PackagedBuiltinPacks(PACKS_ROOT).payloads()) == 29
    pack_dirs = sorted(p.parent for p in AGENT_PACKS_SLOT.glob("*/pack.toml"))
    assert len(pack_dirs) == 10
    reader, est = FilesystemPackReader(), FakeEstimator()
    for pack_dir in pack_dirs:
        payload = reader.read_dir(str(pack_dir))
        for pf in payload.files:
            lowered = pf.content.decode("utf-8").lower()
            assert not pf.path.endswith(".sh")
            for token in FORBIDDEN_TOKENS:
                assert token not in lowered, f"{pack_dir.name}:{pf.path} contains {token!r}"
        cand = build_candidate(payload, estimator=est, scan=True, allowed_licenses=DEFAULT_ALLOWED_LICENSES)
        assert cand.manifest.trust is PackTrust.THIRD_PARTY
        assert cand.manifest.priority == -100
        assert dict(cand.manifest.config) == {}
        assert all(r.compat.verdict is ext_compat.CompatVerdict.CLEAN for r in cand.resources)
        bundles = [r for r in cand.resources if r.kind is ResourceKind.INTEGRATION_BUNDLE]
        assert len(bundles) == 1
        assert set(bdom.parse_bundle_manifest(bundles[0].manifest).targets) == {
            TargetId.ANTIGRAVITY,
            TargetId.CLAUDE_CODE,
            TargetId.CODEX,
            TargetId.CURSOR,
            TargetId.GROK,
        }

    bundle_env.install_migrated("agent-packs-common", "agent-packs-python-backend")
    dto = _payload_dto(reader.read_dir(str(AGENT_PACKS_SLOT / "agent-packs-common")))
    cmd = ext_cmd.InstallPack(
        payload=dto, origin_label="path:common", trust="third_party", allow_quarantine=False
    )
    assert bundle_env.run_cmd(cmd).status == "already_installed"


def test_bundle_projection_golden_outputs_and_grok_unsupported_agents(bundle_env: _BundleEnv) -> None:
    bundle_env.install_migrated("agent-packs-common", "agent-packs-python-backend")
    tgts, ags = ("claude_code", "codex", "cursor", "grok"), ({"key": "reviewer", "profile": "reviewer"},)
    review_doc = _bundle_doc("review-kit", targets=tgts, agents=ags, skills=({"key": "code-review"},))
    bundle_env.seed_bundle_in_core("review-kit", review_doc)
    enabled = ["agent-packs-common", "agent-packs-python-backend"]
    selected = ["agent-pack-common", "agent-pack-python-backend", "review-kit"]
    bundle_env.set_cfg("workspace", bundle_env.workspace_id, "extensions.packs.enabled", enabled)
    bundle_env.set_cfg("project", bundle_env.project_id, "integrations.agents.pack_prefix", "team")
    bundle_env.set_cfg("project", bundle_env.project_id, "integrations.bundles", selected)

    plans = plan_projection(bundle_env.ctx, project_id=bundle_env.project_id, targets=tuple(TargetId))
    outcomes = apply_projection(bundle_env.ctx, plans)
    assert {o.target for o in outcomes} == set(TargetId)
    assert all(o.state is ProjectionState.IN_SYNC for o in outcomes)

    co = bundle_env.checkout_dir
    grok_plan = next(p for p in plans if p.target is TargetId.GROK)
    assert not (co / ".grok" / "agents").exists()
    assert not (co / ".agents" / "agents").exists()
    assert (co / ".agents" / "rules" / "common.md").read_text().startswith("---\ntrigger: always_on\n---\n")
    assert ErrorCode.CAPABILITY_UNAVAILABLE.value in {str(d.get("code")) for d in grok_plan.diagnostics}
    assert "<!-- skm:begin id=bundle.agent-pack-common " in (co / "CLAUDE.md").read_text(encoding="utf-8")
    assert "<!-- skm:begin id=bundle.agent-pack-common " in (co / "AGENTS.md").read_text(encoding="utf-8")
    for target, rel_co, rel_gold in BUNDLE_GOLDENS:
        assert (co / rel_co).read_bytes() == (GOLDEN_ROOT / rel_gold).read_bytes(), (target, rel_co)


def test_gemini_cli_projects_and_removes_bundle_without_overwriting_user_context(
    bundle_env: _BundleEnv,
) -> None:
    target = TargetId.GEMINI_CLI
    instructions = {
        "target": target.value,
        "surface": "instructions",
        "source": "instructions.md",
        "path": "GEMINI.md",
        "ownership": "managed_block",
        "block_id": "bundle.gemini-kit",
    }
    manifest = _bundle_doc(
        "gemini-kit", targets=(target.value,), assets=(instructions,), skills=({"key": "code-review"},)
    )
    bundle_env.seed_bundle_in_core(
        "gemini-kit", manifest, bodies={"instructions.md": b"Verify the checkout before reporting.\n"}
    )
    bundle_env.set_cfg("project", bundle_env.project_id, "integrations.bundles", ["gemini-kit"])
    bundle_env.set_cfg("project", bundle_env.project_id, "integrations.targets", [target.value])
    checkout = bundle_env.checkout_dir
    context = checkout / "GEMINI.md"
    user_context = b"# User context\n\nKeep this context.\n"
    context.write_bytes(user_context)

    assert bundle_env.apply(target).state is ProjectionState.IN_SYNC
    assert context.read_bytes().startswith(user_context)
    assert (GOLDEN_ROOT / "gemini_cli" / "GEMINI.md").read_bytes() in context.read_bytes()
    skill = checkout / ".gemini" / "skills" / "code-review" / "SKILL.md"
    assert skill.read_text(encoding="utf-8").startswith("---\nname: code-review\n")
    assert bundle_env.apply(target).written == ()
    assert bundle_env.drift(target)["state"] == "in_sync"
    assert bundle_env.remove(target).state is ProjectionState.REMOVED
    assert context.read_bytes() == user_context
    assert not skill.exists()

    with pytest.raises(ValidationFailed):
        _resolve_path("GEMINI.md", target=target, surface=bdom.BundleAssetSurface.INSTRUCTIONS)
    with pytest.raises(CapabilityUnavailable):
        _resolve_path(".gemini/workflows/tool.js", target=target, surface=bdom.BundleAssetSurface.WORKFLOWS)


def test_bundle_lifecycle_idempotency_drift_foreign_preservation_and_reinstall(
    bundle_env: _BundleEnv,
) -> None:
    bundle_env.install_migrated("agent-packs-common", "agent-packs-python-backend")
    enabled = ["agent-packs-common", "agent-packs-python-backend"]
    selected = ["agent-pack-common", "agent-pack-python-backend"]
    bundle_env.set_cfg("workspace", bundle_env.workspace_id, "extensions.packs.enabled", enabled)
    bundle_env.set_cfg("project", bundle_env.project_id, "integrations.bundles", selected)

    co = bundle_env.checkout_dir
    (co / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    (co / ".claude" / "workflows").mkdir(parents=True, exist_ok=True)
    foreign_agent = co / ".claude" / "agents" / "user-custom-agent.md"
    foreign_wf = co / ".claude" / "workflows" / "user-flow.js"
    foreign_agent.write_text("# User Custom Agent\n", encoding="utf-8")
    foreign_wf.write_text("// user workflow\n", encoding="utf-8")
    (co / "CLAUDE.md").write_text("# Team Handbook\n\nPreserve user prose.\n", encoding="utf-8")

    assert bundle_env.apply().state is ProjectionState.IN_SYNC
    assert "# Team Handbook" in (co / "CLAUDE.md").read_text(encoding="utf-8")
    assert "bundle.agent-pack-common" in (co / "CLAUDE.md").read_text(encoding="utf-8")
    assert bundle_env.apply().written == ()
    assert (bundle_env.drift()["drifted"], bundle_env.drift()["state"]) == (0, "in_sync")

    drifted_rule = co / ".claude" / "rules" / "python-backend.md"
    drifted_rule.write_text("# Locally customized Python rule\n", encoding="utf-8")
    assert (bundle_env.drift()["drifted"], bundle_env.drift()["state"]) == (1, "drifted")

    removed = bundle_env.remove()
    assert (removed.state, removed.left_modified) == (
        ProjectionState.REMOVED,
        (".claude/rules/python-backend.md",),
    )
    assert drifted_rule.read_text(encoding="utf-8") == "# Locally customized Python rule\n"
    assert not (co / ".claude" / "rules" / "common.md").exists()
    assert not (co / ".claude" / "workflows" / "dev-loop.js").exists()
    assert not (co / ".claude" / "agents" / "skm-code-auditor.md").exists()
    assert foreign_agent.read_text(encoding="utf-8") == "# User Custom Agent\n"
    assert foreign_wf.read_text(encoding="utf-8") == "// user workflow\n"
    assert (co / "CLAUDE.md").read_text(encoding="utf-8") == "# Team Handbook\n\nPreserve user prose.\n"

    drifted_rule.unlink()
    assert bundle_env.apply().state is ProjectionState.IN_SYNC
    assert (co / ".claude" / "rules" / "python-backend.md").is_file()


def _install_pinned_pack(env: _BundleEnv, version: str, body: bytes) -> UUID:
    pt = (
        f'schema = "urn:skm:extensions:pack:v1"\nslug = "pinned-pack"\nversion = "{version}"\n'
        'title = "Pinned Pack"\ndescription = "Pinned test pack."\npublisher = "test"\n'
        'trust = "third_party"\npriority = -100\nlicense = "MIT"\nrequires_skm = ">=0.1.0,<1"\n'
    )
    bt = (
        f'schema = "urn:skm:integrations:bundle:v1"\nkey = "pinned-kit"\nversion = "{version}"\n'
        'title = "Pinned Kit"\ndescription = "Pinned bundle."\ntargets = ["claude_code"]\n'
        'agents = []\nskills = []\n\n[[assets]]\ntarget = "claude_code"\nsurface = "rules"\n'
        'source = "rules/pin.md"\npath = ".claude/rules/pin.md"\nownership = "managed_file"\n'
    )
    bdir = "integration-bundles/pinned-kit"
    f1 = ext_doc.PackPayloadFilesItem(path=f"{bdir}/bundle.toml", content_b64=_b64(bt.encode()))
    f2 = ext_doc.PackPayloadFilesItem(path=f"{bdir}/rules/pin.md", content_b64=_b64(body))
    payload = ext_doc.PackPayload(manifest_text=pt, files=(f1, f2))
    cmd = ext_cmd.InstallPack(
        payload=payload, origin_label=f"path:pinned-{version}", trust="third_party", allow_quarantine=False
    )
    pvid = ext_keys.PackVersionId(env.run_cmd(cmd).pack_version_id)
    with env.app.uow_factory(ports_uow.RequestMeta("req_" + "5" * 26, ports_uow.Surface.CLI, None, NOW)) as u:
        rows = u.repo(ext_ports.ResourceRepository).list_in_pack_versions([pvid], kind=None)
        return UUID(str(rows[0].id))


def test_pinned_bundle_immutability_and_quarantine_diagnostics(bundle_env: _BundleEnv) -> None:
    _install_pinned_pack(bundle_env, "1.0.0", b"# v1.0.0\n")
    pid = bundle_env.project_id
    bundle_env.set_cfg("workspace", bundle_env.workspace_id, "extensions.packs.enabled", ["pinned-pack"])
    bundle_env.set_cfg("project", pid, "integrations.bundles", ["pinned-kit"])
    bundle_env.set_cfg("project", pid, "extensions.packs.versions", {"pinned-pack": "1.0.0"})
    bundle_env.set_cfg(
        "project", pid, "extensions.resources.pinned", {"integration_bundle:pinned-kit": "1.0.0"}
    )

    bundle_env.apply()
    applied_before = bundle_env.applied()
    assert applied_before.projection is not None
    rv_v2 = _install_pinned_pack(bundle_env, "1.1.0", b"# v1.1.0\n")

    assert bundle_env.plan().desired_digest == applied_before.projection.desired_digest
    assert (bundle_env.checkout_dir / ".claude" / "rules" / "pin.md").read_bytes() == b"# v1.0.0\n"
    assert ErrorCode.CAPABILITY_UNAVAILABLE.value in {
        str(d["code"]) for d in bundle_env.desired("codex").diagnostics
    }

    bundle_env.set_cfg("project", pid, "extensions.packs.versions", {"pinned-pack": "1.1.0"})
    bundle_env.set_cfg(
        "project", pid, "extensions.resources.pinned", {"integration_bundle:pinned-kit": "1.1.0"}
    )
    bundle_env.run_cmd(ext_cmd.QuarantineResource(resource_version_id=rv_v2, reason="security review"))
    assert ErrorCode.RESOURCE_QUARANTINED.value in {str(d["code"]) for d in bundle_env.desired().diagnostics}


def test_bundle_path_safety_collisions_and_policy_ceiling_fail_closed(bundle_env: _BundleEnv) -> None:
    bad_a = ("/etc/passwd", "../escape.md", ".claude/rules/../../x.md", ".claude\\rules\\w.md")
    bad_b = (".claude/rules/n\x00.md", "C:.claude/rules/d.md", ".claude/agents/{other}-a.md")
    bad_c = (".claude/hooks/run.sh", ".claude/settings.json", ".claude/agents/wrong.md")
    for bad in (*bad_a, *bad_b, *bad_c):
        with pytest.raises(ValidationFailed) as exc_info:
            _resolve_path(bad)
        assert exc_info.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET

    with pytest.raises(ValidationFailed) as mf_root:
        _resolve_path("CLAUDE.md", surface=bdom.BundleAssetSurface.INSTRUCTIONS)
    assert mf_root.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET

    with pytest.raises(CapabilityUnavailable):
        _resolve_path(".grok/agents/h.md", target=TargetId.GROK, surface=bdom.BundleAssetSurface.AGENTS)

    dup_agents = ({"key": "rev", "profile": "reviewer"}, {"key": "rev", "profile": "scout"})
    with pytest.raises(ValidationFailed) as dup_agent:
        bdom.parse_bundle_manifest(_bundle_doc("dup-agents", agents=dup_agents))
    assert dup_agent.value.code is ErrorCode.INTEGRATION_PATH_COLLISION

    bad_asset = {
        "target": "claude_code",
        "surface": "rules",
        "source": "rules/missing.md",
        "path": ".claude/rules/missing.md",
        "ownership": "managed_file",
    }
    bundle_env.seed_bundle_in_core("missing-src", _bundle_doc("missing-src", assets=(bad_asset,)))
    bundle_env.set_cfg("project", bundle_env.project_id, "integrations.bundles", ["missing-src"])
    with pytest.raises(ValidationFailed) as missing_exc:
        bundle_env.plan()
    assert missing_exc.value.code is ErrorCode.SCHEMA_INVALID

    wide_doc = _bundle_doc("wide-agent-kit", agents=({"key": "impl", "profile": "executor"},))
    bundle_env.seed_bundle_in_core("wide-agent-kit", wide_doc)
    bundle_env.set_cfg("project", bundle_env.project_id, "integrations.permission_profile", "observe")
    bundle_env.set_cfg("project", bundle_env.project_id, "integrations.bundles", ["wide-agent-kit"])
    with pytest.raises(ValidationFailed) as ceiling_exc:
        bundle_env.apply()
    assert ceiling_exc.value.code is ErrorCode.EXTENSION_WIDENS_PERMISSIONS
    assert not (bundle_env.checkout_dir / ".claude" / "agents").exists()


def test_integration_05_zero_execution_on_passive_ops_and_consent_gate(
    bundle_env: _BundleEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawns: list[object] = []

    def _forbid_spawn(*args: object, **kwargs: object) -> Any:
        spawns.append(args)
        raise AssertionError("Passive/bundle operations must NEVER spawn subprocesses")

    monkeypatch.setattr(subprocess, "Popen", _forbid_spawn)
    monkeypatch.setattr(subprocess, "run", _forbid_spawn)

    untrusted_hook = bundle_env.checkout_dir / ".claude" / "hooks" / "untrusted.sh"
    untrusted_hook.parent.mkdir(parents=True, exist_ok=True)
    untrusted_hook.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")

    bundle_env.install_migrated("agent-packs-common")
    bundle_env.set_cfg(
        "workspace", bundle_env.workspace_id, "extensions.packs.enabled", ["agent-packs-common"]
    )
    bundle_env.set_cfg("project", bundle_env.project_id, "integrations.bundles", ["agent-pack-common"])

    bundle_env.desired()
    bundle_env.applied()
    bundle_env.plan()
    bundle_env.drift()
    assert spawns == []
    assert not (bundle_env.checkout_dir / ".claude" / "workflows" / "dev-loop.js").exists()

    gws, ops = bundle_env.services.gateways, bundle_env.services.operations
    api_srv = HostServices(bundle_env.host_id, ports_uow.Surface.API, gws, dict, ops)
    tok = cancel.CancelSource().token
    with pytest.raises(Forbidden):
        api_srv.run("integrations.host.apply_projection", {"plans": []}, client=bundle_env.client, cancel=tok)

    v_act = actor.Actor(VIEWER_ID, actor.PrincipalKind.HUMAN, "viewer")
    v_cli = bundle_env.app.client(actor=v_act, surface=ports_uow.Surface.CLI)
    v_cmd = SetValue(SetValueDefsScopeRef("project", bundle_env.project_id), "integrations.bundles", [])
    with pytest.raises(Forbidden):
        v_cli.dispatch(v_cmd, idempotency_key=v_cli.new_idempotency_key())
    assert not (bundle_env.checkout_dir / ".claude" / "workflows" / "dev-loop.js").exists()

    bundle_env.set_cfg("instance", SEED.instance_id, "integrations.permission_profile", "trusted_full_access")
    refused = bundle_env.desired()
    assert refused.profile == "workspace_contained"
    assert ErrorCode.INTEGRATION_TRUSTED_REFUSED.value in {str(d["code"]) for d in refused.diagnostics}
