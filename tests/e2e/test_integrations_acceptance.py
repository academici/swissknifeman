"""Acceptance suite for ``integrations`` across all four checkout targets (P10.Z)."""

from __future__ import annotations

import io
import json
import os
import sys
import tomllib
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast, override
from uuid import UUID

import psycopg
import pytest

from contracts.extensions.harness import FakeEstimator
from e2e.test_extensions_cli import CliSandbox as ExtSandbox
from e2e.test_integrations_doctor import LookupRunner
from e2e.test_projected_hooks import NATIVE_FILES, assert_native, install_hook_token
from fixtures.hooks.subprocess.harness import (
    HOOK,
    TARGETS,
    Invocation,
    claude_on_path,
    commands,
    installed_daemon,
    native_payload,
    runtime_environment,
)
from security.test_webhook_ssrf import _server
from skm.adapters.checkout_fs import local, user_home
from skm.adapters.event_sinks import _pinned_http, webhook, webhook_signing
from skm.adapters.git.repo_inspect import GitRepositoryInspector
from skm.adapters.integrations.registry import default_target_registry
from skm.adapters.resources import builtin_packs, pack_reader
from skm.adapters.secrets.env import EnvSecretResolver
from skm.application_bus import subscribers as bus_sub
from skm.application_bus.host import HostContext, HostServices
from skm.bootstrap.composition import open_cli_app
from skm.bootstrap.hook import with_hook_state
from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli import context, main
from skm.kernel import actor, error_codes, errors, gateways, ids, ports_uow, tokens
from skm.modules.extensions.ports import BuiltinPacks, PackReader
from skm.modules.integrations import ports as int_ports
from skm.modules.integrations.domain import events, filesystem, managed_block, observed, ownership, target
from skm.modules.integrations.domain.projection import LocalPreImageKey
from skm.modules.integrations.generated import queries, views
from skm.modules.integrations.host import evaluate_hook, observe, trust_hook_subscription
from skm.modules.workspace.ports import RepositoryInspector
from skm.modules.workspace.public import CheckoutBindingId
from skm.platform import system_clock, system_ids
from skm.platform.config import bootstrap, secrets
from skm.platform.logging.logger import get_logger
from skm.platform.schema.registry import SchemaRegistry
from support.git_repo import init_git_repo
from support.pg import TestDatabase, clean_test_database, pg_session, table_counts, test_database

__all__ = ["clean_test_database", "pg_session", "scratch_dsn", "test_database"]
pytestmark = [pytest.mark.e2e, pytest.mark.pg]

PACKS_ROOT = Path(__file__).resolve().parents[2] / "resources/packs"
TARGET_FLAGS = [arg for target_id in TARGETS for arg in ("--target", target_id)]
COMMON_BUNDLE = PACKS_ROOT / "agent-packs-local/agent-packs-common"
ENV_SECRET, HOOK_SECRET = "ghp_SUPER_SECRET_NEVER_ON_DISK", "whsec_acceptance_signing_key"
MCP_CFG = (
    '{"github":{"enabled":true,"type":"stdio","command":"npx","args":["-y","gh"],'
    '"env_refs":{"GITHUB_TOKEN":"secret://env/GITHUB_TOKEN"}}}'
)
RETRY_2 = {"max_attempts": 2, "backoff": {"initial_ms": 100, "factor": 1.0, "max_ms": 100}}


class FakeCheckoutFs:
    def __init__(self, root: Path) -> None:
        self.root, self.files = root, dict[str, bytes]()

    def read(self, relative_path: str) -> bytes | None:
        return self.files.get(relative_path)

    def stat(self, relative_path: str) -> filesystem.FileStat:
        raw = self.files.get(relative_path)
        return filesystem.FileStat(raw is not None, False, 0 if raw is None else len(raw))

    def _cas(self, relative_path: str, expected: str | None) -> None:
        cur = self.files.get(relative_path)
        if (None if cur is None else ownership.sha256_tagged(cur)) != expected:
            raise errors.Conflict(error_codes.ErrorCode.PROJECTION_CONFLICT, "CAS", details={"r": "cas"})

    def write_atomic(self, relative_path: str, data: bytes, *, expected_whole_digest: str | None) -> str:
        self._cas(relative_path, expected_whole_digest)
        self.files[relative_path] = bytes(data)
        return ownership.sha256_tagged(data)

    def remove(self, relative_path: str, *, expected_whole_digest: str) -> None:
        self._cas(relative_path, expected_whole_digest)
        self.files.pop(relative_path, None)

    def is_gitignored(self, relative_path: str) -> bool | None:
        return False


