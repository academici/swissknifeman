"""aicore.util.telemetry and the telemetry-conventions/v1 data: valid, one root, no cycles, no id as a label."""
import json
import tempfile
import unittest
from pathlib import Path

from aicore.util import telemetry
from aicore.util.telemetry import ConventionsError, load_conventions, metric_label_problems, span_name

DATA = Path(telemetry.__file__).resolve().parents[3] / "configs" / "telemetry-conventions.json"


class TestConventionsData(unittest.TestCase):
    def test_the_packaged_file_is_valid(self):
        doc = load_conventions()
        self.assertEqual((doc["namespace"], doc["metric_label_rule"]), ("skm", "low-cardinality-only"))
        self.assertEqual(doc, json.loads(DATA.read_text(encoding="utf-8")))

    def test_the_loaded_copy_is_the_callers(self):
        load_conventions()["spans"].clear()
        self.assertTrue(load_conventions()["spans"])

    def test_names_are_unique(self):
        doc = load_conventions()
        for key in ("spans", "attributes"):
            names = [item["name"] for item in doc[key]]
            self.assertEqual(len(names), len(set(names)), key)

    def test_the_hierarchy_has_the_run_root_and_two_separate_roots_and_no_cycle(self):
        spans = {item["name"]: item["parent"] for item in load_conventions()["spans"]}
        roots = sorted(name for name, parent in spans.items() if parent is None)
        self.assertEqual(roots, ["skm.event.deliver", "skm.plugin.invoke", "skm.run"])
        for name, parent in spans.items():
            self.assertTrue(parent is None or parent in spans, f"{name}: unknown parent {parent}")
            seen, current = set(), name
            while current is not None:
                self.assertNotIn(current, seen, f"cycle through {name}")
                seen.add(current)
                current = spans[current]
        under_run = {name for name in spans if self._root(spans, name) == "skm.run"}
        self.assertEqual(under_run, {"skm.run", "skm.plan.compile", "skm.stage", "skm.agent.execute",
                                     "skm.tool.execute", "skm.effect.apply"})

    @staticmethod
    def _root(spans, name):
        while spans[name] is not None:
            name = spans[name]
        return name

    def test_agent_and_tool_spans_are_genai_spans(self):
        by_name = {item["name"]: item for item in load_conventions()["spans"]}
        self.assertEqual(by_name["skm.agent.execute"]["genai"], "invoke_agent {agent}")
        self.assertEqual(by_name["skm.tool.execute"]["genai"], "execute_tool {tool}")

    def test_ids_are_high_cardinality_and_the_rest_low(self):
        cardinality = {item["name"]: item["cardinality"] for item in load_conventions()["attributes"]}
        for name in ("skm.run.id", "skm.stage.id", "skm.attempt.id", "skm.request.id", "skm.event.id",
                     "skm.plan.item"):
            self.assertEqual(cardinality[name], "high", name)
        for name in ("skm.module", "skm.provider", "skm.model.class", "skm.stage.kind", "skm.outcome",
                     "skm.event.type", "skm.plugin.id", "skm.error.class"):
            self.assertEqual(cardinality[name], "low", name)

    def test_a_broken_file_is_refused_with_its_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            doc = json.loads(DATA.read_text(encoding="utf-8"))
            doc["metric_label_rule"] = "anything"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ConventionsError) as caught:
                load_conventions(path)
            self.assertIn("metric_label_rule", str(caught.exception))
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ConventionsError):
                load_conventions(path)
            with self.assertRaises(ConventionsError):
                load_conventions(Path(tmp) / "missing.json")


class TestMetricLabels(unittest.TestCase):
    def test_ids_and_unprefixed_names_are_problems(self):
        for label in ("skm.run.id", "skm.stage.id", "skm.request.id", "run_id", "stage_id", "request_id"):
            with self.subTest(label=label):
                self.assertEqual(len(metric_label_problems([label])), 1)

    def test_low_cardinality_and_genai_labels_pass(self):
        self.assertEqual(metric_label_problems(["skm.module", "skm.outcome", "gen_ai.provider.name",
                                                "gen_ai.request.model", "gen_ai.operation.name"]), [])

    def test_undeclared_and_foreign_labels_are_problems(self):
        problems = metric_label_problems(["skm.unknown", "gen_ai.agent.name", "otel.thing"])
        self.assertEqual(len(problems), 3)
        self.assertIn("not declared", problems[0])

    def test_one_problem_per_bad_label_and_none_for_nothing(self):
        self.assertEqual(metric_label_problems([]), [])
        self.assertEqual(len(metric_label_problems(["skm.run.id", "skm.module", "run_id"])), 2)

    def test_a_label_that_is_not_a_string_is_a_problem_not_a_crash(self):
        self.assertEqual(len(metric_label_problems([1, None])), 2)

    def test_explicit_conventions_are_used(self):
        doc = load_conventions()
        doc["attributes"] = [item for item in doc["attributes"] if item["name"] != "skm.module"]
        self.assertEqual(len(metric_label_problems(["skm.module"], doc)), 1)


class TestSpanName(unittest.TestCase):
    def test_a_declared_name_is_returned(self):
        self.assertEqual(span_name("skm.run"), "skm.run")
        self.assertEqual(span_name("skm.agent.execute"), "skm.agent.execute")

    def test_a_genai_span_takes_its_target(self):
        self.assertEqual(span_name("skm.agent.execute", "planner"), "invoke_agent planner")
        self.assertEqual(span_name("skm.tool.execute", "bash"), "execute_tool bash")

    def test_wrong_names_and_targets_are_value_errors(self):
        for args in (("skm.nothing",), ("run",), ("skm.run", "x"), ("skm.agent.execute", ""),
                     ("skm.agent.execute", "two\nlines")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                span_name(*args)


if __name__ == "__main__":
    unittest.main()
