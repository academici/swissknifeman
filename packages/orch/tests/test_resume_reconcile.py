"""Interrupted steps recover under the run lease, with fake roles and pipe/FIFO barriers."""
from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import sys
import unittest
from unittest import mock

from orch import adhoc, settings
from orch.conductor import engine, process, progress, prompts
from orch.conductor.application import recovery
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.report import continued
from orch.conductor.infrastructure.files import read_json, write_json
from orch.conductor.policies import risk
from orch.conductor.stages import checks_stage, execute, research, review
from orch.conductor import review_batch
from orch.worksource_file import FileWorkSource
from tests.test_conductor import ConductorCase, FIXTURES, GREEN, ROOT, ROLES, executor_ok, report

BOOT = "import sys; sys.path[:0] = " + repr([str(ROOT / "lib"), str(ROOT.parent / "aicore/lib")]) + "; "
NOTE = "Your previous attempt was interrupted before it reported."

# The first invocation saves partial work and its prompt, then waits in its own session.
# Subsequent invocations use the existing scripted fake role and its normal report contract.
WAIT_ROLE = '''
import json, os, runpy, signal, sys
from pathlib import Path
role = sys.argv[1]
state = Path(os.environ['FAKE_ROLE_STATE'])
state.mkdir(parents=True, exist_ok=True)
marker = state / (role + '.paused')
if role == os.environ['RECOVERY_ROLE'] and not marker.exists():
    prompt = sys.stdin.read()
    marker.touch()
    (state / (role + '.count')).write_text('1')
    (state / (role + '-1.md')).write_text(prompt)
    if role == 'executor':
        Path('out').mkdir(exist_ok=True)
        Path('out/W1.txt').write_text('partial work\\n')
    fd = os.open(os.environ['RECOVERY_FIFO'], os.O_WRONLY)
    os.write(fd, b'ready')
    os.close(fd)
    signal.pause()
else:
    runpy.run_path(sys.argv[2], run_name='__main__')
'''

LAUNCH = '''
from orch.conductor import cli, process
original_wait = process._wait
def wait(child, prompt, raw_path, **kwargs):
    if raw_path.stem == __import__('os').environ['RECOVERY_STEP']:
        print(child.pid, flush=True)  # process.json is already durable at this boundary
    return original_wait(child, prompt, raw_path, **kwargs)
process._wait = wait
raise SystemExit(cli.main(sys.argv[1:]))
'''


