"""Owner answers survive the native blocked registration, through CLI processes only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import bridge_fixture


class QuestionCycleTests(unittest.TestCase):
    def test_blocked_registration_does_not_stale_the_owner_answer(self):
        with tempfile.TemporaryDirectory(prefix="question-cycle-") as temporary:
            base = Path(temporary)
            project, workspace, home = base / "project", base / "workspaces/test", base / "home"
            project.mkdir()
            workspace.mkdir(parents=True)
            orch = bridge_fixture.partners.find_orch_root()
            self.assertIsNotNone(orch, "SKM_ORCH_ROOT must point at the worktree partner")
            foundation = Path(os.environ["AICORE_ROOT"])
            env = {k: v for k, v in os.environ.items() if not k.startswith(("SKM_", "XDG_", "FAKE_"))
                   and k not in ("GIT_INDEX_FILE", "PYTHONPATH")}
            env.update(HOME=str(home), SKM_HOME=str(home / "skm"), SKM_WORKSPACES_ROOT=str(workspace.parent),
                       SKM_WORKSPACES=str(workspace.parent),
                       SKM_AICORE_EVENTS__DELIVERY="off", AICORE_ROOT=str(foundation), SKM_ORCH_ROOT=str(orch),
                       PLANNER_ROOT=str(bridge_fixture.PLANNER), PLANNER_PLAN_PY=str(bridge_fixture.PLAN_PY),
                       SKM_PLANNER_BRIDGES__ROOTS=json.dumps([str(bridge_fixture.BRIDGE.parent)]),
                       GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       FAKE_ROLE_SCRIPT=str(base / "roles.json"), FAKE_ROLE_STATE=str(base / "roles"))

            def git(repo, *args):
                return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True)

            for repo in (project, workspace):
                git(repo, "init", "-q", "-b", "main")
                for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"),
                                   ("commit.gpgsign", "false")):
                    git(repo, "config", key, value)
            marker = project / ".swissknifeman/project.json"
            marker.parent.mkdir()
            marker.write_text(json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1",
                                          "workspace": "test", "project_id": "question-cycle",
                                          "plans_store": "workspace"}))
            (project / ".git/info/exclude").write_text(".swissknifeman/state/\n.swissknifeman/orch/\n")
            bindings = home / "skm/state/workspaces/test/bindings.json"
            bindings.parent.mkdir(parents=True)
            bindings.write_text(json.dumps({"$schema": "urn:swissknifeman:aicore:workspace-bindings:v1", "projects": {
                "question-cycle": {"paths": [str(project)], "primary": str(project),
                                   "bound_at": "2026-10-22T00:00:00Z"}}}))
            plans = workspace / "projects/question-cycle/plans"
            plans.mkdir(parents=True)

            def plan(*args):
                done = bridge_fixture.plan_py(project, *args, env=env)
                self.assertEqual(done.returncode, 0, done.stderr or done.stdout)
                return done

            actor = "claude-code/claude-sonnet-4-6/high"
            plan("new", "--plans-root", str(plans), "--codename", "Q", "--title", "Question cycle",
                 "--repository", "question-cycle", "--owner", "test", "--actor", actor,
                 "--message", "fixture", "--date", "2026.10.22")
            collection = str(next(plans.iterdir()))
            plan("add-phase", collection, "--title", "One")
            plan("set", collection, "P1", "--json", json.dumps({"goal": "Keep the owner answer"}))
            plan("add-item", collection, "P1", "--title", "Work", "--json", json.dumps({
                "summary": "Make the output", "why": "Exercise the answer binding",
                "scope": {"include": ["out/result.txt"], "exclude": []}, "deliverables": ["output"],
                "task_files": [{"path": "out/result.txt", "change": "create"}],
                "validation": [{"id": "V1", "cmd": "test -f out/result.txt", "expect": "exit 0", "kind": "acceptance"}]}))
            plan("design-done", collection, "P1", "--actor", actor)
            git(project, "add", "-A")
            git(project, "commit", "-q", "-m", "fixture")
            git(workspace, "add", "-A")
            git(workspace, "commit", "-q", "-m", "fixture")

            fake = orch / "tests/fixtures/conductor/fake_role.py"
            config = home / "skm/config/config.toml"
            config.parent.mkdir(parents=True)
            lines = ['schema_version = 1', '[orch]', 'work_source = "planner-orch"', '[orch.conductor.argv]']
            lines += [f'{role} = {json.dumps([sys.executable, str(fake), role])}'
                      for role in ("context-scout", "executor", "reviewer", "triager")]
            lines += ['[aicore.plugins.planner-orch]',
                      f'manifest = {json.dumps(str(bridge_fixture.BRIDGE / "extension.json"))}', 'trusted = true']
            config.write_text("\n".join(lines) + "\n")
            report = {"summary": "fixture", "changed_paths": [], "checks_run": [], "evidence": [], "open_issues": []}
            blocked = dict(report, status="blocked", open_issues=[{"kind": "escalation", "text": "Need owner answer"}],
                           questions=[{"id": "Q1", "revision": 1, "kind": "decision", "text": "Keep the name?",
                                       "options": [{"id": "keep", "label": "Keep"}], "blocking": True}])
            (base / "roles.json").write_text(json.dumps({"executor": [{"result": blocked}, {
                "write": {"out/result.txt": "ok\n"}, "result": dict(report, status="done", changed_paths=["out/result.txt"])}],
                "reviewer": [{"result": {"verdict": "GREEN", "findings": []}}]}))

            first = bridge_fixture.conductor_cli(project, "run", "--plan", collection, "--items", "P1.1", "--json-lines", env=env)
            self.assertEqual(first.returncode, 1, first.stderr)
            rows = [json.loads(line) for line in first.stderr.splitlines() if line.startswith("{")]
            self.assertEqual(rows[-1].get("reason_code"), "ITEM_BLOCKED", first.stderr)
            run = rows[0]["run"]
            # Discover the runtime location without importing the partner's path implementation.
            candidates = list(base.rglob(f"{run}/P1.1/input.json"))
            self.assertEqual(len(candidates), 1, candidates)
            item = candidates[0].parent
            before = json.loads((item / "input.json").read_text())
            registered = json.loads(plan("--output", "json", "get", collection, "P1.1").stdout)["data"]["doc"]
            self.assertEqual(registered["status"], "blocked")  # native conductor registrar changed the source
            answered = bridge_fixture.conductor_cli(project, "answer", "--run", run, "--item", "P1.1",
                                                    "--question", "Q1", "--option", "keep", "--by", "owner", env=env)
            self.assertEqual(answered.returncode, 0, answered.stderr)
            resumed = bridge_fixture.conductor_cli(project, "resume", "--run", run, "--retry", "P1.1", "--json-lines", env=env)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            after = json.loads((item / "input.json").read_text())
            self.assertNotEqual(before["digest"], after["digest"])
            self.assertNotEqual(before["provenance"]["source_digest"], after["provenance"]["source_digest"])
            self.assertIn('"QUESTION_ANSWERED"', resumed.stderr)
            self.assertNotIn('"QUESTION_STALE"', resumed.stderr)
            self.assertIn("Answer: keep (by owner)", (base / "roles/executor-2.md").read_text())
            saved = json.loads((item / "questions.json").read_text())["questions"][0]
            self.assertEqual((saved["status"], saved["resolution"]["by"]), ("applied", "owner"))


if __name__ == "__main__":
    unittest.main()
