"""Observer polish before P13: messages that name verbs that exist, a repeated ``--retry``."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from orch.conductor import checks as checks_mod
from orch.conductor import frozen, options as opts, prompts, review_batch
from orch.conductor.application import loop
from orch.conductor.stages import context
from orch.conductor.infrastructure import disk, roles

from orch.conductor.application import run_service
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import work_source


class OwnedPieceHint(unittest.TestCase):
    def test_item_owned_names_the_conductor_verbs_and_not_only_take_over(self):
        hint = work_source.owned_hint({"reason_code": "START_REFUSED", "message": "ITEM_OWNED: P1.1 is in progress by x"})
        self.assertIn("orch conduct release --run RUN --item REF", hint)
        self.assertIn("settle", hint)

    def test_other_refusals_get_no_hint(self):
        self.assertEqual(work_source.owned_hint({"reason_code": "SCENARIO_UNKNOWN", "message": "nope"}), "")

    def test_the_blocked_claim_carries_the_hint(self):
        answer = {"status": "blocked", "ref": "W1", "reason_code": "ITEM_OWNED", "message": "held"}
        me = types.SimpleNamespace(
            _claim_actor=lambda: "p/m", _claim_actor_source=lambda: ("default", None, None), state={"claims": {}}, run_doc={"plan": "T"}, run_id="r", progress=mock.Mock(),
            _orch=lambda *args: (1, answer, ""), _save=lambda: None)
        with self.assertRaises(Stop) as stop:
            work_source.claim(me, "k", ["W1"])
        self.assertEqual(stop.exception.code, "CLAIM_BLOCKED")
        self.assertIn("orch conduct release", stop.exception.message)


class ClaimOverrideRecord(unittest.TestCase):
    def test_a_repeated_claim_without_an_override_keeps_the_recorded_one(self):
        """A group review claims its last, closed piece again: the source answers without actor_override."""
        override = {"reason_code": "ACTOR_OVERRIDE", "ref": "W1", "plan": {"provider": "codex", "model": "m"},
                    "run": {"provider": "claude-code", "model": "opus"}, "message": "W1: replaced"}
        answer = {"status": "claimed", "ref": "W1", "run_id": "src-1"}
        me = types.SimpleNamespace(
            _claim_actor=lambda: "p/m", _claim_actor_source=lambda: ("options", ["provider", "model"], None),
            state={"claims": {"k": {"ref": "W1", "submission": "sub-r-k", "actor_override": override}}},
            run_doc={"plan": "T"}, run_id="r", progress=mock.Mock(), _orch=lambda *args: (0, answer, ""),
            _save=lambda: None)
        work_source.claim(me, "k", ["W1"])
        self.assertEqual(me.state["claims"]["k"]["actor_override"], override)
        me.progress.emit.assert_not_called()  # said once, at the first claim


class RepeatedRetry(unittest.TestCase):
    def fake(self, item: dict):
        return types.SimpleNamespace(state={"items": {"W1": item}, "questions": {}}, _save=lambda: None, progress=mock.Mock(),
                                     directory=Path(tempfile.mkdtemp()))

    def blocked(self) -> dict:
        return {"outcome": "blocked", "stop": {}, "steps": {"brief": {"status": "done", "ended": "1"},
                "executor.1": {"status": "done", "ended": "2", "result": {"report": {"status": "blocked"}}}}}

    def test_a_retry_marks_the_piece_and_a_second_retry_after_a_stop_is_not_an_error(self):
        me = self.fake(self.blocked())
        run_service.retry(me, "W1")
        item = me.state["items"]["W1"]
        self.assertTrue(item["retried"])
        item["outcome"] = "stopped"  # the resume stopped again before the piece was closed
        run_service.retry(me, "W1")  # same command again: no RETRY_NOT_BLOCKED
        self.assertEqual(item["outcome"], "stopped")

    def test_a_piece_never_retried_and_not_blocked_is_still_refused(self):
        me = self.fake({"outcome": "stopped", "steps": {}})
        with self.assertRaises(Stop) as stop:
            run_service.retry(me, "W1")
        self.assertEqual(stop.exception.code, "RETRY_NOT_BLOCKED")


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:  # a zombie of a killed child still answers signal 0
        return Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


def wait_dead(pid: int, seconds: float = 10) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return False


class CheckProcessGroup(unittest.TestCase):
    """A check leaves nothing running: not after an interrupt of the run, not after its own end."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def spawn_cmd(self, tail: str) -> list:
        pid_file = self.dir / "worker.pid"
        return ["bash", "-c", f"sleep 120 & echo $! > {pid_file}; {tail}"]

    def worker(self) -> int:
        for _ in range(100):
            text = (self.dir / "worker.pid").read_text() if (self.dir / "worker.pid").exists() else ""
            if text.strip():
                return int(text)
            time.sleep(0.05)
        self.fail("the check started no worker")

    def test_a_check_that_ends_takes_its_background_workers_with_it(self):
        with open(self.dir / "log", "wb") as out:
            code = checks_mod._run_command(self.spawn_cmd("exit 0"), cwd=self.dir, out=out, timeout_s=0, warn_s=0)
        self.assertEqual(code, 0)
        self.assertTrue(wait_dead(self.worker()))

    def test_the_time_a_check_is_stopped_is_not_counted(self):
        seen = []

        def on_slow(elapsed, _pid):
            seen.append(elapsed)

        def pause_then_continue():
            time.sleep(0.5)
            os.killpg(proc_pid[0], signal.SIGSTOP)
            time.sleep(2.0)
            os.killpg(proc_pid[0], signal.SIGCONT)

        proc_pid = []
        real = checks_mod.subprocess.Popen

        def popen(*args, **kwargs):
            process = real(*args, **kwargs)
            proc_pid.append(process.pid)
            threading.Thread(target=pause_then_continue, daemon=True).start()
            return process

        with mock.patch.object(checks_mod, "POLL_S", 0.1), mock.patch.object(checks_mod.subprocess, "Popen", popen), \
                open(self.dir / "log", "wb") as out:
            code = checks_mod._run_command(["python3", "-c", "import time\nt = time.process_time()\nwhile time.process_time() - t < 1.6: pass"],
                                           cwd=self.dir, out=out, timeout_s=0, warn_s=1,
                                           on_slow=on_slow)
        self.assertEqual(code, 0)
        self.assertTrue(seen)
        # about 1.6 s of work and 2 s stopped (3.6 s on the wall): the beacon never saw more than the work and the polls' slack
        self.assertLess(max(seen), 2.9)

    def test_an_interrupt_kills_the_check_and_its_workers(self):
        def interrupt(_elapsed, _pid):
            raise KeyboardInterrupt

        with mock.patch.object(checks_mod, "POLL_S", 0.1), open(self.dir / "log", "wb") as out:
            with self.assertRaises(KeyboardInterrupt):
                checks_mod._run_command(self.spawn_cmd("sleep 120"), cwd=self.dir, out=out, timeout_s=0, warn_s=1,
                                        on_slow=interrupt)
        self.assertTrue(wait_dead(self.worker()))


