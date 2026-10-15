"""The launcher context: authority over --project and SKM_PROJECT_ROOT, the checks of the umbrella, write containment."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from aicore.state import (LauncherError, ProjectContextConflict, ProjectContextRequired, ProjectWriteError,
                          find_project_root, read_invocation_context, require_project_path, resolve_project,
                          validate_launcher_env)
from aicore.state.invocation import LOCK_SCHEMA, LAUNCHER_PROTOCOL


def make_project(base: Path, name: str = "proj", lock: bool = True) -> Path:
    root = base / name
    (root / ".git").mkdir(parents=True)
    (root / ".swissknifeman").mkdir()
    (root / ".swissknifeman" / "launcher.py").write_text("# launcher\n", encoding="utf-8")
    if lock:
        (root / ".swissknifeman" / "launcher.lock.json").write_text(json.dumps(
            {"$schema": LOCK_SCHEMA, "protocol": LAUNCHER_PROTOCOL, "template_sha256": "0" * 64,
             "managed_files": [".swissknifeman/launcher.py"]}), encoding="utf-8")
    return root.resolve()


def launcher_env(root: Path, cwd: Path = None, **extra) -> dict:
    env = {"SKM_LAUNCHER_ACTIVE": "1", "SKM_LAUNCHER_PROTOCOL": str(LAUNCHER_PROTOCOL),
           "SKM_LAUNCHER_PATH": str(root / ".swissknifeman" / "launcher.py"),
           "SKM_LAUNCHER_PROJECT_ROOT": str(root), "SKM_LAUNCHER_PID": str(os.getpid()),
           "SKM_INVOCATION_CWD": str(cwd or root), "HOME": "/nonexistent-home"}
    env.update(extra)
    return env


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.a = make_project(self.base, "A")
        self.b = make_project(self.base, "B")

    def tearDown(self):
        self._tmp.cleanup()


class ResolverAuthorityTests(Base):
    def test_launcher_root_wins_over_environment_and_markers(self):
        env = launcher_env(self.a, SKM_PROJECT_ROOT=str(self.b))
        context = resolve_project(self.b, env=env)
        self.assertEqual((context.root, context.resolution), (self.a, "launcher"))

    def test_equal_explicit_project_is_accepted(self):
        context = resolve_project(self.a, explicit=str(self.a / "." / ".."/ "A"), env=launcher_env(self.a))
        self.assertEqual(context.root, self.a)

    def test_other_explicit_project_is_a_conflict(self):
        with self.assertRaises(ProjectContextConflict) as caught:
            resolve_project(self.a, explicit=str(self.b), env=launcher_env(self.a))
        self.assertIn("PROJECT_CONTEXT_CONFLICT", str(caught.exception))
        self.assertIsInstance(caught.exception, ProjectContextRequired)  # existing handlers print it

    def test_inherited_launcher_variables_bind_nothing(self):
        env = launcher_env(self.a, SKM_LAUNCHER_PID=str(os.getpid() + 1))
        context = resolve_project(self.b, explicit=str(self.b), env=env)
        self.assertEqual((context.root, context.resolution), (self.b, "flag"))

    def test_legacy_order_without_launcher(self):
        env = {"SKM_PROJECT_ROOT": str(self.b), "HOME": "/nonexistent-home"}
        self.assertEqual(resolve_project(self.a, explicit=str(self.a), env=env).resolution, "flag")
        self.assertEqual(resolve_project(self.a, env=env).root, self.b)
        self.assertEqual(resolve_project(self.a / ".swissknifeman", env={"HOME": "/x"}).root, self.a)

    def test_find_project_root_never_raises_on_a_stale_launcher_root(self):
        env = launcher_env(self.base / "gone")
        self.assertEqual(find_project_root(self.a, env=env), self.a)

    def test_read_invocation_context_keeps_cwd_apart(self):
        nested = self.a / "src"
        nested.mkdir()
        context = read_invocation_context(nested, env=launcher_env(self.a, cwd=nested))
        self.assertEqual((context.project_root, context.invocation_cwd, context.resolution),
                         (self.a, nested, "launcher"))
        self.assertEqual(context.to_json()["plans_root"], str(self.a / "plans"))
        none = read_invocation_context(self.base, env={"HOME": str(self.base)})
        self.assertEqual((none.project_root, none.resolution), (None, "none"))


class ValidateLauncherEnvTests(Base):
    def test_valid_context_is_normalised(self):
        context, env, warnings = validate_launcher_env(launcher_env(self.a, SKM_PROJECT_ROOT=str(self.a)))
        self.assertEqual(context.project_root, self.a)
        self.assertEqual(warnings, [])
        self.assertNotIn("SKM_PROJECT_ROOT", env)

    def test_without_launcher_nothing_changes(self):
        context, env, _ = validate_launcher_env({"PATH": "/bin"})
        self.assertIsNone(context)
        self.assertEqual(env, {"PATH": "/bin"})

    def test_inherited_variables_are_dropped(self):
        context, env, _ = validate_launcher_env(launcher_env(self.a, SKM_LAUNCHER_PID="1"))
        self.assertIsNone(context)
        self.assertFalse(any(key.startswith("SKM_LAUNCHER_") for key in env))

    def assertCode(self, env, code):
        with self.assertRaises(LauncherError) as caught:
            validate_launcher_env(env)
        self.assertEqual(caught.exception.code, code)

    def test_refusals(self):
        self.assertCode(launcher_env(self.a, SKM_LAUNCHER_PROTOCOL=""), "LAUNCHER_PROTOCOL_INVALID")
        self.assertCode(launcher_env(self.a, SKM_LAUNCHER_PROTOCOL="x1"), "LAUNCHER_PROTOCOL_INVALID")
        self.assertCode(launcher_env(self.a, SKM_LAUNCHER_PROTOCOL="0"), "LAUNCHER_PROTOCOL_TOO_OLD")
        self.assertCode(launcher_env(self.a, SKM_LAUNCHER_PROTOCOL=str(LAUNCHER_PROTOCOL + 1)),
                        "LAUNCHER_PROTOCOL_NEWER")
        self.assertCode(launcher_env(self.a, SKM_LAUNCHER_PROJECT_ROOT="relative"), "PROJECT_PATH_INVALID")
        self.assertCode(launcher_env(self.a, SKM_LAUNCHER_PATH=str(self.b / ".swissknifeman" / "launcher.py")),
                        "LAUNCHER_LOCATION_INVALID")
        self.assertCode(launcher_env(self.a, SKM_PROJECT_ROOT=str(self.b)), "PROJECT_CONTEXT_CONFLICT")
        self.assertCode(launcher_env(self.a, SKM_INVOCATION_CWD=str(self.base / "gone")), "PROJECT_PATH_INVALID")

    def test_symlinked_launcher_is_refused(self):
        target = self.a / ".swissknifeman" / "launcher.py"
        real = self.base / "real-launcher.py"
        target.rename(real)
        target.symlink_to(real)
        self.assertCode(launcher_env(self.a), "LAUNCHER_SYMLINK_FORBIDDEN")

    def test_symlinked_project_folder_is_refused(self):
        link = self.base / "link"
        link.symlink_to(self.a)
        env = launcher_env(self.a, SKM_LAUNCHER_PATH=str(link / ".swissknifeman" / "launcher.py"))
        self.assertCode(env, "LAUNCHER_LOCATION_INVALID")

    def test_missing_lock_warns_or_refuses_in_strict_mode(self):
        root = make_project(self.base, "C", lock=False)
        _context, _env, warnings = validate_launcher_env(launcher_env(root))
        self.assertTrue(warnings[0].startswith("LAUNCHER_LOCK_MISSING"))
        self.assertCode(launcher_env(root, SKM_LAUNCHER_STRICT="1"), "LAUNCHER_LOCK_MISSING")

    def test_lock_protocol_must_match(self):
        lock = self.a / ".swissknifeman" / "launcher.lock.json"
        doc = json.loads(lock.read_text())
        doc["protocol"] = LAUNCHER_PROTOCOL + 1
        lock.write_text(json.dumps(doc))
        self.assertCode(launcher_env(self.a), "LAUNCHER_PROTOCOL_NEWER")
        lock.write_text("{")
        self.assertCode(launcher_env(self.a), "LAUNCHER_LOCK_INVALID")


class RequireProjectPathTests(Base):
    def test_paths_inside_pass(self):
        self.assertEqual(require_project_path(self.a, "plans/x.json"), self.a / "plans" / "x.json")
        self.assertEqual(require_project_path(self.a, self.a / "new" / "deep" / "f"), self.a / "new" / "deep" / "f")

    def test_outside_paths_are_refused(self):
        for candidate in ("../B/x", str(self.b / "x"), "/etc/passwd"):
            with self.subTest(candidate=candidate), self.assertRaises(ProjectWriteError) as caught:
                require_project_path(self.a, candidate)
            self.assertEqual(caught.exception.code, "PROJECT_WRITE_OUTSIDE_ROOT")

    def test_prefix_sibling_is_outside(self):
        sibling = make_project(self.base, "A2")
        with self.assertRaises(ProjectWriteError):
            require_project_path(self.a, sibling / "f")

    def test_symlink_escapes_are_refused(self):
        (self.a / "out-file").symlink_to(self.b / "f")
        (self.a / "out-dir").symlink_to(self.b)
        for candidate in ("out-file", "out-dir/f", "out-dir/new/child"):
            with self.subTest(candidate=candidate), self.assertRaises(ProjectWriteError) as caught:
                require_project_path(self.a, candidate)
            self.assertEqual(caught.exception.code, "PROJECT_WRITE_SYMLINK_ESCAPE")


if __name__ == "__main__":
    unittest.main()