@dataclass
class AcceptanceBox(ExtSandbox):
    repo_dir: Path = Path()
    fs_override: int_ports.CheckoutFs | None = None
    runner_override: int_ports.HostCommandRunner | None = None
    project_id: str = ""
    binding_id: str = ""

    @property
    def state_dir(self) -> Path:
        return self.root / "state/skm"

    @override
    def env(self) -> dict[str, str]:
        env, hjson = super().env(), self.state_dir / "host.json"
        env["PATH"] = str(HOOK.parent) + os.pathsep + env.get("PATH", "")
        env.update(GITHUB_TOKEN=ENV_SECRET, SKM_HOOK_SECRET=HOOK_SECRET)
        if hjson.is_file():
            env["SKM_HOST_ID"] = json.loads(hjson.read_text())["host_id"]
        return env

    @override
    def backend_factory(self) -> main.BackendFactory:
        ops = {s.name: s for m in MANIFESTS for s in m.host_operations}

        def _open(opts: context.CliOptions, environ: Mapping[str, str]) -> main.Backend:
            bs = bootstrap.load_bootstrap(opts.bootstrap, environ, self.home, instance=opts.instance)
            bs = replace(bs, host_id=None) if bs.host_id == "auto" else bs
            inv: dict[str, Any] = {"set": list(opts.sets)}
            app, act = open_cli_app(bs, environ=environ, invocation=inv, as_token=opts.actor_hint)
            cp = {**app.bus._gateways.entries, BuiltinPacks: builtin_packs.PackagedBuiltinPacks(PACKS_ROOT)}
            cp[tokens.TokenEstimator] = FakeEstimator()
            app.bus._gateways = gateways.GatewayTable(cp, "control_plane_gateway")
            hid = ids.HostId(bs.host_id) if isinstance(bs.host_id, UUID) else ids.HostId(app.instance_id)
            gws = dict(app.host.gateways.entries) if app.host is not None else {}
            gws[RepositoryInspector] = GitRepositoryInspector(clock=system_clock.SystemClock())
            cfs = self.fs_override or local.LocalCheckoutFs(self.repo_dir, state_dir=bs.state_dir)
            uh = user_home.LocalUserHomeReader(self.home, managed_root=self.root / "mgd")
            gws.update({int_ports.CheckoutFs: cfs, int_ports.UserHomeReader: uh})
            gws[int_ports.IntegrationTargetRegistry] = default_target_registry()
            gws[PackReader] = pack_reader.FilesystemPackReader()
            if self.runner_override is not None:
                gws[int_ports.HostCommandRunner] = self.runner_override
            host = HostServices(
                hid, ports_uow.Surface.CLI, gateways.GatewayTable(gws, "host_gateway"), dict, ops
            )
            return replace(main.app_backend(replace(app, host=host), act), state_dir=bs.state_dir)

        return _open

    def _invoke(self, argv: list[str]) -> tuple[int, str, str]:
        out, err, si, be = io.StringIO(), io.StringIO(), io.StringIO(""), self.backend_factory()
        code = main.main(argv, stdin=si, stdout=out, stderr=err, environ=self.env(), backend=be)
        return code, out.getvalue(), err.getvalue()

    def run_json(self, *argv: str) -> tuple[int, dict[str, Any]]:
        code, out, _ = self._invoke(["--json", *argv])
        return code, json.loads(out.strip().splitlines()[-1])

    def ok(self, *argv: str) -> Any:
        code, env = self.run_json(*argv)
        assert (code, env["ok"]) == (0, True), json.dumps(env)
        return env["result"]

    @contextmanager
    def host_ctx(self) -> Iterator[tuple[HostContext, Path]]:
        be = self.backend_factory()(context.CliOptions(), self.env())
        assert be.host_factory is not None
        try:
            yield be.host_factory(), be.state_dir or self.state_dir
        finally:
            if be.close is not None:
                be.close()

    def ask_applied(self, tgt: str) -> views.AppliedStateView:
        with self.host_ctx() as (ctx, _):
            pid, bid = ids.ProjectId(UUID(self.project_id)), CheckoutBindingId(UUID(self.binding_id))
            req = queries.GetAppliedState(pid, bid, cast("Any", tgt))
            return cast("views.AppliedStateView", ctx.client.ask(req))


@pytest.fixture
def scratch_dsn(clean_test_database: TestDatabase) -> str:
    with psycopg.connect(clean_test_database.dsn) as connection:
        connection.execute("DELETE FROM skm_core.scopes")
    return clean_test_database.dsn


@pytest.fixture
def acc_box(tmp_path: Path, scratch_dsn: str) -> AcceptanceBox:
    repo = init_git_repo(tmp_path / "repos/skm-acc")
    repo.commit_file("README.md", "# SKM Acceptance\n", message="Initial commit")
    repo.add_remote("origin", "https://github.com/acme/skm-acc.git")
    box = AcceptanceBox(tmp_path / "box", scratch_dsn, PACKS_ROOT, repo_dir=repo.path)
    box.home.mkdir(parents=True, exist_ok=True)
    box.ok("init", "--database-url", scratch_dsn)
    box.ok("ext", "sync")
    box.ok("ext", "install", str(COMMON_BUNDLE), "--trust", "third_party", "--no-quarantine")
    proj = box.ok("project", "create", "skm", "--workspace", "personal", "--title", "SKM")
    box.project_id = str(proj["project_id"])
    box.ok("use", "personal/skm")
    box.ok("host", "register", "acc-host", "--os", "linux", "--arch", "x86_64")
    bind_args = ("repo", "bind", "--path", str(repo.path), "--mount", "main", "--register", "--write-marker")
    box.binding_id = str(box.ok(*bind_args)["binding_id"])
    packs, rules = '["core","agent-packs-common"]', "## Acceptance Rules\n- Test."
    box.ok("config", "set", "extensions.packs.enabled", packs, "--scope", "workspace")
    box.ok("config", "set", "integrations.bundles", '["agent-pack-common"]', "--scope", "project")
    box.ok("config", "set", "integrations.instructions.project_text", rules, "--scope", "project")
    box.ok("config", "set", "integrations.mcp.servers", MCP_CFG, "--scope", "project")
    return box


