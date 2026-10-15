"""Role processes of the conductor: a role that keeps writing is never stopped for its length; a silent one is."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import process  # noqa: E402

BUSY = ("import sys,time\\nsys.stdin.read()\\nfor n in range(6):\\n print('{\"type\":\"x\"}', flush=True)\\n time.sleep(0.5)\\n"
        "print('{\"type\":\"result\",\"result\":\"done\",\"usage\":{}}', flush=True)")
LINGER = ("import sys,time\\nsys.stdin.read()\\nprint('{\"type\":\"result\",\"result\":\"done\",\"usage\":{}}', flush=True)\\n"
          "time.sleep(60)")  # the final result is out, but a background task of the provider keeps the process alive
SILENT = "import sys,time\nsys.stdin.read()\ntime.sleep(30)"


class RoleProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = process.POLL_S
        process.POLL_S = 0.2
        self.addCleanup(setattr, process, "POLL_S", self.old)

    def run_role(self, code, **limits):
        return process.run_role([sys.executable, "-c", code.replace("\\n", "\n")], "prompt", transport="stream-json",
                                cwd=Path(self.tmp.name), raw_path=Path(self.tmp.name) / "out.jsonl", **limits)

    def test_a_role_that_keeps_writing_outlives_the_idle_limit(self):
        run = self.run_role(BUSY, timeout_s=0, idle_timeout_s=2)  # runs about 3 s, silent for 0.5 s at most
        self.assertIsNone(run.error, run.detail)
        self.assertEqual(run.text, "done")

    def test_what_a_finished_role_left_in_the_background_is_ended(self):
        marker = Path(self.tmp.name) / "child.pid"
        code = ("import subprocess, sys, json\n"
                f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                f"open({str(marker)!r}, 'w').write(str(child.pid))\n"
                "print(json.dumps({'type': 'result', 'result': 'done'}))\n")
        run = self.run_role(code, timeout_s=0, idle_timeout_s=0)
        self.assertIsNone(run.error, run.detail)
        pid = int(marker.read_text())
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            if Path(f"/proc/{pid}/stat").exists() and Path(f"/proc/{pid}/stat").read_text().split(")")[1].split()[0] == "Z":
                break
            time.sleep(0.1)
        else:
            self.fail(f"the background child {pid} of the role is still alive")

    def test_a_role_that_has_given_its_result_but_does_not_exit_is_reaped_after_the_grace(self):
        started = time.monotonic()
        run = self.run_role(LINGER, timeout_s=0, idle_timeout_s=0, result_grace_s=1)
        self.assertLess(time.monotonic() - started, 20)
        self.assertIsNone(run.error, run.detail)
        self.assertEqual((run.text, run.exit, run.lingered), ("done", 0, True))

    def test_a_role_that_exits_by_itself_is_not_marked_lingering(self):
        run = self.run_role(BUSY, timeout_s=0, idle_timeout_s=0, result_grace_s=1)
        self.assertFalse(run.lingered)

    def test_a_silent_role_is_stopped_by_the_idle_limit(self):
        run = self.run_role(SILENT, timeout_s=0, idle_timeout_s=1)
        self.assertEqual((run.error, run.detail), ("TIMEOUT", "no output for 1 s"))

    def test_the_wall_clock_ceiling_still_stops_a_long_role_when_asked_for(self):
        run = self.run_role(BUSY, timeout_s=1, idle_timeout_s=0)
        self.assertEqual((run.error, run.detail), ("TIMEOUT", "no result within 1 s"))


FAKE = ROOT / "tests" / "fixtures" / "conductor" / "fake_role.py"


class FailureSignalTests(unittest.TestCase):
    """Signals of a failed role: what the stream gives, what is left out, and the error/v1 the rules of aicore make of them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def run_fake(self, answer, provider="claude-code"):
        script = self.dir / "script.json"
        script.write_text(json.dumps({"executor": [answer]}), encoding="utf-8")
        env = {**os.environ, "FAKE_ROLE_SCRIPT": str(script), "FAKE_ROLE_STATE": str(self.dir / "state")}
        return process.run_role([sys.executable, str(FAKE), "executor"], "prompt", transport="jsonl", cwd=self.dir,
                                timeout_s=0, raw_path=self.dir / "out.jsonl", env=env, provider=provider)

    def test_claude_success_subtype_with_is_error_is_a_failure_with_its_status(self):
        # claude-agent-sdk-python#599: result.subtype "success", is_error true, api_error_status 404
        run = self.run_fake({"is_error": True, "api_error_status": 404, "exit": 1, "text": "model: nope-9 not found"})
        self.assertEqual(run.error, "ROLE_FAILED")
        self.assertEqual((run.error_doc["class"], run.error_doc["code"], run.error_doc["evidence"]),
                         ("model_unavailable", "MODEL_UNAVAILABLE", "structured"))
        self.assertNotIn("nope-9", json.dumps(run.error_doc))

    def test_denied_calls_are_counted_once_by_tool_use_id_and_keep_only_the_tool_name(self):
        # claude --permission-prompts none: system permission_denied messages and result.permission_denials name the same calls
        stream = "\n".join(json.dumps(doc) for doc in (
            {"type": "system", "subtype": "permission_denied", "tool_name": "Grep", "tool_use_id": "toolu_1",
             "decision_reason_type": "workingDir", "message": "Claude requested permissions to read /tmp/x"},
            {"type": "result", "subtype": "success", "is_error": False, "result": "done", "usage": {},
             "permission_denials": [{"tool_name": "Grep", "tool_use_id": "toolu_1", "tool_input": {"pattern": "SECRET"}},
                                    {"tool_name": "Bash", "tool_use_id": "toolu_2", "tool_input": {"command": "rm x"}}]}))
        parsed = process.parse_stream("jsonl", stream)
        self.assertEqual(parsed["denials"], [{"tool_name": "Grep"}, {"tool_name": "Bash"}])
        self.assertNotIn("SECRET", json.dumps(parsed["denials"]))
        self.assertEqual(process.parse_stream("text", "x")["denials"], [])
        self.assertEqual(process.parse_stream("jsonl", '{"type":"result","result":"ok","usage":{}}')["denials"], [])

    def test_a_run_reports_its_denials(self):
        run = self.run_fake({"result": {"verdict": "GREEN", "findings": []},
                             "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {}}]})
        self.assertEqual((run.error, run.denials), (None, [{"tool_name": "Bash"}]))

    def test_claude_is_error_with_exit_zero_is_still_a_failure(self):
        run = self.run_fake({"is_error": True, "api_error_status": 401, "text": "invalid key"})
        self.assertEqual((run.error, run.error_doc["code"]), ("ROLE_FAILED", "PROVIDER_AUTH"))

    def test_claude_api_retry_gives_category_status_and_count(self):
        retry = {"type": "system", "subtype": "api_retry", "attempt": 1, "max_retries": 2, "retry_delay_ms": 10,
                 "error_status": None, "error": "authentication_failed"}
        run = self.run_fake({"stream": [retry, {**retry, "attempt": 2}], "is_error": True, "exit": 1, "text": "x"})
        self.assertEqual(run.api_retries, 2)
        self.assertEqual(run.error_doc["code"], "PROVIDER_AUTH")

    def test_claude_api_retry_status_is_used_when_the_result_has_none(self):
        retry = {"type": "system", "subtype": "api_retry", "attempt": 1, "error_status": 529, "error": "unknown"}
        run = self.run_fake({"stream": [retry], "is_error": True, "exit": 1, "text": "x"})
        self.assertEqual(run.error_doc["code"], "PROVIDER_OVERLOADED")

    def test_claude_rejected_limit_event_is_quota_with_the_reset_time(self):
        event = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": int(time.time()) + 7200,
                                                                 "rateLimitType": "five_hour"}}
        run = self.run_fake({"stream": [event], "is_error": True, "exit": 1, "text": "limit"})
        self.assertEqual((run.error_doc["class"], run.error_doc["code"]), ("quota", "PROVIDER_QUOTA"))
        self.assertTrue(7180 <= run.error_doc["retry_after_s"] <= 7200)

    def test_claude_allowed_limit_event_is_not_a_failure_cause(self):
        event = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning", "resetsAt": int(time.time()) + 60}}
        run = self.run_fake({"stream": [event], "is_error": True, "exit": 1, "text": "tool crashed"})
        self.assertEqual(run.error, "ROLE_FAILED")
        self.assertIsNone(run.error_doc)

    def test_unclassified_failure_has_no_error_doc_and_keeps_the_old_detail(self):
        run = self.run_fake({"exit": 1, "stderr": "boom\n", "text": "x"})
        self.assertEqual((run.error, run.error_doc), ("ROLE_FAILED", None))
        self.assertEqual(run.detail, "exit 1: boom")

    def test_stderr_text_classifies_a_codex_failure_without_a_stream_error(self):
        run = self.run_fake({"exit": 1, "stderr": "Quota exceeded. Check your plan and billing details.\n",
                             "text": "x"}, provider="codex")
        self.assertEqual(run.error_doc["code"], "PROVIDER_QUOTA")
        self.assertEqual(run.error_doc["evidence"], "text")

    def test_codex_turn_failed_is_a_failure_with_its_text(self):
        run = self.run_fake({"codex_failed": "You\u2019ve hit your usage limit. Try again later.", "exit": 1},
                            provider="codex")
        self.assertEqual((run.error, run.error_doc["class"], run.error_doc["code"]), ("ROLE_FAILED", "quota", "PROVIDER_QUOTA"))
        self.assertEqual(run.session, "executor-session-1")

    def test_codex_error_event_before_a_completed_turn_is_not_a_failure(self):
        notice = {"type": "error", "message": "Quota exceeded. Reconnecting 1/5"}
        run = self.run_fake({"codex": True, "stream": [notice], "text": "all done"}, provider="codex")
        self.assertIsNone(run.error)
        self.assertEqual((run.text, run.error_doc), ("all done", None))

    def test_tool_and_answer_text_never_becomes_a_signal(self):
        parsed = process.parse_stream("jsonl", "\n".join(json.dumps(doc) for doc in (
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "weekly limit"}]}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Quota exceeded"}},
            {"type": "error", "message": "Quota exceeded"},
            {"type": "turn.completed", "usage": {}})))
        self.assertEqual(parsed["signals"], {"terminal": True})
        self.assertFalse(parsed["is_error"])

    def test_signals_of_each_stream_event(self):
        parsed = process.parse_stream("jsonl", "\n".join(json.dumps(doc) for doc in (
            {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 123, "rateLimitType": "seven_day"}},
            {"type": "system", "subtype": "api_retry", "error_status": 429, "error": "rate_limit"},
            {"type": "result", "subtype": "success", "is_error": True, "result": "limit", "api_error_status": 429})))
        self.assertEqual(parsed["signals"], {
            "limit_status": "rejected", "limit_resets_at": 123, "limit_window": "seven_day", "retry_category": "rate_limit",
            "terminal": True, "fatal_text": "limit", "http_status": 429, "api_retries": 1, "is_error": True})

    def test_the_last_terminal_event_decides_not_an_earlier_failure(self):
        for stream, failed in (
                ((json.dumps({"type": "turn.failed", "error": {"message": "You\u2019ve hit your usage limit."}}),
                  json.dumps({"type": "turn.completed", "usage": {}})), False),
                ((json.dumps({"type": "turn.completed", "usage": {}}),
                  json.dumps({"type": "turn.failed", "error": {"message": "x"}})), True),
                ((json.dumps({"type": "result", "is_error": True, "result": "weekly limit", "api_error_status": 401}),
                  json.dumps({"type": "result", "is_error": False, "result": "all good"})), False)):
            parsed = process.parse_stream("jsonl", "\n".join(stream))
            with self.subTest(stream=stream):
                self.assertEqual(parsed["is_error"], failed)
                self.assertEqual("fatal_text" in parsed["signals"] or "http_status" in parsed["signals"], failed)

    def test_a_later_success_after_an_error_result_is_not_classified_as_the_old_failure(self):
        # exit 1 after a clean final result: the stale text of the earlier error result must not become quota
        code = ("import sys,json\nsys.stdin.read()\n"
                "print(json.dumps({'type':'result','is_error':True,'result':'weekly limit'}))\n"
                "print(json.dumps({'type':'result','is_error':False,'result':'all good'}))\n"
                "sys.stderr.write('boom')\nsys.exit(1)")
        run = process.run_role([sys.executable, "-c", code], "p", transport="jsonl", cwd=self.dir, timeout_s=0,
                               raw_path=self.dir / "o.jsonl", provider="claude-code")
        self.assertEqual((run.error, run.text, run.error_doc), ("ROLE_FAILED", "all good", None))

    def test_a_non_finite_reset_time_is_ignored(self):
        parsed = process.parse_stream("jsonl", '{"type":"rate_limit_event","rate_limit_info":{"status":"rejected","resetsAt":1e309}}')
        self.assertEqual(parsed["signals"], {"limit_status": "rejected"})

    def test_a_run_without_a_provider_is_not_classified(self):
        run = self.run_fake({"is_error": True, "api_error_status": 401, "exit": 1, "text": "x"}, provider=None)
        self.assertEqual((run.error, run.error_doc), ("ROLE_FAILED", None))

    def test_a_cancelled_or_timed_out_role_is_not_a_provider_failure(self):
        run = process.run_role([sys.executable, "-c", SILENT], "p", transport="jsonl", cwd=self.dir, timeout_s=0,
                               idle_timeout_s=1, raw_path=self.dir / "o.jsonl", provider="claude-code")
        self.assertEqual((run.error, run.error_doc), ("TIMEOUT", None))

    def test_text_transport_has_no_signals(self):
        self.assertEqual(process.parse_stream("text", "answer")["signals"], {})