class TerminatedRun(unittest.TestCase):
    def test_sigterm_and_sighup_become_an_interrupt_and_the_handlers_are_restored(self):
        before = {n: signal.getsignal(n) for n in (signal.SIGTERM, signal.SIGHUP)}
        seen = {}

        def pieces():
            seen["handlers"] = {n: signal.getsignal(n) for n in (signal.SIGTERM, signal.SIGHUP)}
            with self.assertRaises(KeyboardInterrupt):
                seen["handlers"][signal.SIGTERM](signal.SIGTERM, None)
            raise KeyboardInterrupt

        me = types.SimpleNamespace(_pieces=pieces, _disk_guard=lambda: None, state={"items": {}}, _segment=None,
                                   _active_s=lambda: 0.0, _save=lambda: None, directory=Path("."), project=Path("."),
                                   reports_dir=lambda: Path("."), progress=mock.Mock(), run_doc={})
        with mock.patch.object(loop.observer, "write_report", side_effect=RuntimeError("no report")):
            self.assertEqual(loop.loop(me), 130)
        self.assertEqual(seen["handlers"], {signal.SIGTERM: loop.terminated, signal.SIGHUP: loop.terminated})
        self.assertEqual({n: signal.getsignal(n) for n in before}, before)


class DiskGuard(unittest.TestCase):
    def test_a_shortage_names_the_filesystem_and_the_limit(self):
        with mock.patch.object(disk, "free_gb", return_value=1.5):
            found = disk.shortage(Path("."), 5)
        self.assertIn("1.5 GB free", found)
        self.assertIn("limits.disk_min_gb 5", found)

    def test_enough_space_and_a_zero_limit_say_nothing(self):
        with mock.patch.object(disk, "free_gb", return_value=50.0):
            self.assertIsNone(disk.shortage(Path("."), 5))
        with mock.patch.object(disk, "free_gb", return_value=0.0):
            self.assertIsNone(disk.shortage(Path("."), 0))

    def test_the_guard_stops_the_run_with_a_resumable_code_and_a_beacon(self):
        from orch.conductor.domain.stop import Stop
        me = types.SimpleNamespace(project=Path("."), conductor={}, progress=mock.Mock())
        with mock.patch.object(disk, "free_gb", return_value=0.2):
            with self.assertRaises(Stop) as stop:
                loop.disk_guard(me)
        self.assertEqual(stop.exception.code, "DISK_LOW")
        self.assertEqual(me.progress.emit.call_args.kwargs["reason_code"], "DISK_LOW")

    def test_the_limit_of_the_piece_wins_over_the_default_and_the_configuration(self):
        item = types.SimpleNamespace(ref="W1", options={"limits": {"disk_min_gb": 0}})
        me = types.SimpleNamespace(project=Path("."), conductor={"limits": {"disk_min_gb": 99}}, progress=mock.Mock())
        with mock.patch.object(disk, "free_gb", return_value=0.2):
            loop.disk_guard(me, item)  # the piece switched it off: no stop
        me = types.SimpleNamespace(project=Path("."), conductor={"limits": {"disk_min_gb": 99}}, progress=mock.Mock())
        with mock.patch.object(disk, "free_gb", return_value=50.0), self.assertRaises(Stop):
            loop.disk_guard(me)  # the configuration's limit applies without a piece


