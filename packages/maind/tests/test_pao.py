"""Тесты pao — детект/статус laravel/pao (SKM-AUDIT-004 P6.2), без реального composer/php."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import maind.pao as pao


class TestPaoStatus(unittest.TestCase):
    def test_non_php_type_is_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pao.status({"type": "node-package"}, Path(tmp)), "n-a")

    def test_opt_out_wins_before_php_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = {"type": "laravel-project", "pao_opt_out": True}
            self.assertEqual(pao.status(proj, Path(tmp)), "opt-out")

    @mock.patch.object(pao, "_php_version", return_value=(8, 1))
    def test_php_too_old(self, _m):
        with tempfile.TemporaryDirectory() as tmp:
            proj = {"type": "php-package"}
            self.assertEqual(pao.status(proj, Path(tmp)), "php-too-old")

    @mock.patch.object(pao, "_php_version", return_value=(8, 3))
    def test_missing_when_not_installed(self, _m):
        with tempfile.TemporaryDirectory() as tmp:
            proj = {"type": "laravel-project"}
            self.assertEqual(pao.status(proj, Path(tmp)), "missing")

    @mock.patch.object(pao, "_php_version", return_value=(8, 4))
    def test_installed_via_vendor_dir(self, _m):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "vendor" / "laravel" / "pao").mkdir(parents=True)
            proj = {"type": "laravel-project"}
            self.assertEqual(pao.status(proj, path), "installed")

    @mock.patch.object(pao, "_php_version", return_value=(8, 4))
    def test_installed_via_composer_lock(self, _m):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "composer.lock").write_text('{"packages":[{"name":"laravel/pao"}]}',
                                                 encoding="utf-8")
            proj = {"type": "php-package"}
            self.assertEqual(pao.status(proj, path), "installed")


class TestApplyPao(unittest.TestCase):
    def test_skip_states_return_no_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            step = pao.apply_pao({"id": "p", "type": "node-package"}, Path(tmp),
                                 interactive=True, dry=False)
            self.assertEqual(step, {"name": "pao", "status": "skipped",
                                    "detail": "не PHP-проект"})

    @mock.patch.object(pao, "status", return_value="missing")
    def test_dry_run_skips_without_prompt(self, _m):
        with tempfile.TemporaryDirectory() as tmp:
            step = pao.apply_pao({"id": "p", "type": "laravel-project"}, Path(tmp),
                                 interactive=True, dry=True)
            self.assertEqual(step["status"], "skipped")
            self.assertEqual(step["detail"], "--dry-run")

    @mock.patch("maind.pao.warn")
    @mock.patch.object(pao, "status", return_value="missing")
    def test_noninteractive_warns_and_does_not_install(self, _m, warn_mock):
        with tempfile.TemporaryDirectory() as tmp:
            step = pao.apply_pao({"id": "p", "type": "laravel-project"}, Path(tmp),
                                 interactive=False, dry=False)
            self.assertEqual(step["status"], "skipped")
            warn_mock.assert_called_once()

    @mock.patch("maind.pao.subprocess.run")
    @mock.patch("builtins.input", return_value="y")
    @mock.patch.object(pao, "status", return_value="missing")
    def test_interactive_confirm_installs(self, _m, _input, run_mock):
        run_mock.return_value = mock.Mock(returncode=0, stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            step = pao.apply_pao({"id": "p", "type": "laravel-project"}, Path(tmp),
                                 interactive=True, dry=False)
            self.assertEqual(step["status"], "ok")
            run_mock.assert_called_once_with(
                ["composer", "require", "laravel/pao", "--dev"],
                cwd=tmp, capture_output=True, text=True, timeout=180)

    @mock.patch("maind.pao.warn")
    @mock.patch("builtins.input", return_value="n")
    @mock.patch.object(pao, "status", return_value="missing")
    def test_interactive_decline_skips(self, _m, _input, warn_mock):
        with tempfile.TemporaryDirectory() as tmp:
            step = pao.apply_pao({"id": "p", "type": "laravel-project"}, Path(tmp),
                                 interactive=True, dry=False)
            self.assertEqual(step["status"], "skipped")
            warn_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
