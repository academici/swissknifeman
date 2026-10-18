"""The tracking policy of the workspace repository: the ignore list, the allowlist and the proof that the machine-local
folder of a project is never staged."""
import unittest

from aicore.workspace import (WorkspaceError, ensure_local, local_dir, set_repo_path, write_project)

from tests import TempCase, git, new_code
from workspace import doctor, layout, policy, sync

PLAN = "2026.10.18-n1-DEMO"


class PolicyCase(TempCase):
    def setUp(self):
        super().setUp()
        layout.init("axioma")
        self.pid = new_code()
        write_project(self.ws, self.pid, "p")
        self.folder = self.ws / "projects" / self.pid

    def put(self, relative: str, text: str = "x\n"):
        path = self.folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def local_files(self):
        """A project-local folder as the contract describes it."""
        set_repo_path(self.ws, self.pid, self.checkout("code"))
        self.put("local/state/orch/run.json", "{}\n")
        self.put("local/backups/20261018T100000000000Z/config.toml", "schema_version = 1\n")
        self.put("local/stubs/launcher.py", "# stub\n")
        self.put("local/notes.txt", "mine\n")

    def staged(self):
        git(self.ws, "add", "-A")
        return [line for line in git(self.ws, "diff", "--cached", "--name-only").splitlines() if line]

    def doctor_item(self):
        return {item["check_id"]: item for item in doctor.run_checks()}["workspace.git-policy"]


