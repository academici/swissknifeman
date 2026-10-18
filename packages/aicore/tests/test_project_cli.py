"""``aicore project``: init, sync, verify, context, doctor of the project-local launcher (no hub on PATH needed)."""
import io
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.project import artifacts, cli
from aicore.util.io import durable_replace

LOCK = ".swissknifeman/launcher.lock.json"
LAUNCHER = ".swissknifeman/launcher.py"


def run(cwd, *argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), env=env if env is not None else {"HOME": "/nonexistent-home", "PATH": ""}, cwd=cwd,
                    out=out, err=err)
    return code, out.getvalue(), err.getvalue()


class ProjectCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve() / "proj"
        (self.root / ".git").mkdir(parents=True)
        (self.root / "src").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def actions(self, output):
        return {item["path"]: item["action"] for item in json.loads(output)["actions"]}

    def test_init_from_a_nested_folder_writes_launcher_and_lock_at_the_root(self):
        code, out, err = run(self.root / "src", "init", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.actions(out), {LAUNCHER: "create", LOCK: "create"})
        launcher = self.root / LAUNCHER
        self.assertEqual(launcher.read_bytes(), artifacts.template_bytes())
        self.assertTrue(os.access(launcher, os.X_OK))
        lock = json.loads((self.root / LOCK).read_text())
        self.assertEqual(lock["template_sha256"], artifacts.sha256(artifacts.template_bytes()))
        self.assertNotIn(str(self.root), (self.root / LOCK).read_text())  # nothing machine-specific
        self.assertFalse((self.root / ".swissknifeman" / artifacts.SYNC_LOCK).exists())

    def test_repeated_sync_is_a_no_op(self):
        run(self.root, "init")
        before = (self.root / LOCK).stat().st_mtime_ns
        code, out, _ = run(self.root, "sync", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(self.actions(out), {LAUNCHER: "unchanged", LOCK: "unchanged"})
        self.assertEqual((self.root / LOCK).stat().st_mtime_ns, before)

    def test_dry_run_changes_nothing(self):
        code, out, _ = run(self.root, "init", "--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(self.actions(out), {LAUNCHER: "create", LOCK: "create"})
        self.assertFalse((self.root / ".swissknifeman").exists())

    def test_init_outside_git_needs_marker_only(self):
        plain = Path(self._tmp.name).resolve() / "plain"
        plain.mkdir()
        code, _, err = run(plain, "init", env={"HOME": str(plain.parent), "PATH": ""})
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_CONTEXT_REQUIRED", err)
        code, _, err = run(plain, "init", "--marker-only", env={"HOME": str(plain.parent), "PATH": ""})
        self.assertEqual(code, 0, err)
        self.assertTrue((plain / LAUNCHER).is_file())

    def test_foreign_launcher_is_kept_without_adopt(self):
        (self.root / ".swissknifeman").mkdir()
        (self.root / LAUNCHER).write_text("print('mine')\n")
        code, _, err = run(self.root, "init")
        self.assertEqual(code, 1)
        self.assertIn("FOREIGN_LAUNCHER", err)
        self.assertEqual((self.root / LAUNCHER).read_text(), "print('mine')\n")
        self.assertFalse((self.root / LOCK).exists())
        code, out, err = run(self.root, "init", "--adopt", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.root / LAUNCHER).read_bytes(), artifacts.template_bytes())
        backups = list((self.root / ".swissknifeman" / "backups").rglob("launcher.py"))
        self.assertEqual([path.read_text() for path in backups], ["print('mine')\n"])

    def test_an_older_launcher_of_the_lock_is_updated(self):
        run(self.root, "init")
        old = b"# older template\n"
        (self.root / LAUNCHER).write_bytes(old)
        lock = json.loads((self.root / LOCK).read_text())
        lock["template_sha256"] = artifacts.sha256(old)
        (self.root / LOCK).write_text(json.dumps(lock))
        code, out, _ = run(self.root, "sync", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(self.actions(out), {LAUNCHER: "update", LOCK: "update"})
        self.assertEqual((self.root / LAUNCHER).read_bytes(), artifacts.template_bytes())

    def test_symlinked_launcher_is_refused(self):
        (self.root / ".swissknifeman").mkdir()
        (self.root / LAUNCHER).symlink_to(artifacts.TEMPLATE)
        code, _, err = run(self.root, "init", "--adopt")
        self.assertEqual(code, 1)
        self.assertIn("LAUNCHER_SYMLINK_FORBIDDEN", err)

    def test_sync_needs_an_initialised_project(self):
        code, _, err = run(self.root, "sync")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_NOT_INITIALIZED", err)

    def test_concurrent_sync_is_refused_and_a_dead_owner_is_taken_over(self):
        run(self.root, "init")
        (self.root / LAUNCHER).write_text("# drift\n")
        held = self.root / ".swissknifeman" / artifacts.SYNC_LOCK
        held.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "started": 0, "operation": "x"}))
        code, _, err = run(self.root, "sync", "--adopt")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_SYNC_LOCKED", err)
        held.write_text(json.dumps({"pid": 2 ** 22 + 12345, "host": socket.gethostname(), "started": 0,
                                    "operation": "x"}))
        code, _, err = run(self.root, "sync", "--adopt")
        self.assertEqual(code, 0, err)
        self.assertFalse(held.exists())

    def test_verify_without_roundtrip(self):
        run(self.root, "init")
        code, out, _ = run(self.root, "verify", "--json", "--no-roundtrip")
        checks = {item["check_id"]: item["status"] for item in json.loads(out)}
        self.assertEqual(checks["project.launcher"], "ok")
        self.assertEqual(checks["project.lock"], "ok")
        self.assertEqual(checks["project.digest"], "ok")
        self.assertEqual(checks["project.hub"], "fail")  # PATH is empty here
        self.assertEqual(code, 1)
        (self.root / LAUNCHER).write_text("# edited\n")
        _code, out, _ = run(self.root, "verify", "--json", "--no-roundtrip")
        checks = {item["check_id"]: item for item in json.loads(out)}
        self.assertIn("LAUNCHER_DIGEST_MISMATCH", checks["project.digest"]["observed"])

    def test_doctor_reports_config_and_write_boundary(self):
        run(self.root, "init")
        (self.root / ".swissknifeman" / "config.toml").write_text("schema_version = 99\n")
        outside = Path(self._tmp.name).resolve() / "outside"
        outside.mkdir()
        (self.root / "plans").symlink_to(outside)
        _code, out, _ = run(self.root, "doctor", "--json")
        checks = {item["check_id"]: item["status"] for item in json.loads(out)}
        self.assertEqual(checks["project.config"], "fail")
        self.assertEqual(checks["project.write-boundary"], "fail")

    def test_doctor_follows_the_marker_to_the_local_folder(self):
        from aicore.workspace import write_marker
        run(self.root, "init")
        ws = Path(self._tmp.name).resolve() / "wss" / "axioma"
        env = {"HOME": "/nonexistent-home", "PATH": "", "SKM_WORKSPACES_ROOT": str(ws.parent)}
        write_marker(self.root, "axioma", "demo", "workspace")
        local = ws / "projects" / "demo" / "local"
        local.mkdir(parents=True)
        (self.root / ".swissknifeman" / "config.toml").write_text("schema_version = 99\n")

        def checks():
            _code, out, _ = run(self.root, "doctor", "--json", env=env)
            return {item["check_id"]: item for item in json.loads(out)}

        found = checks()
        self.assertEqual(found["project.config"]["status"], "skip")
        self.assertIn(str(local / "config.toml"), found["project.config"]["observed"])
        self.assertEqual(found["project.write-boundary"]["status"], "ok")
        (local / "config.toml").write_text("schema_version = 99\n")
        self.assertEqual(checks()["project.config"]["status"], "fail")
        outside = Path(self._tmp.name).resolve() / "outside"
        outside.mkdir()
        (local / "state").symlink_to(outside)
        found = checks()
        self.assertEqual(found["project.write-boundary"]["status"], "fail")
        self.assertIn("local/state", found["project.write-boundary"]["observed"])

    def test_context_names_the_project_layer_file(self):
        from aicore.workspace import write_marker
        ws = Path(self._tmp.name).resolve() / "wss" / "axioma"
        env = {"HOME": "/nonexistent-home", "PATH": "", "SKM_WORKSPACES_ROOT": str(ws.parent)}
        run(self.root, "init")
        write_marker(self.root, "axioma", "demo", "workspace")
        (ws / "projects" / "demo" / "plans").mkdir(parents=True)
        _code, out, _ = run(self.root, "context", "--json", env=env)
        self.assertEqual(json.loads(out)["config"], str(ws / "projects" / "demo" / "local" / "config.toml"))

    def test_doctor_checks_the_plans_store(self):
        from aicore.workspace import write_marker
        run(self.root, "init")
        ws = Path(self._tmp.name).resolve() / "wss" / "axioma"
        env = {"HOME": "/nonexistent-home", "PATH": "", "SKM_WORKSPACES_ROOT": str(ws.parent), "SKM_WORKSPACE": "axioma"}

        def statuses():
            _code, out, _ = run(self.root, "doctor", "--json", env=env)
            return {item["check_id"]: item["status"] for item in json.loads(out)}

        self.assertEqual(statuses()["project.plans-store"], "ok")
        project_id = "demo"
        write_marker(self.root, "axioma", project_id, "workspace")
        self.assertEqual(statuses()["project.plans-store"], "fail")
        (ws / "projects" / project_id / "plans").mkdir(parents=True)
        found = statuses()
        self.assertEqual(found["project.plans-store"], "ok")
        self.assertEqual(found["project.write-boundary"], "ok")

    def test_context_reports_the_plans_store(self):
        from aicore.workspace import write_marker
        ws = Path(self._tmp.name).resolve() / "wss" / "axioma"
        env = {"HOME": "/nonexistent-home", "PATH": "", "SKM_WORKSPACES_ROOT": str(ws.parent), "SKM_WORKSPACE": "axioma"}

        def context():
            return json.loads(run(self.root, "context", "--json", env=env)[1])

        doc = context()
        self.assertEqual(doc["plans_root"], str(self.root / "plans"))
        self.assertEqual(doc["plans_store"], {"kind": "legacy", "project_id": None, "reason": "no-marker",
                                              "workspace": None})
        project_id = "demo"
        write_marker(self.root, "axioma", project_id, "workspace")
        doc = context()
        self.assertEqual((doc["plans_root"], doc["plans_store"]["kind"], doc["plans_store"]["error"]),
                         (str(self.root / "plans"), "unresolved", "WORKSPACE_PROJECT_MISSING"))
        (ws / "projects" / project_id / "plans").mkdir(parents=True)
        doc = context()
        self.assertEqual(doc["plans_root"], str(ws / "projects" / project_id / "plans"))
        self.assertEqual(doc["plans_store"], {"kind": "workspace", "project_id": project_id,
                                              "reason": "marker-workspace",
                                              "workspace": "axioma"})

    def test_context_without_launcher(self):
        code, out, _ = run(self.root / "src", "context", "--json")
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual((doc["project_root"], doc["resolution"], doc["launcher"]), (str(self.root), "git", None))
        self.assertEqual(doc["invocation_cwd"], str(self.root / "src"))

    def test_usage_errors(self):
        self.assertEqual(run(self.root, "nope")[0], 2)
        self.assertEqual(run(self.root, "init", "--bogus")[0], 2)
        self.assertEqual(run(self.root, "exec")[0], 2)


class DurableReplaceTests(unittest.TestCase):
    def test_a_failed_write_keeps_the_old_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "f"
            target.write_bytes(b"old")
            with mock.patch("os.replace", side_effect=OSError("boom")), self.assertRaises(OSError):
                durable_replace(target, b"new")
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(sorted(path.name for path in Path(tmp).iterdir()), ["f"])
            durable_replace(target, b"new", mode=0o644)
            self.assertEqual(target.read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
