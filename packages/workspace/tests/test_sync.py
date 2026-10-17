"""workspace sync: commit (publish-safety, local-only), pull (merge-tree, typed conflicts), resolve and push on local bare
repositories; two machines are two SKM_HOME and two workspace roots on one bare remote (no network)."""
import contextlib
import json
import os
import subprocess
import unittest
from unittest import mock

from aicore.workspace import WorkspaceError

from tests import TempCase, git
from workspace import gitutil, layout, localonly, remote, sync

PID = "prj_" + "0" * 26
PLAN = "2026.10.17-n1-DEMO"


def verb(argv):
    """The git subcommand of an argument list (after ``git`` and any ``-c key=value`` pairs)."""
    items = list(argv[1:])
    while items and items[0] == "-c":
        items = items[2:]
    return items[0] if items else ""


def forbidden(argv):
    """The forbidden form an argument list contains (force push, reset --hard, clean, checkout ., rebase), else ``None``."""
    flat = list(argv[1:])
    name = verb(argv)
    if any(item.startswith("--force") for item in flat) or (name == "push" and "-f" in flat):
        return "force"
    if name == "reset" and "--hard" in flat:
        return "reset --hard"
    if name in ("clean", "rebase"):
        return name
    if name == "checkout" and "." in flat[flat.index("checkout") + 1:]:
        return "checkout ."
    return None


class SyncCase(TempCase):
    def bare(self, name="origin.git"):
        path = self.root / name
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True, capture_output=True)
        return path

    def url(self, path):
        return "file://" + str(path)

    @contextlib.contextmanager
    def machine(self, name):
        """Environment of machine ``name`` (its own SKM_HOME, HOME and workspace root)."""
        env = {"HOME": str(self.root / f"home-{name}"), "SKM_HOME": str(self.root / f"skm-{name}"),
               "SKM_WORKSPACE_ROOT": str(self.root / f"ws-{name}")}
        (self.root / f"home-{name}").mkdir(exist_ok=True)
        with mock.patch.dict(os.environ, env):
            yield self.root / f"ws-{name}"

    def put(self, ws, rel, text, plan=PLAN):
        path = ws / "projects" / PID / "plans" / plan / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def append(self, ws, rel, line, plan=PLAN):
        path = ws / "projects" / PID / "plans" / plan / rel
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def code(self, call, *args, **kwargs):
        with self.assertRaises(WorkspaceError) as caught:
            call(*args, **kwargs)
        return caught.exception.code

    def two_machines(self):
        """A pushed a workspace holding one plan; B cloned it. Returns the bare repository."""
        bare = self.bare()
        layout.init()
        self.put(self.ws, "plan.json", '{"title": "demo"}\n')
        self.put(self.ws, "phases/P2/P2.3.json", '{"summary": "base"}\n')
        self.put(self.ws, "log.jsonl", '{"n": 0}\n')
        remote.connect(self.url(bare))
        sync.sync(push=True)
        with self.machine("b"):
            remote.clone(self.url(bare))
        return bare

    def sync_b(self, **kwargs):
        with self.machine("b"):
            return sync.sync(**kwargs)

    def head(self, ws):
        return git(ws, "rev-parse", "HEAD").strip()


