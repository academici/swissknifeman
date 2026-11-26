"""An unavailable live input receipt is refused before a provider call, never inferred from completed usage.

The socket barriers exercise the real process/terminal parser boundary without a model. They prove the negative
path only: this suite supplies no supported provider adapter and cannot certify a real pre-dispatch receipt.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from orch import bindings, contracts
from orch.conductor import options, process
from orch.conductor.application import route_service
from orch.conductor.domain.stop import Stop
from orch.port import PortError
from tests.test_conductor import ConductorCase
from tests.test_prepare import PrepareCase, fixture, roles


REQUIREMENT = {"role": "executor", "provider": "grok", "model": "grok-4.7", "effort": "high",
               "require_current_input_receipt": True}


class ReceiptRequirementTests(PrepareCase):
    def test_preparation_refuses_before_writing_a_prompt(self):
        policy = fixture("run-policy", "solo")
        next(stage for stage in policy["stages"] if stage["kind"] == "primary")["require_current_input_receipt"] = True
        with self.assertRaises(PortError) as raised:
            self.prepare("native", "grok", policy)
        self.assertEqual(raised.exception.code, "CAPABILITY_UNSUPPORTED")
        refusal = raised.exception.data["launch_plan"]["refusals"][0]
        self.assertEqual((refusal["capability"], refusal["reason_code"]),
                         ("current_input_receipt", "CURRENT_INPUT_RECEIPT_UNSUPPORTED"))
        self.assertIn("record support=unknown, source=declared", refusal["reason"])
        self.assertIn("docs/conductor.md#current-request-input-receipts", refusal["reason"])
        self.assertFalse(self.out.exists())

    def test_a_support_declaration_alone_cannot_invent_an_acquisition_path(self):
        policy = fixture("run-policy", "solo")
        next(stage for stage in policy["stages"] if stage["kind"] == "primary")["require_current_input_receipt"] = True
        for support in ("supported", "adapted"):
            with self.subTest(support=support):
                caps = bindings.load_capabilities()
                caps[("native", "grok")]["current_input_receipt"] = support
                engine = bindings.Native(self.out, catalog=self.catalog, capabilities=caps)
                with self.assertRaises(PortError) as raised:
                    engine.prepare(fixture("execution-input", "plan-bound"), policy, roles(), provider="grok")
                refusal = raised.exception.data["launch_plan"]["refusals"][0]
                self.assertEqual(refusal["reason_code"], "CURRENT_INPUT_RECEIPT_UNSUPPORTED")
                self.assertIn(f"record support={support}", refusal["reason"])

    def test_omitting_the_requirement_preserves_existing_preparation(self):
        self.assertValid(self.prepare("native", "grok"))

    def test_the_capability_field_is_typed_and_completed_usage_stays_supported(self):
        cap = bindings.load_capabilities()[("native", "grok")]
        cap.pop("_path")
        self.assertEqual(contracts.validate(cap, "capability-record"), [])
        self.assertEqual((cap["usage"], cap["current_input_receipt"]), ("supported", "unknown"))
        cap["current_input_receipt"] = "terminal usage proves live input"
        self.assertTrue(contracts.validate(cap, "capability-record"))


class ReceiptOptionTests(unittest.TestCase):
    def test_policy_requirement_survives_option_resolution(self):
        policy = {"policy_id": "live-input", "stages": [{"role": "executor",
                   "require_current_input_receipt": True}]}
        effective, _ = options.effective({}, policy, [])
        self.assertTrue(options.stage_route(effective, "executor")["require_current_input_receipt"])

    def test_source_layers_cannot_remove_an_existing_requirement(self):
        policy = {"stages": [{"role": "executor", "require_current_input_receipt": True}]}
        layer = {"source": "item", "options": {"stages": [{"role": "executor",
                  "require_current_input_receipt": False}]}}
        with self.assertRaises(options.OptionsError) as raised:
            options.effective({}, policy, [layer])
        self.assertEqual(raised.exception.code, "OPTIONS_UNTRUSTED")
        self.assertIn("require_current_input_receipt", raised.exception.message)

    def test_requirement_is_optional_and_boolean(self):
        self.assertEqual(options.layer_problems({"stages": [REQUIREMENT]}), [])
        bad = copy.deepcopy(REQUIREMENT)
        bad["require_current_input_receipt"] = "yes"
        self.assertTrue(options.layer_problems({"stages": [bad]}))
        effective, _ = options.effective({}, {}, [])
        self.assertNotIn("require_current_input_receipt", options.stage_route(effective, "executor"))


class ReceiptConductorTests(ConductorCase):
    def receipt_options(self):
        path = self.script_file.parent / "receipt-options.json"
        path.write_text(json.dumps({"stages": [REQUIREMENT], "fallback_routes": []}))
        return path

    def test_required_receipt_stops_before_any_role_or_dependent_read(self):
        with mock.patch.object(process, "run_role", side_effect=AssertionError("provider must not start")):
            code, out, err = self.run_items("W1", extra=("--options", self.receipt_options()))
        self.assertEqual(code, 1, out + err)
        self.assertIn("CURRENT_INPUT_RECEIPT_UNSUPPORTED", out + err)
        self.assertIn("native/grok", out + err)
        self.assertEqual(self.calls("executor"), 0)
        self.assertEqual(self.calls("context-scout"), 0)
        self.assertFalse((self.project / "out/W1.txt").exists())
        for hint in ("doctor", "--allow-path", "install or log in"):
            self.assertNotIn(hint, out + err)

    def test_dry_run_reports_the_same_unavailable_requirement_without_spawning(self):
        with mock.patch.object(process, "run_role", side_effect=AssertionError("provider must not start")):
            code, out, err = self.run_items("W1", extra=("--options", self.receipt_options(), "--dry-run"))
        self.assertEqual(code, 0, out + err)
        self.assertIn("CURRENT_INPUT_RECEIPT_UNSUPPORTED", out + err)
        self.assertEqual(self.calls("executor"), 0)


class ReceiptCausalTests(unittest.TestCase):
    def assert_refused(self):
        item = SimpleNamespace(options={"stages": [REQUIREMENT]}, routes={"executor": {"provider": "grok"}})
        with self.assertRaises(Stop) as raised:
            route_service.preflight(SimpleNamespace(), item)
        self.assertEqual(raised.exception.code, "CURRENT_INPUT_RECEIPT_UNSUPPORTED")
        self.assertIn("before dependent tool dispatch", raised.exception.message)

    def test_helper_runs_before_completion_and_late_terminal_usage_or_summary_never_admits(self):
        # This is a terminal producer fixture, not an invented supported live receipt adapter. The actual helper is
        # called while completion is held, after terminal publication, and after the delayed summary. No sleeps order it.
        for usage in ({}, {"input_tokens": 50, "cache_read_input_tokens": 100, "output_tokens": 2}):
            with self.subTest(usage=usage), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                raw, summary = base / "out.jsonl", base / "summary.json"
                with socket.socket(socket.AF_UNIX) as listener:
                    listener.bind(str(base / "barrier"))
                    listener.listen(1)
                    listener.settimeout(10)
                    code = ("import json,socket,sys\n"
                            "sys.stdin.read()\n"
                            "print(json.dumps({'type':'system','subtype':'init','session_id':'current',"
                            "'model':'grok-4.7'}),flush=True)\n"
                            f"s=socket.socket(socket.AF_UNIX);s.connect({str(base / 'barrier')!r})\n"
                            "s.sendall(b'R');s.recv(1)\n"
                            f"print(json.dumps({{'type':'result','result':'done','usage':{usage!r}}}),flush=True)\n"
                            "s.sendall(b'T');s.recv(1)\n"
                            f"open({str(summary)!r},'w').write(json.dumps({{'inputTokens':150}}))\n")
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(process.run_role, [sys.executable, "-c", code], "prompt",
                                             transport="jsonl", cwd=base, raw_path=raw, timeout_s=10,
                                             idle_timeout_s=10, provider="grok")
                        control, _ = listener.accept()
                        with control:
                            control.settimeout(10)
                            try:
                                self.assertEqual(control.recv(1), b"R")
                                self.assertFalse(future.done())
                                self.assertFalse(summary.exists())
                                self.assertEqual(process.parse_stream("jsonl", raw.read_text())["usage"],
                                                 {"input": 0, "cached": 0, "output": 0})
                                self.assert_refused()  # helper precedes release of turn completion
                                control.sendall(b"C")
                                self.assertEqual(control.recv(1), b"T")
                                self.assertFalse(summary.exists())
                                terminal = json.loads(raw.read_text().splitlines()[-1])
                                self.assertEqual(terminal["type"], "result")
                                self.assertEqual(terminal["usage"], usage)
                                parsed = process.parse_stream("jsonl", raw.read_text())
                                self.assertEqual(parsed["usage"], process._usage(usage))
                                self.assertEqual(parsed["usage_complete"], bool(usage))
                                self.assert_refused()  # even a now-completed usage record is not a live receipt
                            finally:
                                control.sendall(b"S")
                        run = future.result(timeout=15)
                self.assertIsNone(run.error, run.detail)
                self.assertEqual(run.usage_complete, bool(usage))
                self.assertTrue(summary.exists())
                self.assert_refused()  # replay and delayed post-turn summary cannot change the capability


if __name__ == "__main__":
    unittest.main()