if __name__ == "__main__":
    unittest.main()


class ActivityAndUsageTests(unittest.TestCase):
    def test_activity_names_the_child_processes_of_a_role(self):
        import subprocess
        child = subprocess.Popen(["sh", "-c", "sleep 30 & wait"], start_new_session=True)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        import time
        time.sleep(0.3)
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "s.jsonl"
            raw.write_text('{"type":"assistant","message":{"id":"m1","content":[{"type":"tool_use","name":"Bash",'
                           '"input":{"command":"bash scripts/test.sh"}}],"usage":{"input_tokens":5,'
                           '"cache_read_input_tokens":7,"output_tokens":2}}}\n', encoding="utf-8")
            text = process.activity(child.pid, raw)
            self.assertIn("last command: Bash: bash scripts/test.sh", text)
            self.assertIn("sleep 30", text)
            self.assertEqual(process.partial_usage(raw.read_text()), {"input": 5, "cached": 7, "output": 2})
        import os
        import signal
        os.killpg(child.pid, signal.SIGKILL)

    def test_activity_follows_the_process_tree_into_other_sessions(self):
        # the shell of a model's Bash tool may sit in a session of its own
        import subprocess
        import time
        code = ("import subprocess, time\\nsubprocess.Popen(['sleep', '31'], start_new_session=True)\\ntime.sleep(31)")
        child = subprocess.Popen([sys.executable, "-c", code.replace("\\n", "\n")], start_new_session=True)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        time.sleep(0.5)
        with tempfile.TemporaryDirectory() as tmp:
            text = process.activity(child.pid, Path(tmp) / "none")
        subprocess.run(["pkill", "-fx", "sleep 31"], check=False)
        self.assertIn("sleep 31", text)

    def test_a_role_without_children_is_said_to_wait_on_its_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("no child process", process.activity(999999, Path(tmp) / "none"))
