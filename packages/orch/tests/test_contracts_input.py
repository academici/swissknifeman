from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from orch import contracts

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("execution-input", "run-policy", "role-manifest", "capability-record")
EXPECTED = {
    "run-policy/commit-with-git-none.json": "COMMIT_POLICY_CONFLICT",
    "run-policy/isolation-with-git-none.json": "ISOLATION_POLICY_CONFLICT",
    "run-policy/isolation-bad-mode.json": "enum",

    "execution-input/missing-goal.json": "required",
    "execution-input/extra-field.json": "additional",
    "execution-input/lifecycle-leak.json": "LIFECYCLE_LEAK",
    "execution-input/bad-provenance.json": "one_of",
    "execution-input/digest-mismatch.json": "DIGEST_MISMATCH",
    "execution-input/read-only-write-authority.json": "INPUT_AUTHORITY",
    "run-policy/required-skip.json": "POLICY_REQUIRED_REFUSE",
    "run-policy/review-rounds-3.json": "POLICY_REVIEW_LIMIT",
    "run-policy/two-primary.json": "POLICY_PRIMARY",
    "role-manifest/plan-authority-mismatch.json": "ROLE_AUTHORITY",
    "role-manifest/inline-body.json": "additional",
    "capability-record/declared-supported-no-doc.json": "CAPABILITY_EVIDENCE",
    "capability-record/bad-support.json": "enum",
    "run-policy/fallback-undeclared.json": "FALLBACK_UNDECLARED",
    "capability-record/fresh-before-observed.json": "CAPABILITY_FRESHNESS",
    "execution-input/condensed-drift.json": "CONDENSED_REQUIRED_DRIFT",
    "execution-input/research-bad-need.json": "enum",
    "execution-input/research-extra-key.json": "additional",
}


def fixture(kind, name):
    path = ROOT / "fixtures/exec/v1/valid" / kind / (name + ".json")
    return json.loads(path.read_text(encoding="utf-8"))


def signed(doc):
    result = copy.deepcopy(doc)
    prefix = result["input_id"].rsplit("@", 1)[0]
    result["input_id"] = prefix
    result["digest"] = contracts.canonical_digest(result)
    result["input_id"] = prefix + "@" + result["digest"][:12]
    return result