class ResumeReconcileTests(ConductorCase):
    def interrupt_role(self, role, step):
        wrapper = self.project.parent / "wait-role.py"
        wrapper.write_text(WAIT_ROLE, encoding="utf-8")
        self.write_config({name: [sys.executable, str(wrapper), name, str(FIXTURES / "fake_role.py")] for name in ROLES})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        fifo = self.project.parent / "role-ready.fifo"
        os.mkfifo(fifo)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        self.addCleanup(os.close, reader)
        env = dict(os.environ, RECOVERY_ROLE=role, RECOVERY_STEP=step, RECOVERY_FIFO=str(fifo))
        # Keep the barrier configuration for the resumed fake role too.
        patcher = mock.patch.dict(os.environ, {key: env[key] for key in ("RECOVERY_ROLE", "RECOVERY_STEP", "RECOVERY_FIFO")})
        patcher.start()
        self.addCleanup(patcher.stop)
        log = open(self.project.parent / "conductor-crash.log", "w+")
        self.addCleanup(log.close)
        child = subprocess.Popen([sys.executable, "-I", "-u", "-c", BOOT + LAUNCH,
                                  "run", "--plan", "T", "--items", "W1", "--json-lines"],
                                 cwd=self.project, env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        def cleanup_child():
            if child.poll() is None:
                child.kill()
            child.wait(timeout=15)
            child.stdout.close()
        self.addCleanup(cleanup_child)
        self.assertTrue(select.select([child.stdout], [], [], 30)[0], "conductor did not reach the role barrier")
        line = child.stdout.readline().strip()
        if not line:
            log.seek(0)
            self.fail("conductor exited before its barrier: " + log.read())
        pid = int(line)
        ticks = process.start_ticks(pid)
        def cleanup_role():
            if process.start_ticks(pid) == ticks:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.addCleanup(cleanup_role)
        self.assertTrue(select.select([reader], [], [], 30)[0], "fake role did not reach the FIFO barrier")
        self.assertEqual(b"ready", os.read(reader, 5))
        directory = next(engine.runs_root(self.project).glob("cnd-*"))
        before = read_json(directory / "state.json")
        self.assertEqual("started", before["items"]["W1"]["steps"][step]["status"])
        child.kill()  # SIGKILL only the conductor; the role deliberately survives until resume
        child.wait(timeout=15)
        self.assertTrue(process._group_alive(pid))
        return directory, pid, before

    def test_sigkill_executor_preserves_partial_work_and_adds_one_note_before_green(self):
        directory, pid, before = self.interrupt_role("executor", "executor.1")
        self.assertEqual("partial work\n", (self.project / "out/W1.txt").read_text())
        paths = recovery.dirty_paths(self.project, 200)
        code, _, err = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual(0, code, err)
        self.assertFalse(process._group_alive(pid))
        self.assertEqual(2, self.calls("executor"))
        base = before["items"]["W1"]["steps"]["executor.1"]["base_head"]
        note = prompts.interrupted_correction(base, paths)
        self.assertEqual(1, self.prompt("executor", 2).count(note))
        after = read_json(directory / "state.json")["items"]["W1"]
        self.assertNotIn("interrupted_note", after)
        self.assertEqual(before["items"]["W1"]["retries_used"], after["retries_used"])
        self.assertTrue(all(row["status"] == "done" for row in after["steps"].values()))
        lines = progress.read_lines(directory)
        killed = next(n for n, row in enumerate(lines) if row.get("reason_code") == "ROLE_ORPHAN_KILLED")
        reconciled = next(n for n, row in enumerate(lines) if row.get("reason_code") == "STAGE_INTERRUPTED")
        restarted = max(n for n, row in enumerate(lines) if row["event"] == "stage.start" and row.get("stage") == "executor.1")
        self.assertLess(killed, reconciled)
        self.assertLess(reconciled, restarted)

    def test_sigkill_review_repeats_read_only_role_without_executor_note(self):
        directory, pid, _ = self.interrupt_role("reviewer", "review.1")
        code, _, err = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual(0, code, err)
        self.assertFalse(process._group_alive(pid))
        self.assertEqual((1, 2), (self.calls("executor"), self.calls("reviewer")))
        self.assertNotIn(NOTE, self.prompt("reviewer", 2))
        rows = [row for row in progress.read_lines(directory) if row.get("reason_code") == "STAGE_INTERRUPTED"]
        self.assertEqual([("review.1", "repeated")], [(row["stage"], row["message"]) for row in rows])

    def opened_run(self, steps, **extra):
        run = engine.Conductor(project=self.project, settings=settings.load(project=self.project), mode="quiet")
        state = {"items": {"W1": {"steps": steps, "retries_used": 0, **extra}}, "claims": {}}
        run._open("cnd-recovery", {"items": ["W1"]}, state)
        run.store.create(run.run_doc)
        run._save()
        return run

    def test_checks_compare_sorted_paths_and_keep_changed_tree(self):
        (self.project / "dirty.txt").write_text("before")
        before = recovery.dirty_paths(self.project)
        self.assertEqual(["dirty.txt"], before)
        for changed in (False, True):
            with self.subTest(changed=changed):
                run = self.opened_run({"checks.1": {"status": "started", "dirty_before": before}})
                if changed:
                    (self.project / "new.txt").write_text("partial check output")
                run._reconcile_interrupted()
                calls = []
                run._step(Item("W1", "run", run.state["items"]["W1"], run.directory / "W1", {}),
                          "checks.1", lambda calls=calls: calls.append("ran") or [])
                self.assertEqual(["ran"], calls)
                lines = progress.read_lines(run.directory)
                latest = [row for row in lines if row.get("reason_code") == "STAGE_INTERRUPTED"][-1]
                self.assertEqual("repeated after tree change" if changed else "repeated", latest["message"])
                self.assertEqual(changed, any(row.get("reason_code") == "CHECK_CHANGED_TREE" for row in lines))
        self.assertEqual("partial check output", (self.project / "new.txt").read_text())

    def test_unknown_started_key_stops_with_no_success_and_releases_resume_lease(self):
        run = self.opened_run({"mystery.1": {"status": "started"}})
        with self.assertRaises(engine.Stop) as caught:
            run.resume(run.run_id)
        self.assertEqual("STAGE_RECOVERY_UNKNOWN", caught.exception.code)
        self.assertEqual("W1 mystery.1: no recovery rule; settle the item or retry it", caught.exception.message)
        self.assertEqual("started", read_json(run.directory / "state.json")["items"]["W1"]["steps"]["mystery.1"]["status"])
        self.assertEqual("no recovery rule", progress.read_lines(run.directory)[-1]["message"])
        from orch.conductor.infrastructure.lease import RunLease
        self.assertFalse(RunLease.held(run.directory))

    def test_unknown_started_key_can_be_settled_then_resumed_without_repeating_work(self):
        self.script({"executor": [{"text": "", "exit": 0}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(1, code, err)
        directory = self.run_dir(err)
        state = read_json(directory / "state.json")
        completed = done_steps(state["items"]["W1"]["steps"])
        state["items"]["W1"]["steps"]["mystery.1"] = {"status": "started"}
        state["items"]["W1"]["steps"]["mystery.2"] = {"status": "stopped", "code": "UNKNOWN"}
        write_json(directory / "state.json", state)
        code, _, err = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual(1, code, err)
        self.assertIn("STAGE_RECOVERY_UNKNOWN", err)
        code, _, err = self.conduct("settle", "--run", directory.name, "--item", "W1", "--outcome", "done",
                                    "--reason", "finished by the owner")
        self.assertEqual(0, code, err)
        count = self.calls("executor")
        code, _, err = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual(0, code, err)
        after = read_json(directory / "state.json")["items"]["W1"]
        self.assertEqual("done", after["outcome"])
        self.assertEqual(completed, after["steps"])
        self.assertEqual(count, self.calls("executor"))
        self.assertNotIn("STAGE_INTERRUPTED", err)

    def test_retry_discards_unknown_unfinished_steps_before_reconciliation(self):
        self.script({"executor": [{"result": report("W1", "blocked")}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(1, code, err)
        directory = self.run_dir(err)
        state = read_json(directory / "state.json")
        item = state["items"]["W1"]
        self.assertEqual("blocked", item["outcome"])
        item["steps"]["mystery.1"] = {"status": "started"}
        item["steps"]["mystery.2"] = {"status": "stopped", "code": "UNKNOWN"}
        write_json(directory / "state.json", state)
        source = self.source()
        source["items"]["W1"]["status"] = "todo"
        source["registered"].clear()
        self.state_file.write_text(json.dumps(source), encoding="utf-8")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        reconcile = engine.Conductor._reconcile_interrupted
        def check_retry_applied(run):
            pending = run.state["items"]["W1"]
            self.assertIsNone(pending.get("outcome"))
            self.assertNotIn("mystery.1", pending["steps"])
            self.assertNotIn("mystery.2", pending["steps"])
            return reconcile(run)
        with mock.patch.object(engine.Conductor, "_reconcile_interrupted", check_retry_applied):
            code, _, err = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--json-lines")
        self.assertEqual(0, code, err)
        after = read_json(directory / "state.json")["items"]["W1"]
        self.assertEqual("done", after["outcome"])
        self.assertNotIn("mystery.1", after["steps"])
        self.assertNotIn("mystery.2", after["steps"])
        self.assertNotIn("STAGE_INTERRUPTED", err)
        self.assertEqual(2, self.calls("executor"))

    def test_closed_outcomes_discard_only_started_and_stopped_records(self):
        completed = {"status": "done", "result": {"kept": True, "input_path": "input.json"}}  # a brief result (records/v1)
        for outcome in ("done", "done_with_deviations", "blocked", "abandoned"):
            with self.subTest(outcome=outcome):
                run = self.opened_run({"mystery.1": {"status": "started"},
                                       "mystery.2": {"status": "stopped", "code": "UNKNOWN"},
                                       "brief": completed}, outcome=outcome)
                run._reconcile_interrupted()
                saved = read_json(run.directory / "state.json")["items"]["W1"]
                self.assertEqual(outcome, saved["outcome"])
                self.assertEqual({"brief": completed}, saved["steps"])
                self.assertNotIn("STAGE_INTERRUPTED", [row.get("reason_code") for row in progress.read_lines(run.directory)])

    def test_retry_still_refuses_an_unblocked_interrupted_item(self):
        run = self.opened_run({"mystery.1": {"status": "started"}}, outcome="stopped")
        before = (run.directory / "state.json").read_bytes()
        with self.assertRaises(engine.Stop) as caught:
            run.resume(run.run_id, retry=["W1"])
        self.assertEqual("RETRY_NOT_BLOCKED", caught.exception.code)
        self.assertEqual(before, (run.directory / "state.json").read_bytes())

    def test_old_done_state_and_stopped_step_resume_without_interruption_note(self):
        self.script({"executor": [{"text": "", "exit": 0}], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(1, code)
        directory = self.run_dir(err)
        state = read_json(directory / "state.json")
        self.assertEqual("stopped", state["items"]["W1"]["steps"]["executor.1"]["status"])
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, resumed = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual(0, code, resumed)
        self.assertNotIn(NOTE, self.prompt("executor", 2))
        self.assertNotIn("STAGE_INTERRUPTED", [row.get("reason_code") for row in progress.read_lines(directory)])
        # A legacy state contains done records only; resuming it must skip their work.
        counts = (self.calls("executor"), self.calls("reviewer"))
        code, _, resumed = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual(0, code, resumed)
        self.assertEqual(counts, (self.calls("executor"), self.calls("reviewer")))

    def test_every_l10_repeat_rule_and_executor_note_survive_repeated_resume(self):
        keys = ("brief", "prepare", "scout", "research.2", "review.3", "triage.3-a", "advice.1", "research-save.2",
                "close", "register", "commit")
        run = self.opened_run({key: {"status": "started"} for key in keys})
        run._reconcile_interrupted()
        self.assertEqual({}, run.state["items"]["W1"]["steps"])
        self.assertEqual(len(keys), len(progress.read_lines(run.directory)))
        item = run.state["items"]["W1"]
        item["steps"]["executor.2"] = {"status": "started", "base_head": "abc"}
        run._reconcile_interrupted()
        note = item["interrupted_note"]["executor.2"]
        run._reconcile_interrupted()  # another crash before the loop must not lose or duplicate the note
        self.assertEqual({"executor.2": note}, item["interrupted_note"])
        self.assertEqual(1, note.count(NOTE))
        self.assertEqual(0, item["retries_used"])

    def test_readers_ignore_started_and_stopped_even_with_result_like_fields(self):
        incomplete = {"status": "started", "result": {"report": {"review_recommendation": {"recommended": True}},
                                                     "sha": "wrong", "changed": ["wrong"]}}
        steps = {key: dict(incomplete) for key in ("executor.1", "executor.1-q1", "checks.1", "review.1", "commit", "scout",
                                                  "research.1", "research-save.1")}
        item = Item("W1", "run", {"steps": steps}, self.project, {}, options={"review": {}, "checks": {"red_first": True}})
        run = self.opened_run(steps)
        self.assertEqual({}, done_steps(steps))
        self.assertEqual(set(), continued(steps))
        self.assertFalse(risk.recommended(steps))
        self.assertEqual([], risk.first_checks(steps))
        self.assertEqual([], checks_stage.red_before(item, 2))
        self.assertEqual({}, research.researched(item))
        self.assertEqual(set(), research.paths(item))
        self.assertEqual([], execute.changed(run, item))
        self.assertEqual(([], []), review_batch.commits_of_state({"items": {"W1": item.state}}))
        self.assertFalse(run._work_began(item.state))
        item.state["executor_started"] = True
        self.assertTrue(run._work_began(item.state))  # actual role work still prevents release after a crash
        with mock.patch.object(run, "_write_artifact") as write:
            review.verdict_file(run, item)
            self.assertEqual([], write.call_args.args[2]["rounds"])
        steps["review.1"]["status"] = "stopped"
        self.assertEqual({}, done_steps(steps))

    def test_research_save_repeats_idempotently_after_effect_before_done(self):
        doc = adhoc.build_adhoc_input("Make output", ["out.txt"], checks=["V1=test -f out.txt"])
        path = self.project.parent / "input.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        source = FileWorkSource(path, project=self.project)
        fields = {"plan": str(path), "ref": doc["input_id"], "run_id": "work-run", "number": 2,
                  "result": {"query": "q"}}
        first = source.research(**fields)
        self.assertEqual("recorded", first["outcome"])
        target = self.project / first["path"]
        before = target.read_bytes()
        run = self.opened_run({"research-save.2": {"status": "started"}})
        run._reconcile_interrupted()
        item = Item("W1", "work-run", run.state["items"]["W1"], run.directory / "W1", {})
        result = run._step(item, "research-save.2", lambda: source.research(**fields))
        self.assertEqual("no-op", result["outcome"])
        self.assertEqual(before, target.read_bytes())
        self.assertEqual([target], list(target.parent.glob("research-*.json")))

    def test_porcelain_paths_include_renames_spaces_and_apply_sorted_caps(self):
        (self.project / "README.md").rename(self.project / "new name.md")
        self.git("add", "-A")
        self.assertEqual(["README.md", "new name.md"], recovery.dirty_paths(self.project))
        for index in range(510):
            (self.project / f"z{index:03}.txt").touch()
        paths = recovery.dirty_paths(self.project)
        self.assertEqual(500, len(paths))
        self.assertEqual(sorted(paths), paths)
        text = prompts.interrupted_correction("base", paths)
        self.assertIn("z197.txt", text)
        self.assertNotIn("z198.txt", text)

    def test_overlap_records_checks_before_background_work_and_preserves_dirty_before(self):
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"checks": {"overlap_review": True}}}]}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        original = engine.Conductor._compute_checks
        before = []
        def compute(run, item, number, report, on_result=None):
            row = read_json(run.directory / "state.json")["items"]["W1"]["steps"][f"checks.{number}"]
            self.assertEqual("started", row["status"])
            before.append(row["dirty_before"])
            self.assertEqual(recovery.dirty_paths(self.project), row["dirty_before"])
            return original(run, item, number, report, on_result)
        with mock.patch.object(engine.Conductor, "_compute_checks", compute):
            code, _, err = self.run_items("W1")
        self.assertEqual(0, code, err)
        self.assertEqual(1, len(before))


    def test_a_stop_of_the_overlapping_review_with_failed_checks_leaves_the_checks_stopped(self):
        """W2: the checks step began outside step(); a review Stop other than REVIEW_CANCELLED while the checks failed
        must close it as stopped, or a resume reports a false STAGE_INTERRUPTED."""
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"checks": {"overlap_review": True}}}]}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})

        def review(run, item, number, rows, pending=False, cancel=None):
            raise engine.Stop("TOKEN_BUDGET", "spent while reviewing")

        def compute(run, item, number, report, on_result=None):
            raise engine.Stop("CHECKS_FAILED", "the checks could not run")

        with mock.patch.object(engine.Conductor, "_review", review), \
                mock.patch.object(engine.Conductor, "_compute_checks", compute):
            code, _, err = self.run_items("W1")
        self.assertEqual(1, code, err)
        steps = read_json(self.run_dir(err) / "state.json")["items"]["W1"]["steps"]
        self.assertEqual((steps["checks.1"]["status"], steps["checks.1"]["code"]), ("stopped", "TOKEN_BUDGET"))

    def test_the_interruption_note_says_plainly_when_there_is_no_git_or_no_change(self):
        self.assertNotIn("None", prompts.interrupted_correction(None, ["a.py"]))
        self.assertIn("not a git checkout", prompts.interrupted_correction(None, ["a.py"]))
        clean = prompts.interrupted_correction("abc123", [])
        self.assertIn("shows no change since abc123", clean)
        self.assertNotIn(": .", clean)
        self.assertNotIn("None", prompts.interrupted_correction(None, []))

if __name__ == "__main__":
    unittest.main()
