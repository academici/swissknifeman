"""Тесты drift-детекта generated-файлов agent-packs (E-2): lock_drift + CLI
`agent-packs doctor --drift [--strict]`. Изоляция в tmpdir, без сети."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from harness import agentpacks as ap
from harness.cli import main as cli_main
from tests.fixtures import make_pack, make_project, make_root


class TestLockDrift(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.env = make_root(self.tmp)
        self.pack = make_pack(self.root)
        self.proj = make_project(self.tmp, "p")
        (self.proj / "composer.json").write_text('{"scripts": {"test": "pest"}}')
        ap.do_render(self.env, self.pack, self.proj, auto=True,
                     overrides={"PACK_PREFIX": "acme"}, dry=False,
                     install_only=False, shell_policy="safe")

    def test_no_lock_file_no_drift(self):
        empty_proj = make_project(self.tmp, "empty")
        self.assertEqual(ap.lock_drift(empty_proj), [])

    def test_clean_render_no_drift(self):
        # сразу после render diсk == base_sha256 у всех отслеживаемых файлов
        self.assertEqual(ap.lock_drift(self.proj), [])

    def test_locally_modified_template_reported(self):
        rendered = self.proj / ".claude/agents/acme-reviewer.md"
        rendered.write_text(rendered.read_text() + "\nЛОКАЛЬНАЯ ПРАВКА\n")
        drift = ap.lock_drift(self.proj)
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["pack"], self.pack)
        self.assertEqual(drift[0]["target"], ".claude/agents/acme-reviewer.md")
        self.assertEqual(drift[0]["status"], "modified")

    def test_missing_verbatim_file_reported(self):
        gate = self.proj / ".claude/hooks/gate.sh"
        gate.unlink()
        drift = ap.lock_drift(self.proj)
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["target"], ".claude/hooks/gate.sh")
        self.assertEqual(drift[0]["status"], "missing")

    def test_user_owned_edit_not_reported(self):
        # override.md — user_owned: правка ожидаема, это не «дрейф generated»
        overrides = self.proj / ".claude/agents/acme-overrides.md"
        overrides.write_text(overrides.read_text() + "\nмоя правка\n")
        self.assertEqual(ap.lock_drift(self.proj), [])

    def test_merge_kind_skipped_even_if_tampered(self):
        # settings.json — kind=merge, свой sha не отслеживаем: тампер не должен
        # породить дрейф (даже если формально base_sha256 в lock перестал совпадать)
        settings = self.proj / ".claude/settings.json"
        settings.write_text(settings.read_text() + "\n// tamper\n")
        self.assertEqual(ap.lock_drift(self.proj), [])

    def test_multiple_findings_together(self):
        rendered = self.proj / ".claude/agents/acme-reviewer.md"
        rendered.write_text(rendered.read_text() + "\nX\n")
        (self.proj / ".claude/hooks/gate.sh").unlink()
        drift = ap.lock_drift(self.proj)
        statuses = sorted(d["status"] for d in drift)
        self.assertEqual(statuses, ["missing", "modified"])


class TestDoctorDriftCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.env = make_root(self.tmp)
        self.pack = make_pack(self.root)
        self.proj = make_project(self.tmp, "p")
        (self.proj / "composer.json").write_text('{"scripts": {"test": "pest"}}')
        ap.do_render(self.env, self.pack, self.proj, auto=True,
                     overrides={"PACK_PREFIX": "acme"}, dry=False,
                     install_only=False, shell_policy="safe")

    def _run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                cli_main([str(self.root), "agent-packs", *argv])
        return ctx.exception.code, out.getvalue(), err.getvalue()

    def test_clean_drift_rc0(self):
        rc, out, _err = self._run_cli(["doctor", "--target", str(self.proj), "--drift"])
        self.assertEqual(rc, 0)
        self.assertIn("[OK]", out)

    def test_modified_drift_informative_rc0_without_strict(self):
        rendered = self.proj / ".claude/agents/acme-reviewer.md"
        rendered.write_text(rendered.read_text() + "\nЛОКАЛЬНАЯ ПРАВКА\n")
        rc, _out, err = self._run_cli(["doctor", "--target", str(self.proj), "--drift"])
        self.assertEqual(rc, 0)  # без --strict rc=0, чисто информативно
        self.assertIn("generated-файл правлен локально", err)
        self.assertIn("перенеси правку в override и восстанови render", err)
        self.assertIn(".claude/agents/acme-reviewer.md", err)

    def test_modified_drift_strict_rc1(self):
        rendered = self.proj / ".claude/agents/acme-reviewer.md"
        rendered.write_text(rendered.read_text() + "\nЛОКАЛЬНАЯ ПРАВКА\n")
        rc, _out, err = self._run_cli(
            ["doctor", "--target", str(self.proj), "--drift", "--strict"])
        self.assertEqual(rc, 1)
        self.assertIn("generated-файл правлен локально", err)

    def test_missing_drift_message(self):
        (self.proj / ".claude/hooks/gate.sh").unlink()
        rc, _out, err = self._run_cli(
            ["doctor", "--target", str(self.proj), "--drift", "--strict"])
        self.assertEqual(rc, 1)
        self.assertIn("generated-файл отсутствует", err)
        self.assertIn(".claude/hooks/gate.sh", err)

    def test_drift_without_target_dies(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                cli_main([str(self.root), "agent-packs", "doctor", "--drift"])
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("--target", err.getvalue())


if __name__ == "__main__":
    unittest.main()