class InputContractTests(unittest.TestCase):
    def test_on_demand_json_needs_accessible_identity_and_cannot_hide_inline_content(self):
        doc = fixture("execution-input", "plan-bound")
        entry = {"path": "fixtures/manifest.json", "why": "inspect provenance", "required": True,
                 "exists": True, "sha256": "a" * 64, "delivery": "on-demand"}
        doc["reads"] = [entry]
        self.assertEqual([i for i in contracts.validate(signed(doc), "execution-input") if i.level == "error"], [])
        for change in ({"included": "somewhere"}, {"path": "@plan/knowledge/private.json"}, {"path": "fixtures/manifest.md"},
                       {"path": "../private.json"},
                       {"sha256": None}, {"content": {}}, {"section": "rows"},
                       {"exists": False}, {"error": "invalid JSON"}):
            bad = copy.deepcopy(doc)
            bad["reads"][0].update(change)
            if change == {"sha256": None}:
                del bad["reads"][0]["sha256"]
            self.assertIn("READ_DELIVERY_INVALID", [i.code for i in contracts.validate(signed(bad), "execution-input")])
    def assert_code(self, kind, doc, code):
        issues = contracts.validate(doc, kind)
        self.assertIn(code, [issue.code for issue in issues], issues)

    def test_valid_fixtures(self):
        for kind in KINDS:
            paths = sorted((ROOT / "fixtures/exec/v1/valid" / kind).glob("*.json"))
            self.assertTrue(paths, kind)
            for path in paths:
                with self.subTest(kind=kind, name=path.name):
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    issues = contracts.validate(doc, kind)
                    self.assertEqual([i for i in issues if i.level == "error"], [])
                    if kind == "execution-input":
                        self.assertEqual(doc["digest"], contracts.canonical_digest(doc))
                        self.assertTrue(doc["input_id"].endswith("@" + doc["digest"][:12]))

    def test_read_may_name_the_pack_key_that_holds_it(self):
        path = sorted((ROOT / "fixtures/exec/v1/valid/execution-input").glob("*.json"))[0]
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["reads"] = [{"path": "a.md", "why": "w", "required": True, "exists": True, "included": "reads/1"}]
        doc["digest"] = contracts.canonical_digest(doc)
        doc["input_id"] = doc["input_id"].split("@")[0] + "@" + doc["digest"][:12]
        self.assertEqual([i for i in contracts.validate(doc, "execution-input") if i.level == "error"], [])

    def test_invalid_fixtures_have_exactly_one_expected_error(self):
        paths = [path for kind in KINDS for path in (ROOT / "fixtures/exec/v1/invalid" / kind).glob("*.json")]
        self.assertEqual({str(p.relative_to(ROOT / "fixtures/exec/v1/invalid")) for p in paths}, set(EXPECTED))
        for path in paths:
            key = str(path.relative_to(ROOT / "fixtures/exec/v1/invalid"))
            with self.subTest(fixture=key):
                issues = contracts.validate(json.loads(path.read_text(encoding="utf-8")), path.parent.name)
                self.assertEqual([i.code for i in issues if i.level == "error"], [EXPECTED[key]])

    def test_schemas_load_and_all_properties_have_descriptions(self):
        registry = contracts.load_registry()

        def check(node):
            if isinstance(node, dict):
                for name, prop in node.get("properties", {}).items():
                    self.assertIsInstance(prop.get("description"), str, name)
                    self.assertTrue(prop["description"], name)
                for value in node.values():
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)

        for kind in KINDS:
            node, schema_id = registry.for_kind(kind)
            self.assertEqual(schema_id, contracts.URN_PREFIX + kind + ":v1")
            check(node)

    def test_digest_excludes_derived_suffix_but_binds_identity(self):
        doc = fixture("execution-input", "plan-bound")
        original = copy.deepcopy(doc)
        before = contracts.canonical_digest(doc)
        doc["input_id"] = doc["input_id"].rsplit("@", 1)[0]
        self.assertEqual(contracts.canonical_digest(doc), before)
        doc["input_id"] += "@000000000000"
        doc["digest"] = "other"
        self.assertEqual(contracts.canonical_digest(doc), before)
        doc["input_id"] = "different-task@000000000000"
        self.assertNotEqual(contracts.canonical_digest(doc), before)
        self.assertEqual(contracts.canonical_digest(original), original["digest"])

    def test_input_id_and_check_carriers(self):
        doc = fixture("execution-input", "plan-bound")
        doc["input_id"] = doc["input_id"].rsplit("@", 1)[0] + "@000000000000"
        self.assert_code("execution-input", doc, "INPUT_ID")
        for carrier in ({}, {"cmd": "true", "procedure": "observe"}):
            doc = fixture("execution-input", "plan-bound")
            doc["acceptance"]["checks"] = [{"id": "V1", "expect": "pass", "kind": "acceptance", **carrier}]
            self.assert_code("execution-input", signed(doc), "CHECK_CARRIER")

    def test_read_only_input_authority(self):
        for read_only in (True, False, None):
            for authority in ("none", "code_scope"):
                with self.subTest(read_only=read_only, authority=authority):
                    doc = fixture("execution-input", "review-only")
                    if read_only is None:
                        del doc["scope"]["read_only"]
                    else:
                        doc["scope"]["read_only"] = read_only
                    doc["result_contract"]["write_authority"] = authority
                    issues = contracts.validate(signed(doc), "execution-input")
                    expected = [("/result_contract/write_authority", "INPUT_AUTHORITY", "error")] \
                        if read_only is True and authority == "code_scope" else []
                    self.assertEqual([(i.path, i.code, i.level) for i in issues], expected)

    def test_lifecycle_exceptions_levels_and_json_pointers(self):
        doc = fixture("execution-input", "plan-bound")
        doc["provenance"]["generated_by"]["tool"] = "plan-bridge register report_api"
        doc["constraints"] = [{"text": "Use report_api", "source": "plan.rules[2]"}]
        issues = contracts.validate(signed(doc), "execution-input")
        self.assertEqual([(i.path, i.code, i.level) for i in issues],
                         [("/constraints/0/text", "LIFECYCLE_LEAK", "warning")])
        doc["constraints"][0]["source"] = "item.rules[0]"
        self.assertEqual(contracts.validate(signed(doc), "execution-input")[0].level, "error")
        doc = fixture("execution-input", "adhoc")
        doc["provenance"]["request"] = "Call report_api"
        self.assert_code("execution-input", signed(doc), "LIFECYCLE_LEAK")
        doc = fixture("execution-input", "plan-bound")
        doc["reads"][0]["content"] = {"~/key": ["report API"]}
        issues = contracts.validate(signed(doc), "execution-input")
        self.assertEqual(issues[0].path, "/reads/0/content/~0~1key/0")

    def test_policy_dependency_graph_and_defaults(self):
        for dependencies in (["missing"], ["git"]):
            doc = fixture("run-policy", "solo")
            doc["stages"][0]["depends_on"] = dependencies
            self.assert_code("run-policy", doc, "POLICY_DEPENDS")
        doc = fixture("run-policy", "solo")
        doc["stages"][1]["id"] = doc["stages"][0]["id"]
        self.assert_code("run-policy", doc, "POLICY_DEPENDS")
        doc = fixture("run-policy", "solo")
        for index, stage in enumerate(doc["stages"]):
            stage["depends_on"] = [] if not index else [doc["stages"][index - 1]["id"]]
        self.assertEqual(contracts.validate(doc, "run-policy"), [])

    def test_policy_review_presence_and_limits(self):
        doc = fixture("run-policy", "solo")
        doc["review"]["enabled"] = True
        self.assert_code("run-policy", doc, "POLICY_REVIEW_STAGE")
        doc["stages"].insert(3, {"id": "review", "kind": "review", "role": "reviewer",
                                  "required": True, "on_unavailable": "refuse"})
        self.assertEqual(contracts.validate(doc, "run-policy"), [])
        doc["review"]["max_corrections"] = 2
        self.assert_code("run-policy", doc, "POLICY_REVIEW_LIMIT")
        doc = fixture("run-policy", "solo")
        doc["stages"][1]["kind"] = "bounded"
        self.assert_code("run-policy", doc, "POLICY_PRIMARY")

    def test_policy_numeric_boundaries(self):
        cases = (("retries_budget", "total_max"), ("review", "max_rounds"), ("review", "max_corrections"))
        for parent, field in cases:
            doc = fixture("run-policy", "solo")
            doc[parent][field] = -1
            self.assert_code("run-policy", doc, "POLICY_NEGATIVE")
            doc[parent][field] = 0
            self.assertEqual(contracts.validate(doc, "run-policy"), [])
            doc[parent][field] = True
            self.assert_code("run-policy", doc, "type")
        for extra in ({"retries": {"max": -1}}, {"timeouts": {"stage_s": -1}},
                      {"timeouts": {"silence_s": -1}}):
            doc = fixture("run-policy", "solo")
            doc["stages"][1].update(extra)
            self.assert_code("run-policy", doc, "POLICY_NEGATIVE")

    def test_commit_policy_shape_roles_and_legacy_compatibility(self):
        self.assertEqual(contracts.validate(fixture("run-policy", "solo"), "run-policy"), [])
        for scope in ("item", "unit"):
            doc = fixture("run-policy", "commit-policy")
            doc["commit"]["scope"] = scope
            self.assertEqual(contracts.validate(doc, "run-policy"), [])
        for field in ("scope", "roles", "message_convention"):
            doc = fixture("run-policy", "commit-policy")
            del doc["commit"][field]
            self.assert_code("run-policy", doc, "required")
        for roles in ([], ["executor", "executor"], ["coordinator"]):
            doc = fixture("run-policy", "commit-policy")
            doc["commit"]["roles"] = roles
            self.assertTrue(contracts.validate(doc, "run-policy"))
        for value in (None, [], "wrong", 1):
            doc = fixture("run-policy", "commit-policy")
            doc["commit"] = value
            self.assert_code("run-policy", doc, "type")

    def test_isolation_policy_shape_and_semantics(self):
        self.assertEqual(contracts.validate(fixture("run-policy", "isolation-worktree"), "run-policy"), [])
        doc = fixture("run-policy", "isolation-worktree")
        doc["isolation"]["mode"] = "shared"
        doc["git_action"] = "none"
        del doc["commit"]
        self.assertEqual(contracts.validate(doc, "run-policy"), [])
        for field in ("mode", "integration", "recheck"):
            doc = fixture("run-policy", "isolation-worktree")
            del doc["isolation"][field]
            self.assert_code("run-policy", doc, "required")
        for field, value in (("integration", "parallel"), ("recheck", "some")):
            doc = fixture("run-policy", "isolation-worktree")
            doc["isolation"][field] = value
            self.assert_code("run-policy", doc, "enum")
        for value in (None, [], "worktree"):
            doc = fixture("run-policy", "isolation-worktree")
            doc["isolation"] = value
            self.assert_code("run-policy", doc, "type")
        doc = fixture("run-policy", "solo")
        self.assertNotIn("isolation", doc)
        self.assertEqual(contracts.validate(doc, "run-policy"), [])

    def test_role_authority_both_directions_and_read_only(self):
        doc = fixture("role-manifest", "executor-minimal")
        doc["tools"]["plan_api"] = "write"
        self.assert_code("role-manifest", doc, "ROLE_AUTHORITY")
        doc["write_authority"] = "plan"
        self.assertEqual(contracts.validate(doc, "role-manifest"), [])
        doc["tools"]["plan_api"] = "none"
        doc["write_authority"] = "none"
        self.assert_code("role-manifest", doc, "ROLE_AUTHORITY")
        doc["tools"]["filesystem"] = "read"
        self.assertEqual(contracts.validate(doc, "role-manifest"), [])

    def test_capability_evidence_and_open_extensions(self):
        for support_path in (("model", "set"), ("effort", "observe"), ("restrictions", "sandbox_os"),
                             ("skill_delivery", "per_run_isolation"), ("stream",), ("attach",),
                             ("cancel",), ("resume",), ("usage",), ("plan_write_prevention",)):
            doc = fixture("capability-record", "native-claude-code-declared")
            doc["model"]["set"] = "unknown"
            doc["evidence"][0]["kind"] = "probe"
            target = doc
            for key in support_path[:-1]:
                target = target[key]
            target[support_path[-1]] = "supported"
            self.assert_code("capability-record", doc, "CAPABILITY_EVIDENCE")
            for kind in ("doc", "code"):
                doc["evidence"][0]["kind"] = kind
                self.assertEqual(contracts.validate(doc, "capability-record"), [])
            doc["evidence"][0]["kind"] = "probe"
            doc["status"] = "probed"
            self.assertEqual(contracts.validate(doc, "capability-record"), [])
        doc = fixture("capability-record", "native-claude-code-declared")
        doc["model"]["set"] = "unknown"
        doc["evidence"][0]["kind"] = "perplexity"
        doc["extensions"] = {"nested": {"set": "supported"}, "any-json": [None, False, 1]}
        self.assertEqual(contracts.validate(doc, "capability-record"), [])

    def test_malformed_json_shapes_report_issues_without_crashing(self):
        examples = {kind: fixture(kind, name) for kind, name in (
            ("execution-input", "plan-bound"), ("run-policy", "solo"),
            ("role-manifest", "executor-minimal"), ("capability-record", "native-claude-code-declared"))}
        for kind, doc in examples.items():
            for value in (None, [], "wrong", 1):
                with self.subTest(kind=kind, value=value):
                    self.assert_code(kind, value, "type")
            for field in doc:
                if field in ("$schema", "contract_version"):
                    continue
                with self.subTest(kind=kind, field=field):
                    malformed = copy.deepcopy(doc)
                    malformed[field] = None
                    self.assertTrue(contracts.validate(malformed, kind))
