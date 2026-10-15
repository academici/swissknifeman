"""Observer polish before P13: messages that name verbs that exist, a repeated ``--retry``."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import tempfile
import time
import types
import unittest
from unittest import mock

from orch.conductor import checks as checks_mod
from orch.conductor import options as opts, prompts
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
            _claim_actor=lambda: "p/m", state={"claims": {}}, run_doc={"plan": "T"}, run_id="r", progress=mock.Mock(),
            _orch=lambda *args: (1, answer, ""), _save=lambda: None)
        with self.assertRaises(Stop) as stop:
            work_source.claim(me, "k", ["W1"])
        self.assertEqual(stop.exception.code, "CLAIM_BLOCKED")
        self.assertIn("orch conduct release", stop.exception.message)


class RepeatedRetry(unittest.TestCase):
    def fake(self, item: dict):
        return types.SimpleNamespace(state={"items": {"W1": item}, "questions": {}}, _save=lambda: None, progress=mock.Mock())

    def blocked(self) -> dict:
        return {"outcome": "blocked", "stop": {}, "steps": {"brief": {"ended": "1"},
                "executor.1": {"ended": "2", "result": {"report": {"status": "blocked"}}}}}

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


class TranscriptFolder(unittest.TestCase):
    def test_the_name_is_every_non_alphanumeric_as_a_dash(self):
        self.assertEqual(roles.transcript_folder_name("/home/a b/proj.x/№1"), "-home-a-b-proj-x--1")
        self.assertEqual(roles.transcript_folder_name("/home/vostrikov/projects/packages/swissknifeman-next"),
                         "-home-vostrikov-projects-packages-swissknifeman-next")

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