def test_antigravity_projection_preserves_owner_configuration_and_shared_skills(
    acc_box: AcceptanceBox,
) -> None:
    checkout = acc_box.repo_dir
    instructions = checkout / ".agents/AGENTS.md"
    user_mcp = checkout / ".agents/mcp_config.json"
    instructions.parent.mkdir()
    instructions.write_text("# Team instructions\n", encoding="utf-8")
    user_mcp.write_text('{"mcpServers":{}}\n', encoding="utf-8")
    flags = ("--target", "antigravity", "--target", "codex")
    assert [item["state"] for item in acc_box.ok("integrations", "apply", *flags, "--yes")] == ["in_sync"] * 2

    assert instructions.read_text().startswith("# Team instructions")
    assert "Acceptance Rules" in instructions.read_text()
    assert (checkout / ".agents/rules/common.md").read_text().startswith("---\ntrigger: always_on\n---\n")
    assert not (checkout / ".agents/hooks.json").exists()
    assert not (checkout / ".agents/agents").exists()
    assert user_mcp.read_text() == '{"mcpServers":{}}\n'

    shared = [
        file.relative_path
        for file in acc_box.ask_applied("antigravity").files
        if "skills/" in file.relative_path
    ]
    assert shared
    acc_box.ok("integrations", "remove", "--target", "antigravity", "--yes")
    assert all((checkout / path).is_file() for path in shared)
    assert instructions.read_text().strip() == "# Team instructions"
    assert user_mcp.read_text() == '{"mcpServers":{}}\n'
    assert not (checkout / ".agents/rules/common.md").exists()


def _wh_sub(url: str, *, cls: str = "workflow", policy: str = "deny", attempts: int = 2) -> dict[str, Any]:
    sub: dict[str, Any] = {"class": cls, "kind": "webhook", "execution_location": "control_plane"}
    evt = ["urn:skm:integrations:event:*"]
    sub.update(event_types=evt, failure_policy=policy, retry={**RETRY_2, "max_attempts": attempts})
    sub["target"] = {"url": url, "secret": "secret://env/SKM_HOOK_SECRET"}
    return sub


def _cmd_sub(code: str, *, cls: str = "enforcement", policy: str = "deny") -> dict[str, Any]:
    sub: dict[str, Any] = {"class": cls, "kind": "command", "execution_location": "host"}
    sub.update(event_types=["client:pre_shell"], failure_policy=policy)
    sub["target"] = {"argv": [sys.executable, "-c", code], "cwd": "checkout"}
    if policy == "retry":
        sub["retry"] = dict(RETRY_2)
    return sub


def test_four_targets_fake_and_real_checkout_receipts_noop_and_zero_planning(acc_box: AcceptanceBox) -> None:
    co = acc_box.repo_dir
    (co / "PLAN.md").write_text("# Draft Plan\n- [ ] Not imported by projection\n")
    fake_fs = FakeCheckoutFs(co)
    acc_box.fs_override = fake_fs
    acc_box.ok("config", "set", "integrations.bundles", "[]", "--scope", "project")
    flags = TARGET_FLAGS
    pa, pb = acc_box.ok("integrations", "plan", *flags), acc_box.ok("integrations", "plan", *flags)
    for k in ("plan_digest", "desired_digest"):
        assert [p[k] for p in pa] == [p[k] for p in pb]
    assert (fake_fs.files, (co / "CLAUDE.md").exists()) == ({}, False)
    grok_diags = next(p["diagnostics"] for p in pa if p["target"] == "grok")
    assert any(d.get("code") == "CAPABILITY_UNAVAILABLE" for d in grok_diags)
    acc_box.ok("config", "set", "integrations.bundles", '["agent-pack-common"]', "--scope", "project")
    rule = ".claude/rules/common.md"
    fake_fs.files[rule] = b"# Local rule\n"
    acc_box.ok("integrations", "adopt", rule, "--target", "claude_code", "--reason", "own", "--yes")
    assert [i["state"] for i in acc_box.ok("integrations", "apply", *flags, "--yes")] == ["in_sync"] * 4
    assert fake_fs.files[rule] != b"# Local rule\n"
    assert all(r["drifted"] == 0 for r in acc_box.ok("integrations", "drift", *flags))
    assert {"CLAUDE.md", "AGENTS.md", ".cursor/rules/skm-instructions.mdc"} <= set(fake_fs.files)
    assert not (co / "CLAUDE.md").exists()
    assert not any(p.startswith(".grok/agents/") for p in fake_fs.files)
    assert all(i["written"] == [] for i in acc_box.ok("integrations", "apply", *flags, "--yes"))
    for t in TARGETS:
        assert acc_box.ok("integrations", "remove", "--target", t, "--yes")["state"] == "removed"
    acc_box.fs_override = None
    assert [i["state"] for i in acc_box.ok("integrations", "apply", *flags, "--yes")] == ["in_sync"] * 4
    assert not (co / ".grok/agents").exists()
    for t in TARGETS:
        view = acc_box.ask_applied(t)
        assert view.projection
        assert (view.projection.state, bool(view.files)) == ("in_sync", True)
        for rec in view.files:
            disk = (co / rec.relative_path).read_bytes()
            w_dig, pre_id = rec.applied_whole_digest, rec.pre_image_file_version_id
            assert (ownership.sha256_tagged(disk), pre_id) == (w_dig, None)
            bnd = observe.boundary_from_wire(rec.boundary.to_json())
            assert observed.extract_managed_digest(disk, bnd) == (rec.applied_managed_digest, True)
    replan = acc_box.ok("integrations", "plan", *flags)
    assert all({d["decision"] for d in p["decisions"]} == {"noop"} for p in replan)
    assert all(i["written"] == [] for i in acc_box.ok("integrations", "apply", *flags, "--yes"))
    with psycopg.connect(acc_box.dsn) as conn:
        assert sum(table_counts(conn, "skm_planning").values()) == 0


