"""telemetry: spans of dispatch events and metric labels follow the aicore conventions."""
import unittest

from aicore.util.telemetry import load_conventions, metric_label_problems
from analyst import telemetry
from analyst.trace import DISPATCH_EVENTS


class TestTelemetry(unittest.TestCase):
    def test_every_dispatch_event_has_a_span(self):
        self.assertEqual(set(telemetry.SPAN_FOR_DISPATCH_EVENT), set(DISPATCH_EVENTS))

    def test_spans_are_declared_in_the_conventions(self):
        names = {item["name"] for item in load_conventions()["spans"]}
        self.assertLessEqual(set(telemetry.SPAN_FOR_DISPATCH_EVENT.values()), names)

    def test_metric_labels_follow_the_conventions(self):
        self.assertEqual(metric_label_problems(telemetry.METRIC_LABELS), [])
        self.assertTrue(telemetry.METRIC_LABELS)

    def test_ids_are_not_labels(self):
        self.assertTrue(metric_label_problems(["run_id"]))
        for key in ("run_id", "session_id", "trace_id", "project_id", "event_id"):
            self.assertNotIn(key, telemetry.LABEL_NAME)

    def test_span_for_unknown_event(self):
        with self.assertRaises(KeyError):
            telemetry.span_for("nope")


if __name__ == "__main__":
    unittest.main()