class StepTests(unittest.TestCase):
    def test_plan_steps(self):
        self.assertEqual(sync.plan_steps(False, False, False, False), (True, True, False))
        self.assertEqual(sync.plan_steps(True, False, False, False), (True, False, False))
        self.assertEqual(sync.plan_steps(False, True, False, False), (False, True, False))
        self.assertEqual(sync.plan_steps(False, False, True, False), (True, True, True))
        self.assertEqual(sync.plan_steps(False, False, False, True), (False, False, False))
        self.assertEqual(sync.plan_steps(False, False, True, True), (False, False, True))
        with self.assertRaises(ValueError):
            sync.plan_steps(False, True, False, True)

    def test_conflict_row(self):
        self.assertEqual(sync.conflict_row(f"projects/{PID}/plans/{PLAN}/phases/P2/P2.3.json"),
                         {"path": f"projects/{PID}/plans/{PLAN}/phases/P2/P2.3.json", "project_id": PID, "plan": PLAN,
                          "ref": "P2.3"})
        self.assertEqual(sync.conflict_row(f"projects/{PID}/plans/{PLAN}/decisions/D4.json")["ref"], "D4")
        self.assertEqual(sync.conflict_row(f"projects/{PID}/plans/{PLAN}/plan.json")["ref"], "plan")
        archived = sync.conflict_row(f"projects/{PID}/plans/archive/{PLAN}/plan.json")
        self.assertEqual((archived["plan"], archived["ref"]), (PLAN, "plan"))
        self.assertEqual(sync.conflict_row(f"projects/{PID}/project.json"),
                         {"path": f"projects/{PID}/project.json", "project_id": PID, "plan": None, "ref": None})
        self.assertEqual(sync.conflict_row("workspace.json")["project_id"], None)

    def test_parse_resolutions(self):
        self.assertEqual(sync.parse_resolutions(["a/b.json=local", "./c=remote"]), {"a/b.json": "local", "c": "remote"})
        for bad in (["a"], ["a=both"], ["=local"], ["a=local", "a=remote"]):
            with self.assertRaises(ValueError):
                sync.parse_resolutions(bad)


