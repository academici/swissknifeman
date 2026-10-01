"""Tests doctor.py: environment diagnostics (--help, failure without demon, success
in a locked environment). No live binaries/demon - isolated in tmpdir."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from maind import doctor
from maind.doctor import (_channel_overlap, _fleet_context, _gitignore_drift,
                          _gitignore_drift_report, _skill_drift, cmd_doctor)
from tests.fixtures import FakeMemoryServer, capture, make_repo, write_maind_config


class TestDoctor(unittest.TestCase):
    def test_help_returns_without_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            _, out = capture(cmd_doctor, env, ["--help"])
            self.assertIn("maind doctor", out)

    def test_reports_issue_when_agentmemory_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)               # node_modules/.bin/agentmemory no
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
                cmd_doctor(env, ["--quiet"])      # quiet → only prints dips
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("agentmemory", buf.getvalue())

    def test_passes_when_env_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)               # iii-config.yaml is already in place
            bindir = env.root / "node_modules" / ".bin"
            bindir.mkdir(parents=True)
            (bindir / "agentmemory").write_text("", encoding="utf-8")
            orig = doctor.shutil.which
            doctor.shutil.which = lambda name: "/usr/bin/node"
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cmd_doctor(env, ["--quiet"])  # all checks ok → without SystemExit
                self.assertIn("All checks passed", buf.getvalue())
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
    """Places minimum templates/skills/{ecosystem-mcp,ecosystem-setup}/SKILL.md —
    _apply_managed_skill (skilldoc.py) reads them through env.root/templates/…, which
    not in synthetic tmp-root of the test."""
    for name, body in (("ecosystem-mcp", mcp_body), ("ecosystem-setup", setup_body)):
        d = Path(root) / "templates" / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")


class TestSkillDrift(unittest.TestCase):
    """_skill_drift (doctor --skill-drift): dry run ecosystem-mcp/ecosystem-setup
    by enabled-projects - 'absent' (not rolled out) / 'stale' (template updated) / no
    entries if the file matches the current template."""
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

    def test_skiller_root_bootstrap_projection_is_not_maind_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            _write_ecosystem_templates(root)
            projdir = Path(tmp) / "swissknifeman"
            projdir.mkdir()
            write_maind_config(root, projects=[
                {"id": "swissknifeman", "name": "SKM", "type": "standalone",
                 "status": "active", "local_path": str(projdir)}])
            from maind.config import load_config
            config, _ = load_config(env)
            for name in ("ecosystem-mcp", "ecosystem-setup"):
                text = (f"---\nname: {name}\ncanonical: packages/skiller/skills/"
                        f"repository-bootstrap/{name}/SKILL.md\n"
                        "generator: packages/skiller/lib/skiller/registry.py\n---\n")
                for provider in (".claude", ".agents"):
                    target = projdir / provider / "skills" / name / "SKILL.md"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text, encoding="utf-8")
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
            # maind updated the template ecosystem-mcp (e.g. added "graph-first" rule) —
            # the already rolled out copy should pop up as stale, setup remains fresh
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
    """Plug bin/skiller for _sibling_bin (is only needed exists(), does not start -
    subprocess.run locked)."""
    binp = Path(root) / "packages" / "skiller" / "bin" / "skiller"
    binp.parent.mkdir(parents=True, exist_ok=True)
    binp.write_text("#!/bin/sh\n", encoding="utf-8")
    binp.chmod(0o755)


class TestChannelOverlap(unittest.TestCase):
    """_channel_overlap (doctor --channel-drift): aggregates by fleet dry
    `skiller status --json` each enabled-project, reading it 'channel_overlap'
    (field-feedback: agelto/azguard/dterema handed out buckets and plugin'om, and vendor
    at the same time - found manually, now on radar doctor)."""

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
    """_fleet_context (doctor --context): aggregates by fleet dry `skiller budget
    --first-turn --target <path> --json` (P5.1) of each project - without duplicate token-
    mathematics in maind, consumption only JSON (subprocess mocked, pattern doctor
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
                 "status": "active"}])  # without local_path
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


class TestMemoryAuthDiagnostic(unittest.TestCase):
    """doctor distinguishes «not available» from «unauthorized» (401) — P4.2 Scope Included:
    ping()/health() cannot (/agentmemory/health is always public), need a real one
    protected-call (memory.check_auth), which doctor prints in info-line."""

    def _env_ok(self, env):
        bindir = env.root / "node_modules" / ".bin"
        bindir.mkdir(parents=True)
        (bindir / "agentmemory").write_text("", encoding="utf-8")
        doctor.shutil.which = lambda name: "/usr/bin/node"

    def test_reports_unauthorized_when_secret_mismatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            self._env_ok(env)
            try:
                with FakeMemoryServer(secret="right-token") as url:
                    secret_path = env.root / "memory.secret"
                    secret_path.write_text("wrong-token", encoding="utf-8")
                    write_maind_config(root, memory={"url": url, "secret_file": "memory.secret"})
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        cmd_doctor(env, [])
                    self.assertIn("unauthorized", buf.getvalue())
            finally:
                doctor.shutil.which = __import__("shutil").which

    def test_reports_reachable_when_no_secret_configured(self):
        # without configured client-side secret doctor does NOT state about authorization -
        # only «replies» (check_auth not applicable without headers).
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            self._env_ok(env)
            try:
                with FakeMemoryServer() as url:
                    write_maind_config(root, memory={"url": url})
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        cmd_doctor(env, [])
                    self.assertIn("replies", buf.getvalue())
                    self.assertNotIn("unauthorized", buf.getvalue())
            finally:
                doctor.shutil.which = __import__("shutil").which


if __name__ == "__main__":
    unittest.main()


class TestGitignoreDrift(unittest.TestCase):
    """doctor --gitignore-drift: checking projects against the map configs/gitignore-policy.json."""

    def _project(self, tmp):
        import subprocess
        root, env = make_repo(tmp)
        projdir = Path(tmp) / "proj"
        projdir.mkdir()
        subprocess.run(["git", "-C", str(projdir), "init", "-q"], check=True)
        (projdir / ".claude" / "runs").mkdir(parents=True)
        (projdir / ".claude" / "runs" / "1.json").write_text("{}")
        write_maind_config(root, projects=[
            {"id": "proj", "name": "Proj", "type": "node-package",
             "status": "active", "local_path": str(projdir)}])
        from maind.config import load_config
        config, _ = load_config(env)
        return config

    def test_reports_unignored_runtime_state_with_a_ready_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._project(tmp)
            rows = _gitignore_drift(config)
            self.assertEqual([pid for pid, _f, _p in rows], ["proj"])
            self.assertIn(("unignored", ".claude/runs/1.json"),
                          {(f["code"], f["path"]) for f in rows[0][1]})
            _, out = capture(_gitignore_drift_report, config, True, block=True)
            self.assertIn("proj:", out)
            self.assertIn(".claude/runs/", out)

    def test_summary_line_and_json_do_not_require_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self._project(tmp)
            _, out = capture(_gitignore_drift_report, config, False)
            self.assertIn("diverge", out)
            _, out = capture(_gitignore_drift_report, config, True, as_json=True)
            self.assertEqual(json.loads(out)["projects"][0]["id"], "proj")