CLEAN = "## Findings\nnone\n## Checked and fine\n- the claim path\n"
DRESSED = ("Here is my review.\n\n## Findings\n1. **[Major]** `lib/a.py:12` - wrong state on resume\n   Scenario: x -> y\n"
           "- [Minor] lib/b.py:3 - a nit\n- `[Blocker]` lib/c.py:7 - unsafe path\n\n## Checked and fine\n- [Major] in a bullet here\n")


class ReviewVerdict(unittest.TestCase):
    def test_a_clean_reply_is_none_and_counts_nothing(self):
        read = review_batch.verdict(CLEAN)
        self.assertEqual((read["format"], read["counts"]), ("none", {"Blocker": 0, "Major": 0, "Minor": 0}))

    def test_findings_dressed_as_list_items_numbers_bold_or_code_are_counted(self):
        read = review_batch.verdict(DRESSED)
        self.assertEqual(read["format"], "findings")
        self.assertEqual(read["counts"], {"Blocker": 1, "Major": 1, "Minor": 1})  # the line under "Checked and fine" is not one
        self.assertEqual([row["location"] for row in read["findings"]], ["lib/a.py:12", "lib/b.py:3", "lib/c.py:7"])

    def test_a_reply_in_another_format_is_malformed_and_never_clean(self):
        for text in ("The change looks fine to me.", "", "## Review\nAll good", "## Findings\nIt seems OK, nothing serious.\n"):
            self.assertEqual(review_batch.verdict(text)["format"], "malformed", text)

    def test_the_paths_to_correct_come_from_blocker_and_major_findings_only(self):
        read = review_batch.verdict(DRESSED)
        self.assertEqual(review_batch.followup_paths(read["findings"]), ["lib/a.py", "lib/c.py"])
        hostile = review_batch.verdict("## Findings\n[Major] ../../etc/passwd:1 - x\n[Major] /abs/p.py:1 - y\n")
        self.assertEqual(review_batch.followup_paths(hostile["findings"]), [])

    def test_counts_keeps_its_old_meaning(self):
        self.assertEqual(review_batch.counts("## Findings\n[Major] a.py:1 - d\n")["Major"], 1)