class CommitTests(SyncCase):
    def test_nothing_to_commit(self):
        layout.init()
        doc = sync.sync(commit=True)
        self.assertEqual(doc["commit"]["status"], "nothing")
        self.assertEqual(doc["steps"], ["commit"])

    def test_one_plan_commit_has_plan_subject_and_trailer(self):
        layout.init()
        self.put(self.ws, "plan.json", "{}\n")
        self.put(self.ws, "phases/P1/P1.1.json", "{}\n")
        with mock.patch.object(sync.events, "emit") as emit:
            doc = sync.sync(commit=True)
        message = git(self.ws, "log", "-1", "--format=%B")
        self.assertEqual(doc["commit"]["status"], "committed")
        self.assertEqual(doc["commit"]["files"], 2)
        self.assertTrue(message.startswith(f"skm(plan): {PLAN} sync 2 files"))
        self.assertIn(f"project {PID}: {PLAN}", message)
        self.assertRegex(message, r"Workspace-Device: dev_\w+")
        self.assertEqual(git(self.ws, "status", "--porcelain").strip(), "")
        emit.assert_called_once()
        self.assertEqual(emit.call_args[0][0], "workspace.sync.committed")
        self.assertEqual(emit.call_args[0][1], {"sha": self.head(self.ws), "files": 2})
        state = json.loads((self.state / "sync.json").read_text(encoding="utf-8"))
        self.assertEqual(state["last_result"], "ok")
        self.assertIn("last_commit_at", state)
        audit = [json.loads(line) for line in (self.state / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(row["op"], row["result"]) for row in audit], [("commit", "ok")])

    def test_several_plans_get_the_workspace_subject(self):
        layout.init()
        self.put(self.ws, "plan.json", "{}\n")
        self.put(self.ws, "plan.json", "{}\n", plan="other")
        sync.sync(commit=True)
        self.assertTrue(git(self.ws, "log", "-1", "--format=%s").startswith("skm(workspace): sync 2 files"))

    def test_secret_blocks_everything(self):
        layout.init()
        before = self.head(self.ws)
        self.put(self.ws, "plan.json", "{}\n")
        self.put(self.ws, "notes.md", "token = sk-ABCDEFGHIJKLMNOPQRSTUVWX0123456789\n")
        with self.assertRaises(sync.SyncError) as caught:
            sync.sync(commit=True)
        self.assertEqual(caught.exception.code, "PUBLISH_BLOCKED")
        self.assertEqual(caught.exception.report["commit"]["status"], "blocked")
        self.assertIn("PS-SECRET", {item["rule"] for item in caught.exception.report["commit"]["block"]})
        self.assertNotIn("ABCDEFGHIJKL", json.dumps(caught.exception.report))
        self.assertEqual(self.head(self.ws), before)
        self.assertEqual(git(self.ws, "diff", "--cached", "--name-only").strip(), "")

    def test_manifest_with_absolute_path_blocks(self):
        layout.init()
        path = self.ws / "projects" / PID / "project.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"path": "/home/someone/code"}\n', encoding="utf-8")
        self.assertEqual(self.code(sync.sync, commit=True), "PUBLISH_BLOCKED")

    def test_big_file_is_local_only_and_not_committed(self):
        layout.init()
        self.put(self.ws, "plan.json", "{}\n")
        big = self.put(self.ws, "artifacts/dump.bin", "")
        big.write_bytes(b"\0" + b"x" * (1024 * 1024 + 10))
        doc = sync.sync(commit=True)
        names = git(self.ws, "show", "--name-only", "--format=", "HEAD").split()
        self.assertIn(f"projects/{PID}/local-only.json", names)
        self.assertNotIn(f"projects/{PID}/plans/{PLAN}/artifacts/dump.bin", names)
        self.assertTrue(big.is_file())
        self.assertEqual([item["reason"] for item in doc["commit"]["local_only"]], ["binary"])
        index = localonly.read(self.ws, PID)
        self.assertEqual([item["path"] for item in index["files"]], [f"plans/{PLAN}/artifacts/dump.bin"])
        self.assertIn(f"/projects/{PID}/plans/{PLAN}/artifacts/dump.bin",
                      (self.ws / ".git" / "info" / "exclude").read_text(encoding="utf-8"))
        self.assertEqual(sync.sync(commit=True)["commit"]["status"], "nothing")

    def test_tracked_file_that_becomes_local_only_leaves_the_index(self):
        layout.init()
        data = self.put(self.ws, "artifacts/data.bin", "small\n")
        sync.sync(commit=True)
        rel = f"projects/{PID}/plans/{PLAN}/artifacts/data.bin"
        self.assertIn(rel, git(self.ws, "ls-files").split())
        data.write_bytes(b"\0" + b"y" * (1024 * 1024 + 10))
        doc = sync.sync(commit=True)
        self.assertEqual(doc["commit"]["untracked"], [rel])
        self.assertIn("PS-TRACKED-LOCAL-ONLY", {item["rule"] for item in doc["commit"]["warn"]})
        self.assertNotIn(rel, git(self.ws, "ls-files").split())
        self.assertTrue(data.is_file())
        self.assertEqual(data.stat().st_size, 1024 * 1024 + 11)

    def test_execute_bit_is_cleared_in_the_index(self):
        layout.init()
        script = self.put(self.ws, "tools/run.sh", "#!/bin/sh\n")
        script.chmod(0o755)
        doc = sync.sync(commit=True)
        rel = f"projects/{PID}/plans/{PLAN}/tools/run.sh"
        self.assertEqual(doc["commit"]["executable_cleared"], [rel])
        self.assertTrue(git(self.ws, "ls-files", "-s", "--", rel).startswith("100644"))

    def test_remote_is_shown_without_user_information(self):
        layout.init()
        git(self.ws, "remote", "add", "origin", "https://user:s3cret@example.invalid/team/ws.git")
        self.put(self.ws, "plan.json", "{}\n")
        doc = sync.sync(commit=True)
        self.assertEqual(doc["remote"], "https://example.invalid/team/ws.git")
        self.assertNotIn("s3cret", json.dumps(doc))
        self.assertNotIn("s3cret", (self.state / "audit.jsonl").read_text(encoding="utf-8"))

    def test_unfinished_merge_is_refused(self):
        layout.init()
        (self.ws / ".git" / "MERGE_HEAD").write_text(self.head(self.ws) + "\n", encoding="utf-8")
        self.assertEqual(self.code(sync.sync, commit=True), "WORKSPACE_MERGE_IN_PROGRESS")

    def test_git_older_than_2_38_is_refused(self):
        layout.init()
        with mock.patch.object(gitutil, "git_version", return_value=(2, 30, 0)):
            self.assertEqual(self.code(sync.sync, commit=True), "WORKSPACE_GIT_TOO_OLD")

    def test_pull_without_a_remote(self):
        layout.init()
        self.assertEqual(self.code(sync.sync, pull=True), "REMOTE_NOT_SET")
        self.assertEqual(self.code(sync.sync, push=True), "REMOTE_NOT_SET")


