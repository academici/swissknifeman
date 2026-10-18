"""Plan-store resolution by the project marker: parity with the aicore vectors, ``find_plans_root``, ``Plan.source_root``,
``PLANS_MIGRATED`` of the plan lock, the ``LEGACY_PLANS_PRESENT`` warning and the new refusals in the JSON envelope."""
import contextlib
import io
import json
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import cli, ops, settings, store, workspace  # noqa: E402
from planner.plan.model import PlanError  # noqa: E402

try:
    from . import demo
except ImportError:  # run as `discover -s tests/engine` (no parent package)
    import demo

PID = "billium"
OTHER_PID = "commerz"


def marker_text(plans_store: str, project_id: str = PID) -> str:
    return json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": "axioma", "project_id": project_id,
                       "plans_store": plans_store}, indent=2) + "\n"


def bindings_text(project_id: str, paths, primary) -> str:
    return json.dumps({"$schema": "urn:swissknifeman:aicore:workspace-bindings:v1",
                       "projects": {project_id: {"paths": list(map(str, paths)), "primary": str(primary),
                                                 "bound_at": "2026-10-17T09:30:00Z"}}}, indent=2) + "\n"


def put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class VectorParityTests(unittest.TestCase):
    """The stdlib copy of the rule gives the answers of ``aicore.workspace`` (shared vectors)."""

    def setUp(self):
        root = os.environ.get("AICORE_ROOT")
        if not root:
            self.skipTest("AICORE_ROOT is not set")
        path = Path(root) / "schemas" / "workspace" / "v1" / "resolution-vectors.json"
        if not path.is_file():
            self.skipTest(f"{path} is missing")
        self.vectors = json.loads(path.read_text(encoding="utf-8"))["vectors"]

    def test_every_vector(self):
        self.assertGreater(len(self.vectors), 20)
        for vector in self.vectors:
            with self.subTest(vector["name"]), tempfile.TemporaryDirectory() as tmp:
                real = os.path.realpath(tmp)

                def sub(value, real=real):
                    if isinstance(value, str):
                        return value.replace("{tmp}", real)
                    if isinstance(value, dict):
                        return {sub(k): sub(v) for k, v in value.items()}
                    return value

                for relative, text in sub(vector["files"]).items():
                    put(Path(real) / relative, text)
                env = sub(vector["env"])
                expect = vector["expect"]
                if vector["op"] == "resolve":
                    call = lambda vector=vector, env=env: workspace.resolve_plans_store(  # noqa: E731
                        sub(vector["project_root"]), env)
                else:
                    call = lambda vector=vector, env=env: workspace.source_root_of(  # noqa: E731
                        sub(vector["plan_dir"]), env, sub(vector["launcher"]) if "launcher" in vector else None)
                if "error" in expect:
                    with self.assertRaises(PlanError) as caught:
                        call()
                    self.assertEqual(caught.exception.code, expect["error"])
                    continue
                answer = call()
                if vector["op"] == "resolve":
                    self.assertEqual((answer.kind, str(answer.plans_root), answer.project_id, answer.reason),
                                     (expect["kind"], sub(expect["plans_root"]), expect["project_id"], expect["reason"]))
                else:
                    wanted = sub(expect["source_root"])
                    self.assertEqual(None if answer is None else str(answer), wanted)


