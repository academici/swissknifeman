import tempfile
import unittest
from pathlib import Path
import subprocess

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan
from task import plan_history


def _decision():
    return """---
id: D1
date: 2026-07-02
status: accepted
item: P1.1
items: [P1.1]
supersedes: []
superseded_by: null
---
## Решение

Тест.

## Почему

Проверка.
"""


class PlanHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = write_valid_plan(Path(self.tmp.name), "DEMO-V2", layout="v2")
        (self.plan / "decisions").mkdir(exist_ok=True)
        (self.plan / "findings").mkdir(exist_ok=True)
        (self.plan / "decisions" / "D1-fixture.md").write_text(_decision(), encoding="utf-8")
        (self.plan / "findings" / "P1.1-fixture.md").write_text(
            "---\nitem: P1.1\ndate: 2026-07-02\n---\n\n# Finding\n", encoding="utf-8")
        (self.plan / "journal.jsonl").write_text(
            '{"ts":"2026-07-02T00:00:00Z","plan_id":"DEMO-V2","item_id":"P1.1","command":"plan-run","session_id":null,"run_id":null,"attempt":1,"actor":"sonnet/medium","friction":[],"result":"closed-green","cost_usd":null,"num_turns":null,"duration_ms":null,"note":null}\n',
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_history_is_deterministic_and_uses_three_sources(self):
        first = plan_history.render_history(self.plan, "P1.1")
        second = plan_history.render_history(self.plan, "P1.1")
        self.assertEqual(first, second)
        self.assertLess(first.index("| journal |"), first.index("| decisions |"))
        self.assertLess(first.index("| decisions |"), first.index("| findings |"))
        self.assertIn("projection: history", first)
        self.assertIn("inputs_sha256:", first)

    def test_history_includes_secondary_affected_item(self):
        path = self.plan / "decisions" / "D1-fixture.md"
        path.write_text(_decision().replace("items: [P1.1]", "items: [P1.1, P1.2]"))
        records, inputs = plan_history._decision_records(self.plan, "P1.2")
        self.assertEqual([record.identity for record in records], ["D1"])
        self.assertEqual(inputs, [path])
        self.assertEqual(records[0].payload["items"], ["P1.1", "P1.2"])
        self.assertEqual(plan_history._decision_records(self.plan, "P1.3"), ([], []))

    def test_materialization_is_explicit_and_check_detects_drift(self):
        target = self.plan / ".plan-cache" / "history" / "P1.1.md"
        self.assertEqual(plan_history.materialize_history(self.plan, "P1.1", target), target)
        self.assertEqual(plan_history.materialize_history(self.plan, "P1.1", target, check=True), target)
        target.write_text(target.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
        with self.assertRaises(plan_history.HistoryError):
            plan_history.materialize_history(self.plan, "P1.1", target, check=True)

    def test_missing_findings_source_fails_closed(self):
        for path in (self.plan / "findings").iterdir():
            path.unlink()
        (self.plan / "findings").rmdir()
        with self.assertRaisesRegex(plan_history.HistoryError, "findings"):
            plan_history.render_history(self.plan, "P1.1")

    def test_default_materialization_address_is_gitignored(self):
        repository = Path(__file__).resolve().parents[3]
        probe = subprocess.run(
            ["git", "check-ignore", "-q", ".plan-cache/history/P1.1.md"],
            cwd=repository,
            check=False,
        )
        self.assertEqual(probe.returncode, 0)
