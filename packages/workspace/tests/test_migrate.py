"""workspace migrate: discover, plan (writes nothing), apply through the plans-migrator port, verify, rollback, cleanup.

The tests run the real bridge ``workspace-planner`` as the plugin of the port (registered in the machine config of a
throwaway ``SKM_HOME``) on plans copied from the demo plan of the planner; they are skipped when the hub does not have the
bridge or the planner next to this module. Nothing here touches the real HOME, workspace or plans.
"""
import fcntl
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from aicore.workspace import read_bindings, read_marker, validate_document, write_marker

from tests import BRIDGE_ROOT, HUB_ROOT, MODULE_ROOT, TempCase, git
from workspace import gitutil, migrate, migrator_port

PLANNER_ROOT = Path(os.environ.get("PLANNER_ROOT") or HUB_ROOT / "packages" / "planner")
DEMO = PLANNER_ROOT / "tests" / "engine" / "fixtures" / "demo-plan"
AICORE_ROOT = HUB_ROOT / "packages" / "aicore"
PLAN = "2026.10.05-№7-DEMO"
ARCHIVED = "archive/2026.09.01-№3-DEMO"
NEW_PLAN = "2026.10.08-№9-DEMO"
BIG = "old-thing/artifacts/big.bin"
SECRET = "SECRET-VALUE-MUST-NOT-APPEAR"


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_plan(plans: Path, name: str, running: bool = False, extra: str = "") -> Path:
    """A copy of the demo plan of the planner; its item in progress is put back to ``todo`` unless ``running``."""
    target = plans / name
    shutil.copytree(DEMO, target)
    if not running:
        item = target / "phases" / "P2" / "P2.1.json"
        item.write_text(item.read_text(encoding="utf-8").replace('"status": "in_progress"', '"status": "todo"', 1),
                        encoding="utf-8")
    put(target / "artifacts" / "notes.txt", "see /home/someone/project/file\n")
    if extra:
        put(target / "artifacts" / "extra.txt", extra)
    return target


def snapshot(*roots: Path) -> dict:
    found = {}
    for root in roots:
        for current, dirs, files in os.walk(root):
            for name in dirs + files:
                path = os.path.join(current, name)
                info = os.lstat(path)
                found[path] = (info.st_size, info.st_mtime_ns)
    return found