class WorkspaceCase(unittest.TestCase):
    """A project checkout and a workspace in a temporary directory; machine home and workspace never the real ones."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))
        self.home = self.tmp / "home"
        self.ws = self.tmp / "wss" / "axioma"
        self.project = self.tmp / "proj"
        self.project.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SKM_", "XDG_"))}
        env.update(HOME=str(self.home), SKM_HOME=str(self.home), SKM_WORKSPACES_ROOT=str(self.ws.parent))
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(store, "_LEGACY_WARNED", False)
        patcher.start()
        self.addCleanup(patcher.stop)
        settings.set_invocation(None)
        self.addCleanup(settings.set_invocation, None)

    @property
    def ws_plans(self) -> Path:
        return self.ws / "projects" / PID / "plans"

    def mark(self, plans_store: str, project_id: str = PID, root: Path = None) -> None:
        put((root or self.project) / ".swissknifeman" / "project.json", marker_text(plans_store, project_id))

    def bind(self, *paths: Path, project_id: str = PID) -> None:
        put(self.home / "state" / "workspaces" / "axioma" / "bindings.json", bindings_text(project_id, paths, paths[0]))

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()


class FindPlansRootTests(WorkspaceCase):
    def test_without_a_marker_the_nearest_plans_folder_is_used_as_before(self):
        (self.project / "plans").mkdir()
        (self.project / "src" / "deep").mkdir(parents=True)
        self.assertEqual(store.find_plans_root(self.project / "src" / "deep"), self.project / "plans")
        self.assertEqual(store.find_plans_root(self.project / "plans"), self.project / "plans")
        self.assertEqual(store.find_plans_root(self.tmp / "nowhere"), self.tmp / "nowhere" / "plans")

    def test_a_legacy_marker_keeps_the_project_plans_folder(self):
        self.mark("legacy")
        (self.project / "src").mkdir()
        self.assertEqual(store.find_plans_root(self.project / "src"), self.project / "plans")

    def test_a_workspace_marker_names_the_workspace_folder_from_any_depth(self):
        self.mark("workspace")
        self.ws_plans.mkdir(parents=True)
        (self.project / "plans").mkdir()  # the marker wins over a plans folder
        (self.project / "src" / "deep").mkdir(parents=True)
        for start in (self.project, self.project / "src" / "deep"):
            self.assertEqual(store.find_plans_root(start), self.ws_plans)

    def test_a_workspace_marker_without_the_project_folder_is_refused(self):
        self.mark("workspace")
        with self.assertRaises(PlanError) as caught:
            store.find_plans_root(self.project)
        self.assertEqual(caught.exception.code, "WORKSPACE_PROJECT_MISSING")
        self.assertIn("workspace clone", caught.exception.message)

    def test_an_invalid_marker_is_refused(self):
        put(self.project / ".swissknifeman" / "project.json", "{not json")
        with self.assertRaises(PlanError) as caught:
            store.find_plans_root(self.project)
        self.assertEqual(caught.exception.code, "PROJECT_MARKER_INVALID")

    def test_inside_the_workspace_plans_folder_that_folder_is_the_answer(self):
        plan = demo.make_demo_plan(self.ws_plans)
        self.assertEqual(store.find_plans_root(plan), self.ws_plans)
        self.assertEqual(store.find_plans_root(self.ws_plans), self.ws_plans)

    def test_the_cwd_is_the_default_start(self):
        self.mark("workspace")
        self.ws_plans.mkdir(parents=True)
        with mock.patch.object(Path, "cwd", return_value=self.project):
            self.assertEqual(store.find_plans_root(), self.ws_plans)

    def test_the_launcher_project_resolves_by_its_marker(self):
        self.mark("workspace")
        self.ws_plans.mkdir(parents=True)
        env = {"SKM_LAUNCHER_ACTIVE": "1", "SKM_LAUNCHER_PROJECT_ROOT": str(self.project),
               "SKM_LAUNCHER_PID": str(os.getpid())}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(store.find_plans_root(), self.ws_plans)
            store.require_project_plans(self.ws_plans)
            store.require_project_plans(self.ws_plans / "archive")
            for bad in (self.project / "plans", self.ws.parent / "other" / "plans", self.ws / "projects" / OTHER_PID / "plans"):
                with self.subTest(bad=bad), self.assertRaises(PlanError) as caught:
                    store.require_project_plans(bad)
                self.assertEqual(caught.exception.code, "PROJECT_PATH_OVERRIDE_FORBIDDEN")


class LegacyWarningTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.mark("workspace")
        self.ws_plans.mkdir(parents=True)

    def find(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()) as out:
            root = store.find_plans_root(self.project)
        self.assertEqual(root, self.ws_plans)
        self.assertEqual(out.getvalue(), "")
        return err.getvalue()

    def test_legacy_plans_left_behind_warn_once_per_process(self):
        put(self.project / "plans" / "old-plan" / "plan.json", "{}\n")
        first = self.find()
        self.assertEqual(first.count("\n"), 1)
        self.assertTrue(first.startswith("warning: LEGACY_PLANS_PRESENT: "), first)
        self.assertIn("the workspace copy is used", first)
        self.assertEqual(self.find(), "")

    def test_an_empty_or_missing_legacy_folder_does_not_warn(self):
        self.assertEqual(self.find(), "")
        (self.project / "plans" / "archive").mkdir(parents=True)
        self.assertEqual(self.find(), "")

    def test_a_plans_link_into_the_bound_workspace_is_the_store_not_a_legacy_copy(self):
        demo.make_demo_plan(self.ws_plans)
        os.symlink(self.ws_plans, self.project / "plans")
        self.assertTrue(workspace.is_workspace_link(self.project))
        self.assertFalse(workspace.legacy_plans_present(self.project))
        self.assertEqual(self.find(), "")

    def test_a_plans_link_to_another_place_still_warns(self):
        elsewhere = self.tmp / "elsewhere"
        put(elsewhere / "old-plan" / "plan.json", "{}\n")
        os.symlink(elsewhere, self.project / "plans")
        self.assertFalse(workspace.is_workspace_link(self.project))
        self.assertTrue(workspace.legacy_plans_present(self.project))
        self.assertIn("LEGACY_PLANS_PRESENT", self.find())

    def test_a_legacy_store_never_warns(self):
        self.mark("legacy")
        put(self.project / "plans" / "old-plan" / "plan.json", "{}\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(store.find_plans_root(self.project), self.project / "plans")
        self.assertEqual(err.getvalue(), "")

    def test_the_json_envelope_is_unchanged(self):
        put(self.project / "plans" / "old-plan" / "plan.json", "{}\n")
        demo.make_demo_plan(self.ws_plans)
        with mock.patch.object(Path, "cwd", return_value=self.project):
            code, out, err = self.run_cli("--output", "json", "plans")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["ok"], True)
        self.assertEqual(err.count("LEGACY_PLANS_PRESENT"), 1)


class SourceRootTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.mark("workspace")
        self.plan_dir = demo.make_demo_plan(self.ws_plans)

    def test_a_bound_checkout_is_the_source_and_repo_root(self):
        self.bind(self.project)
        plan = store.load_plan(self.plan_dir)
        self.assertEqual(plan.source_root, self.project)
        self.assertEqual(plan.repo_root, self.project)

    def test_an_unbound_plan_has_no_source_but_can_still_be_read_and_changed(self):
        plan = store.load_plan(self.plan_dir)
        self.assertIsNone(plan.source_root)
        with self.assertRaises(PlanError) as caught:
            _ = plan.repo_root
        self.assertEqual(caught.exception.code, "PLAN_SOURCE_UNBOUND")
        self.assertIn("workspace project attach", caught.exception.message)
        store.append_log(self.plan_dir, store.new_event("note", "written without a checkout", demo.AUTHORING))
        self.assertEqual(store.read_log(self.plan_dir)[-1]["summary"], "written without a checkout")

    def test_the_launcher_checkout_wins_and_another_project_conflicts(self):
        env = {"SKM_LAUNCHER_ACTIVE": "1", "SKM_LAUNCHER_PROJECT_ROOT": str(self.project),
               "SKM_LAUNCHER_PID": str(os.getpid())}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(store.load_plan(self.plan_dir).source_root, self.project)
            self.mark("workspace", OTHER_PID)
            with self.assertRaises(PlanError) as caught:
                _ = store.load_plan(self.plan_dir).source_root
            self.assertEqual(caught.exception.code, "PROJECT_CONTEXT_CONFLICT")

    def test_a_legacy_plan_is_the_parent_of_plans_live_and_archived(self):
        legacy = self.tmp / "other"
        live = demo.make_demo_plan(legacy / "plans")
        self.assertEqual(store.load_plan(live).repo_root, legacy)
        (legacy / "plans" / "archive").mkdir()
        archived = live.rename(legacy / "plans" / "archive" / live.name)
        self.assertEqual(store.load_plan(archived).repo_root, legacy)

    def test_the_settings_project_is_the_source_root(self):
        self.assertIsNone(settings.project_root_of(self.ws_plans))
        self.bind(self.project)
        self.assertEqual(settings.project_root_of(self.ws_plans), self.project)
        self.assertEqual(settings.project_root_of(self.ws_plans / "archive"), self.project)
        self.assertEqual(settings.project_root_of(self.tmp / "other" / "plans"), self.tmp / "other")
        self.assertIsNone(settings.project_root_of(self.tmp / "other"))

    def test_a_new_plan_names_the_source_checkout_as_its_repository(self):
        self.assertEqual(ops.default_repository(self.ws_plans), PID)  # no checkout bound: the project folder name
        self.bind(self.project)
        self.assertEqual(ops.default_repository(self.ws_plans), "proj")
        self.assertEqual(ops.default_repository(self.tmp / "other" / "plans"), "other")

    def test_a_damaged_bindings_file_is_a_layout_error(self):
        put(self.home / "state" / "workspaces" / "axioma" / "bindings.json", "{not json")
        with self.assertRaises(PlanError) as caught:
            _ = store.load_plan(self.plan_dir).source_root
        self.assertEqual(caught.exception.code, "WORKSPACE_LAYOUT_INVALID")


class PlansMigratedTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.legacy_plans = self.project / "plans"
        self.legacy = demo.make_demo_plan(self.legacy_plans)

    def test_a_legacy_plan_is_locked_and_changed_while_the_marker_says_legacy_or_is_absent(self):
        for text in (None, marker_text("legacy")):
            with self.subTest(marker=text):
                if text:
                    put(self.project / ".swissknifeman" / "project.json", text)
                with store.PlanLock(self.legacy):
                    pass

    def test_the_switch_makes_the_legacy_lock_refuse_and_release_the_file(self):
        self.mark("workspace")
        with self.assertRaises(PlanError) as caught:
            with store.PlanLock(self.legacy):
                self.fail("the lock must not be granted")
        self.assertEqual(caught.exception.code, "PLANS_MIGRATED")
        self.assertIn("rerun the command", caught.exception.message)
        # the flock was released: another lock on the same file succeeds at once
        import fcntl
        with open(self.legacy / store.LOCK, "a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_an_archived_legacy_plan_is_refused_too(self):
        (self.legacy_plans / "archive").mkdir()
        archived = self.legacy.rename(self.legacy_plans / "archive" / self.legacy.name)
        self.mark("workspace")
        with self.assertRaises(PlanError) as caught:
            store.PlanLock(archived).__enter__()
        self.assertEqual(caught.exception.code, "PLANS_MIGRATED")

    def test_a_mutation_through_the_api_is_refused_and_writes_nothing(self):
        before = (self.legacy / "plan.json").read_bytes()
        self.mark("workspace")
        with self.assertRaises(PlanError) as caught:
            ops.patch(store.load_plan(self.legacy), "plan", {"context": "lost write"})
        self.assertEqual(caught.exception.code, "PLANS_MIGRATED")
        self.assertEqual((self.legacy / "plan.json").read_bytes(), before)

    def test_a_plan_reached_through_the_plans_link_is_a_workspace_plan(self):
        self.mark("workspace")
        copy = demo.make_demo_plan(self.ws_plans)
        shutil.rmtree(self.legacy_plans)
        os.symlink(self.ws_plans, self.legacy_plans)
        with store.PlanLock(self.legacy_plans / copy.name):
            pass
        ops.patch(store.load_plan(self.legacy_plans / copy.name), "plan", {"context": "through the link"})
        self.assertEqual(json.loads((copy / "plan.json").read_text(encoding="utf-8"))["context"], "through the link")

    def test_the_workspace_copy_is_locked_without_the_check(self):
        self.mark("workspace")
        copy = demo.make_demo_plan(self.ws_plans)
        with mock.patch.object(workspace, "read_marker", side_effect=AssertionError("marker read")):
            with store.PlanLock(copy):
                pass

    def test_a_folder_without_a_marker_beside_it_is_not_checked(self):
        with mock.patch.object(workspace, "read_marker", side_effect=AssertionError("marker read")):
            with store.PlanLock(self.legacy):
                pass

    def test_the_refusal_reaches_the_json_envelope(self):
        self.mark("workspace")
        code, out, _ = self.run_cli("--output", "json", "log", self.legacy, "P1.2", "--type", "note", "--summary", "x")
        document = json.loads(out)
        self.assertFalse(document["ok"])
        self.assertEqual(code, 1)
        self.assertEqual(document["error"]["code"], "PLANS_MIGRATED")


class EnvelopeTests(WorkspaceCase):
    def test_a_missing_workspace_project_is_an_envelope_error(self):
        self.mark("workspace")
        with mock.patch.object(Path, "cwd", return_value=self.project):
            code, out, _ = self.run_cli("--output", "json", "plans")
        document = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(document["error"]["code"], "WORKSPACE_PROJECT_MISSING")

    def test_an_invalid_marker_is_an_envelope_error(self):
        put(self.project / ".swissknifeman" / "project.json", "[]\n")
        with mock.patch.object(Path, "cwd", return_value=self.project):
            code, out, _ = self.run_cli("--output", "json", "plans")
        self.assertEqual(json.loads(out)["error"]["code"], "PROJECT_MARKER_INVALID")
        self.assertEqual(code, 1)

    def test_new_in_the_workspace_records_the_bound_checkout_name(self):
        self.mark("workspace")
        self.ws_plans.mkdir(parents=True)
        self.bind(self.project)
        with mock.patch.object(Path, "cwd", return_value=self.project):
            code, out, err = self.run_cli("new", "--codename", "DEMO", "--title", "Demo", "--message", "first message",
                                          "--actor", "claude-code/claude-opus-5-5/high")
        self.assertEqual(code, 0, err)
        created = next(store.plan_dirs(self.ws_plans))
        self.assertEqual(store.load_plan(created).plan["repository"], "proj")


if __name__ == "__main__":
    unittest.main()