class SessionRoute(unittest.TestCase):
    def me(self, state: dict):
        return types.SimpleNamespace(state=state, _shared_session=lambda item, role, route: True, progress=mock.Mock(),
                                     _session_mode=lambda item: "shared")  # a later piece resumes only a shared session

    def test_a_piece_on_another_model_resumes_the_session_and_says_so_once(self):
        item = types.SimpleNamespace(ref="W2")
        me = self.me({"executor_session": "s1", "executor_session_route": "claude-code/claude-haiku-5-5/low"})
        route = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
        self.assertEqual(roles.resume_args(me, item, "executor", route), ["--resume", "s1"])
        self.assertEqual(roles.resume_args(me, item, "executor", route), ["--resume", "s1"])
        emitted = [call.kwargs["reason_code"] for call in me.progress.emit.call_args_list]
        self.assertEqual(emitted, ["SESSION_ROUTE_CHANGED"])

    def test_the_same_route_says_nothing_and_no_session_gives_no_resume(self):
        item = types.SimpleNamespace(ref="W2")
        route = {"provider": "claude-code", "model": "m", "effort": "high"}
        me = self.me({"executor_session": "s1", "executor_session_route": "claude-code/m/high"})
        self.assertEqual(roles.resume_args(me, item, "executor", route), ["--resume", "s1"])
        me.progress.emit.assert_not_called()
        self.assertEqual(roles.resume_args(self.me({}), item, "executor", route), [])

    def test_keep_session_records_the_route_and_forgets_it_with_a_failed_session(self):
        item, route = types.SimpleNamespace(ref="W1"), {"provider": "claude-code", "model": "m", "effort": "low"}
        me = self.me({})
        me._save = lambda: None
        roles.keep_session(me, item, "executor", route, types.SimpleNamespace(error=None, session="s9"))
        self.assertEqual((me.state["executor_session"], me.state["executor_session_route"]), ("s9", "claude-code/m/low"))
        roles.keep_session(me, item, "executor", route, types.SimpleNamespace(error="ROLE_FAILED", session=None))
        self.assertNotIn("executor_session_route", me.state)


class FrozenMode(unittest.TestCase):
    def hub(self) -> Path:
        import subprocess
        base = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(base, True))
        hub = base / "hub"
        for path in ("packages/orch", "bridges/one"):
            (hub / path / "lib").mkdir(parents=True)
            (hub / path / "lib" / "mark.txt").write_text(f"committed {path}\n")
        (hub / "packages" / "orch" / "scripts").mkdir(parents=True)
        (hub / "packages" / "orch" / "scripts" / "conduct.py").write_text("print('frozen entry')\n")
        git = lambda *a: subprocess.run(["git", "-C", str(hub), *a], check=True, capture_output=True)
        git("init", "-q")
        git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
        git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "c")
        (hub / "packages" / "orch" / "lib" / "mark.txt").write_text("edited after the commit\n")  # not in the snapshot
        return hub

    def test_the_snapshot_is_the_committed_state_and_holds_the_four_paths(self):
        hub = self.hub()
        target = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(target, True))
        frozen.freeze(hub, target)
        self.assertEqual((target / "packages/orch/lib/mark.txt").read_text(), "committed packages/orch\n")
        self.assertTrue((target / "bridges/one/lib/mark.txt").is_file())

    def test_the_command_line_loses_frozen_and_project_and_keeps_the_rest(self):
        self.assertEqual(frozen.strip(["--config", "c.toml", "--project", "/x", "run", "--plan", "P", "--items", "A", "B", "--frozen"]),
                         ["--config", "c.toml", "run", "--plan", "P", "--items", "A", "B"])
        self.assertEqual(frozen.strip(["--project=/x", "resume", "--run", "R", "--frozen"]), ["resume", "--run", "R"])

    def test_every_path_inside_the_checkout_points_into_the_snapshot_and_pythonpath_is_dropped(self):
        hub = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(hub, True))
        (hub / "packages" / "a").mkdir(parents=True)
        env = frozen.environment(Path("/snap"), hub, {"PYTHONPATH": str(hub / "lib"), "KEEP": "1", "OTHER": "/elsewhere/x",
                                                       "ROOT_A": str(hub / "packages" / "a"), "TEXT": "not a path"})
        self.assertEqual((env["ROOT_A"], env["OTHER"], env["KEEP"], env["TEXT"]),
                         ("/snap/packages/a", "/elsewhere/x", "1", "not a path"))
        self.assertNotIn("PYTHONPATH", env)

    def test_relaunch_runs_the_entry_of_the_snapshot_with_the_project_and_removes_the_snapshot(self):
        hub = self.hub()
        cache = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(cache, True))
        seen, real = {}, frozen.subprocess.run

        def fake_run(command, env=None, cwd=None, **kwargs):
            if command[0] == "git":  # the snapshot is really taken
                return real(command, **kwargs)
            seen.update(command=command, env=env, cwd=cwd, entry=Path(command[1]).read_text())
            return types.SimpleNamespace(returncode=7)

        with mock.patch.object(frozen, "hub_root", return_value=hub), mock.patch.object(frozen, "CACHE", cache), \
                mock.patch.object(frozen.subprocess, "run", fake_run):
            code = frozen.relaunch(["run", "--plan", "P", "--items", "A", "--frozen"], Path("/the/project"))
        self.assertEqual(code, 7)
        self.assertEqual(seen["entry"], "print('frozen entry')\n")
        self.assertEqual(seen["command"][2:], ["--project", "/the/project", "run", "--plan", "P", "--items", "A"])
        self.assertEqual(list(cache.iterdir()), [])  # the snapshot is gone

    def test_a_checkout_without_the_sources_cannot_be_frozen(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, True))
        with mock.patch.object(frozen, "ORCH_ROOT", outside):
            with self.assertRaises(frozen.FrozenError) as stop:
                frozen.hub_root()
        self.assertEqual(stop.exception.code, "FROZEN_UNAVAILABLE")