class IgnoreListTests(PolicyCase):
    def test_init_writes_the_policy_block_into_the_gitignore(self):
        text = (self.ws / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text, layout.GITIGNORE)
        lines = text.splitlines()
        self.assertEqual((lines.count(policy.BEGIN), lines.count(policy.END)), (1, 1))
        for pattern in policy.PATTERNS:
            self.assertIn(pattern, lines)
        self.assertIn("/projects/*/local/", policy.PATTERNS)
        self.assertEqual(policy.missing(self.ws), [])
        self.assertTrue(policy.local_ignored(self.ws))

    def test_the_gitignore_names_no_absolute_path(self):
        for pattern in policy.PATTERNS:
            self.assertNotIn("/home/", pattern)
            self.assertNotIn("~", pattern)

    def test_the_machine_local_folder_is_never_staged(self):
        self.local_files()
        self.put("decisions/D1.json", "{}\n")  # next to local/: a candidate, local/ is not
        staged = self.staged()
        self.assertIn(f"projects/{self.pid}/decisions/D1.json", staged)
        self.assertEqual([path for path in staged if "/local/" in path or path.endswith("/local")], [])
        self.assertEqual(git(self.ws, "ls-files", "--", f"projects/{self.pid}/local"), "")
        status = git(self.ws, "status", "--porcelain", "--untracked-files=all", "--ignored=matching")
        self.assertIn(f"!! projects/{self.pid}/local/", status)

    def test_sync_commit_never_takes_the_local_folder(self):
        self.local_files()
        self.put("plans/" + PLAN + "/plan.json", '{"title": "demo"}\n')
        self.put("decisions/D1.json", "{}\n")
        result = sync.sync(commit=True)
        self.assertEqual(result["commit"]["status"], "committed")
        tracked = git(self.ws, "ls-files").splitlines()
        self.assertIn(f"projects/{self.pid}/project.json", tracked)
        self.assertIn(f"projects/{self.pid}/plans/{PLAN}/plan.json", tracked)
        self.assertIn(f"projects/{self.pid}/decisions/D1.json", tracked)
        self.assertEqual([path for path in tracked if "/local/" in path], [])
        self.assertEqual(git(self.ws, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertEqual(policy.audit(self.ws)["local"], [])

    def test_a_workspace_made_before_the_policy_gets_the_ignore_list_before_anything_is_staged(self):
        (self.ws / ".gitignore").write_text(layout.BASELINE_IGNORE, encoding="utf-8")
        git(self.ws, "add", "-A")
        git(self.ws, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "old workspace")
        self.assertEqual(self.doctor_item()["status"], "warn")
        self.assertIn("POLICY_IGNORE_MISSING", "\n".join(self.doctor_item()["evidence"]))
        self.assertIn("workspace sync --commit", self.doctor_item()["remediation"])
        self.local_files()
        self.put("plans/" + PLAN + "/plan.json", "{}\n")
        sync.sync(commit=True)
        self.assertEqual([path for path in git(self.ws, "ls-files").splitlines() if "/local/" in path], [])
        self.assertEqual(policy.missing(self.ws), [])
        self.assertEqual(self.doctor_item()["status"], "ok")

    def test_what_a_plan_needs_is_tracked_and_the_rest_is_ignored(self):
        tracked = ["project.json", "plans/.gitkeep", f"plans/{PLAN}/plan.json", f"plans/{PLAN}/log.jsonl",
                   f"plans/{PLAN}/phases/P1/P1.1.json", "decisions/D1.json", "legacy-plans/old/plan.json",
                   "migrations/mig_1.json", "local-only.json"]
        ignored = ["local/config.toml", "local/state/x.json", "runs/r1/events.jsonl", f"plans/{PLAN}/runs/r1.json",
                   f"plans/{PLAN}/artifacts/P1.1/executor/stream.jsonl", f"plans/{PLAN}/orch/state.json",
                   "orch-artifacts/run/stage-report.json", ".claude/settings.local.json", ".codex/config.toml",
                   "models.local.toml", "provider.local.json", "dist/app.js", f"plans/{PLAN}/build/out.txt",
                   "node_modules/x/index.js", "tools/__pycache__/x.pyc"]
        for relative in tracked + ignored:
            self.put(relative)
        staged = [path[len(f"projects/{self.pid}/"):] for path in self.staged()
                  if path.startswith(f"projects/{self.pid}/")]
        for relative in tracked:
            self.assertIn(relative, staged)
        for relative in ignored:
            self.assertNotIn(relative, staged)


    def test_publish_safety_blocks_a_local_file_that_an_old_gitignore_lets_through(self):
        from workspace import safety
        (self.ws / ".gitignore").write_text(layout.BASELINE_IGNORE, encoding="utf-8")
        self.local_files()
        report = safety.check(self.ws, True, None, None)
        self.assertIn(f"projects/{self.pid}/local/config.toml", [item["path"] for item in report.block])
        self.assertEqual({item["rule"] for item in report.block}, {"PS-PROJECT-LEVEL"})


class ApplyTests(PolicyCase):
    def test_apply_is_idempotent_and_keeps_the_lines_outside_the_block(self):
        path = self.ws / ".gitignore"
        path.write_text("mine/\n" + layout.GITIGNORE + "after/\n", encoding="utf-8")
        before = path.stat().st_mtime_ns
        self.assertEqual(policy.apply(self.ws), [])
        self.assertEqual(path.stat().st_mtime_ns, before)
        path.write_text("mine/\n" + layout.BASELINE_IGNORE + "after/\n", encoding="utf-8")
        added = policy.apply(self.ws)
        self.assertEqual(added, list(policy.PATTERNS))
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("mine/\n/.staging/\n"))
        self.assertIn("\nafter/\n", text)
        self.assertTrue(text.endswith(policy.END + "\n"))  # a file without a block gets it at the end
        self.assertEqual(policy.missing(self.ws), [])
        self.assertEqual(policy.apply(self.ws), [])

    def test_an_outdated_block_is_replaced_not_duplicated(self):
        path = self.ws / ".gitignore"
        path.write_text(f"a/\n{policy.BEGIN}\n/old/\n{policy.END}\nb/\n", encoding="utf-8")
        policy.apply(self.ws)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("/old/", text)
        self.assertEqual(text.count(policy.BEGIN), 1)
        self.assertTrue(text.startswith("a/\n" + policy.BEGIN))
        self.assertTrue(text.endswith(policy.END + "\nb/\n"))

    def test_a_block_without_an_end_is_refused_and_left_alone(self):
        path = self.ws / ".gitignore"
        text = f"a/\n{policy.BEGIN}\n/old/\n"
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(WorkspaceError) as caught:
            policy.apply(self.ws)
        self.assertEqual(caught.exception.code, "WORKSPACE_LAYOUT_INVALID")
        self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_a_missing_gitignore_is_created(self):
        (self.ws / ".gitignore").unlink()
        self.assertEqual(policy.apply(self.ws), list(policy.PATTERNS))
        self.assertEqual((self.ws / ".gitignore").read_text(encoding="utf-8"), policy.block())


class DoctorPolicyTests(PolicyCase):
    def test_a_fresh_workspace_follows_the_policy(self):
        item = self.doctor_item()
        self.assertEqual((item["status"], item["category"]), ("ok", "state"))

    def test_without_a_workspace_the_check_is_skipped(self):
        import shutil
        shutil.rmtree(self.ws)
        self.assertEqual(self.doctor_item()["status"], "skip")

    def test_a_tracked_file_of_a_local_folder_fails(self):
        self.local_files()
        git(self.ws, "add", "-f", "--", f"projects/{self.pid}/local/config.toml")
        item = self.doctor_item()
        self.assertEqual(item["status"], "fail")
        self.assertIn("POLICY_LOCAL_TRACKED", item["observed"])
        self.assertEqual(item["evidence"], [f"projects/{self.pid}/local/config.toml"])
        self.assertIn("rm -r --cached", item["remediation"])

    def test_a_tracked_file_outside_the_allowlist_and_a_tracked_ignored_file_warn(self):
        self.put("scratch/notes.txt")
        self.put("dist/app.js")
        (self.ws / "stray.txt").write_text("x", encoding="utf-8")
        git(self.ws, "add", "-f", "--", f"projects/{self.pid}/scratch/notes.txt", f"projects/{self.pid}/dist/app.js",
            "stray.txt")
        item = self.doctor_item()
        self.assertEqual(item["status"], "warn")
        text = "\n".join(item["evidence"])
        self.assertIn(f"POLICY_TRACKED_OUTSIDE_ALLOWLIST: projects/{self.pid}/scratch/notes.txt", text)
        self.assertIn("POLICY_TRACKED_OUTSIDE_ALLOWLIST: stray.txt", text)
        self.assertIn(f"POLICY_TRACKED_IGNORED: projects/{self.pid}/dist/app.js", text)

    def test_a_negation_after_the_block_is_reported(self):
        with open(self.ws / ".gitignore", "a", encoding="utf-8") as handle:
            handle.write("!/projects/*/local/\n")
        item = self.doctor_item()
        self.assertEqual(item["status"], "warn")
        self.assertIn("POLICY_LOCAL_NOT_IGNORED", "\n".join(item["evidence"]))

    def test_the_local_folder_is_part_of_the_layout(self):
        ensure_local(self.ws, self.pid)
        self.put("decisions/D1.json")
        layout_item = {item["check_id"]: item for item in doctor.run_checks()}["workspace.layout"]
        self.assertEqual(layout_item["status"], "ok", layout_item)
        self.assertTrue(local_dir(self.ws, self.pid).is_dir())


if __name__ == "__main__":
    unittest.main()
