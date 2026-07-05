"""Тесты doctor.py: диагностика окружения (--help, провал при отсутствии демона, успех
при замоканном окружении). Без живых бинарей/демона — изолированно в tmpdir."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from maind import doctor
from maind.doctor import _skill_drift, cmd_doctor
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


if __name__ == "__main__":
    unittest.main()