@unittest.skipUnless(BRIDGE_ROOT.is_dir() and DEMO.is_dir(), "the bridge workspace-planner and the planner are not in the hub")
class MigrateCase(TempCase):
    """A workspace, the bridge registered as the migrator plugin, and a checkout with plans of every class."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"PLANNER_ROOT": str(PLANNER_ROOT), "AICORE_ROOT": str(AICORE_ROOT)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.register(True)
        self.assertEqual(self.run_cli("init")[0], 0)

    def register(self, enabled: bool) -> None:
        config = self.root / "skm" / "config" / "config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        text = "schema_version = 1\n"
        if enabled:
            text += (f'\n[aicore.plugins.workspace-planner]\nmanifest = "{BRIDGE_ROOT / "extension.json"}"\n'
                     "trusted = true\n")
        config.write_text(text, encoding="utf-8")

    def build(self, name: str = "alpha", plans: tuple = (PLAN, ARCHIVED), extra: str = "") -> Path:
        """A checkout with v4 plans, an opaque legacy folder with a 6 MiB file, an artifacts-only folder, a nested legacy
        folder under ``plans/archive`` and a loose file; derived files of the plan are there too."""
        root = self.checkout(name, remotes=[("origin", f"https://example.org/team/{name}.git")])
        folder = root / "plans"
        for plan in plans:
            make_plan(folder, plan, extra=extra)
        live = folder / plans[0]
        for derived in ("views/roadmap.md", "context/P1.1.json", ".lock"):
            put(live / derived, "derived\n")
        put(folder / "only-artifacts" / "artifacts" / "a.txt", "a\n")
        put(folder / "archive" / "old-legacy" / "notes.txt", "n\n")
        put(folder / "old-thing" / "notes.txt", "legacy\n")
        big = folder / BIG
        big.parent.mkdir(parents=True, exist_ok=True)
        big.write_bytes(b"\0" * (6 * 1024 * 1024))
        put(folder / "README.md", "top level\n")
        return root

    def apply(self, root: Path, *args: str) -> dict:
        return self.json_cli("migrate", "apply", "--project", str(root), "--yes", *args)

    def failing(self, *args: str) -> str:
        code, out, err = self.run_cli(*args)
        self.assertEqual(code, 1, out + err)
        return err

    def project_dir(self, project_id: str) -> Path:
        return self.ws / "projects" / project_id

    def reports(self, project_id: str) -> list:
        folder = self.project_dir(project_id) / "migrations"
        return sorted(folder.glob("*.json")) if folder.is_dir() else []

    def events(self) -> list:
        journal = self.root / "skm" / "state" / "events" / "events.jsonl"
        if not journal.is_file():
            return []
        return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]

    def commit(self, root: Path) -> None:
        git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")


class DiscoverTests(MigrateCase):
    def launcher(self, base: Path, name: str, plans: bool = True) -> Path:
        root = base / name
        put(root / ".swissknifeman" / "launcher.py", "")
        if plans:
            put(root / "plans" / "p1" / "plan.json", "{}")
            put(root / "plans" / "legacy" / "x.txt", "xx")
        return root

    def test_launcher_projects_and_registry_paths_are_candidates(self):
        base = self.root / "projects"
        first = self.launcher(base, "first")
        self.launcher(base, "no-plans", plans=False)
        put(base / "node_modules" / "dep" / ".swissknifeman" / "launcher.py", "")
        other = self.root / "elsewhere" / "second"
        put(other / "plans" / "legacy" / "y.txt", "yyy")
        registry = self.root / "skm" / "state" / "maind" / "registry.json"
        put(registry, json.dumps({"projects": [{"id": "x", "repo": "r", "local_path": str(other)},
                                               {"id": "y", "local_path": str(self.root / "gone")}, "junk"]}))
        doc = self.json_cli("migrate", "discover", str(base))
        rows = {row["path"]: row for row in doc["candidates"]}
        self.assertEqual(sorted(rows), sorted([str(first), str(other)]))
        self.assertEqual(rows[str(first)]["sources"], ["launcher"])
        self.assertEqual(rows[str(other)]["sources"], ["registry"])
        self.assertEqual({key: rows[str(first)]["plans"][key] for key in ("v4", "legacy", "files", "bytes")},
                         {"v4": 1, "legacy": 1, "files": 2, "bytes": 4})
        self.assertIsNone(rows[str(first)]["marker"])

    def test_the_default_directory_is_projects_under_home_and_markers_are_shown(self):
        root = self.launcher(self.home / "projects", "mine")
        write_marker(root, "prj_" + "0" * 26, "legacy")
        doc = self.json_cli("migrate", "discover")
        self.assertEqual([row["path"] for row in doc["candidates"]], [str(root)])
        self.assertEqual(doc["candidates"][0]["marker"], {"project_id": "prj_" + "0" * 26, "plans_store": "legacy"})

    def test_the_content_of_plan_files_is_never_read(self):
        root = self.launcher(self.root / "projects", "closed")
        locked = put(root / "plans" / "legacy" / "locked.txt", "no access")
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o600)
        with mock.patch("workspace.migrate._sha256", side_effect=AssertionError("hashed")):
            doc = self.json_cli("migrate", "discover", str(self.root / "projects"))
        self.assertEqual(len(doc["candidates"]), 1)

    def test_a_missing_directory_is_reported_and_a_damaged_marker_is_named(self):
        root = self.launcher(self.root / "projects", "broken")
        put(root / ".swissknifeman" / "project.json", "{")
        doc = self.json_cli("migrate", "discover", str(self.root / "projects"), str(self.root / "nowhere"))
        self.assertEqual(doc["candidates"][0]["marker_error"], "PROJECT_MARKER_INVALID")
        self.assertEqual(doc["skipped"][0]["reason"], "missing")


class PlanTests(MigrateCase):
    def test_plan_classifies_without_writing_anything(self):
        root = self.build()
        before = snapshot(self.ws, root, self.root / "skm" / "state", self.home)
        doc = self.json_cli("migrate", "plan", "--project", str(root))
        self.assertEqual(snapshot(self.ws, root, self.root / "skm" / "state", self.home), before)
        self.assertEqual(doc["mode"], "initial")
        self.assertEqual(doc["project"]["origin"], "new")
        self.assertTrue(doc["ready"])
        rows = {row["name"]: row for row in doc["plans"]}
        self.assertEqual({name: (row["class"], row["action"]) for name, row in rows.items()}, {
            PLAN: ("v4", "copied"), ARCHIVED: ("v4", "copied"), "only-artifacts": ("legacy", "copied"),
            "archive/old-legacy": ("legacy", "copied"), "old-thing": ("legacy", "copied"),
            migrate.ROOT_NAME: ("legacy", "copied")})
        self.assertEqual(rows[PLAN]["digest"], migrate.folder_digest(root / "plans" / PLAN, "v4"))
        self.assertEqual(rows["old-thing"]["digest"], migrate.folder_digest(root / "plans" / "old-thing", "legacy"))
        self.assertEqual(rows["old-thing"]["files"], 2)  # derived files of a plan are not part of it
        self.assertEqual([(item["path"], item["reason"]) for item in doc["local_only"]],
                         [(f"legacy-plans/{BIG}", "size")])
        warning = {item["code"]: item for item in doc["warnings"]}
        self.assertEqual(warning["PS_HOME_PATH"]["count"], 2)
        self.assertEqual(warning["PS_HOME_PATH"]["paths"], [f"plans/{PLAN}/artifacts/notes.txt",
                                                            f"plans/{ARCHIVED}/artifacts/notes.txt"])
        self.assertEqual(doc["blockers"], [])

    def test_the_digest_of_a_plan_is_the_same_in_the_checkout_and_the_workspace(self):
        root = self.build()
        plan = self.json_cli("migrate", "plan", "--project", str(root))
        project_id = self.apply(root)["project_id"]
        for row in plan["plans"]:
            kind = "plans" if row["class"] == "v4" else "legacy-plans"
            self.assertEqual(migrate.folder_digest(self.project_dir(project_id) / kind / row["name"], row["class"]),
                             row["digest"], row["name"])

    def test_a_secret_blocks_the_plan_and_is_never_printed(self):
        root = self.build()
        put(root / "plans" / "old-thing" / ".env", f"API_KEY={SECRET}\n")
        code, out, err = self.run_cli("migrate", "plan", "--project", str(root), "--json")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("MIGRATION_BLOCKED_SECRET: "), err)
        doc = json.loads(out)
        blocker = doc["blockers"][0]
        self.assertEqual(blocker["code"], "MIGRATION_BLOCKED_SECRET")
        self.assertEqual([item["path"] for item in blocker["findings"]], ["legacy-plans/old-thing/.env"])
        self.assertNotIn(SECRET, out + err)
        self.assertFalse(doc["ready"])

    def test_a_secret_in_the_text_of_a_file_blocks_too(self):
        root = self.build()
        put(root / "plans" / "old-thing" / "notes.txt", f"password = {SECRET}\n")
        doc = json.loads(self.run_cli("migrate", "plan", "--project", str(root), "--json")[1])
        self.assertEqual(doc["blockers"][0]["code"], "MIGRATION_BLOCKED_SECRET")
        self.assertNotIn(SECRET, json.dumps(doc))

    def test_a_symlink_blocks_the_plan(self):
        root = self.build()
        os.symlink("/etc/hostname", root / "plans" / "old-thing" / "link")
        doc = json.loads(self.run_cli("migrate", "plan", "--project", str(root), "--json")[1])
        self.assertEqual(doc["blockers"][0]["code"], "MIGRATION_BLOCKED_SYMLINK")
        self.assertEqual(doc["blockers"][0]["paths"], ["old-thing/link"])

    def test_an_item_in_progress_blocks_unless_allowed(self):
        root = self.build()
        make_plan(root / "plans", "2026.10.07-№8-DEMO", running=True)
        code, out, err = self.run_cli("migrate", "plan", "--project", str(root), "--json")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("MIGRATION_IN_PROGRESS: "), err)
        self.assertEqual(json.loads(out)["blockers"][0]["items"], ["2026.10.07-№8-DEMO/P2.1"])
        allowed = self.json_cli("migrate", "plan", "--project", str(root), "--allow-in-progress")
        self.assertEqual(allowed["blockers"], [])
        self.assertIn("MIGRATION_IN_PROGRESS", [item["code"] for item in allowed["warnings"]])

    def test_an_invalid_marker_is_a_blocker(self):
        root = self.build()
        put(root / ".swissknifeman" / "project.json", "{")
        code, out, err = self.run_cli("migrate", "plan", "--project", str(root), "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["blockers"][0]["code"], "PROJECT_MARKER_INVALID")

    def test_a_checkout_that_matches_a_project_by_its_remote_needs_a_confirmation(self):
        first = self.build("alpha")
        self.apply(first)
        second = self.build("alpha2")
        git(second, "remote", "set-url", "origin", "https://example.org/team/alpha.git")
        doc = self.json_cli("migrate", "plan", "--project", str(second))
        self.assertEqual(doc["project"]["origin"], "remote-match")
        self.assertTrue(doc["project"]["needs_confirmation"])
        self.assertEqual(doc["mode"], "import")
        err = self.failing("migrate", "apply", "--project", str(second))
        self.assertTrue(err.startswith("ATTACH_CONFIRM_REQUIRED: "), err)

    def test_the_workspace_must_exist(self):
        shutil.rmtree(self.ws)
        err = self.failing("migrate", "plan", "--project", str(self.build()))
        self.assertTrue(err.startswith("WORKSPACE_NOT_INITIALIZED: "), err)

    def test_the_plan_writes_the_same_names_apply_uses(self):
        root = self.build()
        plan = self.json_cli("migrate", "plan", "--project", str(root))
        applied = self.apply(root)
        self.assertEqual({(row["name"], row["action"]) for row in applied["plans"]},
                         {(row["name"], row["action"]) for row in plan["plans"]})

    def test_a_bad_on_conflict_value_is_a_usage_error(self):
        code, _out, err = self.run_cli("migrate", "plan", "--on-conflict", "overwrite")
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class ApplyTests(MigrateCase):
    def test_apply_moves_the_plans_and_writes_report_local_only_binding_and_event(self):
        root = self.build()
        self.commit(root)
        head = git(root, "rev-parse", "HEAD").strip()
        workspace_head = git(self.ws, "rev-parse", "HEAD")
        doc = self.apply(root)
        project_id = doc["project_id"]
        self.assertFalse(doc["noop"])
        self.assertEqual(doc["mode"], "initial")
        folder = self.project_dir(project_id)
        for kind, name in (("plans", PLAN), ("plans", ARCHIVED), ("legacy-plans", "only-artifacts"),
                           ("legacy-plans", "archive/old-legacy"), ("legacy-plans", "old-thing"),
                           ("legacy-plans", "_root")):
            self.assertTrue((folder / kind / name).is_dir(), f"{kind}/{name}")
        self.assertTrue((folder / "legacy-plans" / "_root" / "README.md").is_file())
        self.assertFalse((folder / "plans" / PLAN / "views").exists())  # derived files are not copied
        self.assertTrue((root / "plans" / PLAN / "views").is_dir())  # the source is not touched
        self.assertEqual(read_marker(root), {"$schema": "urn:swissknifeman:aicore:project-marker:v1",
                                             "project_id": project_id, "plans_store": "workspace"})
        self.assertEqual(read_bindings()["projects"][project_id]["paths"], [str(root)])
        self.assertEqual(git(self.ws, "rev-parse", "HEAD"), workspace_head)  # nothing is committed
        self.assertTrue(any("git -C" in line and "project.json" in line for line in doc["next"]))
        # report
        reports = self.reports(project_id)
        self.assertEqual([path.stem for path in reports], [doc["op_id"]])
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(validate_document("workspace-migration", report), [])
        self.assertEqual(report["source"], {"checkout_name": "alpha", "head": head})
        self.assertEqual(report["mode"], "initial")
        self.assertEqual(report["local_only"], 1)
        self.assertEqual(report["warnings"], ["PS_HOME_PATH"])
        self.assertIn("archive%2F2026.09.01-№3-DEMO", [row["name"] for row in report["plans"]])
        self.assertEqual({row["action"] for row in report["plans"]}, {"copied"})
        self.assertNotIn(str(self.root), reports[0].read_text(encoding="utf-8"))
        # local-only index and exclude block
        index = json.loads((folder / "local-only.json").read_text(encoding="utf-8"))
        self.assertEqual([(item["path"], item["reason"], item["bytes"]) for item in index["files"]],
                         [(f"legacy-plans/{BIG}", "size", 6 * 1024 * 1024)])
        self.assertEqual(validate_document("workspace-local-only", index), [])
        exclude = (self.ws / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertIn(f"/projects/{project_id}/legacy-plans/{BIG}", exclude)
        status = git(self.ws, "status", "--porcelain", "--untracked-files=all")
        self.assertNotIn("big.bin", status)
        # events
        types = [event["type"] for event in self.events()]
        self.assertEqual(types, ["workspace.root.initialized", "workspace.project.attached", "workspace.migration.applied"])
        self.assertEqual(self.events()[-1]["data"], {"project_id": project_id, "op_id": doc["op_id"], "mode": "initial",
                                                     "plans": 6, "local_only": 1})

    def test_a_repeat_after_a_full_migration_is_a_noop_without_a_new_report(self):
        root = self.build()
        first = self.apply(root)
        again = self.apply(root)
        self.assertTrue(again["noop"])
        self.assertEqual({row["action"] for row in again["plans"]}, {"skipped-equal"})
        self.assertEqual(len(self.reports(first["project_id"])), 1)
        self.assertEqual([e["type"] for e in self.events()].count("workspace.migration.applied"), 1)

    def test_apply_does_not_commit_anything_in_the_checkout_or_the_workspace(self):
        root = self.build()
        self.commit(root)
        before = git(root, "rev-parse", "HEAD")
        calls = []
        real = gitutil.run

        def spy(argv, cwd, *args, **kwargs):
            calls.append(list(argv))
            return real(argv, cwd, *args, **kwargs)

        with mock.patch("workspace.gitutil.run", side_effect=spy):
            self.apply(root)
        self.assertEqual(git(root, "rev-parse", "HEAD"), before)
        forbidden = {"commit", "add", "push", "reset", "clean", "rm"}
        self.assertFalse([argv for argv in calls if forbidden & set(argv[1:3])], calls)

    def test_a_blocker_refuses_before_the_port_apply_and_writes_nothing(self):
        root = self.build()
        put(root / "plans" / "old-thing" / ".env", f"TOKEN={SECRET}\n")
        ops = []
        real = migrator_port.call

        def spy(op, payload, env=None, home=None):
            ops.append(op)
            return real(op, payload, env, home)

        with mock.patch("workspace.migrator_port.call", side_effect=spy):
            err = self.failing("migrate", "apply", "--project", str(root), "--yes")
        self.assertTrue(err.startswith("MIGRATION_BLOCKED_SECRET: "), err)
        self.assertNotIn(SECRET, err)
        self.assertEqual(ops, ["inspect"])
        self.assertIsNone(read_marker(root))
        self.assertEqual(sorted(path.name for path in (self.ws / "projects").iterdir()), [".gitkeep"])

    def test_an_item_in_progress_is_refused_unless_allowed(self):
        root = self.build(plans=(PLAN,))
        make_plan(root / "plans", "2026.10.07-№8-DEMO", running=True)
        err = self.failing("migrate", "apply", "--project", str(root), "--yes")
        self.assertTrue(err.startswith("MIGRATION_IN_PROGRESS: "), err)
        doc = self.apply(root, "--allow-in-progress")
        report = json.loads(self.reports(doc["project_id"])[0].read_text(encoding="utf-8"))
        self.assertIn("MIGRATION_IN_PROGRESS", report["warnings"])

    def test_a_refusal_of_the_port_is_reported_and_writes_no_report_event_or_index(self):
        root = self.build()
        real = migrator_port.call

        def refuse(op, payload, env=None, home=None):
            if op == "apply":
                return {"result": "refused", "code": "MIGRATION_LOCKED", "message": "plan is held", "phase": "lock",
                        "locked": [PLAN]}
            return real(op, payload, env, home)

        with mock.patch("workspace.migrator_port.call", side_effect=refuse):
            err = self.failing("migrate", "apply", "--project", str(root), "--yes")
        self.assertTrue(err.startswith("MIGRATION_LOCKED: plan is held"), err)
        self.assertIn(PLAN, err)
        project_id = read_marker(root)["project_id"]  # the attach before the port call stays: it is harmless
        self.assertEqual(read_marker(root)["plans_store"], "legacy")
        self.assertEqual(self.reports(project_id), [])
        self.assertFalse((self.project_dir(project_id) / "local-only.json").exists())
        self.assertNotIn("workspace.migration.applied", [event["type"] for event in self.events()])

    def test_a_held_plan_lock_is_migration_locked(self):
        root = self.build(plans=(PLAN,))
        with open(root / "plans" / PLAN / ".lock", "a+") as handle:  # the PlanLock of the planner: flock on <plan>/.lock
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            err = self.failing("migrate", "apply", "--project", str(root), "--yes", "--lock-timeout", "1")
        self.assertTrue(err.startswith("MIGRATION_LOCKED: "), err)
        self.assertEqual(read_marker(root)["plans_store"], "legacy")
        self.assertFalse(list(self.project_dir(read_marker(root)["project_id"]).glob("plans/*")))

    def test_an_existing_marker_and_project_are_used_as_they_are(self):
        root = self.build()
        first = self.json_cli("project", "attach", "--project", str(root))
        doc = self.apply(root)
        self.assertEqual(doc["project_id"], first["project_id"])
        self.assertEqual([e["type"] for e in self.events()].count("workspace.project.attached"), 1)

    def test_without_plans_nothing_is_migrated_and_no_project_is_made(self):
        root = self.checkout("empty")
        doc = self.apply(root)
        self.assertTrue(doc["noop"])
        self.assertEqual(sorted(path.name for path in (self.ws / "projects").iterdir()), [".gitkeep"])

    def test_the_text_output_names_the_next_commands(self):
        root = self.build()
        code, out, _ = self.run_cli("migrate", "apply", "--project", str(root), "--yes")
        self.assertEqual(code, 0)
        self.assertIn("migrated 6 folder(s)", out)
        self.assertIn("next: git -C", out)
        self.assertIn("next: swissknifeman workspace sync", out)


class ImportTests(MigrateCase):
    """The second machine: the workspace already holds the project and the checkout brings its own copies."""

    def second_checkout(self, project_id: str) -> Path:
        root = self.build("beta", plans=(PLAN, ARCHIVED), extra="")
        shutil.rmtree(root / "plans" / ARCHIVED)
        make_plan(root / "plans", ARCHIVED, extra="changed on the other machine\n")
        make_plan(root / "plans", NEW_PLAN)
        write_marker(root, project_id, "legacy")
        return root

    def test_equal_plans_are_skipped_new_ones_copied_different_ones_conflict(self):
        first = self.build("alpha")
        project_id = self.apply(first)["project_id"]
        second = self.second_checkout(project_id)
        doc = self.json_cli("migrate", "plan", "--project", str(second))
        self.assertEqual(doc["mode"], "import")
        actions = {row["name"]: row["action"] for row in doc["plans"]}
        self.assertEqual((actions[PLAN], actions[ARCHIVED], actions[NEW_PLAN]), ("skipped-equal", "conflict", "copied"))
        self.assertEqual(doc["conflicts"], [ARCHIVED])
        self.assertFalse(doc["ready"])
        before = snapshot(self.ws)
        err = self.failing("migrate", "apply", "--project", str(second))
        self.assertTrue(err.startswith("MIGRATION_CONFLICT: "), err)
        self.assertIn(ARCHIVED, err)
        self.assertEqual(snapshot(self.ws), before)
        self.assertEqual(read_marker(second)["plans_store"], "legacy")

    def test_import_copy_keeps_both_versions_and_never_overwrites(self):
        first = self.build("alpha")
        project_id = self.apply(first)["project_id"]
        second = self.second_checkout(project_id)
        original = migrate.folder_digest(self.project_dir(project_id) / "plans" / ARCHIVED, "v4")
        doc = self.apply(second, "--on-conflict", "import-copy")
        short = migrate.device_short(json.loads((self.root / "skm" / "state" / "workspace" / "device.json")
                                                .read_text(encoding="utf-8"))["device_id"])
        rows = {row["name"]: row for row in doc["plans"]}
        self.assertEqual(rows[ARCHIVED]["action"], "imported-copy")
        self.assertEqual(rows[ARCHIVED]["stored_as"], f"{ARCHIVED}~{short}")
        self.assertEqual(rows[PLAN]["action"], "skipped-equal")
        plans = self.project_dir(project_id) / "plans"
        self.assertEqual(migrate.folder_digest(plans / ARCHIVED, "v4"), original)
        self.assertTrue((plans / f"{ARCHIVED}~{short}" / "artifacts" / "extra.txt").is_file())
        self.assertTrue((plans / NEW_PLAN).is_dir())
        report = json.loads(self.reports(project_id)[-1].read_text(encoding="utf-8"))
        self.assertEqual(report["mode"], "import")
        self.assertEqual(validate_document("workspace-migration", report), [])
        self.assertEqual(len(self.reports(project_id)), 2)

    def test_keep_workspace_leaves_the_workspace_copy_alone(self):
        first = self.build("alpha")
        project_id = self.apply(first)["project_id"]
        second = self.second_checkout(project_id)
        original = migrate.folder_digest(self.project_dir(project_id) / "plans" / ARCHIVED, "v4")
        doc = self.apply(second, "--on-conflict", "keep-workspace")
        self.assertEqual({row["name"]: row["action"] for row in doc["plans"]}[ARCHIVED], "kept-workspace")
        plans = self.project_dir(project_id) / "plans"
        self.assertEqual(migrate.folder_digest(plans / ARCHIVED, "v4"), original)
        self.assertEqual([path.name for path in (plans / "archive").iterdir() if "~" in path.name], [])

    def test_rollback_of_an_import_removes_only_what_it_brought(self):
        first = self.build("alpha")
        project_id = self.apply(first)["project_id"]
        second = self.second_checkout(project_id)
        self.apply(second, "--on-conflict", "import-copy")
        plans = self.project_dir(project_id) / "plans"
        doc = self.json_cli("migrate", "rollback", "--project", str(second))
        self.assertEqual(len(doc["removed"]), 2)
        self.assertIn(f"plans/{NEW_PLAN}", doc["removed"])
        self.assertTrue(any(item.startswith(f"plans/{ARCHIVED}~") for item in doc["removed"]))
        self.assertFalse((plans / NEW_PLAN).exists())
        self.assertTrue((plans / PLAN).is_dir() and (plans / ARCHIVED).is_dir())
        self.assertEqual(read_marker(second)["plans_store"], "legacy")
        self.assertEqual(read_marker(first)["plans_store"], "workspace")


class VerifyTests(MigrateCase):
    def states(self, root: Path) -> dict:
        return {row["name"]: row["state"] for row in self.json_cli("migrate", "verify", "--project", str(root))["plans"]}

    def test_verify_tells_each_kind_of_change(self):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        self.assertEqual(set(self.states(root).values()), {"equal"})
        self.assertTrue(self.json_cli("migrate", "verify", "--project", str(root))["all_equal"])
        put(self.project_dir(project_id) / "plans" / PLAN / "artifacts" / "new.txt", "workspace edit\n")
        put(root / "plans" / "old-thing" / "later.txt", "legacy edit\n")
        shutil.rmtree(root / "plans" / "only-artifacts")
        (root / "plans" / "README.md").write_text("changed\n", encoding="utf-8")
        states = self.states(root)
        self.assertEqual(states[PLAN], "changed-in-workspace")
        self.assertEqual(states["old-thing"], "changed-in-legacy")
        self.assertEqual(states["only-artifacts"], "legacy-removed")
        self.assertEqual(states[migrate.ROOT_NAME], "changed-in-legacy")
        self.assertEqual(states[ARCHIVED], "equal")

    def test_a_derived_file_is_not_a_change(self):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        put(self.project_dir(project_id) / "plans" / PLAN / "views" / "roadmap.md", "regenerated\n")
        self.assertEqual(self.states(root)[PLAN], "equal")

    def test_verify_without_a_migration_is_refused(self):
        root = self.build()
        self.json_cli("project", "attach", "--project", str(root))
        err = self.failing("migrate", "verify", "--project", str(root))
        self.assertTrue(err.startswith("MIGRATION_NOT_APPLIED: "), err)
        err = self.failing("migrate", "verify", "--project", str(self.checkout("plain")))
        self.assertTrue(err.startswith("PROJECT_UNKNOWN: "), err)


class RollbackTests(MigrateCase):
    def test_rollback_restores_the_marker_and_removes_what_the_migration_brought(self):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        doc = self.json_cli("migrate", "rollback", "--project", str(root))
        self.assertTrue(doc["rolled_back"])
        folder = self.project_dir(project_id)
        self.assertEqual(read_marker(root)["plans_store"], "legacy")
        self.assertEqual([path.name for path in (folder / "plans").iterdir()] if (folder / "plans").exists() else [], [])
        self.assertFalse((folder / "legacy-plans").exists() and any((folder / "legacy-plans").iterdir()))
        self.assertTrue((root / "plans" / PLAN / "plan.json").is_file())  # the source is untouched
        report = json.loads(self.reports(project_id)[0].read_text(encoding="utf-8"))
        self.assertEqual(migrate.report_issues(report), [])
        self.assertRegex(report["rolled_back_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        index = json.loads((folder / "local-only.json").read_text(encoding="utf-8"))
        self.assertEqual(index["files"], [])
        exclude = (self.ws / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertNotIn("big.bin", exclude)
        self.assertEqual(list((self.ws / ".staging").iterdir()), [])
        self.assertEqual(self.events()[-1]["type"], "workspace.migration.rolled-back")
        self.assertEqual(self.events()[-1]["data"], {"project_id": project_id, "op_id": report["op_id"]})
        err = self.failing("migrate", "rollback", "--project", str(root))
        self.assertTrue(err.startswith("MIGRATION_NOT_APPLIED: "), err)
        states = {row["name"]: row["state"] for row in self.json_cli("migrate", "verify", "--project", str(root))["plans"]}
        self.assertEqual(set(states.values()), {"equal"})
        again = self.apply(root)  # the plans can be migrated again after a rollback
        self.assertFalse(again["noop"])
        self.assertEqual(len(self.reports(project_id)), 2)

    def test_a_changed_plan_in_the_workspace_refuses_the_rollback_and_changes_nothing(self):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        put(self.project_dir(project_id) / "plans" / PLAN / "artifacts" / "later.txt", "new work\n")
        before = snapshot(self.ws)
        err = self.failing("migrate", "rollback", "--project", str(root))
        self.assertTrue(err.startswith("MIGRATION_DIVERGED: "), err)
        self.assertIn(f"{PLAN} (changed-in-workspace)", err)
        self.assertEqual(snapshot(self.ws), before)
        self.assertEqual(read_marker(root)["plans_store"], "workspace")

    def test_a_plan_added_to_the_workspace_after_an_initial_migration_refuses_the_rollback(self):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        make_plan(self.project_dir(project_id) / "plans", NEW_PLAN)
        err = self.failing("migrate", "rollback", "--project", str(root))
        self.assertIn(f"{NEW_PLAN} (added-in-workspace)", err)

    def test_a_missing_or_changed_old_folder_refuses_the_rollback(self):
        root = self.build()
        self.apply(root)
        shutil.rmtree(root / "plans" / PLAN)
        put(root / "plans" / "old-thing" / "later.txt", "x")
        err = self.failing("migrate", "rollback", "--project", str(root))
        self.assertTrue(err.startswith("MIGRATION_DIVERGED: "), err)
        self.assertIn(f"{PLAN} (legacy-removed)", err)
        self.assertIn("old-thing (changed-in-legacy)", err)

    def test_rollback_before_any_migration_is_refused(self):
        root = self.build()
        self.json_cli("project", "attach", "--project", str(root))
        err = self.failing("migrate", "rollback", "--project", str(root))
        self.assertTrue(err.startswith("MIGRATION_NOT_APPLIED: "), err)

    def test_a_second_migration_in_progress_blocks_the_rollback(self):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        with migrate._migration_lock(project_id, None, None):
            err = self.failing("migrate", "rollback", "--project", str(root))
        self.assertTrue(err.startswith("MIGRATION_LOCKED: "), err)
        self.assertEqual(read_marker(root)["plans_store"], "workspace")


class RecoveryTests(MigrateCase):
    """A call that stops after the bridge switched the marker is finished by the next one; rollback never loses a copy."""

    def failing_report(self):
        original = migrate.atomic_write_text

        def write(path, text, *args, **kwargs):
            if path.parent.name == "migrations":
                raise OSError("disk full")
            return original(path, text, *args, **kwargs)
        return mock.patch.object(migrate, "atomic_write_text", write)

    def intents(self) -> list:
        return sorted(self.state.glob("migrate-*.intent.json"))

    def test_a_refused_second_apply_does_not_remove_the_intent_of_the_first(self):
        root = self.build()
        with self.failing_report(), self.assertRaises(OSError):
            migrate.apply(root, yes=True)
        project_id = read_marker(root)["project_id"]
        self.assertEqual(len(self.intents()), 1)
        self.assertEqual(self.reports(project_id), [])
        write_marker(root, project_id, "legacy")  # the second apply was planned before the switch
        refused = {"result": "refused", "code": "MIGRATION_LOCKED", "message": "busy", "phase": "lock"}
        real = migrator_port.call

        def call(op, *args, **kwargs):
            return refused if op == "apply" else real(op, *args, **kwargs)
        with mock.patch.object(migrator_port, "call", call), self.assertRaises(migrate.WorkspaceError):
            migrate.apply(root, yes=True)
        self.assertEqual(len(self.intents()), 1)
        write_marker(root, project_id, "workspace")
        again = migrate.apply(root, yes=True)
        self.assertFalse(again["noop"])
        self.assertEqual(len(self.reports(project_id)), 1)
        self.assertEqual(self.intents(), [])

    def test_the_report_of_a_retry_keeps_the_decision_of_the_bridge(self):
        root = self.build()
        real = migrator_port.call
        project = {}

        def call(op, payload, *args, **kwargs):
            if op == "apply":  # the folders appear in the workspace after the dry run
                target = self.project_dir(payload["project_id"]) / "plans"
                project["id"] = payload["project_id"]
                shutil.copytree(root / "plans" / PLAN, target / PLAN)
            return real(op, payload, *args, **kwargs)
        with self.failing_report(), mock.patch.object(migrator_port, "call", call), self.assertRaises(OSError):
            migrate.apply(root, yes=True)
        done = migrate.apply(root, yes=True)
        self.assertFalse(done["noop"])
        report = json.loads(self.reports(project["id"])[0].read_text(encoding="utf-8"))
        actions = {row["name"]: row["action"] for row in report["plans"]}
        self.assertEqual(actions[PLAN], "skipped-equal")
        self.assertEqual(self.json_cli("migrate", "rollback", "--project", str(root))["rolled_back"], True)
        self.assertTrue((self.project_dir(project["id"]) / "plans" / PLAN / "plan.json").is_file())

    def rollback_stopped(self, extra: bool):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        plan = self.project_dir(project_id) / "plans" / PLAN

        def drop(*args, **kwargs):
            put(plan / ".lock", "")  # what a planner's PlanLock makes at the old path
            if extra:
                put(plan / "plan.json", "new\n")
            raise OSError("boom")
        with mock.patch.object(migrate, "_drop_local_only", drop):
            try:
                migrate.rollback(root)
            except (OSError, migrate.WorkspaceError) as exc:
                return root, plan, exc
        self.fail("the rollback did not stop")

    def test_a_stopped_rollback_puts_the_plan_back_over_a_lock_file(self):
        root, plan, exc = self.rollback_stopped(False)
        self.assertIsInstance(exc, OSError)
        self.assertIn('"$schema"', (plan / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(read_marker(root)["plans_store"], "workspace")

    def test_a_stopped_rollback_keeps_the_staged_copy_when_the_old_path_is_taken(self):
        root, plan, exc = self.rollback_stopped(True)
        self.assertEqual(getattr(exc, "code", None), "MIGRATION_FAILED")
        self.assertIn(".staging", str(exc))
        staged = list((self.ws / ".staging").glob(f"rollback-*/plans/{PLAN}/plan.json"))
        self.assertEqual(len(staged), 1)
        self.assertIn('"$schema"', staged[0].read_text(encoding="utf-8"))


class CleanupTests(MigrateCase):
    def test_the_confirmation_must_be_the_project_id_of_the_marker(self):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        for wrong in ("prj_" + "0" * 26, "yes", ""):
            err = self.failing("migrate", "cleanup", "--project", str(root), "--confirm", wrong)
            self.assertTrue(err.startswith("CLEANUP_CONFIRM_MISMATCH: "), err)
        self.assertTrue((root / "plans" / PLAN).is_dir())
        code, _out, err = self.run_cli("migrate", "cleanup", "--project", str(root))
        self.assertEqual(code, 2)
        self.assertIn("--confirm", err)
        self.assertEqual(read_marker(root)["project_id"], project_id)

    def test_cleanup_removes_every_old_folder_and_the_empty_plans_folder_without_running_git(self):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        with mock.patch("workspace.gitutil.run", side_effect=AssertionError("cleanup ran git")):
            doc = self.json_cli("migrate", "cleanup", "--project", str(root), "--confirm", project_id)
        self.assertEqual(sorted(doc["removed"]), sorted([PLAN, ARCHIVED, "only-artifacts", "archive/old-legacy",
                                                         "old-thing", "README.md"]))
        self.assertEqual(doc["kept"], [])
        self.assertTrue(doc["plans_removed"])
        self.assertFalse((root / "plans").exists())
        self.assertTrue((self.project_dir(project_id) / "plans" / PLAN / "plan.json").is_file())
        self.assertEqual(doc["next"], [])  # plans/ was not tracked: no commit to suggest

    def test_a_tracked_plans_folder_gets_the_commit_command_printed_not_run(self):
        root = self.build()
        git(root, "add", "plans")
        self.commit(root)
        head = git(root, "rev-parse", "HEAD")
        project_id = self.apply(root)["project_id"]
        doc = self.json_cli("migrate", "cleanup", "--project", str(root), "--confirm", project_id)
        self.assertEqual(len(doc["next"]), 1)
        self.assertIn("rm -r --cached plans", doc["next"][0])
        self.assertIn("chore(skm): планы перенесены в portable workspace", doc["next"][0])
        self.assertEqual(git(root, "rev-parse", "HEAD"), head)
        self.assertIn("plans/", git(root, "ls-files"))  # still tracked: the user commits

    def test_a_folder_that_differs_from_its_copy_is_kept_with_the_reason(self):
        root = self.build()
        project_id = self.apply(root)["project_id"]
        put(root / "plans" / PLAN / "artifacts" / "late.txt", "written after the migration\n")
        shutil.rmtree(self.project_dir(project_id) / "legacy-plans" / "only-artifacts")
        doc = self.json_cli("migrate", "cleanup", "--project", str(root), "--confirm", project_id)
        kept = {item["name"]: item["reason"] for item in doc["kept"]}
        self.assertEqual(kept, {PLAN: "workspace-copy-differs", "only-artifacts": "workspace-copy-missing"})
        self.assertNotIn(PLAN, doc["removed"])
        self.assertTrue((root / "plans" / PLAN / "artifacts" / "late.txt").is_file())
        self.assertTrue((root / "plans" / "only-artifacts").is_dir())
        self.assertFalse((root / "plans" / "old-thing").exists())
        self.assertFalse(doc["plans_removed"])

    def test_a_project_that_still_keeps_its_plans_in_the_checkout_is_refused(self):
        root = self.build()
        project_id = self.json_cli("project", "attach", "--project", str(root))["project_id"]
        err = self.failing("migrate", "cleanup", "--project", str(root), "--confirm", project_id)
        self.assertTrue(err.startswith("MIGRATION_NOT_APPLIED: "), err)
        self.assertTrue((root / "plans" / PLAN).is_dir())

    def test_an_imported_copy_counts_as_the_copy_of_its_source(self):
        first = self.build("alpha")
        project_id = self.apply(first)["project_id"]
        second = ImportTests.second_checkout(self, project_id)
        self.apply(second, "--on-conflict", "import-copy")
        doc = self.json_cli("migrate", "cleanup", "--project", str(second), "--confirm", project_id)
        self.assertIn(ARCHIVED, doc["removed"])
        self.assertEqual(doc["kept"], [])

    def test_plans_tracked_reads_the_index_without_git(self):
        root = self.checkout("tracked")
        put(root / "plans" / "p" / "a.txt", "a")
        put(root / "docs" / "plans" / "b.txt", "b")
        self.assertFalse(migrate._plans_tracked(root))
        git(root, "add", "docs")
        self.assertFalse(migrate._plans_tracked(root))  # docs/plans/ is not plans/
        git(root, "add", "plans")
        self.assertTrue(migrate._plans_tracked(root))
        self.assertFalse(migrate._plans_tracked(self.root))  # not a repository


class PortTests(MigrateCase):
    def test_no_plugin_and_no_hub_module_is_migrator_unavailable_with_the_way_to_register_it(self):
        self.register(False)
        with mock.patch("workspace.migrator_port._unit_folders", return_value=[]):
            err = self.failing("migrate", "plan", "--project", str(self.build()))
        self.assertTrue(err.startswith("MIGRATOR_UNAVAILABLE: "), err)
        self.assertIn("swissknifeman config set aicore plugins.workspace-planner.manifest", err)

    def test_the_port_of_a_hub_module_is_used_when_the_config_has_no_plugin(self):
        self.register(False)
        found = migrator_port.registration()
        self.assertEqual((found.id, found.trusted), ("workspace-planner", False))
        doc = self.json_cli("migrate", "plan", "--project", str(self.build()))  # inspect needs no planner
        self.assertIn(PLAN, [row["name"] for row in doc["plans"]])

    def test_the_configured_plugin_wins_and_is_trusted_as_configured(self):
        self.assertTrue(migrator_port.registration().trusted)

    def test_a_disabled_plugin_is_unavailable(self):
        config = self.root / "skm" / "config" / "config.toml"
        config.write_text(config.read_text(encoding="utf-8") + "enabled = false\n", encoding="utf-8")
        with self.assertRaises(Exception) as caught:
            migrator_port.registration()
        self.assertEqual(caught.exception.code, "MIGRATOR_UNAVAILABLE")

    def test_a_plugin_that_fails_to_start_is_unavailable_with_its_code(self):
        with mock.patch.dict(os.environ, {"PLANNER_ROOT": str(self.root / "nowhere")}):
            self.register(True)
            err = self.failing("migrate", "apply", "--project", str(self.build()), "--yes")
        self.assertTrue(err.startswith("MIGRATOR_UNAVAILABLE: "), err)


class NamesTests(unittest.TestCase):
    def test_report_names_survive_a_round_trip_and_hold_no_slash(self):
        for name in (PLAN, ARCHIVED, "archive/a%b", "~odd", "a\\b", "_root"):
            encoded = migrate.encode_name(name)
            self.assertNotIn("/", encoded)
            self.assertFalse(encoded.startswith("~"))
            self.assertEqual(migrate.decode_name(encoded), name)

    def test_the_digest_ignores_derived_files_of_a_plan_but_not_of_other_folders(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "p"
            put(folder / "plan.json", "{}")
            put(folder / "views" / "x.md", "x")
            put(folder / "__pycache__" / "y.pyc", "y")
            plain = migrate.folder_digest(folder, "v4")
            self.assertEqual(migrate.folder_digest(folder, "legacy"),
                             migrate.digest_files([{"path": "plan.json", "sha256": migrate._sha256(folder / "plan.json")},
                                                   {"path": "views/x.md", "sha256": migrate._sha256(folder / "views/x.md")}]))
            self.assertNotEqual(plain, migrate.folder_digest(folder, "legacy"))
            self.assertIsNone(migrate.folder_digest(folder / "absent", "v4"))

    def test_the_contract_in_the_hub_knows_rolled_back_at(self):
        path = HUB_ROOT / "packages" / "aicore" / "schemas" / "workspace-migration" / "v1" / "workspace-migration.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("rolled_back_at", schema["properties"])
        self.assertNotIn("rolled_back_at", schema["required"])

    def test_a_report_with_a_bad_rollback_time_is_invalid(self):
        report = {"rolled_back_at": "yesterday"}
        self.assertIn("rolled_back_at: not a UTC time", migrate.report_issues(report))
        self.assertEqual(migrate.report_issues([]), ["not an object"])

    def test_the_schema_and_the_events_are_declared(self):
        unit = json.loads((MODULE_ROOT / "unit.json").read_text(encoding="utf-8"))
        for event in ("workspace.migration.applied", "workspace.migration.rolled-back"):
            self.assertIn(event, unit["provides"]["events"])
            self.assertTrue((MODULE_ROOT / "schemas" / "event-data" / "v1" / f"{event}.schema.json").is_file())


if __name__ == "__main__":
    unittest.main()
