"""Tests sync.py (fan-out + providers mcp/graph/memory-hook) and common.managed_block."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import ProviderId
from maind.provider_deploy import ProviderDeployPlan, ProviderDeployResult
_TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

from maind.provision import sync
from maind.common import managed_block, upsert_block
from maind.config import load_config
from maind.mcpconfig import has_server
from tests.fixtures import make_repo, write_maind_config


def _ensure_umbrella_packages(project):
    """Minimal monorepo layout so instructions provisioner applies (production: swissknifeman)."""
    for pkg in ("skiller", "maind", "harness"):
        (project / "packages" / pkg).mkdir(parents=True, exist_ok=True)


def _setup(tmp):
    root, env = make_repo(tmp)
    proj = Path(tmp) / "flexcrm"
    (proj / ".claude").mkdir(parents=True, exist_ok=True)
    (proj / "composer.json").write_text(
        json.dumps({"name": "axioma-studio/flexcrm",
                    "require": {"axioma-studio/azguard-core": "@dev"}}), encoding="utf-8")
    projects = [{"id": "flexcrm", "name": "FlexCRM", "type": "php-package",
                 "status": "active", "enabled": True, "local_path": str(proj)}]
    write_maind_config(root, graph={"adapter": "federation"}, projects=projects)
    config, _ = load_config(env)
    return env, config, proj


class TestManagedBlock(unittest.TestCase):
    MARK = "maind:healthcheck"

    def test_insert_then_idempotent(self):
        t0 = "# Project\n\nDocumentation.\n"
        t1, changed, state = upsert_block(t0, "PRIORITY №1", self.MARK)
        self.assertTrue(changed)
        self.assertEqual(state, "absent")
        self.assertIn("PRIORITY №1", t1)
        self.assertIn("# Project", t1)  # someone else's text saved
        t2, changed2, state2 = upsert_block(t1, "PRIORITY №1", self.MARK)
        self.assertFalse(changed2)
        self.assertEqual(state2, "fresh")
        self.assertEqual(t1, t2)

    def test_update_on_drift(self):
        t0, _, _ = upsert_block("# P\n", "old text", self.MARK)
        t1, changed, state = upsert_block(t0, "new text", self.MARK)
        self.assertTrue(changed)
        self.assertEqual(state, "stale")
        self.assertIn("new text", t1)
        self.assertNotIn("old text", t1)
        self.assertEqual(t1.count(self.MARK), 2)  # one block (begin+end), not two

    def test_block_has_hash(self):
        self.assertIn("hash=", managed_block("x", self.MARK))


class TestDelegatedCapabilityReceipt(unittest.TestCase):
    def test_dry_run_success_is_not_an_applied_change(self):
        self.assertFalse(sync._capability_changed(0, True))
        self.assertTrue(sync._capability_changed(0, False))
        self.assertFalse(sync._capability_changed(1, False))


class TestInstructionsApplicability(unittest.TestCase):
    def test_consumer_project_skips_instructions_provisioner(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            context = sync.contexts(env, config, config["projects"])[0]
            self.assertFalse(sync._instructions_applicable(context))
            rows = sync._instruction_run(env, config, [context], "auto", True)
            self.assertEqual(rows[0]["status"], "skip")
            self.assertEqual(rows[0]["state"], "n-a")

    def test_umbrella_layout_applies_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            proj = Path(tmp) / "swissknifeman"
            for pkg in ("skiller", "maind", "harness"):
                (proj / "packages" / pkg).mkdir(parents=True)
            projects = [{"id": "swissknifeman", "name": "SKM", "type": "standalone",
                         "status": "active", "enabled": True, "local_path": str(proj)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            context = sync.contexts(env, config, projects)[0]
            self.assertTrue(sync._instructions_applicable(context))


class TestProviderContexts(unittest.TestCase):
    def test_refused_bootstrap_keeps_mcp_failed_and_config_unwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _project = _setup(tmp)
            context = sync.contexts(env, config, config["projects"])[0]
            ordinary_plan = ProviderDeployPlan((ProviderDeployResult(
                ProviderId.CLAUDE_CODE, "project", ".mcp.json", b"", (), "planned"),))
            result = {
                "provider_plan": ordinary_plan,
                "provider_changed": False,
                "bootstrap_transfer": {"status": "refused", "actions": (),
                                       "diagnostic": "MAIND_PROVIDER_DEPLOY_REFUSED"},
                "written": [], "targets": [], "skipped": [],
            }
            with mock.patch("maind.provision.deploy.deploy_project", return_value=result), \
                    mock.patch("maind.provision.deploy.mark_deployed") as mark_deployed, \
                    mock.patch("maind.projects.write_config") as write_config:
                rows = sync._mcp_run(env, config, [context], "auto", False)
            self.assertEqual(rows[0]["status"], "failed")
            self.assertEqual(rows[0]["provider_aggregate"], "green")
            mark_deployed.assert_not_called()
            write_config.assert_not_called()

    def test_mcp_repair_mode_reaches_provider_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _project = _setup(tmp)
            context = sync.contexts(env, config, config["projects"])[0]
            result = {
                "provider_plan": None,
                "provider_changed": False,
                "bootstrap_transfer": {"status": "not-selected", "actions": (),
                                       "diagnostic": None},
                "written": [],
                "targets": [],
                "skipped": [],
            }
            with mock.patch("maind.provision.deploy.deploy_project", return_value=result) as deploy:
                rows = sync._mcp_run(env, config, [context], "repair", True)
            self.assertTrue(deploy.call_args.kwargs["provider_repair"])
            self.assertEqual(rows[0]["bootstrap_transfer"]["status"], "not-selected")

    def test_context_is_resolved_once_and_reused_across_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _proj = _setup(tmp)
            import maind.provision.deploy as deploy
            calls, seen = [], []
            original_context = deploy.provider_projection_context
            original_provisioners, original_order = sync.PROVISIONERS, sync.ORDER
            def first(_env, _config, contexts, _mode, _dry):
                seen.append(contexts[0])
                return [sync._result("first", contexts[0]["id"], "ok")]
            def second(_env, _config, contexts, _mode, _dry):
                seen.append(contexts[0])
                return [sync._result("second", contexts[0]["id"], "ok")]
            def counted(*args):
                calls.append(args[2]["id"])
                return original_context(*args)
            deploy.provider_projection_context = counted
            sync.PROVISIONERS = {"first": first, "second": second}
            sync.ORDER = ["first", "second"]
            try:
                sync.run_sync(env, config, config["projects"])
            finally:
                deploy.provider_projection_context = original_context
                sync.PROVISIONERS, sync.ORDER = original_provisioners, original_order
            self.assertEqual(calls, ["flexcrm"])
            self.assertIs(seen[0], seen[1])
            self.assertTrue(seen[0].provider_context.providers)

    def test_required_provider_failure_is_visible_in_aggregate(self):
        aggregate = sync.ProviderProvisionAggregate(({
            "provider_id": "codex", "status": "failed", "required": True,
            "diagnostic": "MAIND_PROJECTION_MISSING"},))
        result = sync._result("mcp", "demo", "failed", provider_aggregate=aggregate)
        self.assertFalse(aggregate.green)
        self.assertEqual(result["provider_aggregate"], "non-green")
        self.assertEqual(result["providers"][0]["diagnostic"], "MAIND_PROJECTION_MISSING")

    def test_real_mcp_and_graph_order_resolves_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _proj = _setup(tmp)
            import maind.provision.deploy as deploy
            calls, original = [], deploy.provider_projection_context
            def counted(*args):
                calls.append(args[2]["id"])
                return original(*args)
            deploy.provider_projection_context = counted
            try:
                results = sync.run_sync(env, config, config["projects"], only="mcp,graph")
            finally:
                deploy.provider_projection_context = original
            self.assertEqual(calls, ["flexcrm"])
            self.assertEqual([row["provisioner"] for row in results], ["mcp", "graph"])

    def test_instruction_provisioner_uses_context_provider_ids_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, project = _setup(tmp)
            _ensure_umbrella_packages(project)
            config["projects"][0]["providers"] = {
                "contract_version": "1.0.0",
                "selection": {"claude-code": {"enabled": True}, "codex": {"enabled": True}},
            }
            first = sync.run_sync(env, config, config["projects"], only="instructions", mode="auto")
            self.assertEqual(first[0]["provider_aggregate"], "green")
            self.assertEqual({row["provider_id"] for row in first[0]["providers"]},
                             {"claude-code", "codex"})
            self.assertTrue((project / "CLAUDE.md").is_file())
            self.assertTrue((project / "AGENTS.md").is_file())
            for package in ("skiller", "harness", "maind"):
                self.assertTrue((project / "packages" / package / "CLAUDE.md").is_file())
                self.assertTrue((project / "packages" / package / "AGENTS.md").is_file())
            for package in ("analyst", "task"):
                self.assertFalse((project / "packages" / package / "CLAUDE.md").exists())
                self.assertFalse((project / "packages" / package / "AGENTS.md").exists())
            second = sync.run_sync(env, config, config["projects"], only="instructions", mode="auto")
            self.assertEqual(second[0]["provider_aggregate"], "green")
            self.assertFalse(second[0]["changed"])

    def test_instruction_scope_ids_follow_real_package_topology(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, project = _setup(tmp)
            context = sync.contexts(env, config, config["projects"])[0]
            self.assertEqual(sync._instruction_scope_ids(context), ("root",))

            for package in ("skiller", "harness", "maind", "task"):
                (project / "packages" / package).mkdir(parents=True)
            linked = Path(tmp) / "linked-analyst"
            linked.mkdir()
            (project / "packages" / "analyst").symlink_to(linked, target_is_directory=True)
            self.assertEqual(sync._instruction_scope_ids(context),
                             ("root", "skiller", "harness", "maind", "task"))

            (project / "packages" / "analyst").unlink()
            (project / "packages" / "analyst").mkdir()
            self.assertEqual(sync._instruction_scope_ids(context),
                             ("root", "skiller", "harness", "maind", "analyst", "task"))

    def test_instruction_provisioner_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, project = _setup(tmp)
            _ensure_umbrella_packages(project)
            row = sync.run_sync(env, config, config["projects"], only="instructions", dry=True)[0]
            self.assertEqual(row["status"], "dry")
            self.assertFalse((project / "CLAUDE.md").exists())

    def test_instruction_repair_changes_only_managed_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, project = _setup(tmp)
            _ensure_umbrella_packages(project)
            sync.run_sync(env, config, config["projects"], only="instructions", mode="auto")
            target = project / "CLAUDE.md"
            original = target.read_text(encoding="utf-8")
            target.write_text("local heading\n" + original.replace("#", "# drifted", 1)
                              + "\nlocal footer\n", encoding="utf-8")
            drift = sync.run_sync(env, config, config["projects"], only="instructions", mode="auto")[0]
            self.assertEqual(drift["status"], "failed")
            repaired = sync.run_sync(env, config, config["projects"], only="instructions", mode="repair")[0]
            self.assertEqual(repaired["status"], "ok")
            restored = target.read_text(encoding="utf-8")
            self.assertTrue(restored.startswith("local heading\n"))
            self.assertTrue(restored.endswith("\nlocal footer\n"))


class TestRoleAgentPacks(unittest.TestCase):
    """Option C: project.roles → config.role_packs[role], additive to the profile pack."""
    CFG = {"role_packs": {"tech-lead": "role-tech-lead", "solo-founder": "role-founder"}}

    def test_roles_only(self):
        self.assertEqual(
            sync._resolve_agent_pack(self.CFG, {"id": "x", "roles": ["tech-lead"]}),
            ["role-tech-lead"])

    def test_explicit_plus_roles_additive(self):
        self.assertEqual(
            sync._resolve_agent_pack(
                self.CFG,
                {"id": "y", "agent_pack": ["backend-laravel", "_common"],
                 "roles": ["tech-lead", "solo-founder"]}),
            ["backend-laravel", "_common", "role-tech-lead", "role-founder"])

    def test_unknown_role_ignored(self):
        self.assertEqual(
            sync._resolve_agent_pack(self.CFG, {"id": "z", "roles": ["nope"]}), [])

    def test_no_roles_unchanged(self):
        self.assertEqual(
            sync._resolve_agent_pack(self.CFG, {"id": "w", "agent_pack": "foo"}), ["foo"])

    def test_role_dedup(self):
        cfg = {"role_packs": {"tech-lead": "role-tech-lead"}}
        self.assertEqual(
            sync._resolve_agent_pack(
                cfg, {"id": "d", "agent_pack": ["role-tech-lead"], "roles": ["tech-lead"]}),
            ["role-tech-lead"])


class TestAgentPackRun(unittest.TestCase):
    """update should not crash on a pack that is not yet in lock'e goals (field-feedback:
    profile has grown with a new pack → sync --mode update strangled him through upgrade, requiring
    prior-install; supposed to be repaired install-way, upgrade - already standing)."""

    def test_installed_agent_packs_reads_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".claude").mkdir()
            (Path(tmp) / ".claude" / "agent-pack.lock.json").write_text(
                json.dumps({"schema": 1, "packs": {"role-maintainer": {"version": "0.2.1"}}}),
                encoding="utf-8")
            self.assertEqual(sync._installed_agent_packs(tmp), {"role-maintainer"})

    def test_installed_agent_packs_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sync._installed_agent_packs(tmp), set())

    def test_update_mode_installs_missing_falls_back_to_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".claude").mkdir()
            (Path(tmp) / ".claude" / "agent-pack.lock.json").write_text(
                json.dumps({"schema": 1, "packs": {"role-maintainer": {"version": "0.2.1"}}}),
                encoding="utf-8")
            project = {"id": "p", "local_path": tmp, "roles": [],
                       "agent_pack": ["laravel-package", "_common", "role-maintainer"]}
            calls = []

            def fake_run_capability(env, config, project_id, capability, extra=None, *, dry=False):
                calls.append((project_id, capability, list(extra or [])))
                return 0

            import maind.provision.orchestrate as orchestrate
            orig = orchestrate.run_capability
            orchestrate.run_capability = fake_run_capability
            try:
                results = sync._agent_pack_run(None, {}, [project], "update", False)
            finally:
                orchestrate.run_capability = orig

            caps = {pack: cap for _pid, cap, extra in calls
                    for pack in [extra[extra.index("--pack") + 1]]}
            self.assertEqual(caps["laravel-package"], "env:agent-pack")
            self.assertEqual(caps["_common"], "env:agent-pack")
            self.assertEqual(caps["role-maintainer"], "env:agent-pack-upgrade")
            self.assertTrue(all(r["status"] == "ok" for r in results))


class TestSync(unittest.TestCase):
    def test_missing_local_path_is_provider_qualified_skip_while_existing_project_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, project = _setup(tmp)
            config["projects"].append({
                "id": "missing", "name": "Missing", "type": "php-package",
                "status": "active", "enabled": True,
                "providers": {"contract_version": "1.0.0", "selection": {
                    "claude-code": {"enabled": True}, "codex": {"enabled": True},
                }},
            })
            rows = sync.run_sync(env, config, config["projects"], only="mcp", dry=True)
            existing = next(row for row in rows if row["id"] == "flexcrm")
            missing = next(row for row in rows if row["id"] == "missing")
            self.assertEqual(existing["status"], "ok")
            self.assertEqual(missing["status"], "skip")
            self.assertEqual(missing["state"], "ineligible")
            self.assertIn("MAIND_PROJECT_LOCAL_PATH_MISSING", missing["detail"])
            self.assertEqual(missing["provider_aggregate"], "green")
            self.assertEqual(missing["providers"], [
                {"provider_id": "claude-code", "status": "skip", "required": False,
                 "diagnostic": "MAIND_PROJECT_LOCAL_PATH_MISSING"},
                {"provider_id": "codex", "status": "skip", "required": False,
                 "diagnostic": "MAIND_PROJECT_LOCAL_PATH_MISSING"},
            ])

    def test_select_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _ = _setup(tmp)
            self.assertEqual([p["id"] for p in
                              sync.select_projects(env, config, {"all": True})], ["flexcrm"])
            self.assertEqual([p["id"] for p in
                              sync.select_projects(env, config, {"project": "flexcrm"})],
                             ["flexcrm"])

    def test_mcp_provisioner_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            r1 = sync.run_sync(env, config, projs, only="mcp")
            self.assertTrue(has_server(proj / ".mcp.json", "maind"))
            self.assertFalse(has_server(proj / ".mcp.json", "agentmemory"))  # raw output
            self.assertTrue(r1[0]["changed"])
            r2 = sync.run_sync(env, config, projs, only="mcp")
            self.assertFalse(r2[0]["changed"])  # repeat - no change

    def test_mcp_provisioner_graphify_config_driven(self):
        # graphify:true in the project entry → provider mcp rolls out graphify
        # (when the binary is available); without a flag - no. We mock up the binary for those present.
        from maind.provision import deploy
        orig = deploy.shutil.which
        deploy.shutil.which = lambda name: f"/usr/bin/{name}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env, config, proj = _setup(tmp)
                config["projects"][0]["graphify"] = True
                projs = sync.select_projects(env, config, {"all": True})
                sync.run_sync(env, config, projs, only="mcp")
                self.assertTrue(has_server(proj / ".mcp.json", "codegraph"))
        finally:
            deploy.shutil.which = orig

    def test_mcp_provisioner_no_graphify_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            sync.run_sync(env, config, projs, only="mcp")
            self.assertFalse(has_server(proj / ".mcp.json", "serena"))

    def test_graph_provisioner_builds_stores(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _ = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            sync.run_sync(env, config, projs, only="graph")
            self.assertTrue((env.data_dir / "graphs" / "flexcrm.db").exists())
            self.assertTrue((env.data_dir / "graphs" / "_index.db").exists())

    def test_graph_provisioner_changed_is_honest(self):
        # repeated derive without source changes → changed=False (deterministic store)
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _ = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            r1 = sync.run_sync(env, config, projs, only="graph")
            self.assertTrue(all(r["changed"] for r in r1))  # first run - creation
            r2 = sync.run_sync(env, config, projs, only="graph")
            self.assertTrue(all(not r["changed"] for r in r2))  # repeat - no change

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            sync.run_sync(env, config, projs, only="mcp", dry=True)
            self.assertFalse((proj / ".mcp.json").exists())

    def test_unknown_provisioner_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup(tmp)
            with self.assertRaises(SystemExit):
                sync.provisioner_names("bogus")

    def test_memory_hook_in_default_order(self):
        # auto-loading of memory is rolled out and normal `maind sync --all`
        self.assertIn("memory-hook", sync.provisioner_names())


class TestMemoryHookProvisioner(unittest.TestCase):
    """memory-hook reads the intent from .claude/memory.env.ini: MODE=maind → digest injection +
    native off; no config → pass; off → revert. So the feature is rolled out through sync."""

    def _with_templates(self, tmp):
        env, config, proj = _setup(tmp)
        shutil.copytree(_TEMPLATES, env.root / "templates")  # templates health in env.root
        return env, config, proj

    def test_skip_when_no_memory_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = self._with_templates(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            r = sync.run_sync(env, config, projs, only="memory-hook")
            self.assertEqual(r[0]["status"], "skip")
            self.assertFalse((proj / ".claude" / "maind-memory.sh").is_file())

    def test_apply_when_mode_maind_then_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = self._with_templates(tmp)
            (proj / ".claude").mkdir(parents=True, exist_ok=True)
            (proj / ".claude" / "memory.env.ini").write_text("MODE=maind\n", encoding="utf-8")
            projs = sync.select_projects(env, config, {"all": True})
            r1 = sync.run_sync(env, config, projs, only="memory-hook")
            self.assertEqual(r1[0]["provisioner"], "memory-hook")
            self.assertTrue(r1[0]["changed"])
            self.assertTrue((proj / ".claude" / "maind-memory.sh").is_file())
            s = json.loads((proj / ".claude" / "settings.json").read_text())
            self.assertIs(s["autoMemoryEnabled"], False)
            cmds = [h["command"] for g in s["hooks"]["SessionStart"] for h in g["hooks"]]
            self.assertTrue(any("maind-memory" in c for c in cmds))
            r2 = sync.run_sync(env, config, projs, only="memory-hook")
            self.assertFalse(r2[0]["changed"])  # repeat - no change

    def test_revert_when_mode_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = self._with_templates(tmp)
            (proj / ".claude").mkdir(parents=True, exist_ok=True)
            (proj / ".claude" / "memory.env.ini").write_text("MODE=maind\n", encoding="utf-8")
            projs = sync.select_projects(env, config, {"all": True})
            sync.run_sync(env, config, projs, only="memory-hook")          # first set
            (proj / ".claude" / "memory.env.ini").write_text("MODE=off\n", encoding="utf-8")
            sync.run_sync(env, config, projs, only="memory-hook")          # then rollback
            s = json.loads((proj / ".claude" / "settings.json").read_text())
            self.assertNotIn("autoMemoryEnabled", s)
            cmds = [h["command"] for g in s.get("hooks", {}).get("SessionStart", [])
                    for h in g["hooks"]]
            self.assertFalse(any("maind-memory" in c for c in cmds))

    def test_manual_removes_digest_and_keeps_native_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = self._with_templates(tmp)
            (proj / ".claude").mkdir(parents=True, exist_ok=True)
            (proj / ".claude" / "memory.env.ini").write_text("MODE=maind\n", encoding="utf-8")
            projs = sync.select_projects(env, config, {"all": True})
            sync.run_sync(env, config, projs, only="memory-hook")
            (proj / ".claude" / "memory.env.ini").write_text("MODE=manual\n", encoding="utf-8")
            sync.run_sync(env, config, projs, only="memory-hook")
            s = json.loads((proj / ".claude" / "settings.json").read_text())
            self.assertIs(s["autoMemoryEnabled"], False)
            cmds = [h["command"] for g in s.get("hooks", {}).get("SessionStart", [])
                    for h in g["hooks"]]
            self.assertFalse(any("maind-memory" in c for c in cmds))


class TestOutputStyleProvisioner(unittest.TestCase):
    """output-style: outputStyle=lean in everything.claude/settings.local.json (env:hooks), opt-out
    per-project via project.output_style="off". Goes to ORDER."""
    _HARNESS = Path(__file__).resolve().parents[2] / "harness" / "bin" / "harness"

    def test_in_default_order(self):
        self.assertIn("output-style", sync.provisioner_names())

    def test_skip_when_opted_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            config["projects"][0]["output_style"] = "off"
            projs = sync.select_projects(env, config, {"all": True})
            r = sync.run_sync(env, config, projs, only="output-style")
            self.assertEqual(r[0]["status"], "skip")
            self.assertIn("output_style=off", r[0]["detail"])

    def test_skip_when_no_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            projs[0] = dict(projs[0])
            del projs[0]["local_path"]
            r = sync.run_sync(env, config, projs, only="output-style")
            self.assertEqual(r[0]["status"], "skip")

    def test_applies_lean_by_default_dry(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            old = os.environ.get("MAIND_HARNESS_BIN")
            os.environ["MAIND_HARNESS_BIN"] = str(self._HARNESS)
            try:
                r = sync.run_sync(env, config, projs, only="output-style", dry=True)
            finally:
                if old is None:
                    os.environ.pop("MAIND_HARNESS_BIN", None)
                else:
                    os.environ["MAIND_HARNESS_BIN"] = old
            self.assertEqual(r[0]["status"], "ok")
            self.assertIn("style=lean", r[0]["detail"])
            # honest dry-run harness — nothing recorded
            self.assertFalse((proj / ".claude" / "settings.local.json").exists())


class TestSkillsCatalogProvisioner(unittest.TestCase):
    """skills-catalog: skm:update will re-resolve the project skills catalog (buckets/exclude with
    drive) — new skills of already selected buckets arrive without manual re-run. Goes to ORDER."""
    _SKM = Path(__file__).resolve().parents[2] / "skiller" / "bin" / "skiller"

    def test_in_default_order(self):
        self.assertIn("skills-catalog", sync.provisioner_names())

    def test_skip_when_no_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            projs[0] = dict(projs[0])
            del projs[0]["local_path"]
            r = sync.run_sync(env, config, projs, only="skills-catalog")
            self.assertEqual(r[0]["status"], "skip")

    def test_delegates_to_skm_update(self):
        # tmp-project is not connected to the registry skiller — 'skiller update' ends honestly
        # rc=1 ('not connected'), the provider reflects this as failed, WITHOUT side entries
        # (does not touch home ~/.swissknifeman neither the test nor the real user).
        import os
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            old = os.environ.get("MAIND_SKM_BIN")
            os.environ["MAIND_SKM_BIN"] = str(self._SKM)
            try:
                r = sync.run_sync(env, config, projs, only="skills-catalog", dry=True)
            finally:
                if old is None:
                    os.environ.pop("MAIND_SKM_BIN", None)
                else:
                    os.environ["MAIND_SKM_BIN"] = old
            self.assertEqual(r[0]["provisioner"], "skills-catalog")
            self.assertEqual(r[0]["status"], "failed")
            self.assertIn("rc=1", r[0]["detail"])


class TestRouterConfigProvisioner(unittest.TestCase):
    """router-config: opt-in by .claude/agent-router.env.ini (POLICY!=off). No file/off →
    skip; enabled → generates a directory intent-router via harness (env:router). Goes to ORDER."""
    _HARNESS = Path(__file__).resolve().parents[2] / "harness" / "bin" / "harness"

    def test_in_default_order(self):
        self.assertIn("router-config", sync.provisioner_names())

    def test_skip_when_not_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            r = sync.run_sync(env, config, projs, only="router-config")
            self.assertEqual(r[0]["status"], "skip")
            self.assertIn("not enabled", r[0]["detail"])

    def test_skip_when_policy_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            (proj / ".claude" / "agent-router.env.ini").write_text("POLICY=off\n")
            projs = sync.select_projects(env, config, {"all": True})
            r = sync.run_sync(env, config, projs, only="router-config")
            self.assertEqual(r[0]["status"], "skip")

    def test_generate_when_enabled_dry(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            (proj / ".claude" / "agent-router.env.ini").write_text("POLICY=propose\n")
            projs = sync.select_projects(env, config, {"all": True})
            old = os.environ.get("MAIND_HARNESS_BIN")
            os.environ["MAIND_HARNESS_BIN"] = str(self._HARNESS)
            try:
                r = sync.run_sync(env, config, projs, only="router-config", dry=True)
            finally:
                if old is None:
                    os.environ.pop("MAIND_HARNESS_BIN", None)
                else:
                    os.environ["MAIND_HARNESS_BIN"] = old
            self.assertEqual(r[0]["status"], "ok")


class TestSyncCliExitStatus(unittest.TestCase):
    def test_json_stdout_boundary_moves_provider_fd_output_to_stderr(self):
        stdout_read, stdout_write = os.pipe()
        stderr_read, stderr_write = os.pipe()
        saved_stdout, saved_stderr = os.dup(1), os.dup(2)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(stdout_write, 1)
            os.dup2(stderr_write, 2)
            with sync._json_stdout_boundary(True):
                os.write(1, b"provider chatter\\n")
            os.write(1, b"[]\\n")
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(saved_stdout, 1)
            os.dup2(saved_stderr, 2)
            for descriptor in (saved_stdout, saved_stderr, stdout_write, stderr_write):
                os.close(descriptor)
        self.assertEqual(os.read(stdout_read, 1024), b"[]\\n")
        self.assertEqual(os.read(stderr_read, 1024), b"provider chatter\\n")
        os.close(stdout_read)
        os.close(stderr_read)

    def test_json_mode_exits_nonzero_when_a_provisioner_failed(self):
        rows = [{"provisioner": "mcp", "id": "demo", "status": "failed",
                 "detail": "repair-required"}]
        with (mock.patch.object(sync, "load_config", return_value=({"projects": []}, None)),
              mock.patch.object(sync, "select_projects", return_value=[]),
              mock.patch.object(sync, "run_sync", return_value=rows),
              self.assertRaises(SystemExit) as raised):
            sync.cmd_sync(object(), ["--all", "--json", "--dry-run"])
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
