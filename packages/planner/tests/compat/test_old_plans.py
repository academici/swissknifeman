"""Plans written by earlier engines stay readable: frozen fixtures are copied, read and rendered unchanged."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from planner.plan import check, context, lifecycle, schema, snapshot, store, views

PLANS = Path(__file__).resolve().parent / "plans"
FIXTURES = sorted(path for path in PLANS.iterdir() if (path / "plan.json").is_file())
# Warnings the engine 0.28.3 demo plan produces today: the fixture names files of a repository that is not there.
EXPECTED_WARNINGS_0_28_3 = {
    "modify_missing": 8,
    "read_missing": 1,
    "context_unbound": 1,
    "validation_id_clash": 4,
    "review_strategy": 4,  # the 0.28.3 items have review none without a reason
    # check_overlap: 0 — its checks are `bash scripts/test.sh` and `python3 -m unittest ...`, no module script pair
}


def _digest(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


class OldPlanCase(unittest.TestCase):
    """One temporary copy of a fixture per test, inside a ``plans/`` root, with an empty machine home."""

    fixture: Path = PLANS / "engine-0.28.3"

    def setUp(self):
        scratch = Path(tempfile.mkdtemp(prefix="skm-compat-"))
        self.addCleanup(shutil.rmtree, scratch, True)
        home = scratch / "home"
        home.mkdir()
        patcher = mock.patch.dict(os.environ, {"HOME": str(home), "SKM_HOME": str(home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.plans_root = scratch / "plans"
        plan_id = json.loads((self.fixture / "plan.json").read_text(encoding="utf-8"))["id"]
        self.root = self.plans_root / plan_id
        shutil.copytree(self.fixture, self.root)
        self.before = _digest(self.root)

    def load(self) -> store.Plan:
        return store.load_plan(self.root)


class FixtureTests(unittest.TestCase):
    def test_fixtures_exist_and_are_marked_frozen(self):
        self.assertTrue(FIXTURES)
        self.assertIn("never regenerate", (PLANS / "README.md").read_text(encoding="utf-8"))

    def test_fixture_uses_the_unchanged_plan_urn(self):
        for fixture in FIXTURES:
            document = json.loads((fixture / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(document["$schema"], "urn:swissknifeman:task:plan:plan:v1", fixture.name)


class Engine0283Tests(OldPlanCase):
    def test_loads_without_problems(self):
        plan = self.load()
        self.assertEqual(plan.problems, [])
        self.assertEqual(sorted(plan.items), ["P1.1", "P1.2", "P2.1", "P2.2"])
        self.assertEqual(sorted(plan.decisions), ["D1", "D2"])

    def test_check_has_no_errors_and_the_known_warnings(self):
        issues = check.check(self.load())
        self.assertEqual([issue for issue in issues if issue.level == "error"], [])
        counts: dict = {}
        for issue in issues:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        self.assertEqual(counts, EXPECTED_WARNINGS_0_28_3)
        self.assertNotIn("check_overlap", counts)

    def test_next_returns_a_step(self):
        step = lifecycle.next(self.load())
        # The frozen fixture opted into required design audit before the gate was implemented.
        self.assertEqual(step.kind, "audit-phase")
        self.assertEqual((step.phase, step.reason), ("P2", "missing"))

    def test_none_preserves_the_historical_next_step(self):
        plan = self.load()
        plan.plan["settings"]["design_audit"] = "none"
        step = lifecycle.next(plan)
        self.assertEqual((step.kind, step.items), ("run-items", ("P2.1",)))

    def test_context_of_every_item_carries_the_orchestration_scenario(self):
        plan = self.load()
        for item_id in plan.items:
            pack = context.collect(plan, item_id)
            self.assertTrue(pack["ref"].endswith("." + item_id), item_id)
            self.assertIn("scenario", pack["orchestration"], item_id)
            self.assertIn("scenario_source", pack["orchestration"], item_id)

    def test_export_is_valid_by_the_snapshot_schema(self):
        value = snapshot.export(self.load())
        self.assertEqual(schema.validate(value, "snapshot"), [])
        self.assertEqual(len(value["items"]), 4)

    def test_render_has_no_errors_and_leaves_the_documents_alone(self):
        plan = self.load()
        changed = views.render_all(plan)
        self.assertIn("views/plan.md", changed)
        self.assertEqual(views.render_all(plan, check=True), [])
        after = _digest(self.root)
        sources = {name: data for name, data in after.items() if not name.startswith("views/")}
        self.assertEqual(sources, self.before)

    def test_reading_verbs_do_not_touch_a_document(self):
        plan = self.load()
        check.check(plan)
        lifecycle.next(plan)
        snapshot.export(plan)
        for item_id in plan.items:
            context.collect(plan, item_id)
        self.assertEqual(_digest(self.root), self.before)

    def test_cli_reads_the_plan_through_the_command_line(self):
        import subprocess
        script = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"
        env = dict(os.environ, PYTHONPATH=str(script.parent.parent / "lib"))
        for verb in ("check", "show", "next", "export"):
            result = subprocess.run([sys.executable, str(script), verb, self.root.name, "--plans-root",
                                     str(self.plans_root)], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(result.returncode, 0, f"{verb}: {result.stdout}{result.stderr}")
        self.assertEqual(_digest(self.root), self.before)


if __name__ == "__main__":
    unittest.main()
