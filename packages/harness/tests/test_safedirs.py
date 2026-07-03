"""safe-dirs: rm/rmdir внутри доверенных директорий проходят мимо deny_hard.

Два слоя:
  1. Юнит — ядро вердикта lib/safedirs.py (importlib по пути): containment,
     fail-closed на глобах/подстановках/флагах, cd-трекинг, защита .git/корня.
  2. Сценарный — РЕАЛЬНЫЙ auto-approve.sh через subprocess с HOME=tmp
     (machine-owned фикстуры safe-dirs.json/projects.json), включая регрессию
     «вне allowlist — deny как раньше» и иммунитет к project-override конфига."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
HOOK_DIR = PKG / "configs" / "claude-code" / "hooks" / "auto-approve"
SAFEDIRS_PY = HOOK_DIR / "lib" / "safedirs.py"
HAS_JQ = shutil.which("jq") is not None

_spec = importlib.util.spec_from_file_location("safedirs", SAFEDIRS_PY)
safedirs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(safedirs)


class _Fixture(unittest.TestCase):
    """tmp-«машина»: $HOME с .swissknifeman/safe-dirs.json и деревом проектов.
    Конфиг передаётся хуку ЯВНО (path-аргумент / $SKM_SAFE_DIRS_CONFIG) — иначе
    лестница поиска нашла бы реальный монорепо-конфиг машины через PATH."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="safedirs-test."))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.demo = self.home / "projects" / "demo"
        (self.demo / "build").mkdir(parents=True)
        (self.home / ".swissknifeman").mkdir(parents=True)
        (self.tmp / "outside").mkdir()
        self.cfg_path = self.home / ".swissknifeman" / "safe-dirs.json"
        self.write_config()

    def write_config(self, **over):
        cfg = {"version": 1, "include_registered_projects": False,
               "dirs": ["~/projects"], "exclude": [],
               "protect_git": True, "allow_globs": True}
        cfg.update(over)
        self.cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    def load(self):
        return safedirs.load_allowlist(str(self.home), str(self.cfg_path))


class TestVerdictCore(_Fixture):
    """Ядро command_is_safe: fail-closed везде, где анализ неоднозначен."""

    def safe(self, cmd, cwd=None):
        allow = self.load()
        self.assertIsNotNone(allow, "конфиг должен грузиться")
        return safedirs.command_is_safe(
            cmd, str(self.demo) if cwd is None else cwd, allow, str(self.home))

    # --- позитив: то, ради чего фича существует
    def test_inside_relative_and_absolute(self):
        self.assertTrue(self.safe("rm -rf build"))
        self.assertTrue(self.safe(f"rm -rf {self.demo}/build", cwd=str(self.home)))

    def test_flags_ddash_quotes_multiargs(self):
        self.assertTrue(self.safe("rm -rf -- build"))
        self.assertTrue(self.safe('rm -rf "a b"'))
        self.assertTrue(self.safe("rm -f a.txt b.txt --verbose"))
        self.assertTrue(self.safe("rmdir build"))

    def test_glob_static_prefix_inside(self):
        self.assertTrue(self.safe("rm -rf build/*"))
        # глоб по детям корня safe-dir — можно (сам корень не удаляется)
        self.assertTrue(self.safe(f"rm -rf {self.home}/projects/*", cwd=str(self.home)))

    def test_cd_tracking(self):
        self.assertTrue(self.safe("cd projects/demo && rm -rf build", cwd=str(self.home)))
        self.assertTrue(self.safe("cd build; rm -rf out"))  # оба candidate внутри
        self.assertTrue(self.safe("rm -rf build && npm ci"))  # чужая голова — не наша забота

    def test_tilde_path_inside(self):
        self.assertTrue(self.safe("rm -rf ~/projects/demo/build"))

    # --- негатив: containment
    def test_outside_paths(self):
        self.assertFalse(self.safe("rm -rf /etc/passwd"))
        self.assertFalse(self.safe(f"rm -rf {self.tmp}/outside"))
        self.assertFalse(self.safe("rm -rf build /etc/passwd"))  # all-or-nothing

    def test_dotdot_rejected_lexically(self):
        self.assertFalse(self.safe("rm -rf ../../outside"))
        self.assertFalse(self.safe("rm -rf build/../../.."))

    def test_symlink_escape(self):
        os.symlink("/etc", self.demo / "etclink")
        self.assertFalse(self.safe("rm -rf etclink/passwd"))

    def test_safe_dir_root_and_home(self):
        self.assertFalse(self.safe(f"rm -rf {self.home}/projects", cwd=str(self.home)))
        self.assertFalse(self.safe("rm -rf ~"))
        self.assertFalse(self.safe("rm -rf ~otheruser/x"))

    def test_protect_git(self):
        self.assertFalse(self.safe("rm -rf .git"))
        self.assertFalse(self.safe("rm -rf .git/index"))
        self.assertFalse(self.safe("rm -rf .git*"))
        self.assertFalse(self.safe("rm -rf .*"))
        self.assertFalse(self.safe("rm -rf sub*/.git"))
        self.write_config(protect_git=False)
        self.assertTrue(self.safe("rm -rf .git"))

    def test_exclude(self):
        self.write_config(exclude=[str(self.demo / "build")])
        self.assertFalse(self.safe("rm -rf build"))
        self.assertFalse(self.safe("rm -rf build/x.o"))
        self.assertTrue(self.safe("rm -rf other.txt"))

    # --- негатив: fail-closed на shell-магии и структуре
    def test_substitutions_and_vars(self):
        self.assertFalse(self.safe("rm -rf $DIR"))
        self.assertFalse(self.safe("rm -rf $(ls)"))
        self.assertFalse(self.safe("rm -rf `ls`"))
        self.assertFalse(self.safe("rm -rf {a,b}"))

    def test_rm_not_at_head(self):
        self.assertFalse(self.safe("ls | xargs rm"))
        self.assertFalse(self.safe("sudo rm -rf build"))
        self.assertFalse(self.safe("FOO=1 rm -rf build"))
        self.assertFalse(self.safe("time rm -rf build"))

    def test_git_rm_alone_is_not_ours(self):
        # git rm обслуживает маскирование analyze.sh — нам нечего разрешать
        self.assertFalse(self.safe("git rm file.txt"))

    def test_unknown_flags_and_empty_args(self):
        self.assertFalse(self.safe("rm --no-preserve-root -rf build"))
        self.assertFalse(self.safe("rmdir -p a/b"))
        self.assertFalse(self.safe("rm -rf"))

    def test_globs_disabled(self):
        self.write_config(allow_globs=False)
        self.assertFalse(self.safe("rm -rf build/*"))
        self.assertTrue(self.safe("rm -rf build"))

    def test_multiline_and_no_cwd(self):
        self.assertFalse(self.safe("rm -rf build\nchmod -R 777 /"))
        self.assertFalse(self.safe("rm -rf build", cwd=""))
        self.assertTrue(self.safe(f"rm -rf {self.demo}/build", cwd=""))  # абсолютный не страдает

    def test_cd_branching_or_unresolvable(self):
        self.assertFalse(self.safe("cd projects/demo || rm -rf build", cwd=str(self.home)))
        self.assertFalse(self.safe("cd $DIR && rm -rf build", cwd=str(self.home)))
        self.assertFalse(self.safe("cd /etc; rm -rf passwd", cwd=str(self.home)))
        self.assertFalse(self.safe("cd - && rm -rf build"))


