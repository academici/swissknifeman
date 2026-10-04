"""Native ACP transport boundaries without launching a reviewer or model call."""
import io
import json
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import unittest
from unittest.mock import patch

from task import review_grok_acp as acp


class _Pipe:
    def __init__(self):
        self.rows = queue.Queue()

    def put(self, value):
        self.rows.put((json.dumps(value) + "\n").encode())

    def readline(self):
        return self.rows.get()

    def close(self):
        pass


class _Process:
    def __init__(self, *, stop="end_turn", usage=None, model="grok-4.7", session="reviewer-id",
                 permission=False, silent=False, error=False):
        self.stdout, self.stderr = _Pipe(), io.BytesIO(b"provider diagnostics\n")
        self.stdin = self
        self.sent = []
        self.session = session
        self.stop, self.model = stop, model
        self.usage = usage if usage is not None else {
            "inputTokens": 10, "outputTokens": 5, "cachedReadTokens": 0,
            "cacheCreationTokens": 0, "numTurns": 2,
            "modelUsage": {"grok-4.7-build": {"inputTokens": 10, "outputTokens": 5}}}
        self.permission, self.silent, self.error = permission, silent, error
        self.terminated = False

    def write(self, raw):
        request = json.loads(raw)
        self.sent.append(request)
        if "method" not in request or self.silent:
            return
        method, rid = request["method"], request["id"]
        if method == "session/new":
            result = {"sessionId": self.session}
        elif method == "session/prompt":
            if self.error:
                self.stdout.put({"id": rid, "error": {"code": -1, "message": "provider failure"}})
                return
            if self.permission:
                self.stdout.put({"id": 71, "method": "session/request_permission", "params": {}})
            self.chunk("I will inspect the code.")
            self.finished_response()
            self.chunk('{"verdict":"GREEN"}')
            self.finished_response()
            result = {"stopReason": self.stop, "_meta": {"sessionId": self.session,
                      "modelId": self.model, "usage": self.usage}}
        else:
            result = {}
        self.stdout.put({"jsonrpc": "2.0", "id": rid, "result": result})

    def chunk(self, text):
        self.stdout.put({"method": "session/update", "params": {"sessionId": self.session,
                        "update": {"sessionUpdate": "agent_message_chunk",
                                   "content": {"type": "text", "text": text}}}})

    def finished_response(self):
        self.stdout.put({"method": "_x.ai/session_notification", "params": {"sessionId": self.session,
                        "update": {"sessionUpdate": "response_completed"}}})

    def flush(self):
        pass

    def close(self):
        pass

    def terminate(self):
        self.terminated = True
        self.stdout.rows.put(b"")

    def poll(self):
        return -15 if self.terminated else None


class _ActiveProcess(_Process):
    def __init__(self, *, noise=False, response_notifications=0):
        super().__init__()
        self.noise = noise
        self.response_notifications = response_notifications

    def write(self, raw):
        request = json.loads(raw)
        if request.get("method") != "session/prompt":
            return super().write(raw)
        self.sent.append(request)

        def stream():
            for _ in range(15):
                time.sleep(.02)
                if self.terminated:
                    return
                self.stdout.put({"method": "session/update", "params": {
                    "sessionId": "unrelated-session" if self.noise else self.session,
                    "update": {"sessionUpdate": "agent_thought_chunk",
                               "content": {"type": "text", "text": "activity"}}}})
            for _ in range(self.response_notifications):
                self.finished_response()
            self.chunk('{"verdict":"GREEN"}')
            self.finished_response()
            self.stdout.put({"id": request["id"], "result": {
                "stopReason": "end_turn", "_meta": {"sessionId": self.session,
                "modelId": self.model, "usage": self.usage}}})

        threading.Thread(target=stream, daemon=True).start()


class GrokACPTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"route": {"model": "grok-4.7", "context_tokens": 500000},
                         "effort": "high", "executor_session": "executor"}
        self.witness = {"session_id": "reviewer-id", "model": "grok-4.7", "effort": "high",
                        "context_tokens": 500000}

    def run_transport(self, process=None, witness=None, timeout=1):
        process = process or _Process()
        witness = self.witness if witness is None else witness
        with patch.object(acp.subprocess, "Popen", return_value=process) as launch, \
                patch.object(acp, "provider_route", return_value=witness), \
                patch.object(acp, "_stop", side_effect=lambda proc: proc.terminate()):
            result = acp.run(self.manifest, b"unchanged digest-bound packet", cwd=Path("/work"),
                             timeout=timeout, max_turns=20)
        self.assertTrue(process.terminated)
        self.assertEqual(launch.call_args.kwargs["cwd"], Path("/work"))
        return result, process

    def test_fresh_route_and_complete_usage_accept_accounting_alias(self):
        result, process = self.run_transport()
        self.assertTrue(result["complete"])
        self.assertEqual(result["session"], "reviewer-id")
        self.assertEqual(result["observed_context"], 500000)
        self.assertEqual(result["output"], b'{"verdict":"GREEN"}')
        self.assertIn(b"grok-4.7-build", result["raw"])
        requests = [row for row in process.sent if "method" in row]
        self.assertEqual([row["method"] for row in requests],
                         ["initialize", "session/new", "session/set_model", "session/prompt"])
        self.assertEqual(requests[2]["params"]["_meta"], {"contextWindow": 500000, "reasoningEffort": "high"})
        self.assertEqual(requests[3]["params"]["prompt"], [{"type": "text", "text": "unchanged digest-bound packet"}])
        self.assertIn(b"provider diagnostics", result["stderr"])

    def test_small_missing_capacity_and_wrong_route_refuse_before_prompt(self):
        cases = [({**self.witness, "context_tokens": 256000}, "REVIEW_CONTEXT_UNDERSHOOT"),
                 ({**self.witness, "context_tokens": None}, "REVIEW_CONTEXT_UNVERIFIABLE"),
                 ({}, "REVIEW_CONTEXT_UNVERIFIABLE"),
                 ({**self.witness, "model": "grok-4.6"}, "REVIEW_ROUTE_MISMATCH"),
                 ({**self.witness, "effort": "medium"}, "REVIEW_ROUTE_MISMATCH")]
        for witness, code in cases:
            with self.subTest(code=code, witness=witness):
                result, process = self.run_transport(witness=witness, timeout=.03)
                self.assertFalse(result["complete"])
                self.assertIn(code, result["detail"])
                self.assertNotIn("session/prompt", [row.get("method") for row in process.sent])

    def test_config_acknowledgement_cannot_replace_native_witness(self):
        result, _ = self.run_transport(witness={}, timeout=.03)
        self.assertFalse(result["complete"])
        self.assertIn("native session summary is unavailable", result["detail"])

    def test_post_prompt_route_change_never_completes(self):
        process = _Process()
        states = [self.witness]
        def witness(*args):
            return states.pop() if states else {**self.witness, "effort": "low"}
        with patch.object(acp.subprocess, "Popen", return_value=process), \
                patch.object(acp, "provider_route", side_effect=witness), \
                patch.object(acp, "_stop", side_effect=lambda proc: proc.terminate()):
            result = acp.run(self.manifest, b"packet", cwd=Path("/work"), timeout=.03, max_turns=20)
        self.assertFalse(result["complete"])
        self.assertIn("REVIEW_ROUTE_MISMATCH", result["detail"])

    def test_stale_native_default_capacity_converges_before_prompt(self):
        process = _Process()
        states = [{**self.witness, "context_tokens": 256000}, self.witness, self.witness]
        def witness(*args):
            current = states.pop(0)
            if current["context_tokens"] == 256000:
                self.assertNotIn("session/prompt", [row.get("method") for row in process.sent])
            return current
        with patch.object(acp.subprocess, "Popen", return_value=process), \
                patch.object(acp, "provider_route", side_effect=witness), \
                patch.object(acp, "_stop", side_effect=lambda proc: proc.terminate()):
            result = acp.run(self.manifest, b"packet", cwd=Path("/work"), timeout=1, max_turns=20)
        self.assertTrue(result["complete"])
        self.assertEqual(result["observed_context"], 500000)

    def test_denied_permission_gets_cancelled_without_execution(self):
        result, process = self.run_transport(_Process(permission=True))
        self.assertTrue(result["complete"])
        response = next(row for row in process.sent if row["id"] == 71)
        self.assertEqual(response["result"], {"outcome": {"outcome": "cancelled"}})

    def test_cancelled_missing_usage_or_terminal_wrong_model_are_incomplete(self):
        for process in (_Process(stop="max_turns"), _Process(usage={}),
                        _Process(model="grok-4.6"), _Process(usage={"inputTokens": 0, "outputTokens": 0,
                                     "cachedReadTokens": 0, "cacheCreationTokens": 0, "numTurns": 1}),
                        _Process(usage={"inputTokens": 1, "outputTokens": 1,
                                     "cachedReadTokens": 0, "cacheCreationTokens": 0, "numTurns": 21})):
            result, _ = self.run_transport(process)
            self.assertFalse(result["complete"])

    def test_self_review_refused_before_prompt(self):
        result, process = self.run_transport(_Process(session="executor"))
        self.assertFalse(result["complete"])
        self.assertNotEqual(result["session"], "executor")
        self.assertIn("REVIEW_NOT_INDEPENDENT", result["detail"])
        self.assertNotIn("session/prompt", [row.get("method") for row in process.sent])

    def test_timeout_and_provider_error_archive_diagnostics_and_cleanup(self):
        for process, code in ((_Process(silent=True), "timeout"), (_Process(error=True), "REVIEW_ACP_ERROR")):
            result, _ = self.run_transport(process, timeout=.03)
            self.assertFalse(result["complete"])
            self.assertIn(code, result["detail"])
            self.assertTrue(result["stderr"])

    def test_read_only_native_argv(self):
        args = acp.argv(self.manifest, max_turns=20)
        for flag in ("--no-leader", "--no-subagents", "--disable-web-search", "MCPTool", "Bash", "Edit", "Write"):
            self.assertIn(flag, args)
        self.assertIn("read_file,grep,list_dir", args)
        self.assertEqual(args[-1], "stdio")
        self.assertNotIn("--prompt-file", args)

    def test_active_review_outlives_timeout_and_emits_liveness_probes(self):
        process = _ActiveProcess(response_notifications=25)
        heartbeats = []
        with patch.object(acp.subprocess, "Popen", return_value=process), \
                patch.object(acp, "provider_route", return_value=self.witness), \
                patch.object(acp, "_stop", side_effect=lambda proc: proc.terminate()):
            result = acp.run(self.manifest, b"packet", cwd=Path("/work"), timeout=.1,
                             max_turns=20, heartbeat_interval=.03, progress=heartbeats.append)
        self.assertTrue(result["complete"], result["detail"])
        self.assertGreater(heartbeats[-1]["elapsed_seconds"], .1)
        self.assertGreater(heartbeats[-1]["activity_events"], 0)
        self.assertTrue(all(row["process_alive"] for row in heartbeats))
        self.assertEqual(result["output"], b'{"verdict":"GREEN"}')

    def test_unrelated_stream_activity_does_not_hide_stalled_reviewer(self):
        process = _ActiveProcess(noise=True)
        with patch.object(acp.subprocess, "Popen", return_value=process), \
                patch.object(acp, "provider_route", return_value=self.witness), \
                patch.object(acp, "_stop", side_effect=lambda proc: proc.terminate()):
            result = acp.run(self.manifest, b"packet", cwd=Path("/work"), timeout=.1,
                             heartbeat_interval=.03)
        self.assertFalse(result["complete"])
        self.assertIn("REVIEW_INACTIVE", result["detail"])
        self.assertTrue(process.terminated)
        self.assertTrue(result["heartbeats"])
        self.assertEqual(result["heartbeats"][-1]["activity_events"], 0)

    def test_default_turn_cap_is_absent_and_native_usage_may_exceed_twenty(self):
        process = _Process()
        process.usage["numTurns"] = 45
        with patch.object(acp.subprocess, "Popen", return_value=process), \
                patch.object(acp, "provider_route", return_value=self.witness), \
                patch.object(acp, "_stop", side_effect=lambda proc: proc.terminate()):
            result = acp.run(self.manifest, b"packet", cwd=Path("/work"), timeout=1)
        self.assertTrue(result["complete"])
        self.assertNotIn("--max-turns", result["argv"])

    def test_timeout_cleanup_kills_group_and_reaps_process(self):
        from unittest.mock import Mock
        process = Mock(pid=987654)
        process.wait.side_effect = [subprocess.TimeoutExpired("grok", 2), 0]
        with patch.object(acp.os, "name", "posix"), patch.object(acp.os, "killpg") as kill:
            acp._stop(process)
        self.assertEqual([call.args[1] for call in kill.call_args_list], [acp.signal.SIGTERM, acp.signal.SIGKILL])
        self.assertEqual(process.wait.call_count, 2)

    def test_summary_is_session_and_cwd_bound(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(acp.Path, "home", return_value=Path(directory)):
            root = Path("/work/project")
            path = Path(directory) / ".grok/sessions/%2Fwork%2Fproject/reviewer-id/summary.json"
            path.parent.mkdir(parents=True)
            value = {"info": {"id": "reviewer-id", "cwd": str(root)}, "current_model_id": "grok-4.7",
                     "reasoning_effort": "high", "context_window": 500000}
            path.write_text(json.dumps(value))
            self.assertEqual(acp.provider_route(root, "reviewer-id")["context_tokens"], 500000)
            value["info"]["cwd"] = "/another-project"
            path.write_text(json.dumps(value))
            self.assertEqual(acp.provider_route(root, "reviewer-id"), {})


if __name__ == "__main__":
    unittest.main()
