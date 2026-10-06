from __future__ import annotations

from pathlib import Path
import re
import unittest

from orch.port import BINDINGS, PORT_ERROR_CODES, EnginePort, PortError

ROOT = Path(__file__).resolve().parents[1]


class DummyPort:
    binding = "claude-only"

    def capabilities(self):
        return []

    def prepare(self, input_doc, policy, roles, *, provider=None, dry_run=True):
        raise PortError("NOT_IMPLEMENTED", "prepare")

    def run(self, launch_plan):
        raise PortError("NOT_IMPLEMENTED", "run")

    def watch(self, run_id):
        raise PortError("NOT_IMPLEMENTED", "watch")

    def cancel(self, run_id):
        raise PortError("NOT_IMPLEMENTED", "cancel")

    def resume(self, run_id):
        raise PortError("NOT_IMPLEMENTED", "resume")

    def results(self, run_id):
        raise PortError("NOT_IMPLEMENTED", "results")


class IncompletePort:
    binding = "native"

    def capabilities(self):
        return []


def documented_codes():
    """Codes from the first column of the table under `## Errors` in docs/engine-port.md."""
    text = (ROOT / "docs/engine-port.md").read_text(encoding="utf-8")
    section = text.split("\n## Errors\n", 1)[1].split("\n## ", 1)[0]
    return tuple(re.findall(r"^\| `([A-Z_]+)` \|", section, re.MULTILINE))


class EnginePortTests(unittest.TestCase):
    def test_protocol_is_runtime_checkable(self):
        self.assertIsInstance(DummyPort(), EnginePort)
        self.assertNotIsInstance(IncompletePort(), EnginePort)
        self.assertIn(DummyPort.binding, BINDINGS)

    def test_port_error_carries_code_message_and_data(self):
        error = PortError("CAPABILITY_UNSUPPORTED", "model.set unknown", {"launch_plan": {"refusals": []}})
        self.assertEqual((error.code, error.message), ("CAPABILITY_UNSUPPORTED", "model.set unknown"))
        self.assertEqual(error.data, {"launch_plan": {"refusals": []}})
        self.assertEqual(str(error), "CAPABILITY_UNSUPPORTED: model.set unknown")
        self.assertEqual(PortError("RUN_UNKNOWN", "x").data, {})

    def test_port_error_codes_are_closed(self):
        for code in PORT_ERROR_CODES:
            self.assertEqual(PortError(code, "m").code, code)
        with self.assertRaises(ValueError):
            PortError("NOT_A_CODE", "m")
        with self.assertRaises(PortError) as caught:
            DummyPort().run({})
        self.assertIn(caught.exception.code, PORT_ERROR_CODES)

    def test_codes_match_documented_table(self):
        self.assertEqual(len(set(PORT_ERROR_CODES)), len(PORT_ERROR_CODES))
        self.assertEqual(documented_codes(), PORT_ERROR_CODES)


if __name__ == "__main__":
    unittest.main()
