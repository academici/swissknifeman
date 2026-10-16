from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from aicore.util import digest as canonical

from orch import contracts

ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "fixtures/exec/v1/valid"
ERROR_SCHEMA = ROOT.parent / "aicore/schemas/error/v1/error.schema.json"


def load(kind, name):
    return json.loads((VALID / kind / (name + ".json")).read_text(encoding="utf-8"))


def codes(kind, doc):
    return [issue.code for issue in contracts.validate(doc, kind) if issue.level == "error"]


class ProtocolContractTests(unittest.TestCase):
    def test_new_fixtures_validate(self):
        for kind, name in (("launch-plan", "dry-run-proof"), ("capability-record", "probed-fresh"),
                           ("run-policy", "on-error-table"), ("execution-input", "condensed")):
            with self.subTest(kind=kind):
                self.assertEqual(codes(kind, load(kind, name)), [])

    def test_aicore_permissions_and_source_refs_resolve(self):
        registry = contracts.load_registry()
        for ref in ("urn:swissknifeman:aicore:permissions:v1#/$defs/permissions",
                    "urn:swissknifeman:aicore:capability-support:v1#/$defs/source"):
            registry.resolve(ref, "urn:swissknifeman:orch:exec:run-policy:v1")

    def test_launch_plan_digest_is_the_canonical_digest(self):
        plan = load("launch-plan", "dry-run-proof")
        body = {key: value for key, value in plan.items() if key != "digest"}
        self.assertEqual(plan["digest"], contracts.canonical_digest(body))
        self.assertEqual(plan["digests"]["input"], plan["input_digest"])
        self.assertEqual(plan["config"]["digest"], plan["digests"]["config"])
        values = canonical.sha256_hex(canonical.canonical_json_bytes(plan["config"]["values"]))
        self.assertEqual(plan["config"]["digest"], values)

    def test_launch_plan_shapes(self):
        plan = load("launch-plan", "dry-run-proof")
        for path, mutate, code in (
            ("digests", lambda d: d["digests"].pop("roles"), "required"),
            ("decision kind", lambda d: d["decisions"][0].update(kind="other"), "enum"),
            ("decision stage", lambda d: d["decisions"][0].update(stage_id="Bad Stage"), "pattern"),
            ("tie break", lambda d: d["decisions"][0].update(tie_break="Declared"), "pattern"),
            ("policy decision", lambda d: d["policy_decision"].update(decision="maybe"), "enum"),
            ("reason code", lambda d: d["policy_decision"].update(reason_codes=["lower"]), "pattern"),
            ("proof source", lambda d: d["proof"]["capabilities"][0].update(source="guessed"), "enum"),
            ("proof extra", lambda d: d["proof"].update(extra=1), "additional"),
            ("chain", lambda d: d["refusals"][0]["chain"][0].pop("reason"), "required"),
            ("delivery skill", lambda d: d["stages"][0]["delivery"]["skills"][0].update(digest="0" * 64), "pattern"),
            ("module", lambda d: d["modules"][0].update(version="x"), "pattern"),
            ("input ref", lambda d: d["input_ref"].update(size=-1), "minimum"),
        ):
            doc = copy.deepcopy(plan)
            mutate(doc)
            with self.subTest(path=path):
                self.assertIn(code, codes("launch-plan", doc))

    def test_launch_plan_key_reuse(self):
        plan = load("launch-plan", "dry-run-proof")
        plan["run_id"] = plan["submission_id"]
        self.assertEqual(codes("launch-plan", plan), ["KEY_REUSED"])

    def test_condense_stage_kind_is_accepted(self):
        plan = load("launch-plan", "dry-run-proof")
        plan["stages"][0]["kind"] = "condense"
        self.assertEqual(codes("launch-plan", plan), [])

    def test_on_error_table_covers_the_classes_of_error_v1(self):
        error = json.loads(ERROR_SCHEMA.read_text(encoding="utf-8"))
        classes = set(error["$defs"]["error-class"]["enum"]) | {"unknown_outcome"}
        policy = load("run-policy", "on-error-table")
        self.assertEqual(set(policy["on_error"]), classes)
        registry = contracts.load_registry()
        node, _ = registry.for_kind("run-policy")
        self.assertEqual(set(node["properties"]["on_error"]["propertyNames"]["enum"]), classes)

    def test_on_error_rejects_unknown_class_action_and_extra_fields(self):
        policy = load("run-policy", "on-error-table")
        for mutate, code in (
            (lambda d: d["on_error"].update(cosmic_ray={"action": "stop"}), "property_name"),
            (lambda d: d["on_error"]["quota"].update(action="panic"), "enum"),
            (lambda d: d["on_error"]["quota"].update(max=-1), "minimum"),
            (lambda d: d["on_error"]["quota"].update(extra=1), "additional"),
            (lambda d: d["on_error"]["quota"].pop("action"), "required"),
            (lambda d: d["sandbox"].update(profile="container"), "enum"),
            (lambda d: d["sandbox"].update(filesystem=["root"]), "enum"),
            (lambda d: d.update(version="1.0"), "pattern"),
            (lambda d: d["budgets"].update(brief_max_bytes=-1), "minimum"),
            (lambda d: d["fallback_routes"][0].pop("model_class"), "required"),
        ):
            doc = copy.deepcopy(policy)
            mutate(doc)
            self.assertIn(code, codes("run-policy", doc))

    def test_fallback_route_needs_declared_routes(self):
        policy = load("run-policy", "on-error-table")
        policy["on_error"]["timeout"] = {"action": "fallback_route"}
        self.assertEqual(codes("run-policy", policy), [])
        policy["fallback_routes"] = []
        self.assertEqual(codes("run-policy", policy), ["FALLBACK_UNDECLARED"])
        del policy["fallback_routes"]
        policy["on_error"]["transport"] = {"action": "fallback_route"}
        self.assertEqual(codes("run-policy", policy), ["FALLBACK_UNDECLARED", "FALLBACK_UNDECLARED"])
        policy["on_error"] = {"timeout": {"action": "retry", "max": 3}}
        self.assertEqual(codes("run-policy", policy), [])

    def test_capability_freshness(self):
        record = load("capability-record", "probed-fresh")
        for observed, fresh, expected in (
            ("2026-10-10T12:00:00Z", "2026-10-10T12:00:00Z", []),
            ("2026-10-10T12:00:00.5Z", "2026-10-10T12:00:00Z", ["CAPABILITY_FRESHNESS"]),
            ("2026-10-10T12:00:00Z", "2026-10-10T11:59:59Z", ["CAPABILITY_FRESHNESS"]),
        ):
            doc = copy.deepcopy(record)
            doc.update(observed_at=observed, fresh_until=fresh)
            self.assertEqual(codes("capability-record", doc), expected, (observed, fresh))
        doc = copy.deepcopy(record)
        del doc["fresh_until"]
        self.assertEqual(codes("capability-record", doc), [])

    def test_capability_freshness_compares_any_number_of_fraction_digits(self):
        record = load("capability-record", "probed-fresh")
        for observed, fresh, expected in (
            ("2026-10-10T12:00:00.123456789Z", "2026-10-10T11:00:00.123456789Z", ["CAPABILITY_FRESHNESS"]),
            ("2026-10-10T12:00:00.1234567891Z", "2026-10-10T12:00:00.1234567890Z", ["CAPABILITY_FRESHNESS"]),
            ("2026-10-10T12:00:00.123456789Z", "2026-10-10T12:00:00.123456789Z", []),
            ("2026-10-10T12:00:00.1Z", "2026-10-10T12:00:00.100000000Z", []),
            ("2026-10-10T12:00:00Z", "2026-10-10T12:00:00.000000001Z", []),
            ("2026-10-10T12:00:00.000000001Z", "2026-10-10T12:00:00Z", ["CAPABILITY_FRESHNESS"]),
            ("2026-13-10T12:00:00Z", "2026-10-10T11:00:00Z", []),  # not a calendar time: nothing to compare
        ):
            doc = copy.deepcopy(record)
            doc.update(observed_at=observed, fresh_until=fresh)
            self.assertEqual(codes("capability-record", doc), expected, (observed, fresh))

    def test_capability_source_and_status(self):
        record = load("capability-record", "probed-fresh")
        for source, status, expected in (
            ("probed", "probed", []), ("declared", "declared", []), ("inferred", "declared", []),
            ("declared", "probed", ["CAPABILITY_FRESHNESS"]), ("probed", "declared", ["CAPABILITY_FRESHNESS"]),
            ("inferred", "probed", ["CAPABILITY_FRESHNESS"]),
        ):
            doc = copy.deepcopy(record)
            doc.update(source=source, status=status)
            if status == "declared":
                doc["evidence"] = [{"kind": "doc", "ref": "fixture:doc"}]
            self.assertEqual(codes("capability-record", doc), expected, (source, status))
        doc = copy.deepcopy(record)
        doc["source"] = "guessed"
        self.assertIn("enum", codes("capability-record", doc))

    def test_previous_capability_records_have_no_freshness_requirements(self):
        record = load("capability-record", "native-claude-code-declared")
        self.assertNotIn("source", record)
        self.assertEqual(codes("capability-record", record), [])

    def test_condensed_required_digest(self):
        doc = load("execution-input", "condensed")
        self.assertEqual(codes("execution-input", doc), [])
        self.assertEqual(doc["condensed"]["required_digest"], contracts.required_digest(doc))
        self.assertIn("escalation", doc)
        for name, mutate in (
            ("goal", lambda d: d.update(goal=d["goal"] + " changed")),
            ("route", lambda d: d["route"]["minimum"].update(effort="max")),
            ("escalation", lambda d: d.pop("escalation")),
            ("decisions", lambda d: d.update(decisions=[])),
        ):
            drifted = copy.deepcopy(doc)
            mutate(drifted)
            self.assertNotEqual(drifted, doc, name)
            with self.subTest(key=name):
                self.assertEqual(codes("execution-input", sealed_digest_only(drifted)), ["CONDENSED_REQUIRED_DRIFT"])

    def test_optional_part_does_not_enter_the_required_digest(self):
        doc = load("execution-input", "condensed")
        changed = copy.deepcopy(doc)
        changed["why"] += " Extra words."
        changed["guidance"] = "Other guidance."
        self.assertEqual(contracts.required_digest(changed), doc["condensed"]["required_digest"])
        self.assertEqual(codes("execution-input", sealed_digest_only(changed)), [])
        self.assertEqual(contracts.required_digest({"goal": "x"}),
                         contracts.required_digest({"goal": "x", "why": "y"}))

    def test_required_digest_is_over_canonical_json_of_the_listed_keys(self):
        from hashlib import sha256
        doc = {"goal": "g", "route": {"minimum": {"class": "economy", "effort": "low"}}, "why": "ignored"}
        text = '{"goal":"g","route":{"minimum":{"class":"economy","effort":"low"}}}'
        self.assertEqual(contracts.required_digest(doc), sha256(text.encode()).hexdigest())

    def test_condensed_with_float_is_reported_not_raised(self):
        doc = load("execution-input", "condensed")
        doc["constraints"] = [{"text": "x", "n": 1.5}]
        self.assertIn("CONDENSED_REQUIRED_DRIFT", [i.code for i in contracts.validate(doc, "execution-input")])

    def test_lone_surrogate_is_reported_not_raised(self):
        doc = load("execution-input", "condensed")
        doc["goal"] = json.loads('"\\ud800"')
        self.assertIn("CONDENSED_REQUIRED_DRIFT", [i.code for i in contracts.validate(doc, "execution-input")])
        doc.pop("condensed")
        self.assertIn("DIGEST_MISMATCH", [i.code for i in contracts.validate(doc, "execution-input")])
        del doc["digest"]
        contracts.validate(doc, "execution-input")  # must not raise

    def test_condensed_shapes(self):
        doc = load("execution-input", "condensed")
        for mutate, code in (
            (lambda d: d["condensed"]["parts"][0].update(kind="gossip"), "enum"),
            (lambda d: d["condensed"]["parts"][0]["source"].pop("path"), "required"),
            (lambda d: d["condensed"].pop("required_digest"), "required"),
            (lambda d: d["condensed"]["parts"][0].update(summary=""), "min_length"),
            (lambda d: d["provenance"].update(commit="XYZ"), "one_of"),
        ):
            changed = copy.deepcopy(doc)
            mutate(changed)
            self.assertIn(code, codes("execution-input", changed))

    def test_previous_documents_stay_valid(self):
        for kind in ("launch-plan", "run-policy", "capability-record", "execution-input"):
            for path in sorted((VALID / kind).glob("*.json")):
                doc = json.loads(path.read_text(encoding="utf-8"))
                if any(key in doc for key in ("digests", "on_error", "source", "condensed")):
                    continue
                with self.subTest(fixture=f"{kind}/{path.name}"):
                    self.assertEqual(codes(kind, doc), [])


def sealed_digest_only(doc):
    """Re-sign the document digest and input_id without touching condensed.required_digest."""
    doc = copy.deepcopy(doc)
    doc.pop("digest")
    doc["digest"] = contracts.canonical_digest(doc)
    doc["input_id"] = doc["input_id"].rsplit("@", 1)[0] + "@" + doc["digest"][:12]
    return doc
