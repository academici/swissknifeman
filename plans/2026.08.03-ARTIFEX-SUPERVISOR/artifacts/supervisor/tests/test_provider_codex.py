from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from artifex.providers import codex
from artifex.providers.common import AdapterRefusal


ROOT = Path(__file__).resolve().parents[5]
ROUTING = ROOT / "packages/task/configs/command-routing.json"


def request():
    return {"provider": {"id": "codex", "cli_version": "codex-cli 0.146.0"},
            "route": {"model_class": "implementation", "effort": "high"},
            "permissions": {"approval_mode": "never", "sandbox_mode": "read_only"},
            "budgets": {"max_event_count": 4}, "bundle": {},
            "child_policy": {"mode": "forbidden"}}


class CodexAdapterTests(unittest.TestCase):
    def test_empty_tools_refuse_before_binary_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(AdapterRefusal, "CAPABILITY_UNSUPPORTED"):
                codex.build_argv(request(), routing_path=ROUTING, schema_path=schema,
                                 cwd=directory, native_tools=(), binary="missing-binary")

    def test_refuses_children_and_unknown_version(self):
        value = request()
        value["child_policy"] = {"mode": "allowed"}
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.json"; schema.write_text("{}")
            with self.assertRaisesRegex(AdapterRefusal, "CAPABILITY_UNSUPPORTED"):
                codex.build_argv(value, routing_path=ROUTING, schema_path=schema, cwd=directory, native_tools=(), binary="x")
        value = request(); value["provider"]["cli_version"] = "other"
        self.assertEqual(codex.normalize_record("{}", value)["reason_code"], "MAPPING_UNKNOWN")

    def test_fold_is_closed_over_terminal_and_exit(self):
        success = [json.dumps({"type": "thread.started", "thread_id": "t"}),
                   json.dumps({"type": "turn.completed", "usage": {}})]
        self.assertEqual(codex.fold_records(success, request(), exit_code=0)["reason_code"], "OK")
        self.assertEqual(codex.fold_records(success[:1], request(), exit_code=0)["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        self.assertEqual(codex.fold_records(success, request(), exit_code=1)["reason_code"], "PROVIDER_NONZERO")

    def test_malformed_and_over_cap_are_refused(self):
        self.assertEqual(codex.fold_records(["{"], request(), exit_code=0)["reason_code"], "PROVIDER_PROTOCOL_UNKNOWN")
        self.assertEqual(codex.fold_records(["{}"] * 5, request(), exit_code=0)["reason_code"], "BUDGET_EVENT_COUNT")


if __name__ == "__main__":
    unittest.main()
