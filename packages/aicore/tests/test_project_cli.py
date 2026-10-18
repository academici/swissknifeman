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

    def _linked_project(self):
        from aicore.workspace import write_marker
        run(self.root, "init")
        ws = Path(self._tmp.name).resolve() / "wss" / "axioma"
        env = {"HOME": "/nonexistent-home", "PATH": "", "SKM_WORKSPACES_ROOT": str(ws.parent), "SKM_WORKSPACE": "axioma"}
        write_marker(self.root, "axioma", "demo", "workspace")
        for name in ("plans", "tasks"):
            (ws / "projects" / "demo" / name).mkdir(parents=True)

        def found():
            _code, out, _ = run(self.root, "doctor", "--json", env=env)
            return {item["check_id"]: item for item in json.loads(out)}

        return ws, found

    def test_doctor_checks_the_optional_links(self):
        import subprocess
        from aicore.workspace.links import write_exclude
        ws, found = self._linked_project()
        self.assertEqual(found()["project.links"]["status"], "skip")
        for name in ("plans", "tasks"):
            (self.root / name).symlink_to(ws / "projects" / "demo" / name)
        self.assertEqual(found()["project.links"]["status"], "ok")  # not a git repository: no exclude file to compare
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        warned = found()["project.links"]
        self.assertEqual(warned["status"], "warn")
        self.assertIn("plans/ is not listed in .git/info/exclude", warned["observed"])
        write_exclude(self.root, ["plans", "tasks"])
        self.assertEqual(found()["project.links"]["status"], "ok")
        self.assertEqual(found()["project.write-boundary"]["status"], "ok")
        (self.root / "tasks").unlink()
        outside = Path(self._tmp.name).resolve() / "outside"
        outside.mkdir()
        (self.root / "tasks").symlink_to(outside)
        warned = found()["project.links"]
        self.assertEqual(warned["status"], "warn")
        self.assertIn("tasks/ is a link to", warned["observed"])
        self.assertIn("left alone", warned["observed"])

    def test_doctor_reports_a_link_to_a_missing_workspace_folder(self):
        ws, found = self._linked_project()
        (self.root / "tasks").symlink_to(ws / "projects" / "demo" / "tasks")
        (ws / "projects" / "demo" / "tasks").rmdir()
        warned = found()["project.links"]
        self.assertEqual(warned["status"], "warn")
        self.assertIn("does not exist", warned["observed"])

    def test_the_write_boundary_lets_a_legacy_store_link_into_the_workspace_pass(self):
        from aicore.workspace import write_marker
        ws, found = self._linked_project()
        write_marker(self.root, "axioma", "demo", "legacy")
        (self.root / "plans").symlink_to(ws / "projects" / "demo" / "plans")
        self.assertEqual(found()["project.write-boundary"]["status"], "ok")
        (self.root / "plans").unlink()
        outside = Path(self._tmp.name).resolve() / "outside"
        outside.mkdir()
        (self.root / "plans").symlink_to(outside)
        self.assertEqual(found()["project.write-boundary"]["status"], "fail")

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