class TestAllowlistLoading(_Fixture):
    """Гарды machine-owned конфига: не доверяем даже своему JSON."""

    def roots(self):
        allow = self.load()
        return allow["roots"] if allow else None

    def test_dangerous_roots_ignored(self):
        self.write_config(dirs=["/", str(self.home), str(self.home.parent),
                                "~/projects"])
        self.assertEqual(self.roots(), [str((self.home / "projects").resolve())])

    def test_missing_or_broken_config_disables(self):
        self.cfg_path.write_text("{битый", encoding="utf-8")
        self.assertIsNone(self.load())
        self.cfg_path.unlink()
        self.assertIsNone(self.load())

    def test_unknown_version_disables(self):
        self.write_config(version=2)
        self.assertIsNone(self.load())

    def test_registered_projects_included(self):
        proj = self.tmp / "elsewhere" / "repo"
        proj.mkdir(parents=True)
        (self.home / ".swissknifeman" / "projects.json").write_text(
            json.dumps({"version": 1, "projects": [{"path": str(proj)}]}), encoding="utf-8")
        self.write_config(dirs=[], include_registered_projects=True)
        self.assertEqual(self.roots(), [str(proj.resolve())])
        self.assertTrue(safedirs.command_is_safe(
            "rm -rf dist", str(proj), self.load(), str(self.home)))


class TestConfigPathLadder(_Fixture):
    """Лестница поиска конфига: env-override → корень монорепо (PATH) → legacy home."""

    def test_env_override_is_exclusive(self):
        with unittest.mock.patch.dict(os.environ,
                                      {"SKM_SAFE_DIRS_CONFIG": "/x/y.json"}):
            self.assertEqual(safedirs._config_path(str(self.home)), "/x/y.json")

    def test_repo_root_via_launcher_realpath(self):
        # фейковый монорепо: маркер .claude-plugin/marketplace.json + лаунчер в bin/
        repo = self.tmp / "repo"
        (repo / ".claude-plugin").mkdir(parents=True)
        (repo / ".claude-plugin" / "marketplace.json").write_text("{}", encoding="utf-8")
        (repo / "bin").mkdir()
        launcher = repo / "bin" / "swissknifeman"
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        (repo / "safe-dirs.json").write_text(
            json.dumps({"version": 1, "dirs": []}), encoding="utf-8")
        with unittest.mock.patch.dict(os.environ, {}, clear=False), \
                unittest.mock.patch.object(safedirs.shutil, "which",
                                           lambda n: str(launcher) if n == "swissknifeman" else None):
            os.environ.pop("SKM_SAFE_DIRS_CONFIG", None)
            self.assertEqual(safedirs._config_path(str(self.home)),
                             str(repo / "safe-dirs.json"))

    def test_legacy_home_fallback_without_launchers(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=False), \
                unittest.mock.patch.object(safedirs.shutil, "which", lambda n: None):
            os.environ.pop("SKM_SAFE_DIRS_CONFIG", None)
            self.assertEqual(safedirs._config_path(str(self.home)),
                             str(self.home / ".swissknifeman" / "safe-dirs.json"))


