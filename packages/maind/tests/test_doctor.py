"""Тесты doctor.py: диагностика окружения (--help, провал при отсутствии демона, успех
при замоканном окружении). Без живых бинарей/демона — изолированно в tmpdir."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from maind import doctor
from maind.doctor import _channel_overlap, _fleet_context, _skill_drift, cmd_doctor
from tests.fixtures import capture, make_repo, write_maind_config


class TestDoctor(unittest.TestCase):
    def test_help_returns_without_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            _, out = capture(cmd_doctor, env, ["--help"])
            self.assertIn("maind doctor", out)

    def test_reports_issue_when_agentmemory_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)               # node_modules/.bin/agentmemory нет
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
                cmd_doctor(env, ["--quiet"])      # quiet → печатает только провалы
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("agentmemory", buf.getvalue())

    def test_passes_when_env_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)               # iii-config.yaml уже на месте
            bindir = env.root / "node_modules" / ".bin"
            bindir.mkdir(parents=True)
            (bindir / "agentmemory").write_text("", encoding="utf-8")
            orig = doctor.shutil.which
            doctor.shutil.which = lambda name: "/usr/bin/node"
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cmd_doctor(env, ["--quiet"])  # все проверки ок → без SystemExit
                self.assertIn("Все проверки пройдены", buf.getvalue())
            finally:
                doctor.shutil.which = orig

    def test_provider_trust_json_executes_json_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            write_maind_config(root)
            rows = [{"project_id": "alpha", "provider_id": "codex",
                     "green": False, "diagnostics": ["CODEX_TRUST_MISSING"]}]
            with mock.patch.object(doctor, "provider_trust_report", return_value=rows):
                _, out = capture(cmd_doctor, env, ["--provider-trust", "--json"])
            self.assertEqual(json.loads(out), {"providers": rows, "non_green": 1})


def _write_ecosystem_templates(root, *, mcp_body="ecosystem-mcp {{PROJECT}} {{SCOPE}}\n",
                               setup_body="ecosystem-setup {{PROJECT}}\n"):
    """Кладёт минимальные templates/skills/{ecosystem-mcp,ecosystem-setup}/SKILL.md —
    _apply_managed_skill (skilldoc.py) читает их через env.root/templates/…, которых
    нет в синтетическом tmp-корне теста."""
    for name, body in (("ecosystem-mcp", mcp_body), ("ecosystem-setup", setup_body)):
        d = Path(root) / "templates" / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")


class TestSkillDrift(unittest.TestCase):
    """_skill_drift (doctor --skill-drift): сухой прогон ecosystem-mcp/ecosystem-setup
    по enabled-проектам — 'absent' (не раскатан) / 'stale' (шаблон обновился) / нет
    записи, если файл совпадает с текущим шаблоном."""
    def test_reports_absent_when_skill_never_deployed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _write_ecosystem_templates(root)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            write_maind_config(root, projects=[
                {"id": "proj", "name": "Proj", "type": "node-package",
                 "status": "active", "local_path": str(projdir)}])
            from maind.config import load_config
            config, _ = load_config(env)
            drifted = _skill_drift(env, config)
            self.assertEqual({(pid, label) for pid, label, _ in drifted},
                             {("proj", "ecosystem-mcp"), ("proj", "ecosystem-setup")})
            self.assertTrue(all(state == "absent" for *_x, state in drifted))

    def test_no_drift_when_content_matches_current_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _write_ecosystem_templates(root)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            write_maind_config(root, projects=[
                {"id": "proj", "name": "Proj", "type": "node-package",
                 "status": "active", "local_path": str(projdir)}])
            from maind.config import load_config
            config, _ = load_config(env)
            from maind.provision.skilldoc import apply_ecosystem_skill, apply_setup_skill
            apply_ecosystem_skill(env, config, config["projects"][0], "auto", False)
            apply_setup_skill(env, config, config["projects"][0], "auto", False)
            self.assertEqual(_skill_drift(env, config), [])

    def test_reports_stale_when_template_changed_after_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _write_ecosystem_templates(root)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            write_maind_config(root, projects=[
                {"id": "proj", "name": "Proj", "type": "node-package",
                 "status": "active", "local_path": str(projdir)}])
            from maind.config import load_config
            config, _ = load_config(env)
            from maind.provision.skilldoc import apply_ecosystem_skill, apply_setup_skill
            apply_ecosystem_skill(env, config, config["projects"][0], "auto", False)
            apply_setup_skill(env, config, config["projects"][0], "auto", False)
            # maind обновил шаблон ecosystem-mcp (напр. добавил "graph-first" правило) —
            # уже раскатанная копия должна всплыть как stale, setup остаётся fresh
            _write_ecosystem_templates(root, mcp_body="ecosystem-mcp v2 {{PROJECT}} {{SCOPE}}\n")
            self.assertEqual(_skill_drift(env, config),
                             [("proj", "ecosystem-mcp", "stale")])

    def test_disabled_project_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _write_ecosystem_templates(root)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            write_maind_config(root, projects=[
                {"id": "proj", "name": "Proj", "type": "node-package",
                 "status": "active", "enabled": False, "local_path": str(projdir)}])
            from maind.config import load_config
            config, _ = load_config(env)
            self.assertEqual(_skill_drift(env, config), [])


def _write_skiller_stub(root):
    """Заглушка bin/skiller для _sibling_bin (нужен только exists(), не запускается —
    subprocess.run замокан)."""
    binp = Path(root) / "packages" / "skiller" / "bin" / "skiller"
    binp.parent.mkdir(parents=True, exist_ok=True)
    binp.write_text("#!/bin/sh\n", encoding="utf-8")
    binp.chmod(0o755)


class TestChannelOverlap(unittest.TestCase):
    """_channel_overlap (doctor --channel-drift): агрегирует по флоту сухой
    `skiller status --json` каждого enabled-проекта, читая его 'channel_overlap'
    (field-feedback: agelto/azguard/dterema раздавали бакеты и plugin'ом, и вендором
    одновременно — найдено вручную, теперь на радаре doctor)."""

    def _config(self, tmp, root, env, projects):
        _write_skiller_stub(root)
        all_projects = [
            {"id": "swissknifeman", "name": "Swissknifeman", "type": "standalone",
             "status": "active", "enabled": False, "local_path": str(root)},
        ] + projects
        write_maind_config(root, projects=all_projects)
        from maind.config import load_config
        config, _ = load_config(env)
        return config

    def test_reports_overlap_from_skiller_status_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            config = self._config(tmp, root, env, [
                {"id": "proj", "name": "Proj", "type": "php-package",
                 "status": "active", "local_path": str(projdir)}])
            fake = mock.Mock(stdout='{"channel_overlap": ["php", "quality"]}')
            with mock.patch("subprocess.run", return_value=fake) as run:
                overlaps = _channel_overlap(env, config)
            self.assertEqual(overlaps, [("proj", ["php", "quality"])])
            self.assertIn("status", run.call_args.args[0])
            self.assertIn("--json", run.call_args.args[0])

    def test_no_overlap_reported_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            config = self._config(tmp, root, env, [
                {"id": "proj", "name": "Proj", "type": "php-package",
                 "status": "active", "local_path": str(projdir)}])
            fake = mock.Mock(stdout='{"channel_overlap": []}')
            with mock.patch("subprocess.run", return_value=fake):
                self.assertEqual(_channel_overlap(env, config), [])

    def test_broken_json_skipped_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            config = self._config(tmp, root, env, [
                {"id": "proj", "name": "Proj", "type": "php-package",
                 "status": "active", "local_path": str(projdir)}])
            fake = mock.Mock(stdout="not json")
            with mock.patch("subprocess.run", return_value=fake):
                self.assertEqual(_channel_overlap(env, config), [])


class TestFleetContext(unittest.TestCase):
    """_fleet_context (doctor --context): агрегирует по флоту сухой `skiller budget
    --first-turn --target <path> --json` (P5.1) каждого проекта — без дубля токен-
    математики в maind, только потребление JSON (subprocess mocked, паттерн doctor
    --audit settings)."""

    def _config(self, tmp, root, env, projects):
        _write_skiller_stub(root)
        all_projects = [
            {"id": "swissknifeman", "name": "Swissknifeman", "type": "standalone",
             "status": "active", "enabled": False, "local_path": str(root)},
        ] + projects
        write_maind_config(root, projects=all_projects)
        from maind.config import load_config
        config, _ = load_config(env)
        return config

    def test_reports_total_and_verdict_from_skiller_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            config = self._config(tmp, root, env, [
                {"id": "proj", "name": "Proj", "type": "php-package",
                 "status": "active", "local_path": str(projdir)}])
            fake = mock.Mock(stdout='{"target": "'+str(projdir)+'", "sources": {}, '
                             '"total": 4200, "verdict": "OK"}')
            with mock.patch("subprocess.run", return_value=fake) as run:
                rows = _fleet_context(env, config)
            self.assertEqual(rows, [{"id": "proj",
                                     "context": {"total": 4200, "verdict": "OK"}}])
            self.assertIn("budget", run.call_args.args[0])
            self.assertIn("--first-turn", run.call_args.args[0])
            self.assertIn("--json", run.call_args.args[0])

    def test_broken_json_maps_to_na_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            config = self._config(tmp, root, env, [
                {"id": "proj", "name": "Proj", "type": "php-package",
                 "status": "active", "local_path": str(projdir)}])
            fake = mock.Mock(stdout="not json")
            with mock.patch("subprocess.run", return_value=fake):
                rows = _fleet_context(env, config)
            self.assertEqual(rows, [{"id": "proj", "context": "n/a"}])

    def test_missing_local_path_maps_to_na_without_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            config = self._config(tmp, root, env, [
                {"id": "proj", "name": "Proj", "type": "php-package",
                 "status": "active"}])  # без local_path
            with mock.patch("subprocess.run") as run:
                rows = _fleet_context(env, config)
            self.assertEqual(rows, [{"id": "proj", "context": "n/a"}])
            run.assert_not_called()

    def test_cmd_doctor_context_json_prints_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj"
            projdir.mkdir()
            self._config(tmp, root, env, [
                {"id": "proj", "name": "Proj", "type": "php-package",
                 "status": "active", "local_path": str(projdir)}])
            fake = mock.Mock(stdout='{"target": "'+str(projdir)+'", "sources": {}, '
                             '"total": 5000, "verdict": "ELEVATED"}')
            with mock.patch("subprocess.run", return_value=fake):
                _, out = capture(cmd_doctor, env, ["--context", "--json"])
            data = json.loads(out)
            self.assertEqual(data["projects"],
                             [{"id": "proj", "context": {"total": 5000, "verdict": "ELEVATED"}}])


if __name__ == "__main__":
    unittest.main()
