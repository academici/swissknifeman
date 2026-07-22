"""Тесты sync.py (фан-аут + провиженеры mcp/graph/memory-hook) и common.managed_block."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

_TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

from maind.provision import sync
from maind.common import managed_block, upsert_block
from maind.config import load_config
from maind.mcpconfig import has_server
from tests.fixtures import make_repo, write_maind_config


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
        t0 = "# Project\n\nДокументация.\n"
        t1, changed, state = upsert_block(t0, "ПРИОРИТЕТ №1", self.MARK)
        self.assertTrue(changed)
        self.assertEqual(state, "absent")
        self.assertIn("ПРИОРИТЕТ №1", t1)
        self.assertIn("# Project", t1)  # чужой текст сохранён
        t2, changed2, state2 = upsert_block(t1, "ПРИОРИТЕТ №1", self.MARK)
        self.assertFalse(changed2)
        self.assertEqual(state2, "fresh")
        self.assertEqual(t1, t2)

    def test_update_on_drift(self):
        t0, _, _ = upsert_block("# P\n", "старый текст", self.MARK)
        t1, changed, state = upsert_block(t0, "новый текст", self.MARK)
        self.assertTrue(changed)
        self.assertEqual(state, "stale")
        self.assertIn("новый текст", t1)
        self.assertNotIn("старый текст", t1)
        self.assertEqual(t1.count(self.MARK), 2)  # один блок (begin+end), не два

    def test_block_has_hash(self):
        self.assertIn("hash=", managed_block("x", self.MARK))


class TestProviderContexts(unittest.TestCase):
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
            for package in ("skiller", "harness", "maind", "analyst", "task"):
                self.assertTrue((project / "packages" / package / "CLAUDE.md").is_file())
                self.assertTrue((project / "packages" / package / "AGENTS.md").is_file())
            second = sync.run_sync(env, config, config["projects"], only="instructions", mode="auto")
            self.assertEqual(second[0]["provider_aggregate"], "green")
            self.assertFalse(second[0]["changed"])

    def test_instruction_provisioner_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, project = _setup(tmp)
            row = sync.run_sync(env, config, config["projects"], only="instructions", dry=True)[0]
            self.assertEqual(row["status"], "dry")
            self.assertFalse((project / "CLAUDE.md").exists())

    def test_instruction_repair_changes_only_managed_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, project = _setup(tmp)
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
    """Вариант C: project.roles → config.role_packs[role], аддитивно к профильному паку."""
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
    """update не должен падать на паке, которого ещё нет в lock'е цели (field-feedback:
    профиль дорос новым паком → sync --mode update душил его через upgrade, требующий
    prior-install; чинить полагается install-путём, апгрейдить — уже стоящие)."""

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
            self.assertFalse(has_server(proj / ".mcp.json", "agentmemory"))  # raw выведен
            self.assertTrue(r1[0]["changed"])
            r2 = sync.run_sync(env, config, projs, only="mcp")
            self.assertFalse(r2[0]["changed"])  # повтор — без изменений

    def test_mcp_provisioner_graphify_config_driven(self):
        # graphify:true в записи проекта → провиженер mcp раскатывает graphify
        # (когда бинарь есть); без флага — нет. Бинарь мокаем присутствующим.
        from maind.provision import deploy
        orig = deploy.shutil.which
        deploy.shutil.which = lambda name: f"/usr/bin/{name}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env, config, proj = _setup(tmp)
                config["projects"][0]["graphify"] = True
                projs = sync.select_projects(env, config, {"all": True})
                sync.run_sync(env, config, projs, only="mcp")
                self.assertTrue(has_server(proj / ".mcp.json", "serena"))
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
        # повторный derive без изменений источников → changed=False (детерминированный стор)
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _ = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            r1 = sync.run_sync(env, config, projs, only="graph")
            self.assertTrue(all(r["changed"] for r in r1))  # первый прогон — создание
            r2 = sync.run_sync(env, config, projs, only="graph")
            self.assertTrue(all(not r["changed"] for r in r2))  # повтор — без изменений

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
        # авто-загрузка памяти раскатывается и обычным `maind sync --all`
        self.assertIn("memory-hook", sync.provisioner_names())


class TestMemoryHookProvisioner(unittest.TestCase):
    """memory-hook читает интент из .claude/memory.env.ini: MODE=maind → инжект дайджеста +
    native off; нет конфига → пропуск; off → revert. Так фича докатывается через sync."""

    def _with_templates(self, tmp):
        env, config, proj = _setup(tmp)
        shutil.copytree(_TEMPLATES, env.root / "templates")  # шаблоны health в env.root
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
            self.assertFalse(r2[0]["changed"])  # повтор — без изменений

    def test_revert_when_mode_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = self._with_templates(tmp)
            (proj / ".claude").mkdir(parents=True, exist_ok=True)
            (proj / ".claude" / "memory.env.ini").write_text("MODE=maind\n", encoding="utf-8")
            projs = sync.select_projects(env, config, {"all": True})
            sync.run_sync(env, config, projs, only="memory-hook")          # сперва ставим
            (proj / ".claude" / "memory.env.ini").write_text("MODE=off\n", encoding="utf-8")
            sync.run_sync(env, config, projs, only="memory-hook")          # потом откатываем
            s = json.loads((proj / ".claude" / "settings.json").read_text())
            self.assertNotIn("autoMemoryEnabled", s)
            cmds = [h["command"] for g in s.get("hooks", {}).get("SessionStart", [])
                    for h in g["hooks"]]
            self.assertFalse(any("maind-memory" in c for c in cmds))


class TestOutputStyleProvisioner(unittest.TestCase):
    """output-style: outputStyle=lean во все .claude/settings.local.json (env:hooks), опт-аут
    per-project через project.output_style="off". Идёт в ORDER."""
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
            # честный dry-run harness — ничего не записано
            self.assertFalse((proj / ".claude" / "settings.local.json").exists())


class TestSkillsCatalogProvisioner(unittest.TestCase):
    """skills-catalog: skm:update пере-резолвит каталог скиллов проекта (buckets/exclude с
    диска) — новые скиллы уже выбранных бакетов доезжают без ручного re-run. Идёт в ORDER."""
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
        # tmp-проект не подключён к реестру skiller — 'skiller update' честно завершается
        # rc=1 ('не подключён'), провиженер отражает это как failed, БЕЗ побочных записей
        # (не трогает домашний ~/.swissknifeman ни у теста, ни у реального пользователя).
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
    """router-config: opt-in по .claude/agent-router.env.ini (POLICY!=off). Нет файла/off →
    skip; включён → генерит каталог intent-router через harness (env:router). Идёт в ORDER."""
    _HARNESS = Path(__file__).resolve().parents[2] / "harness" / "bin" / "harness"

    def test_in_default_order(self):
        self.assertIn("router-config", sync.provisioner_names())

    def test_skip_when_not_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj = _setup(tmp)
            projs = sync.select_projects(env, config, {"all": True})
            r = sync.run_sync(env, config, projs, only="router-config")
            self.assertEqual(r[0]["status"], "skip")
            self.assertIn("не включён", r[0]["detail"])

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


if __name__ == "__main__":
    unittest.main()