@unittest.skipUnless(HAS_JQ, "нужен jq")
class TestHookEndToEnd(_Fixture):
    """Реальный auto-approve.sh: allow внутри safe-dirs, deny вне (регрессия)."""

    def setUp(self):
        super().setUp()
        # tmp-копия хука = machine-owned HOOK_DIR (env.ini под нашим контролем)
        self.hookdir = self.tmp / "hook"
        shutil.copytree(HOOK_DIR, self.hookdir)
        # пустой «проект», чтобы CLAUDE_PROJECT_DIR сессии не влиял на тест
        self.proj = self.tmp / "proj"
        (self.proj / ".claude").mkdir(parents=True)

    def decide(self, command, cwd=None, mode="strict"):
        (self.hookdir / "env.ini").write_text(f"MODE={mode}\n", encoding="utf-8")
        ev = {"tool_name": "Bash", "cwd": cwd or str(self.demo),
              "tool_input": {"command": command}}
        p = subprocess.run(
            ["bash", str(self.hookdir / "auto-approve.sh")],
            input=json.dumps(ev).encode(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=20,
            # env-override эксклюзивен: без него хук нашёл бы конфиг реального
            # монорепо машины через PATH-лаунчеры
            env={**os.environ, "HOME": str(self.home),
                 "SKM_SAFE_DIRS_CONFIG": str(self.cfg_path),
                 "CLAUDE_PROJECT_DIR": str(self.proj)})
        out = p.stdout.decode("utf-8", "replace").replace(" ", "")
        if '"permissionDecision":"allow"' in out:
            return "allow"
        if '"permissionDecision":"deny"' in out:
            return "deny"
        return "fallthrough"

    def test_rm_inside_allowed(self):
        self.assertEqual(self.decide("rm -rf build"), "allow")
        self.assertEqual(self.decide(f"rm -rf {self.demo}/build", cwd=str(self.home)),
                         "allow")
        self.assertEqual(self.decide("cd projects/demo && rm -rf build",
                                     cwd=str(self.home)), "allow")
        self.assertEqual(self.decide('rm -rf "a b"'), "allow")
        self.assertEqual(self.decide("rm -rf build", mode="bypass"), "allow")

    def test_rm_outside_denied_regression(self):
        self.assertEqual(self.decide("rm -rf /etc/passwd"), "deny")
        self.assertEqual(self.decide("rm -rf ../../outside"), "deny")
        self.assertEqual(self.decide("ls | xargs rm"), "deny")
        self.assertEqual(self.decide("rm -rf /etc/passwd", mode="bypass"), "deny")
        self.assertEqual(self.decide("rm -rf build /etc/passwd"), "deny")

    def test_no_config_means_old_behavior(self):
        (self.home / ".swissknifeman" / "safe-dirs.json").unlink()
        self.assertEqual(self.decide("rm -rf build"), "deny")

    def test_mixed_compound_falls_through(self):
        # rm валиден, но npm — неизвестная голова: не allow и не deny, обычный промпт
        self.assertEqual(self.decide("rm -rf build && npm ci"), "fallthrough")

    def test_git_rm_unchanged(self):
        # git rm — мутация (deny_block_approve): обычный промпт, как и раньше
        self.assertEqual(self.decide("git rm file.txt"), "fallthrough")

    def test_project_override_cannot_grant_safedirs(self):
        # враждебный репозиторий подменяет config.json хука целиком — allowlist
        # safe-dirs machine-owned и не читается из project-override
        evil_cfg = json.loads((HOOK_DIR / "config.json").read_text(encoding="utf-8"))
        (self.proj / ".claude" / "auto-approve.config.json").write_text(
            json.dumps(evil_cfg), encoding="utf-8")
        self.assertEqual(self.decide(f"rm -rf {self.tmp}/outside"), "deny")
        # ...а легитимный rm внутри safe-dirs работает и при override
        self.assertEqual(self.decide("rm -rf build"), "allow")

    def test_read_only_still_auto_approved(self):
        self.assertEqual(self.decide("ls -la"), "allow")


if __name__ == "__main__":
    unittest.main()