class PreviewBatchKeys(unittest.TestCase):
    """``--dry-run`` says whether the run is a batch (the default for several pieces), apart from ``--ready``."""

    def preview(self, items, ready=False, batch=None) -> dict:
        from orch.conductor import cli
        args = types.SimpleNamespace(scenario=None, options=None, plan="P", input=None, items=items, ready=ready, batch=batch)
        item = types.SimpleNamespace(routes={}, policy={}, options={"reviewer": "x", "fallback_routes": []}, sources={},
                                     route_notes=[])
        conductor = types.SimpleNamespace(run_id="", run_doc={}, settings=types.SimpleNamespace(default_profile="solo"),
                                          _resolve=lambda *a, **k: None, _routes=lambda *a, **k: None,
                                          _sandbox_mode=lambda it: "off", _claim_actor=lambda: "p/m")
        with mock.patch.object(cli.engine, "Item", return_value=item), \
                mock.patch.object(cli.sandbox, "probe", return_value={"available": False, "reason": "test"}):
            return cli._preview(conductor, args)

    def test_several_pieces_are_a_batch_unless_no_batch(self):
        self.assertEqual(self.preview(["A", "B"])["batch"], True)
        self.assertEqual(self.preview(["A", "B"], batch=False)["batch"], False)
        self.assertEqual(self.preview(["A"])["batch"], False)
        shown = self.preview(None, ready=True)
        self.assertEqual((shown["batch"], shown["ready"]), (True, True))


class PreviewClaimActor(unittest.TestCase):
    """``--dry-run`` shows the actor a real run claims with, and warns when the claim would not match the routed executor."""

    def preview(self, claim_actor="codex/gpt-6.1-sol/xhigh", executor=None):
        from orch.conductor import cli
        args = types.SimpleNamespace(scenario=None, options=None, plan="P", input=None, items=["A"], ready=False, batch=None)
        routes = {"executor": executor or {"provider": "codex", "model": "gpt-6.1-sol", "effort": "xhigh",
                                           "argv": ["codex"]}}
        item = types.SimpleNamespace(routes=routes, policy={}, options={"reviewer": "x", "fallback_routes": []}, sources={},
                                     route_notes=[])
        conductor = types.SimpleNamespace(
            run_id="", run_doc={}, settings=types.SimpleNamespace(default_profile="solo"), _resolve=lambda *a, **k: None,
            _routes=lambda *a, **k: None, _sandbox_mode=lambda it: "off", _claim_actor=lambda: claim_actor,
            route_problem=lambda route: None, _role_argv=lambda it, role, route: route["argv"],
            declared_network=lambda role: "none", _codex_sandboxed=lambda route: False, _claude_bash=lambda route: False)
        with mock.patch.object(cli.engine, "Item", return_value=item), \
                mock.patch.object(cli.sandbox, "probe", return_value={"available": True, "reason": ""}):
            return cli._preview(conductor, args)

    def test_the_claim_actor_is_shown_and_a_matching_route_has_no_warning(self):
        shown = self.preview()
        self.assertEqual(shown["claim_actor"], "codex/gpt-6.1-sol/xhigh")
        self.assertFalse([w for w in shown["warnings"] if "claim" in w], shown["warnings"])

    def test_a_claim_that_differs_from_the_routed_executor_is_a_warning(self):
        shown = self.preview(claim_actor="claude-code/claude-opus-5-5")
        self.assertEqual(shown["claim_actor"], "claude-code/claude-opus-5-5")
        gap = [w for w in shown["warnings"] if "the claim names" in w]
        self.assertEqual(len(gap), 1, shown["warnings"])
        self.assertIn("provider, model differ", gap[0])

    def test_an_effort_the_claim_names_must_match_the_route(self):
        shown = self.preview(claim_actor="codex/gpt-6.1-sol/high")
        self.assertTrue(any("effort differ" in w for w in shown["warnings"]), shown["warnings"])

    def test_a_claim_without_effort_does_not_contradict_a_route_with_one(self):
        shown = self.preview(claim_actor="codex/gpt-6.1-sol")
        self.assertFalse([w for w in shown["warnings"] if "the claim names" in w], shown["warnings"])