class PullPushTests(SyncCase):
    def test_push_to_an_empty_remote_and_clone(self):
        bare = self.bare()
        layout.init()
        self.put(self.ws, "plan.json", "{}\n")
        remote.connect(self.url(bare))
        seen = []
        with mock.patch.object(sync.events, "emit") as emit:
            doc = sync.sync(push=True, announce=seen.append)
        self.assertEqual(seen, [{"remote": self.url(bare), "branch": "main"}])
        self.assertEqual(doc["push"]["status"], "pushed")
        self.assertEqual(doc["pull"]["status"], "no-remote-branch")
        self.assertEqual(git(bare, "rev-parse", "main").strip(), self.head(self.ws))
        self.assertEqual([call[0][0] for call in emit.call_args_list],
                         ["workspace.sync.committed", "workspace.sync.pulled", "workspace.sync.pushed"])
        self.assertEqual(sync.sync(push=True)["push"]["status"], "up-to-date")
        state = json.loads((self.state / "sync.json").read_text(encoding="utf-8"))
        self.assertIn("last_push_at", state)

    def test_changes_of_different_plans_converge_without_conflict(self):
        self.two_machines()
        self.put(self.ws, "plan.json", '{"title": "A edit"}\n')
        self.put(self.ws, "plan.json", '{"title": "other plan"}\n', plan="plan-b")
        sync.sync(push=True)
        with self.machine("b") as ws_b:
            self.put(ws_b, "phases/P2/P2.3.json", '{"summary": "B edit"}\n', plan="plan-c")
            doc = sync.sync(push=True)
            self.assertEqual(doc["pull"]["status"], "merged")
            self.assertEqual(doc["push"]["status"], "pushed")
            self.assertEqual((ws_b / "projects" / PID / "plans" / PLAN / "plan.json").read_text(encoding="utf-8"),
                             '{"title": "A edit"}\n')
        doc = sync.sync(push=True)
        self.assertEqual(doc["pull"]["status"], "fast-forward")
        self.assertTrue((self.ws / "projects" / PID / "plans" / "plan-c" / "phases/P2/P2.3.json").is_file())
        self.assertEqual(self.head(self.ws), self.head(self.root / "ws-b"))

    def test_log_jsonl_of_one_plan_merges_by_union(self):
        self.two_machines()
        self.append(self.ws, "log.jsonl", '{"n": "a1"}')
        sync.sync(push=True)
        with self.machine("b") as ws_b:
            self.append(ws_b, "log.jsonl", '{"n": "b1"}')
            doc = sync.sync(push=True)
            self.assertEqual(doc["pull"]["status"], "merged")
            lines = (ws_b / "projects" / PID / "plans" / PLAN / "log.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(sorted(lines), sorted(['{"n": 0}', '{"n": "a1"}', '{"n": "b1"}']))

    def test_conflict_is_typed_and_leaves_tree_and_head_alone(self):
        self.two_machines()
        rel = f"projects/{PID}/plans/{PLAN}/phases/P2/P2.3.json"
        self.put(self.ws, "phases/P2/P2.3.json", '{"summary": "from A"}\n')
        sync.sync(push=True)
        with self.machine("b") as ws_b:
            self.put(ws_b, "phases/P2/P2.3.json", '{"summary": "from B"}\n')
            sync.sync(commit=True)
            head, tree = self.head(ws_b), (ws_b / rel).read_text(encoding="utf-8")
            with mock.patch.object(sync.events, "emit") as emit:
                with self.assertRaises(sync.SyncError) as caught:
                    sync.sync(pull=True)
            exc = caught.exception
            self.assertEqual(exc.code, "WORKSPACE_CONFLICT")
            self.assertEqual(exc.report["conflicts"], [{"path": rel, "project_id": PID, "plan": PLAN, "ref": "P2.3"}])
            self.assertEqual(self.head(ws_b), head)
            self.assertEqual((ws_b / rel).read_text(encoding="utf-8"), tree)
            self.assertEqual(git(ws_b, "status", "--porcelain").strip(), "")
            self.assertFalse((ws_b / ".git" / "MERGE_HEAD").exists())
            emit.assert_called_once_with("workspace.sync.conflict", {"paths": [rel]}, subject=mock.ANY, env=mock.ANY,
                                         home=mock.ANY)
            state = json.loads((self.root / "skm-b" / "state" / "workspace" / "sync.json").read_text(encoding="utf-8"))
            self.assertEqual(state["last_conflicts"]["conflicts"][0]["ref"], "P2.3")
            self.assertEqual(state["pending_resolutions"], {})
            self.assertEqual(state["last_result"], "WORKSPACE_CONFLICT")

    def conflict_on_b(self):
        """A and B edited P2.3 and D4; A pushed; B committed and pulled into a conflict. Returns (ws_b, [paths])."""
        self.two_machines()
        self.put(self.ws, "decisions/D4.json", '{"d": "base"}\n')
        self.put(self.ws, "phases/P2/P2.3.json", '{"summary": "from A"}\n')
        sync.sync(push=True)
        with self.machine("b"):
            sync.sync(pull=True)
        self.put(self.ws, "decisions/D4.json", '{"d": "A"}\n')
        self.put(self.ws, "phases/P2/P2.3.json", '{"summary": "A again"}\n')
        sync.sync(push=True)
        ws_b = self.root / "ws-b"
        with self.machine("b"):
            self.put(ws_b, "decisions/D4.json", '{"d": "B"}\n')
            self.put(ws_b, "phases/P2/P2.3.json", '{"summary": "B"}\n')
            self.assertEqual(self.code(sync.sync), "WORKSPACE_CONFLICT")
        base = f"projects/{PID}/plans/{PLAN}/"
        return ws_b, [base + "decisions/D4.json", base + "phases/P2/P2.3.json"]

    def test_resolve_in_parts_then_merge_and_push(self):
        ws_b, (d4, p23) = self.conflict_on_b()
        with self.machine("b"):
            local_head = self.head(ws_b)
            doc = sync.sync(resolve=[f"{d4}=remote"])
            self.assertEqual(doc["resolution"], {"decided": 1, "remaining": [p23]})
            self.assertEqual(self.head(ws_b), local_head)
            state = sync.read_state()
            self.assertEqual(state["pending_resolutions"], {d4: "remote"})
            with mock.patch.object(sync.events, "emit") as emit:
                doc = sync.sync(resolve=[f"{p23}=local"], push=True)
            self.assertEqual(doc["resolution"]["remaining"], [])
            self.assertTrue(doc["resolution"]["merged"])
            self.assertEqual(doc["push"]["status"], "pushed")
            self.assertEqual((ws_b / d4).read_text(encoding="utf-8"), '{"d": "A"}\n')
            self.assertEqual((ws_b / p23).read_text(encoding="utf-8"), '{"summary": "B"}\n')
            self.assertEqual(git(ws_b, "log", "--merges", "-1", "--format=%s").strip(),
                             "skm(workspace): merge origin/main (resolved 2)")
            self.assertEqual(git(ws_b, "status", "--porcelain").strip(), "")
            self.assertIsNone(sync.read_state()["last_conflicts"])
            self.assertEqual([call[0][0] for call in emit.call_args_list],
                             ["workspace.sync.pulled", "workspace.sync.pushed"])
        doc = sync.sync(pull=True)
        self.assertEqual(self.head(self.ws), self.head(ws_b))
        self.assertEqual((self.ws / p23).read_text(encoding="utf-8"), '{"summary": "B"}\n')
        self.assertEqual(doc["pull"]["status"], "fast-forward")

    def test_resolve_path_outside_the_conflicts_is_refused_and_records_nothing(self):
        ws_b, (d4, p23) = self.conflict_on_b()
        with self.machine("b"):
            self.assertEqual(self.code(sync.sync, resolve=[f"{d4}=local", "workspace.json=local"]), "RESOLUTION_INCOMPLETE")
            self.assertEqual(sync.read_state()["pending_resolutions"], {})

    def test_resolve_without_conflicts_is_refused(self):
        self.two_machines()
        self.assertEqual(self.code(sync.sync, resolve=["workspace.json=local"]), "RESOLUTION_INCOMPLETE")

    def test_resolve_reset_clears_the_decisions(self):
        ws_b, (d4, p23) = self.conflict_on_b()
        with self.machine("b"):
            sync.sync(resolve=[f"{d4}=local"])
            doc = sync.sync(resolve_reset=True)
            self.assertEqual(doc["resolution"], {"decided": 0, "remaining": [d4, p23], "reset": True})
            self.assertEqual(sync.read_state()["pending_resolutions"], {})
            self.assertEqual(sync.read_state()["last_conflicts"]["conflicts"][0]["path"], d4)

    def test_remote_that_moved_makes_the_decisions_stale(self):
        ws_b, (d4, p23) = self.conflict_on_b()
        self.put(self.ws, "plan.json", '{"title": "A moved on"}\n')
        sync.sync(push=True)
        with self.machine("b"):
            local_head = self.head(ws_b)
            sync.sync(resolve=[f"{d4}=local"])
            self.assertEqual(self.code(sync.sync, resolve=[f"{p23}=remote"]), "WORKSPACE_CONFLICT_STALE")
            state = sync.read_state()
            self.assertEqual(state["pending_resolutions"], {})
            self.assertIsNone(state["last_conflicts"])
            self.assertEqual(self.head(ws_b), local_head)
            self.assertFalse((ws_b / ".git" / "MERGE_HEAD").exists())
            self.assertEqual(self.code(sync.sync, resolve=[f"{p23}=remote"]), "RESOLUTION_INCOMPLETE")
            self.assertEqual(self.code(sync.sync), "WORKSPACE_CONFLICT")

    def test_error_during_resolve_aborts_the_merge(self):
        ws_b, (d4, p23) = self.conflict_on_b()
        with self.machine("b"):
            local_head = self.head(ws_b)
            before = (ws_b / d4).read_text(encoding="utf-8")
            with mock.patch.object(sync, "_apply_side", side_effect=sync.SyncError("WORKSPACE_SYNC_FAILED", "boom")):
                self.assertEqual(self.code(sync.sync, resolve=[f"{d4}=remote", f"{p23}=remote"]), "WORKSPACE_SYNC_FAILED")
            self.assertEqual(self.head(ws_b), local_head)
            self.assertFalse((ws_b / ".git" / "MERGE_HEAD").exists())
            self.assertEqual(git(ws_b, "status", "--porcelain").strip(), "")
            self.assertEqual((ws_b / d4).read_text(encoding="utf-8"), before)

    def test_modify_delete_conflict_follows_the_decision(self):
        for side, exists in (("remote", False), ("local", True)):
            with self.subTest(side=side):
                self.tearDownMachines()
                self.two_machines()
                gone = self.ws / "projects" / PID / "plans" / PLAN / "phases/P2/P2.3.json"
                gone.unlink()
                sync.sync(push=True)
                with self.machine("b") as ws_b:
                    self.put(ws_b, "phases/P2/P2.3.json", '{"summary": "B edit"}\n')
                    self.assertEqual(self.code(sync.sync), "WORKSPACE_CONFLICT")
                    rel = f"projects/{PID}/plans/{PLAN}/phases/P2/P2.3.json"
                    sync.sync(resolve=[f"{rel}={side}"])
                    self.assertEqual((ws_b / rel).exists(), exists)
                    self.assertEqual(git(ws_b, "status", "--porcelain").strip(), "")
                    self.assertFalse((ws_b / ".git" / "MERGE_HEAD").exists())

    def tearDownMachines(self):
        import shutil
        for name in ("ws", "ws-b", "origin.git", "skm", "skm-b"):
            shutil.rmtree(self.root / name, ignore_errors=True)

    def test_push_that_lost_a_race_is_behind(self):
        self.two_machines()
        self.put(self.ws, "plan.json", '{"title": "A"}\n')
        sync.sync(push=True)
        with self.machine("b") as ws_b:
            self.put(ws_b, "plan.json", '{"title": "B"}\n')
            with mock.patch.object(sync, "_step_pull"):  # the remote moves between the pull and the push
                with self.assertRaises(sync.SyncError) as caught:
                    sync.sync(push=True)
            self.assertEqual(caught.exception.code, "WORKSPACE_BEHIND")
            self.assertEqual(caught.exception.report["push"]["status"], "behind")
            self.assertEqual(sync.read_state()["last_result"], "WORKSPACE_BEHIND")

    def test_unrelated_histories_are_refused(self):
        bare = self.bare()
        other = self.root / "other"
        layout.init(other)
        git(other, "push", "-q", str(bare), "HEAD:refs/heads/main")
        layout.init()
        git(self.ws, "remote", "add", "origin", self.url(bare))
        self.assertEqual(self.code(sync.sync, pull=True), "WORKSPACE_UNRELATED_HISTORIES")

    def test_unreachable_remote_keeps_the_commit_and_reports_it(self):
        layout.init()
        git(self.ws, "remote", "add", "origin", "file://" + str(self.root / "missing.git"))
        self.put(self.ws, "plan.json", "{}\n")
        with self.assertRaises(sync.SyncError) as caught:
            sync.sync()
        self.assertEqual(caught.exception.code, "REMOTE_UNREACHABLE")
        self.assertEqual(caught.exception.report["commit"]["status"], "committed")

    def test_no_git_call_uses_a_forbidden_form(self):
        calls = []
        real = gitutil.run

        def spy(argv, *args, **kwargs):
            calls.append(list(argv))
            return real(argv, *args, **kwargs)

        with mock.patch.object(gitutil, "run", side_effect=spy):
            ws_b, (d4, p23) = self.conflict_on_b()
            with self.machine("b"):
                sync.sync(resolve=[f"{d4}=remote", f"{p23}=local"], push=True)
            self.put(self.ws, "plan.json", '{"title": "late"}\n')
            sync.sync(push=True)
        verbs = {verb(call) for call in calls}
        self.assertTrue({"merge-tree", "merge", "push", "fetch", "commit", "checkout"} <= verbs, verbs)
        self.assertEqual([(call, forbidden(call)) for call in calls if forbidden(call)], [])
        pushes = [call for call in calls if verb(call) == "push"]
        self.assertTrue(pushes)
        self.assertTrue(all(call[-1].startswith("HEAD:") for call in pushes))


class CliTests(SyncCase):
    def test_sync_json_and_exit_codes(self):
        self.two_machines()
        code, out, err = self.run_cli("sync", "--commit", "--json")
        self.assertEqual((code, json.loads(out)["commit"]["status"], err), (0, "nothing", ""))
        code, out, err = self.run_cli("sync", "--resolve", "oops")
        self.assertEqual(code, 2)
        self.assertIn("INVALID_ARGUMENT", err)
        code, out, err = self.run_cli("sync", "--pull", "--resolve", "a=local")
        self.assertEqual(code, 2)

    def test_conflict_prints_the_report_and_exits_1(self):
        self.two_machines()
        self.put(self.ws, "plan.json", '{"title": "A"}\n')
        sync.sync(push=True)
        with self.machine("b") as ws_b:
            self.put(ws_b, "plan.json", '{"title": "B"}\n')
            code, out, err = self.run_cli("sync", "--json")
            doc = json.loads(out)
            self.assertEqual(code, 1)
            self.assertIn("WORKSPACE_CONFLICT", err)
            self.assertEqual(doc["conflicts"][0]["ref"], "plan")
            self.assertEqual(doc["error"]["code"], "WORKSPACE_CONFLICT")
            code, out, err = self.run_cli("sync")
            self.assertEqual(code, 1)
            self.assertIn("conflict projects/", out)

    def test_push_prints_remote_and_branch_before_it_runs(self):
        bare = self.bare()
        layout.init()
        self.put(self.ws, "plan.json", "{}\n")
        remote.connect(self.url(bare))
        code, out, err = self.run_cli("sync", "--push")
        self.assertEqual(code, 0, err)
        self.assertLess(out.index(f"pushing to {self.url(bare)} branch main"), out.index("push: pushed"))
        code, out, err = self.run_cli("sync", "--push", "--json")
        doc = json.loads(out)
        self.assertEqual((doc["push"]["remote"], doc["push"]["branch"]), (self.url(bare), "main"))

    def test_events_are_valid_against_their_schemas(self):
        bare = self.bare()
        layout.init()
        self.put(self.ws, "plan.json", "{}\n")
        remote.connect(self.url(bare))
        code, out, err = self.run_cli("sync", "--push")
        self.assertEqual(code, 0, err)
        self.assertNotIn("WORKSPACE_EVENT_NOT_EMITTED", err)


if __name__ == "__main__":
    unittest.main()