def test_shared_skills_foreign_bytes_json_toml_and_secret_refs_preserved(acc_box: AcceptanceBox) -> None:
    co = acc_box.repo_dir
    c_hdr, a_hdr = "# Team Claude\n\nKeep prose.\n", "# Team Agents\n\nKeep codex prose.\n"
    c_hook = [{"matcher": "Bash", "hooks": [{"type": "command", "command": "./scripts/audit.sh"}]}]
    toml_seed = '# Foreign TOML comment\n[mcp_servers.docs]\ncommand = "npx"\nargs = ["docs"]\n'
    skill_md = "---\nname: team-own\ndescription: Custom\n---\n"
    c_json = json.dumps({"includeCoAuthoredBy": False, "hooks": {"PreToolUse": c_hook}})
    seeds = {"CLAUDE.md": c_hdr, "AGENTS.md": a_hdr, ".claude/settings.json": c_json}
    seeds.update({".claude/skills/team-own/SKILL.md": skill_md, ".agents/skills/team-own/SKILL.md": skill_md})
    seeds[".codex/hooks.json"] = json.dumps({"description": "Team", "hooks": {"PreToolUse": c_hook}})
    seeds[".cursor/hooks.json"] = '{"hooks":{"beforeShellExecution":[{"command":"./cur.sh"}]}}\n'
    seeds.update({".codex/config.toml": toml_seed, ".grok/config.toml": toml_seed})
    seeds[".cursor/cli.json"] = '{"customCliOpt": false}\n'
    seeds[".grok/hooks/team.json"] = '{"description": "foreign"}\n'
    for rel, txt in seeds.items():
        (co / rel).parent.mkdir(parents=True, exist_ok=True)
        (co / rel).write_text(txt)
    applied = acc_box.ok("integrations", "apply", *TARGET_FLAGS, "--yes")
    assert [o["state"] for o in applied] == ["in_sync"] * 4
    assert all(r["drifted"] == 0 for r in acc_box.ok("integrations", "drift", *TARGET_FLAGS))
    sdig: dict[str, dict[str, str]] = {}
    for t in ("codex", "cursor", "grok"):
        files = acc_box.ask_applied(t).files
        sdig[t] = {r.relative_path: r.applied_whole_digest for r in files if "skills/" in r.relative_path}
    assert sdig["codex"]
    assert (sdig["codex"], sdig["cursor"], any(co.rglob("skill.toml"))) == (sdig["grok"], sdig["grok"], False)
    assert (co / "CLAUDE.md").read_text().startswith(c_hdr)
    assert (co / "AGENTS.md").read_text().startswith(a_hdr)
    c_set = json.loads((co / ".claude/settings.json").read_text())
    assert c_set["includeCoAuthoredBy"] is False
    assert c_set["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "./scripts/audit.sh"
    assert json.loads((co / ".cursor/cli.json").read_text())["customCliOpt"] is False
    cur_hooks = json.loads((co / ".cursor/hooks.json").read_text())["hooks"]
    assert cur_hooks["beforeShellExecution"][0]["command"] == "./cur.sh"
    assert (co / ".grok/hooks/team.json").read_text() == '{"description": "foreign"}\n'
    cfg = co / ".codex/config.toml"
    for tp in (cfg, co / ".grok/config.toml"):
        txt = tp.read_text()
        assert "# Foreign TOML comment" in txt
        assert tomllib.loads(txt)["mcp_servers"]["docs"] == {"command": "npx", "args": ["docs"]}
    for mp in (".mcp.json", ".cursor/mcp.json", ".codex/config.toml", ".grok/config.toml"):
        raw = (co / mp).read_text()
        assert ("secret://env/GITHUB_TOKEN" in raw, ENV_SECRET in raw) == (True, False)
    desired = cfg.read_bytes()
    edited = desired.replace(b'"gh"', b'"local-gh"')
    cfg.write_bytes(edited)
    code, env = acc_box.run_json("integrations", "apply", "--target", "codex", "--yes")
    assert code == 6
    assert ".codex/config.toml" in env["result"][0]["conflicts"]
    assert (cfg.with_suffix(".toml.skm-new").read_bytes(), cfg.read_bytes()) == (desired, edited)
    cfg.write_bytes(desired)
    for t in ("codex", "cursor", "grok"):
        acc_box.ok("integrations", "remove", "--target", t, "--yes")
        assert all((co / rel).exists() == (t != "grok") for rel in sdig["grok"])
    assert (co / ".agents/skills/team-own/SKILL.md").read_text() == skill_md


def test_adopt_drift_skm_new_conflict_leave_modified_and_pre_image_restore(acc_box: AcceptanceBox) -> None:
    co, r_rel, s_raw = acc_box.repo_dir, ".claude/rules/common.md", b'{\n  "includeCoAuthoredBy": false\n}\n'
    rule, settings = co / r_rel, co / ".claude/settings.json"
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_bytes(b"# Unmanaged rule\n")
    settings.write_bytes(s_raw)
    p0 = acc_box.ok("integrations", "plan", "--target", "claude_code")[0]["decisions"]
    assert next(d["decision"] for d in p0 if d["relative_path"] == r_rel) == "adopt_required"
    claude = ("--target", "claude_code")
    receipt = acc_box.ok("integrations", "adopt", r_rel, *claude, "--reason", "own", "--yes")
    view = acc_box.ask_applied("claude_code")
    assert (view.projection.row_version if view.projection else None) == 1
    pre_id = next(r.pre_image_file_version_id for r in view.files if r.relative_path == r_rel)
    assert pre_id
    assert str(pre_id) == receipt["pre_image_file_version_id"]
    with acc_box.host_ctx() as (ctx, _):
        key = LocalPreImageKey(
            ids.ProjectId(UUID(acc_box.project_id)),
            CheckoutBindingId(UUID(acc_box.binding_id)),
            target.TargetId.CLAUDE_CODE,
            r_rel,
        )
        assert observe.read_pre_image_bytes(ctx, key, ids.FileVersionId(pre_id)) == b"# Unmanaged rule\n"
    p1 = acc_box.ok("integrations", "plan", *claude)[0]["decisions"]
    assert next(d["decision"] for d in p1 if d["relative_path"] == r_rel) == "update"
    assert acc_box.ok("integrations", "apply", *claude, "--yes")[0]["state"] == "in_sync"
    projection = acc_box.ask_applied("claude_code").projection
    assert (projection.row_version if projection else None) == 2
    claude_md, agent_md = co / "CLAUDE.md", co / ".claude/agents/skm-code-auditor.md"
    claude_md.write_text(claude_md.read_text() + "\n## Outside note\n")
    assert acc_box.run_json("integrations", "drift", *claude)[0] == 0
    edited_agent = agent_md.read_bytes() + b"\n<!-- local tweak -->\n"
    agent_md.write_bytes(edited_agent)
    block = "instructions.project"
    old = managed_block.render_block(block, "## Acceptance Rules\n- Test.")
    desired = claude_md.read_bytes().replace(old, managed_block.render_block(block, "## Rules v2"))
    edited_claude = claude_md.read_text().replace("Acceptance Rules", "Edited Rules")
    claude_md.write_text(edited_claude)
    d_code, d_env = acc_box.run_json("integrations", "drift", *claude)
    assert (d_code, d_env["result"][0]["state"]) == (6, "drifted")
    acc_box.ok("config", "set", "integrations.agents.pack_prefix", "team", "--scope", "project")
    acc_box.ok("config", "set", "integrations.instructions.project_text", "## Rules v2", "--scope", "project")
    c_code, c_env = acc_box.run_json("integrations", "apply", *claude, "--yes")
    res0 = c_env["result"][0]
    assert (c_code, res0["state"], "CLAUDE.md" in res0["conflicts"]) == (6, "drifted", True)
    assert ".claude/agents/skm-code-auditor.md" in res0["left_modified"]
    assert ((co / "CLAUDE.md.skm-new").read_bytes(), claude_md.read_text()) == (desired, edited_claude)
    assert agent_md.read_bytes() == edited_agent
    assert (co / ".claude/agents/team-code-auditor.md").is_file()
    rem_cmd = ("integrations", "remove", *claude, "--restore-pre-image", "--yes")
    r_code, r_env = acc_box.run_json(*rem_cmd)
    assert (r_code, r_env["result"]["state"], rule.read_bytes()) == (6, "removed", b"# Unmanaged rule\n")
    assert ("CLAUDE.md" in r_env["result"]["left_modified"], settings.read_bytes()) == (True, s_raw)


def test_doctor_and_budget_readonly_redaction_journals_and_incomplete(acc_box: AcceptanceBox) -> None:
    spy = LookupRunner()
    acc_box.runner_override = cast("Any", spy)
    acc_box.ok("config", "set", "integrations.hooks.mode", '{"session_start":"off"}', "--scope", "project")
    acc_box.ok("integrations", "apply", "--target", "claude_code", "--target", "codex", "--yes")
    codex_cfg = acc_box.repo_dir / ".codex/config.toml"
    codex_cfg.write_text("[features]\nhooks = false\n\n" + codex_cfg.read_text())
    sub_json = json.dumps({"g": _cmd_sub("pass")})
    acc_box.ok("config", "set", "hooks.subscriptions", sub_json, "--scope", "project", "--yes")
    (acc_box.repo_dir / ".claude/rules/common.md").write_text("# Local edit\n")
    lfs = local.LocalCheckoutFs(acc_box.repo_dir, state_dir=acc_box.state_dir)
    lfs.write_journal(acc_box.binding_id, "crash01", b'{"kind":"apply","stage":"mutating"}')
    secret_val = "sk-" + "secret9876543210" * 4
    user_claude = acc_box.home / ".claude/settings.json"
    user_claude.parent.mkdir(parents=True, exist_ok=True)
    hk = {"SessionStart": [{"hooks": [{"type": "command", "command": "touch x"}]}]}
    user_claude.write_text(json.dumps({"env": {"API_KEY": secret_val}, "hooks": hk}))

    def snap() -> dict[str, bytes]:
        files = [p for r in (acc_box.repo_dir, acc_box.home) for p in r.rglob("*") if p.is_file()]
        return {str(p): p.read_bytes() for p in files if ".git" not in p.parts}

    before = snap()
    doc_flags = ("--target", "claude_code", "--target", "codex")
    c1, e1 = acc_box.run_json("doctor", *doc_flags)
    c2, e2 = acc_box.run_json("integrations", "doctor", *doc_flags)
    hc, ho, he = acc_box._invoke(["doctor", *doc_flags])
    assert (c1, c2, hc, e1["result"]) == (1, 1, 1, e2["result"])
    assert secret_val not in json.dumps(e1) + ho + he
    by_id = {(c["target"], c["check_id"]): c for c in e1["result"]["checks"]}
    assert by_id[("claude_code", "claude.secrets_in_env")]["level"] == "error"
    assert by_id[("codex", "codex.hooks_feature_disabled")]["level"] == "warning"
    assert by_id[("claude_code", "hooks.subscriptions_untrusted")]["level"] == "warning"
    warnings = [c for c in e1["result"]["checks"] if c["target"] == "claude_code" and c["level"] == "warning"]
    drift = {c["path"] for c in warnings if c["check_id"] == "projection.drift"}
    assert {"host-journal:crash01", ".claude/rules/common.md"} <= drift
    bc, be = acc_box.run_json("budget", "--target", "claude_code")
    bs_code, out, err = acc_box._invoke(["budget", "--target", "claude_code", "--strict"])
    assert secret_val not in out + err
    assert "incomplete" in out.lower()
    assert (bc, bs_code, be["result"]["verdict"], be["result"]["total"]) == (0, 1, "incomplete", None)
    kinds = ["skills", "agents", "instructions", "hooks", "mcp"]
    assert [s["kind"] for s in be["result"]["sources"]] == kinds
    hsrc = next(s for s in be["result"]["sources"] if s["kind"] == "hooks")
    assert (hsrc["tokens"], hsrc["detail"]["run_hooks"], snap()) == (None, False, before)
    user_claude.write_text("{}")
    b_ok = acc_box.ok("budget", "--target", "claude_code", "--strict")
    assert (b_ok["verdict"], isinstance(b_ok["total"], int) and b_ok["total"] > 0) == ("ok", True)
    assert all(call[0] == "which" for call in spy.calls)


def test_skm_hook_codecs_outage_timeout_malformed_and_foreign_cwd(
    acc_box: AcceptanceBox, tmp_path: Path, record_property: Any
) -> None:
    co, guard = acc_box.repo_dir, "lifecycle.git_guardrails"
    bs_toml = acc_box.root / "config/skm/bootstrap.toml"
    bs_toml.write_text(bs_toml.read_text().replace("[database]\n", "[database]\npool_timeout_seconds = 1\n"))
    modes = '{"git_guardrails":"strict","command_log":"warn","session_start":"warn"}'
    acc_box.ok("config", "set", "integrations.hooks.mode", modes, "--scope", "project")
    acc_box.ok("integrations", "apply", *TARGET_FLAGS, "--yes")
    base_env = acc_box.env()
    workspace = acc_box.ok("workspace", "show", "personal")
    install_hook_token(base_env, co, acc_box.state_dir / "secrets/hook.token", workspace["workspace_id"])
    dead_dsn = "postgresql://skm:unused@127.0.0.1:1/missing?connect_timeout=1"

    with runtime_environment(base_env) as active:
        claude_on_path(active)
        for tgt in reversed(TARGETS):
            regs = commands(json.loads((co / NATIVE_FILES[tgt]).read_text()))
            cache = acc_box.state_dir / "hooks" / f"{acc_box.project_id}-{tgt}.json"

            def inv(
                s: str,
                c: str = "git status",
                *,
                dead: bool = False,
                _r: Any = regs,
                _t: str = tgt,
            ) -> Invocation:
                argv = next(a for a in _r if a[a.index("--surface") + 1] == s)
                env = {**active, "SKM_DATABASE_URL": dead_dsn} if dead else dict(active)
                return Invocation(argv, native_payload(_t, argv[1], co, c), env, co)

            with installed_daemon(active, cwd=co, bootstrap=bs_toml):
                res_live, live_ms = inv(guard, "git reset --hard").execute()
                assert_native(res_live, tgt, denied=True)
                assert "Unsafe Git operation" in res_live.stdout + res_live.stderr
                assert cache.is_file()
                foreign = inv(guard)
                foreign.payload["cwd"] = str(tmp_path)
                assert_native(foreign.execute()[0], tgt, denied=True)
                res_mal, _ = replace(inv(guard), payload={}).execute()
                assert_native(res_mal, tgt, denied=True)
                assert "HOOK_PAYLOAD_INVALID" in res_mal.stdout + res_mal.stderr

                if tgt == "claude_code":
                    with psycopg.connect(acc_box.dsn) as lock:
                        lock.execute("LOCK TABLE skm_integrations.projections IN ACCESS EXCLUSIVE MODE")
                        call = inv(guard)
                        call.environ["SKM__INTEGRATIONS__HOOK__TIMEOUT_MS"] = "80"
                        result, elapsed = call.execute()
                        assert_native(result, tgt, denied=True)
                        assert "HOOK_BACKEND_UNAVAILABLE" in result.stdout + result.stderr
                        assert elapsed < live_ms + 900

            res_warm, cold_ms = inv(guard, dead=True).execute()
            record_property(f"cold_cached_{tgt}_ms", round(cold_ms, 3))
            assert_native(res_warm, tgt, denied=True)
            assert "HOOK_BACKEND_UNAVAILABLE" in res_warm.stdout + res_warm.stderr
            for surface in ("lifecycle.command_log", "context.session_start"):
                cache.unlink(missing_ok=True)
                result, _ = inv(surface, dead=True).execute()
                assert_native(result, tgt, denied=False)
                assert "HOOK_BACKEND_UNAVAILABLE" in result.stdout + result.stderr


def _run_relay_once(box: AcceptanceBox) -> None:
    env = box.env()
    bs = bootstrap.load_bootstrap(None, env, box.home, instance=None)
    app, _ = open_cli_app(bs, environ=env, invocation={}, as_token=None)
    with closing(app):
        clk = system_clock.SystemClock()
        wh_cfg = {"allow_http_loopback": True, "allow_private_networks": True}
        sink = webhook.WebhookSink(
            http=_pinned_http.PinnedHttpClient(), settings=wh_cfg, clock=clk, version="2.0.0"
        )
        cp = {**app.bus._gateways.entries, bus_sub.EventSinkRegistry: bus_sub.EventSinkRegistry((sink,))}
        sec = secrets.SecretResolvers([EnvSecretResolver(env)], on_reveal=lambda _s: None)
        sa = actor.Actor(actor.SYSTEM_PRINCIPAL_ID, actor.PrincipalKind.SERVICE, "system")
        kw: dict[str, Any] = {"registry": app.bus._registry, "uow_factory": app.uow_factory, "clock": clk}
        kw.update(config=app.config, settings=bus_sub.DeliverySettings, ids=system_ids.Uuid7Generator(clk))
        kw["gateways"] = gateways.GatewayTable(cp, "control_plane_gateway")
        kw.update(log=get_logger("test.r"), relay_id="a", batch_size=50, secrets=sec, dispatcher=app.bus)
        relay = bus_sub.OutboxRelayPass(**kw, actor=sa)
        relay.run_once()
        relay.run_once()


def test_webhook_ssrf_redirect_hmac_and_dead_retry(acc_box: AcceptanceBox) -> None:
    kw_p: Any = {"body": b"{}", "headers": {}, "timeout_ms": 500, "allow_private_networks": True}
    with pytest.raises(_pinned_http.HttpRefused, match="address_refused"):
        _pinned_http.PinnedHttpClient().post("https://169.254.169.254/v1", **kw_p)
    acc_box.ok("config", "set", "hooks.webhook.allow_http_loopback", "true", "--scope", "instance")
    acc_box.ok("config", "set", "hooks.webhook.allow_private_networks", "true", "--scope", "instance")
    with _server(302) as (redir_url, _):
        r_cfg = json.dumps({"wh-r": _wh_sub(redir_url, attempts=1)})
        acc_box.ok("config", "set", "hooks.subscriptions", r_cfg, "--scope", "project", "--yes")
        acc_box.ok("hooks", "test", "wh-r")
        _run_relay_once(acc_box)
        dead_r = acc_box.ok("hooks", "deliveries", "--state", "dead")["items"][0]
        assert dead_r["last_error"] == "redirect_refused"

    with _server(200, b"ok") as (ok_url, ok_reqs), _server(503, b"down") as (fail_url, fail_reqs):
        subs = {"wh-ok": _wh_sub(ok_url, cls="observation", policy="retry"), "wh-dead": _wh_sub(fail_url)}
        acc_box.ok("config", "set", "hooks.subscriptions", json.dumps(subs), "--scope", "project", "--yes")
        acc_box.ok("hooks", "test", "wh-ok")
        _run_relay_once(acc_box)
        sig, body = ok_reqs[0]["headers"]["SKM-Signature"], ok_reqs[0]["body"]
        assert webhook_signing.verify(body, sig, secret=HOOK_SECRET, now=int(sig.split(",")[0][2:]))
        acc_box.ok("hooks", "test", "wh-dead")
        _run_relay_once(acc_box)
        deliveries = acc_box.ok("hooks", "deliveries")["items"]
        with psycopg.connect(acc_box.dsn) as conn:
            conn.execute("UPDATE skm_core.outbox SET available_at = available_at - interval '5 seconds'")
        _run_relay_once(acc_box)
        assert len(fail_reqs) == 2
        dead_items = acc_box.ok("hooks", "deliveries", "--state", "dead")["items"]
        (dead_wh,) = [i for i in dead_items if i["subscription_id"] == "wh-dead"]
        evt_sql = "SELECT payload FROM skm_core.domain_events WHERE event_type = %s"
        with psycopg.connect(acc_box.dsn) as conn:
            rows = conn.execute(evt_sql, (events.HookDeliveryFailed.event_type,)).fetchall()
        assert any(r[0].get("subscription_id") == "wh-dead" and r[0]["blocking"] for r in rows)
        _run_relay_once(acc_box)
        assert len(acc_box.ok("hooks", "deliveries")["items"]) == len(deliveries) == 3
        assert acc_box.ok("hooks", "retry", str(dead_wh["delivery_id"]))["requeued"] == 1


def _eval_custom_sub(box: AcceptanceBox, cls: str) -> Mapping[str, Any]:
    with box.host_ctx() as (hctx, sdir):
        for cfile in (sdir / "hooks").glob("*.json"):
            cfile.unlink(missing_ok=True)
        pl = native_payload("claude_code", "PreToolUse", box.repo_dir)
        req: Any = {"target": "claude_code", "surface": "custom.subscriptions", "class": cls}
        req["project_id"], req["event_name"], req["payload"] = box.project_id, "PreToolUse", pl
        return evaluate_hook.run(with_hook_state(hctx, sdir), req)


def test_host_subscription_trust_digest_mismatch_and_spool_drain(acc_box: AcceptanceBox) -> None:
    marker = acc_box.repo_dir / "host-sub-ran"
    out_doc = '{"schema":"urn:skm:integrations:host-command-output:v1","decision":"deny"}'
    enf_code = f"open({str(marker)!r},'w').write('1');print({out_doc!r})"
    subs = {"enf": _cmd_sub(enf_code)}
    subs["obs"] = _cmd_sub("raise SystemExit(1)", cls="observation", policy="retry")
    acc_box.ok("config", "set", "hooks.subscriptions", json.dumps(subs), "--scope", "project", "--yes")
    assert (_eval_custom_sub(acc_box, "enforcement")["verdict"], marker.exists()) == ("ask", False)
    bad_req: Any = {"project_id": acc_box.project_id, "subscription_id": "enf"}
    bad_req["expected_digest"] = "sha256:" + "0" * 64
    with acc_box.host_ctx() as (ctx, _), pytest.raises(errors.Conflict) as exc:
        trust_hook_subscription.run(ctx, bad_req)
    assert exc.value.code is error_codes.ErrorCode.VERSION_CONFLICT
    for key in subs:
        assert acc_box.ok("hooks", "trust", key, "--yes")["trusted"] is True
    subs["enf"]["target"]["argv"].append("tampered")
    acc_box.ok("config", "set", "hooks.subscriptions", json.dumps(subs), "--scope", "project", "--yes")
    assert (_eval_custom_sub(acc_box, "enforcement")["verdict"], marker.exists()) == ("ask", False)
    assert _eval_custom_sub(acc_box, "observation")["verdict"] == "none"
    for sp in (acc_box.state_dir / "hooks/spool").rglob("*.json"):
        doc = json.loads(sp.read_text())
        doc["available_at"] = (system_clock.SystemClock().now() - timedelta(seconds=5)).isoformat()
        sp.write_text(json.dumps(doc))
    assert acc_box.ok("hooks", "drain") == {"replayed": 1, "dead": 1, "dropped": 0}


def test_capability_facts_and_summarize_session_none_ench6_boundary(tmp_path: Path) -> None:
    nat, unsup = target.SurfaceSupport.NATIVE, target.SurfaceSupport.UNSUPPORTED
    expected = {
        target.TargetId.ANTIGRAVITY: ("antigravity@1", "1.5.13", date(2026, 11, 20), unsup),
        target.TargetId.CLAUDE_CODE: ("claude_code@1", "2.1.220", date(2026, 8, 2), nat),
        target.TargetId.CODEX: ("codex@1", "0.165.0", date(2026, 10, 26), nat),
        target.TargetId.CURSOR: ("cursor@1", "2026.09.15-d2fe57e", date(2026, 10, 26), nat),
        target.TargetId.GEMINI_CLI: ("gemini_cli@1", "unverified", date(2026, 11, 23), unsup),
        target.TargetId.GROK: ("grok@1", "0.1.0", date(2026, 10, 26), unsup),
    }
    reg = default_target_registry()
    assert [t.target_id for t in reg.all()] == list(expected)
    transcript = tmp_path / "session.jsonl"
    transcript.write_text('{"type":"user","message":"hi"}\n{"type":"assistant","message":"ok"}\n')
    fake_fs, local_fs = FakeCheckoutFs(tmp_path), local.LocalCheckoutFs(tmp_path, state_dir=tmp_path / "s")
    fake_fs.files["session.jsonl"] = transcript.read_bytes()
    pl: dict[str, Any] = {"session_id": "s1", "transcript_path": str(transcript), "reason": "completed"}
    pl["cwd"] = str(tmp_path)
    nat_surfs = [target.Surface(s) for s in ["instructions", "skills", "permissions", "hooks", "mcp"]]
    for adapter in reg.all():
        caps = adapter.capabilities()
        r_ver, c_ver, v_date, ag_sup = expected[adapter.target_id]
        assert (adapter.renderer_version, caps.tested_client_version) == (r_ver, c_ver)
        assert (caps.verified_at, caps.surfaces[target.Surface.AGENTS]) == (v_date, ag_sup)
        supported = (
            {target.Surface.INSTRUCTIONS, target.Surface.SKILLS}
            if adapter.target_id in {target.TargetId.ANTIGRAVITY, target.TargetId.GEMINI_CLI}
            else set(nat_surfs)
        )
        assert {surface for surface in nat_surfs if caps.surfaces[surface] is nat} == supported
        assert adapter.summarize_session(pl, fake_fs) is None
        assert adapter.summarize_session(pl, local_fs) is None
    raw_sum = (
        '{"schema":"urn:skm:learning:activity-summary:v1","source_kind":"client_session",'
        '"source_key":"01900000-0000-7000-8000-000000000099","outcome":"unknown",'
        '"observed_at":"2026-11-18T00:00:00Z","tools_total":null,"reads_total":null,"task_outcome":null}'
    )
    SchemaRegistry.load_default().require_valid("urn:skm:learning:activity-summary:v1", json.loads(raw_sum))
