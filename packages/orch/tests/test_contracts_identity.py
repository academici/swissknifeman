from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from orch import contracts

ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "fixtures/exec/v1/valid"


def load(kind, name):
    return json.loads((VALID / kind / (name + ".json")).read_text(encoding="utf-8"))


def codes(kind, doc):
    return [issue.code for issue in contracts.validate(doc, kind) if issue.level == "error"]


class IdentityContractTests(unittest.TestCase):
    def test_aicore_references_resolve_in_the_registry(self):
        registry = contracts.load_registry()
        for ref in ("urn:swissknifeman:aicore:error:v1", "urn:swissknifeman:aicore:artifact-ref:v1",
                    "urn:swissknifeman:aicore:digest:v1"):
            registry.resolve(ref, "urn:swissknifeman:orch:exec:run-event:v1")

    def test_new_fixtures_validate(self):
        for kind, name in (("run-event", "identity-full"), ("stage-result", "with-skills-and-modules"),
                           ("effect-receipt", "precondition-changed")):
            with self.subTest(kind=kind):
                self.assertEqual(codes(kind, load(kind, name)), [])

    def test_aicore_error_and_artifact_ref_are_validated(self):
        event = load("run-event", "identity-full")
        event["error"]["class"] = "nonsense"
        self.assertIn("enum", codes("run-event", event))
        event = load("run-event", "identity-full")
        event["raw"]["digest"] = "abc"
        self.assertIn("pattern", codes("run-event", event))
        result = load("stage-result", "with-skills-and-modules")
        result["errors"][0]["error"]["extra"] = 1
        self.assertIn("additional", codes("stage-result", result))

    def test_key_formats(self):
        event = load("run-event", "identity-full")
        for field, bad in (("event_id", "run-1"), ("causation_id", "sub-1"), ("correlation_id", "evt-1"),
                           ("attempt_id", "call-1"), ("call_id", "att-1")):
            doc = copy.deepcopy(event)
            doc[field] = bad
            with self.subTest(field=field):
                self.assertIn("pattern", codes("run-event", doc))

    def test_skill_and_module_shapes(self):
        result = load("stage-result", "with-skills-and-modules")
        doc = copy.deepcopy(result)
        doc["skills"][0]["digest"] = "0" * 64  # untagged digest
        self.assertIn("pattern", codes("stage-result", doc))
        doc = copy.deepcopy(result)
        doc["modules"][0]["version"] = "one"
        self.assertIn("pattern", codes("stage-result", doc))
        doc = copy.deepcopy(result)
        del doc["modules"][0]["id"]
        self.assertIn("required", codes("stage-result", doc))

    def test_key_reuse_across_levels(self):
        event = load("run-event", "identity-full")
        self.assertEqual(codes("run-event", event), [])
        event["run_id"] = event["event_id"]
        self.assertEqual(codes("run-event", event), ["KEY_REUSED"])
        result = load("stage-result", "with-skills-and-modules")
        result["run_id"] = result["submission_id"]
        self.assertEqual(codes("stage-result", result), ["KEY_REUSED"])
        # A document without keys of two levels cannot reuse one.
        self.assertEqual(codes("run-event", load("run-event", "started")), [])

    def test_owner_epoch_must_be_positive_in_every_document(self):
        for kind, name in (("run-event", "identity-full"), ("stage-result", "with-skills-and-modules"),
                           ("effect-receipt", "precondition-changed")):
            for epoch, expected in ((1, []), (0, ["EPOCH_INVALID"]), (-3, ["EPOCH_INVALID"])):
                doc = load(kind, name)
                doc["owner_epoch"] = epoch
                with self.subTest(kind=kind, epoch=epoch):
                    self.assertEqual(codes(kind, doc), expected)

    def test_precondition_mismatch_requires_failed_outcome(self):
        receipt = load("effect-receipt", "precondition-changed")
        self.assertEqual(codes("effect-receipt", receipt), [])
        receipt["outcome"] = "already_applied"
        self.assertEqual(codes("effect-receipt", receipt), ["PRECONDITION_MISMATCH"])
        receipt["precondition"]["matched"] = True
        self.assertEqual(codes("effect-receipt", receipt), [])

    def test_previous_documents_stay_valid_without_new_fields(self):
        for kind in ("run-event", "stage-result", "effect-receipt"):
            for path in sorted((VALID / kind).glob("*.json")):
                doc = json.loads(path.read_text(encoding="utf-8"))
                if "owner_epoch" in doc or "precondition" in doc:
                    continue
                with self.subTest(fixture=path.name):
                    self.assertEqual(codes(kind, doc), [])