class DiffForReview(unittest.TestCase):
    def test_headers_alone_are_no_diff(self):
        self.assertFalse(review_batch.has_hunks("diff --git a/x b/x\nindex 1..2 100644\n--- a/x\n+++ b/x\n"))
        self.assertTrue(review_batch.has_hunks("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"))

    def test_the_whole_project_is_read_by_default(self):
        self.assertEqual(review_batch.INCLUDE, ["."])


class ReadableErrors(unittest.TestCase):
    def test_a_schema_violation_names_its_path_once(self):
        from orch.conductor import contract
        self.assertEqual(contract.problems({"limits": {"nope": 1}}, "run-options"), ["/limits/nope: unexpected property 'nope'"])
        self.assertEqual(contract.problems({"limits": {"disk_min_gb": "x"}}, "run-options"),
                         ["/limits/disk_min_gb: expected integer, got string"])


class TranscriptFolder(unittest.TestCase):
    def test_the_name_is_every_non_alphanumeric_as_a_dash(self):
        self.assertEqual(roles.transcript_folder_name("/home/a b/proj.x/№1"), "-home-a-b-proj-x--1")
        self.assertEqual(roles.transcript_folder_name("/work/alpha/beta-next"), "-work-alpha-beta-next")

    def test_a_character_outside_the_basic_plane_is_two_dashes_as_in_utf16(self):
        self.assertEqual(roles.transcript_folder_name("/p/\U0001F600x"), "-p---x")

    def make(self, project: str):
        home = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(home, True))
        return types.SimpleNamespace(project=Path(project)), Path(home)

    def test_a_long_path_opens_the_parent_folder_because_the_hash_is_unknown(self):
        me, home = self.make("/" + "d" * 250)
        with mock.patch.object(Path, "home", return_value=home):
            self.assertEqual(roles.claude_transcripts(me), str(home / ".claude" / "projects"))

    def test_a_short_path_gets_its_own_folder(self):
        me, home = self.make("/work/proj")
        with mock.patch.object(Path, "home", return_value=home):
            self.assertEqual(roles.claude_transcripts(me), str(home / ".claude" / "projects" / "-work-proj"))


class FileToolsRule(unittest.TestCase):
    def blocks(self, **extra) -> str:
        from tests.test_conductor_prompts import fixture
        found = prompts.executor(fixture("adhoc"), item="W1", step="executor.1", **extra)
        return "\n".join(block.text for block in found)

    def test_the_rule_is_a_run_rules_block_only_when_asked(self):
        self.assertNotIn("## File tools", self.blocks())
        text = self.blocks(file_tools=True)
        self.assertIn("## File tools", text)
        self.assertIn("Do not read or change files through Bash", text)

    def route(self, tools: str) -> dict:
        return {"argv": ["claude", "-p", "--tools", tools]}

    def me(self, **instructions):
        item = types.SimpleNamespace(options={"instructions": instructions}, routes={"executor": self.route("Bash,Read,Edit,Write")})
        return types.SimpleNamespace(_route_tools=context.route_tools), item

    def test_default_on_for_a_route_with_read_and_edit(self):
        me, item = self.me()
        self.assertTrue(context.file_tools_rule(me, item))

    def test_off_by_the_option_or_when_the_route_has_no_edit_tool(self):
        me, item = self.me(file_tools_rule=False)
        self.assertFalse(context.file_tools_rule(me, item))
        me, item = self.me()
        item.routes["executor"] = self.route("Bash,Read")
        self.assertFalse(context.file_tools_rule(me, item))
        item.routes["executor"] = {"argv": ["codex", "exec"]}  # no tool list at all
        self.assertFalse(context.file_tools_rule(me, item))

    def test_the_default_is_documented_and_true(self):
        self.assertIs(opts.DEFAULTS["instructions"]["file_tools_rule"], True)


if __name__ == "__main__":
    unittest.main()