class LauncherOnlyTests(unittest.TestCase):
    """PLAN7 P3.3: the checkout holds the launcher and the marker; the project layer lives in ``local/`` of the workspace."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.root = base / "proj"
        (self.root / ".git").mkdir(parents=True)
        self.ws = base / "wss" / "axioma"
        self.env = {"HOME": "/nonexistent-home", "PATH": "", "SKM_WORKSPACES_ROOT": str(self.ws.parent)}
        self.checkout = self.root / ".swissknifeman"
        self.local = self.ws / "projects" / "demo" / "local"

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *argv, cwd=None):
        return run(cwd or self.root, *argv, env=self.env)

    def attach_project(self):
        (self.ws / "projects" / "demo").mkdir(parents=True)

    def fill_checkout(self):
        self.checkout.mkdir(exist_ok=True)
        (self.checkout / "config.toml").write_text("schema_version = 1\n")
        (self.checkout / "state" / "orch").mkdir(parents=True)
        (self.checkout / "state" / "orch" / "journal.ndjson").write_text("{}\n")
        (self.checkout / "backups" / "2026").mkdir(parents=True)
        (self.checkout / "backups" / "2026" / "launcher.py").write_text("old\n")
        (self.checkout / "stubs").mkdir()
        (self.checkout / "stubs" / "tool").write_text("stub\n")

    def test_init_writes_only_the_launcher_its_lock_and_the_marker(self):
        code, out, err = self.run_cli("init", "--project", "demo", "--workspace", "axioma", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["actions"][-1], {"path": ".swissknifeman/project.json", "action": "create"})
        self.assertEqual(sorted(path.name for path in self.checkout.iterdir()),
                         ["launcher.lock.json", "launcher.py", "project.json"])
        self.assertEqual(json.loads((self.checkout / "project.json").read_text()),
                         {"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": "axioma",
                          "project_id": "demo", "plans_store": "workspace"})
        code, out, _ = self.run_cli("init", "--project=demo", "--workspace=axioma", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(set(item["action"] for item in json.loads(out)["actions"]), {"unchanged"})

    def test_init_without_a_project_writes_no_marker(self):
        self.assertEqual(self.run_cli("init")[0], 0)
        self.assertFalse((self.checkout / "project.json").exists())

    def test_init_takes_the_selected_workspace_and_the_legacy_store_of_a_checkout_with_plans(self):
        (self.ws).mkdir(parents=True)
        (self.ws / "workspace.json").write_text("{}")
        (self.root / "plans" / "2026.01.01-one").mkdir(parents=True)
        code, _, err = self.run_cli("init", "--project", "demo")
        self.assertEqual(code, 0, err)
        marker = json.loads((self.checkout / "project.json").read_text())
        self.assertEqual((marker["workspace"], marker["plans_store"]), ("axioma", "legacy"))

    def test_init_keeps_a_marker_with_other_values_and_writes_nothing(self):
        self.assertEqual(self.run_cli("init", "--project", "demo", "--workspace", "axioma")[0], 0)
        before = (self.checkout / "project.json").read_text()
        (self.checkout / "launcher.py").unlink()
        code, _, err = self.run_cli("init", "--project", "other", "--workspace", "axioma")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_MARKER_CONFLICT", err)
        self.assertEqual((self.checkout / "project.json").read_text(), before)
        self.assertFalse((self.checkout / "launcher.py").exists())

    def test_init_dry_run_with_a_project_writes_nothing(self):
        code, out, _ = self.run_cli("init", "--project", "demo", "--workspace", "axioma", "--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(self.actions(out)[".swissknifeman/project.json"], "create")
        self.assertFalse(self.checkout.exists())

    def actions(self, output):
        return {item["path"]: item["action"] for item in json.loads(output)["actions"]}

    def test_init_options_are_checked(self):
        self.assertEqual(self.run_cli("init", "--workspace", "axioma")[0], 2)
        self.assertEqual(self.run_cli("init", "--project", "Bad Code")[0], 2)
        self.assertEqual(self.run_cli("init", "--project")[0], 2)
        self.assertEqual(self.run_cli("init", "--project", "demo", "--workspace", "axioma", "--plans-store", "x")[0], 2)
        code, _, err = self.run_cli("init", "--project", "demo")
        self.assertEqual(code, 1)
        self.assertIn("WORKSPACE_NOT_FOUND", err)
        self.assertFalse(self.checkout.exists())

    def test_migrate_moves_the_project_layer_into_local(self):
        self.run_cli("init", "--project", "demo", "--workspace", "axioma")
        self.attach_project()
        self.fill_checkout()
        code, out, err = self.run_cli("migrate", "--json")
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertTrue(doc["applied"])
        self.assertEqual(doc["remaining"], [])
        self.assertEqual(sorted(item["action"] for item in doc["items"]), ["move"] * 4)
        self.assertEqual((self.local / "config.toml").read_text(), "schema_version = 1\n")
        self.assertEqual((self.local / "config.toml").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.local / "state" / "orch" / "journal.ndjson").read_text(), "{}\n")
        self.assertEqual((self.local / "backups" / "2026" / "launcher.py").read_text(), "old\n")
        self.assertEqual((self.local / "stubs" / "tool").read_text(), "stub\n")
        self.assertEqual(sorted(path.name for path in self.checkout.iterdir()),
                         ["launcher.lock.json", "launcher.py", "project.json"])
        code, out, _ = self.run_cli("migrate", "--json")
        self.assertEqual((code, json.loads(out)["items"]), (0, []))

    def test_migrate_dry_run_changes_nothing(self):
        self.run_cli("init", "--project", "demo", "--workspace", "axioma")
        self.attach_project()
        self.fill_checkout()
        code, out, _ = self.run_cli("migrate", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("would move .swissknifeman/config.toml", out)
        self.assertTrue((self.checkout / "config.toml").is_file())
        self.assertFalse(self.local.exists())

    def test_migrate_never_overwrites_a_different_file(self):
        self.run_cli("init", "--project", "demo", "--workspace", "axioma")
        self.attach_project()
        self.fill_checkout()
        (self.local / "state" / "orch").mkdir(parents=True)
        (self.local / "state" / "orch" / "journal.ndjson").write_text("{}\n")  # the same bytes: dropped
        (self.local / "config.toml").write_text("schema_version = 1\n[x]\ny = 1\n")  # other bytes: a conflict
        code, out, err = self.run_cli("migrate", "--json")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_MIGRATE_CONFLICT", err)
        by_path = {item["path"]: item["action"] for item in json.loads(out)["items"]}
        self.assertEqual(by_path["config.toml"], "conflict")
        self.assertEqual(by_path["state/orch/journal.ndjson"], "drop")
        self.assertEqual((self.checkout / "config.toml").read_text(), "schema_version = 1\n")
        self.assertEqual((self.local / "config.toml").read_text(), "schema_version = 1\n[x]\ny = 1\n")
        self.assertFalse((self.checkout / "state").exists())
        self.assertEqual((self.local / "stubs" / "tool").read_text(), "stub\n")

    def test_migrate_refuses_a_symbolic_link(self):
        self.run_cli("init", "--project", "demo", "--workspace", "axioma")
        self.attach_project()
        outside = Path(self._tmp.name).resolve() / "outside"
        outside.mkdir()
        (self.checkout / "state").symlink_to(outside)
        code, _, err = self.run_cli("migrate")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_MIGRATE_SYMLINK", err)
        self.assertTrue((self.checkout / "state").is_symlink())

    def test_migrate_needs_the_project_folder_of_the_workspace(self):
        code, _, err = self.run_cli("migrate")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_LOCAL_UNAVAILABLE", err)
        self.run_cli("init", "--project", "demo", "--workspace", "axioma")
        self.fill_checkout()
        code, _, err = self.run_cli("migrate", "--json")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_LOCAL_UNAVAILABLE", err)
        self.assertTrue((self.checkout / "config.toml").is_file())

    def test_doctor_checks_the_local_folder_and_the_leftovers(self):
        def checks():
            _code, out, _ = self.run_cli("doctor", "--json")
            return {item["check_id"]: item for item in json.loads(out)}

        self.run_cli("init")
        self.assertEqual(checks()["project.local"]["status"], "skip")
        self.run_cli("init", "--project", "demo", "--workspace", "axioma")
        found = checks()
        self.assertEqual(found["project.local"]["status"], "warn")
        self.assertNotIn("project.checkout-layer", found)
        self.attach_project()
        self.fill_checkout()
        found = checks()
        self.assertEqual(found["project.local"]["status"], "ok")
        self.assertEqual(found["project.checkout-layer"]["status"], "warn")
        self.assertIn("project migrate", found["project.checkout-layer"]["remediation"])
        self.assertIn("state", found["project.checkout-layer"]["observed"])
        self.run_cli("migrate")
        self.assertEqual(checks()["project.checkout-layer"]["status"], "ok")

    def test_doctor_reads_repo_path_and_the_contract_of_the_local_config(self):
        from aicore.workspace import set_repo_path

        def local():
            _code, out, _ = self.run_cli("doctor", "--json")
            return {item["check_id"]: item for item in json.loads(out)}["project.local"]

        self.run_cli("init", "--project", "demo", "--workspace", "axioma")
        self.attach_project()
        set_repo_path(self.ws, "demo", self.root)
        self.assertEqual(local()["status"], "ok")
        other = Path(self._tmp.name).resolve() / "other"
        other.mkdir()
        set_repo_path(self.ws, "demo", other)
        self.assertEqual(local()["status"], "warn")
        (self.local / "config.toml").write_text("not = toml = at all\n")
        self.assertEqual(local()["status"], "fail")


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
