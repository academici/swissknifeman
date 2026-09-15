"""Evidence-anchor admission and closure continuity."""
import hashlib
import subprocess
import tempfile
import unittest
import json
from pathlib import Path

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan

from task import plan_bundle, plan_evidence, plan_gates, task_contract


class EvidenceGraphTests(unittest.TestCase):
    def test_missing_only_and_empty_anchors_are_not_product_coverage(self):
        for paths in ([], [{"path": "a.py; b.py", "state": "missing"}]):
            anchor = {"paths": paths, "sha256": "0" * 64}
            with self.subTest(paths=paths), self.assertRaisesRegex(
                    plan_evidence.EvidenceError, "PRODUCT_COVERAGE_MISSING"):
                plan_evidence.verify_closure(anchor, anchor)

    def test_semicolon_files_bind_real_product_bytes_and_detect_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.py").write_text("before")
            (root / "b.py").write_text("stable")
            paths = plan_evidence._declared_paths("a.py; b.py")
            before = plan_evidence._anchor(paths, repo_root=root)
            self.assertEqual([row["state"] for row in before["paths"]], ["file", "file"])
            plan_evidence.verify_closure(before, before)
            (root / "a.py").write_text("after")
            with self.assertRaisesRegex(plan_evidence.EvidenceError, "PRODUCT_ANCHOR_DRIFT"):
                plan_evidence.verify_closure(before, plan_evidence._anchor(paths, repo_root=root))
        with self.assertRaisesRegex(plan_evidence.EvidenceError, "EVIDENCE_PATH_INVALID"):
            plan_evidence._declared_paths("a.py; b.py with explanatory prose")

    @staticmethod
    def _git(root, *arguments):
        return subprocess.run(("git", *arguments), cwd=root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_spec_and_digest_inputs_must_precede_product_anchor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.invalid")
            self._git(root, "config", "user.name", "Test")
            plan_dir = write_valid_plan(root, layout="v2")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "spec")
            product = root / "product.txt"
            product.write_text("v1\n", encoding="utf-8")
            self._git(root, "add", "product.txt")
            product_anchor = self._git(root, "commit", "-qm", "product")
            product_anchor = self._git(root, "rev-parse", "HEAD")
            spec = plan_dir / "phases" / "P1" / "P1.1.md"
            spec.write_text(spec.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "late spec")

            with self.assertRaisesRegex(plan_evidence.EvidenceError,
                                        "EXECUTION_INPUTS_NOT_ANCESTOR"):
                plan_evidence.compile_graph(plan_dir, "P1.1", execution_ref=product_anchor)

    def test_declared_file_that_is_a_digest_input_refuses_same_anchor_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            plan_dir = write_valid_plan(root, layout="v2")
            spec = plan_dir / "phases" / "P1" / "P1.1.md"
            spec.write_text(
                spec.read_text(encoding="utf-8").replace(
                    "**Files:** lib/pkg/config.py",
                    "**Files:** `brief/00-brief.md` · `lib/pkg/config.py`",
                ),
                encoding="utf-8",
            )
            plan_bundle.build(plan_dir, "P1.1")

            graph = plan_evidence.compile_graph(plan_dir, "P1.1")

            self.assertEqual(graph["collisions"], ["plans/DEMO-1/lib/pkg/config.py"])
            with self.assertRaisesRegex(plan_evidence.EvidenceError,
                                        "SELF_INVALIDATING_EVIDENCE_ANCHOR"):
                plan_evidence.admit_pre_mutation(graph, requires_closure_freshness=True)

    def test_non_overlapping_inputs_collapse_to_one_anchor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            plan_dir = write_valid_plan(root, layout="v2")
            spec = plan_dir / "phases" / "P1" / "P1.1.md"
            spec.write_text(
                spec.read_text(encoding="utf-8").replace(
                    "**Files:** lib/pkg/config.py", "**Files:** `artifact.txt`",
                ), encoding="utf-8")
            (plan_dir / "artifact.txt").write_text("product\n", encoding="utf-8")

            graph = plan_evidence.compile_graph(plan_dir, "P1.1")

            self.assertEqual(graph["collisions"], [])
            self.assertEqual(
                plan_evidence.admit_pre_mutation(graph, requires_closure_freshness=True)["anchor_mode"],
                "collapsed",
            )

    def test_repository_files_are_not_misclassified_as_missing_plan_carriers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            plan_dir = write_valid_plan(root, layout="v2")
            (plan_dir / "lib" / "pkg" / "config.py").unlink()
            source = root / "lib" / "pkg" / "config.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\n", encoding="utf-8")
            plan_bundle.build(plan_dir, "P1.1")

            graph = plan_evidence.compile_graph(plan_dir, "P1.1")

            self.assertEqual(graph["product_paths"], ["lib/pkg/config.py"])
            self.assertEqual(graph["collisions"], ["lib/pkg/config.py"])
            self.assertEqual(graph["nodes"][2]["anchor"]["paths"], [{
                "path": "lib/pkg/config.py", "state": "file",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }])

    def test_closure_requires_declared_product_bytes_to_be_identical(self):
        product = {"paths": [{"path": "product.txt", "state": "file", "sha256": "a" * 64}],
                   "sha256": "b" * 64}
        closure = {"paths": [{"path": "product.txt", "state": "file", "sha256": "a" * 64}],
                   "sha256": "c" * 64}

        proof = plan_evidence.verify_closure(product, closure)

        self.assertEqual(proof["status"], "green")
        closure["paths"][0]["sha256"] = "d" * 64
        with self.assertRaisesRegex(plan_evidence.EvidenceError, "PRODUCT_ANCHOR_DRIFT"):
            plan_evidence.verify_closure(product, closure)

    def test_audit_owned_volatile_carrier_is_not_product_without_deliverable_declaration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            plan_dir = write_valid_plan(root, layout="v2")
            spec = plan_dir / "phases" / "P1" / "P1.1.md"
            spec.write_text(spec.read_text(encoding="utf-8").replace(
                "**Files:** lib/pkg/config.py", "**Files:** `journal.jsonl` · `artifact.txt`"),
                encoding="utf-8")
            (plan_dir / "artifact.txt").write_text("v1\n", encoding="utf-8")
            subprocess.run(("git", "add", "."), cwd=root, check=True)

            before = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")
            with (plan_dir / "journal.jsonl").open("a", encoding="utf-8") as output:
                output.write("{\"audit\": true}\n")
            after = plan_gates.phase_candidate_fingerprint(plan_dir, "P1")

            self.assertEqual(before["fingerprint"], after["fingerprint"])

    def test_task_contract_surfaces_anchor_refusal_at_pre_mutation_boundary(self):
        fixture = (Path(__file__).resolve().parents[3]
                   / "plans/archive/2026.07.24-AGENT-RELIABILITY/"
                     "artifacts/P0.2/task-contract-examples.json")
        contract = next(example["contract"] for example in json.loads(
            fixture.read_text(encoding="utf-8"))["examples"]
            if example["id"] == "routine-continuation")
        graph = {"schema_version": plan_evidence.SCHEMA_VERSION, "collisions": ["product.txt"],
                 "sha256": "a" * 64}

        self.assertEqual(
            task_contract.pre_mutation(contract, evidence_graph=graph,
                                       requires_closure_freshness=True),
            "SELF_INVALIDATING_EVIDENCE_ANCHOR",
        )

    def test_audit_finalization_binds_rebuilt_candidate_to_allowing_close_gate(self):
        before = {"fingerprint": "a" * 64}
        after = {"fingerprint": "a" * 64}

        receipt = plan_evidence.audit_finalization(
            before_candidate=before, after_candidate=after,
            lifecycle_selection={"validation": "focused"}, close_admission="allow")

        self.assertEqual(receipt["schema_version"], "audit-finalization/v1")
        self.assertEqual(receipt["after_fingerprint"], after["fingerprint"])
        with self.assertRaisesRegex(plan_evidence.EvidenceError, "AUDIT_FINALIZATION_REFUSED"):
            plan_evidence.audit_finalization(
                before_candidate=before, after_candidate=after,
                lifecycle_selection={}, close_admission="PHASE_AUDIT_STALE")
