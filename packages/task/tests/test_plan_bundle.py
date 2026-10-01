import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task import journal, plan_bundle, terminal_policy


class PlanBundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = Path(self.tmp.name) / "plan-v2"
        shutil.copytree(Path(__file__).parent / "data" / "plan-v2", self.plan)

    def tearDown(self):
        self.tmp.cleanup()

    def test_authority_extension_is_optional_in_the_bundle_schema(self):
        root = Path(__file__).resolve().parents[3]
        current = json.loads((root / "packages/task/configs/bundle-v1.schema.json").read_text())
        self.assertNotIn("authority", current["required"])
        self.assertEqual(current["properties"]["authority"]["required"], ["gate", "evidence_paths"])

    def test_build_is_deterministic_and_check_is_byte_fresh(self):
        one = plan_bundle.render(self.plan, "P1.1")
        two = plan_bundle.render(self.plan, "P1.1")
        self.assertEqual(one, two)
        target = plan_bundle.build(self.plan, "P1.1")
        self.assertEqual(target.read_text(encoding="utf-8"), one)
        plan_bundle.build(self.plan, "P1.1", check=True)
        target.write_bytes(target.read_bytes() + b" ")
        with self.assertRaises(plan_bundle.BundleError):
            plan_bundle.build(self.plan, "P1.1", check=True)

    def test_unresolvable_is_atomic_and_names_raw_declaration(self):
        target = plan_bundle.build(self.plan, "P1.1")
        expected = target.read_bytes()
        spec = self.plan / "phases/P1/P1.1.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace("brief/00-brief.md", "missing.md"), encoding="utf-8")
        with self.assertRaisesRegex(plan_bundle.BundleError, r"unresolvable_entry: .*missing\.md"):
            plan_bundle.build(self.plan, "P1.1")
        self.assertEqual(target.read_bytes(), expected)

    def test_external_declared_input_is_rejected_before_open(self):
        spec = self.plan / "phases/P1/P1.1.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace(
            "`brief/00-brief.md`", "`file:///tmp/secret.json`"), encoding="utf-8")
        with self.assertRaisesRegex(plan_bundle.BundleError, "PORTABILITY_EXTERNAL_INPUT"):
            plan_bundle.model(self.plan, "P1.1")

    def test_symlink_input_is_rejected_without_reading_external_target(self):
        source = self.plan / "brief/00-brief.md"
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("external", encoding="utf-8")
        source.unlink()
        source.symlink_to(outside)
        with self.assertRaisesRegex(plan_bundle.BundleError, "unsafe_input"):
            plan_bundle.model(self.plan, "P1.1")

    def test_unicode_cross_plan_decision_path_builds_as_one_declared_input(self):
        plans = Path(self.tmp.name) / "plans"
        source = plans / "2026.09.12-№1-DEMO-SOURCE"
        consumer = plans / "2026.09.12-№2-DEMO-CONSUMER"
        shutil.copytree(self.plan, source)
        shutil.copytree(self.plan, consumer)

        decision = source / "decisions" / "D16-owner-domain-control-plane.md"
        decision.write_text("# D16\n", encoding="utf-8")
        path = "plans/2026.09.12-№1-DEMO-SOURCE/decisions/D16-owner-domain-control-plane.md"
        spec = consumer / "phases" / "P1" / "P1.1.md"
        spec.write_text(
            spec.read_text(encoding="utf-8")
            .replace("**Inputs:** `brief/00-brief.md` · `phases/P0/P0.closed.md`", f"**Inputs:** `{path}`")
            .replace("**Required Reads:** 1) `brief/00-brief.md`", f"**Required Reads:** 1) `{path}`"),
            encoding="utf-8",
        )

        bundle = plan_bundle.model(consumer, "P1.1")

        self.assertEqual(
            [entry["path"] for entry in bundle["declaration"]["inputs"]],
            [path],
        )

    def test_deduplicates_one_path_and_decision_resolution_in_the_same_ordinal(self):
        spec = self.plan / "phases/P1/P1.1.md"
        spec.write_text(
            spec.read_text(encoding="utf-8").replace(
                "**Required Reads:** 1) `brief/00-brief.md`",
                "**Required Reads:** 1) `decisions/D1-fixture.md` (D1)",
            ),
            encoding="utf-8",
        )

        bundle = plan_bundle.model(self.plan, "P1.1")
        declaration = bundle["declaration"]["required_reads"]
        entries = [entry for entry in bundle["entries"]
                   if entry["declaration_ref"] == {"field": "Required Reads", "ordinal": 1}]

        self.assertEqual(len(declaration), 1)
        self.assertEqual(len(entries), 1)
        self.assertEqual(declaration[0]["path"], "decisions/D1-fixture.md")

    def test_consumer_reads_only_digest_bound_terminal_readiness_projection(self):
        producer = self.plan / "phases" / "P0" / "P0.1.md"
        producer.write_text(producer.read_text(encoding="utf-8").replace(
            "**Deliverables:** terminal fixture artifact.",
            "**Deliverables:** terminal fixture artifact. `producer-readiness/v1`: "
            "consumer=P1.1; modes=nonempty-candidates|empty-by-decision."),
            encoding="utf-8")
        readiness = {
            "schema_version": "producer-readiness/v1", "producer_item": "P0.1",
            "consumer_item": "P1.1", "mode": "nonempty-candidates",
            "roots": ["phases/P0"], "command": "find phases/P0 -type f",
            "candidate_count": 1, "candidate_paths_sha256": "a" * 64,
            "source_commit": "b" * 40, "predicate": "declared files", "exclusions": [],
        }
        decision = terminal_policy.build_decision(
            self.plan, "P0.1", result="closed-green",
            validation=[{"carrier": "readiness verifier", "status": "green",
                         "evidence_ids": ["fixture:green"]}],
            producer_readiness=readiness)
        event = journal.new_entry(
            plan_id=self.plan.name, item_id="P0.1", command="plan-run",
            actor="implementation/high", result="closed-green", decision=decision)
        with (self.plan / "journal.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

        projection = plan_bundle.producer_readiness(self.plan, "P1.1")[0]

        self.assertEqual(set(projection), {
            "schema_version", "digest", "producer_item", "consumer_item", "mode",
            "candidate_count", "source_commit",
        })
        self.assertEqual(projection["producer_item"], "P0.1")
