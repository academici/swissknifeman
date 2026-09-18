import copy
import unittest

from core.runs import EventEnvelope, event_key


def _event(provider_id="claude-code"):
    return {
        "contract_version": "1.0.0",
        "provider_id": provider_id,
        "session_id": "session-01",
        "project_id": "project-01",
        "event_id": "event-01",
        "occurred_at": "2026-07-22T00:00:00Z",
        "event_kind": "run_summary",
        "outcome": "ok",
        "metrics": {"tools": 3, "reads": 4, "errors": 0},
        "provenance": {
            "raw_ref": "local:source-01",
            "sha256": "a" * 64,
            "reader_id": "claude-run-report",
            "reader_version": "1.0.0",
        },
    }


class EventEnvelopeTests(unittest.TestCase):
    def test_contract_golden_is_immutable_and_provider_qualified(self):
        claude = EventEnvelope.from_mapping(_event())
        codex = EventEnvelope.from_mapping(_event("codex"))
        cursor = EventEnvelope.from_mapping(_event("cursor"))
        self.assertEqual(claude.metrics["tools"], 3)
        self.assertNotEqual(event_key(claude), event_key(codex))
        self.assertNotEqual(event_key(claude), event_key(cursor))
        with self.assertRaises(TypeError):
            claude.metrics["tools"] = 4

    def test_contract_rejects_raw_fields_unknown_provider_and_bad_provenance(self):
        for mutate in (
            lambda event: event.update({"prompt": "secret"}),
            lambda event: event.update({"provider_id": "unknown"}),
            lambda event: event["provenance"].update({"raw_ref": "local:/source"}),
        ):
            event = copy.deepcopy(_event())
            mutate(event)
            with self.assertRaises(ValueError):
                EventEnvelope.from_mapping(event)


if __name__ == "__main__":
    unittest.main()
