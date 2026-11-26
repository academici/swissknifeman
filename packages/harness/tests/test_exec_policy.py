"""Internal documentation."""
import json
import tempfile
import unittest
from pathlib import Path

from harness import execpolicy as ep

_ROLE_CONTENT = "You are a task orchestrator.\n\n## Plan Format\n\nplan text without markers\n"

_ROLES_CANON = {
    "catalog_version": "1.0.0",
    "roles": [
        {"pack_id": "_common", "role_id": "orchestrator", "content": _ROLE_CONTENT},
    ],
}

_TEMPLATE_TEXT = "# Orchestrator\n\ninstallation template without markers\n"

_LANDED_ROLE_CONTENT = (
    "You are a task orchestrator.\n\n"
    "PLAN\nTask 1 -> @role : goal ; deps: none ; output: <return format>\nEND\n\n"
    "## Job Contract\n\n"
    "- objective: one task target\n"
    "- output: result return format\n"
    "- tools: tools and skills\n"
    "- sources: sources and fact checking\n"
    "- boundaries: where the role ends\n"
)

_LANDED_TEMPLATE_TEXT = _LANDED_ROLE_CONTENT


def _base_policy():
    return {
        "policy_version": "1.0",
        "spawn_threshold": {
            "decision_rule": "spawn only if EVERY positive condition holds AND NO negative condition holds; a doubt is a negative",
            "positive_conditions": [
                {"id": "bulk-raw-material", "text": "flood", "provenance": "findings/05 F22"},
            ],
            "negative_conditions": [
                {"id": "parent-reuses-raw-material", "text": "reused", "provenance": "findings/05 F22"},
            ],
            "scale_by_task_class": [
                {
                    "task_class": "fact-finding", "agents": "1", "tool_calls_hint": "3-10 per agent",
                    "unverified": True, "provenance": "findings/05 F21 [UNVERIFIED]",
                },
            ],
        },
        "max_parallel_agents": {
            "subjects": [
                {
                    "subject": "session-agent-tool", "provider": "claude-code", "total": 200,
                    "total_scope": "session", "concurrent": 20, "nesting_depth": 3,
                    "settings": [], "controlled_by_us": False, "provenance": "findings/04 F17",
                },
                {
                    "subject": "workflow-runtime", "provider": "claude-code", "total": 1000,
                    "total_scope": "run", "concurrent": 16, "nesting_depth": None,
                    "settings": [], "controlled_by_us": False, "provenance": "findings/04 F17",
                },
                {
                    "subject": "codex-subagents", "provider": "codex", "total": None,
                    "total_scope": "session", "concurrent": None, "nesting_depth": None,
                    "settings": [], "controlled_by_us": False, "provenance": "findings/03 F11",
                },
            ],
            "fleet_cap": {
                "value": 2, "applies_to": "session-agent-tool",
                "condition": "file-independent tasks only",
                "provenance": "RAG:— repo-grounded",
            },
        },
        "allowed_agent_roles": {
            "source": "roles.json",
            "key": ["pack_id", "role_id"],
            "rule": "allowed = every (pack_id, role_id) present in the canon, minus exclusions",
            "exclusions": [
                {"pack_id": "_common", "role_id": "orchestrator", "reason": "delegate-only role"},
            ],
        },
        "delegation_contract": {
            "required_fields": [
                {"id": "objective", "text": "goal", "provenance": "findings/05 F19"},
                {"id": "output_format", "text": "shape", "provenance": "findings/05 F19"},
                {"id": "tool_guidance", "text": "tools", "provenance": "findings/05 F19"},
                {"id": "source_guidance", "text": "sources", "provenance": "findings/05 F19"},
                {"id": "boundaries", "text": "boundaries", "provenance": "findings/05 F19"},
            ],
            "refusal_rule": "an assignment without a declared return format is not issued",
            "enforcement_points": [
                {
                    "id": "plan-grammar-canon", "carrier": "roles.json",
                    "carrier_kind": "role-canon-content",
                    "selector": {"pack_id": "_common", "role_id": "orchestrator", "field": "content"},
                    "field_markers": dict(ep._FIELD_MARKERS),
                    "grammar_marker": ep._GRAMMAR_MARKER,
                    "status": "pending",
                    "pending_until": "2026.07.29-DEMO-PLAN P4.4",
                },
                {
                    "id": "plan-grammar-template", "carrier": "orchestrator.md",
                    "carrier_kind": "markdown-template",
                    "field_markers": dict(ep._FIELD_MARKERS),
                    "grammar_marker": ep._GRAMMAR_MARKER,
                    "status": "pending",
                    "pending_until": "2026.07.29-DEMO-PLAN P4.4",
                },
            ],
        },
    }


class ExecPolicyTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)
        (self.root / "roles.json").write_text(json.dumps(_ROLES_CANON), encoding="utf-8")
        (self.root / "orchestrator.md").write_text(_TEMPLATE_TEXT, encoding="utf-8")

        self._orig_repo_root = ep._REPO_ROOT
        self._orig_roles_json = ep._ROLES_JSON
        ep._REPO_ROOT = self.root
        ep._ROLES_JSON = self.root / "roles.json"
        self.addCleanup(self._restore_globals)

    def _restore_globals(self):
        ep._REPO_ROOT = self._orig_repo_root
        ep._ROLES_JSON = self._orig_roles_json

    def _run(self, data):
        path = self.root / "execution-policy.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return ep.run_checks(path)

    def test_positive_pending_state_is_clean(self):
        violations, code = self._run(_base_policy())
        self.assertEqual([str(v) for v in violations], [])
        self.assertEqual(code, 0)

    def test_negative_unknown_top_level_key(self):
        data = _base_policy()
        data["extra_field"] = "surprise"
        violations, code = self._run(data)
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "top-level" for v in violations))

    def test_negative_missing_required_field(self):
        data = _base_policy()
        del data["spawn_threshold"]["decision_rule"]
        violations, code = self._run(data)
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "spawn-threshold" for v in violations))

    def test_negative_numeric_object_without_provenance(self):
        data = _base_policy()
        del data["max_parallel_agents"]["subjects"][0]["provenance"]
        violations, code = self._run(data)
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "provenance" for v in violations))

    def test_negative_role_absent_from_canon(self):
        data = _base_policy()
        data["allowed_agent_roles"]["exclusions"].append(
            {"pack_id": "_common", "role_id": "no-such-role", "reason": "made up"})
        violations, code = self._run(data)
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "allowed-agent-roles" and "no-such-role" in v.message
                            for v in violations))

    def test_negative_enforced_point_with_nonexistent_address(self):
        data = _base_policy()
        point = data["delegation_contract"]["enforcement_points"][0]
        point["status"] = "enforced"
        del point["pending_until"]
        point["selector"] = {"pack_id": "_common", "role_id": "no-such-role", "field": "content"}
        violations, code = self._run(data)
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "delegation-contract" and "does not resolve" in v.message
                            for v in violations))

    def test_negative_pending_point_without_pending_until(self):
        data = _base_policy()
        del data["delegation_contract"]["enforcement_points"][1]["pending_until"]
        violations, code = self._run(data)
        self.assertEqual(code, 1)
        self.assertTrue(any(v.check == "delegation-contract" and "pending_until" in v.message
                            for v in violations))

    def test_missing_policy_file_gives_exit_2(self):
        violations, code = ep.run_checks(self.root / "nope.json")
        self.assertEqual(code, 2)
        self.assertTrue(violations)

    def _landed_policy(self):
        """Internal documentation."""
        (self.root / "roles.json").write_text(
            json.dumps({"catalog_version": "1.0.0", "roles": [
                {"pack_id": "_common", "role_id": "orchestrator", "content": _LANDED_ROLE_CONTENT},
            ]}), encoding="utf-8")
        (self.root / "orchestrator.md").write_text(_LANDED_TEMPLATE_TEXT, encoding="utf-8")
        data = _base_policy()
        for point in data["delegation_contract"]["enforcement_points"]:
            point["status"] = "enforced"
            del point["pending_until"]
        return data

    def test_positive_enforced_state_is_clean(self):
        violations, code = self._run(self._landed_policy())
        self.assertEqual([str(v) for v in violations], [])
        self.assertEqual(code, 0)

    def test_negative_enforced_point_missing_each_field_marker(self):
        for field_id, marker in ep._FIELD_MARKERS.items():
            with self.subTest(field=field_id):
                data = self._landed_policy()
                for point in data["delegation_contract"]["enforcement_points"]:
                    point["field_markers"][field_id] = marker  # keep declared marker as-is
                canon = json.loads((self.root / "roles.json").read_text(encoding="utf-8"))
                stripped = canon["roles"][0]["content"].replace(marker, "")
                canon["roles"][0]["content"] = stripped
                (self.root / "roles.json").write_text(json.dumps(canon), encoding="utf-8")
                violations, code = self._run(data)
                self.assertEqual(code, 1)
                self.assertTrue(any(
                    v.check == "delegation-contract" and "markers are physically missing" in v.message
                    and field_id in v.message
                    for v in violations), [str(v) for v in violations])

    def test_negative_enforced_point_missing_grammar_marker(self):
        data = self._landed_policy()
        canon = json.loads((self.root / "roles.json").read_text(encoding="utf-8"))
        canon["roles"][0]["content"] = canon["roles"][0]["content"].replace(ep._GRAMMAR_MARKER, "")
        (self.root / "roles.json").write_text(json.dumps(canon), encoding="utf-8")
        violations, code = self._run(data)
        self.assertEqual(code, 1)
        self.assertTrue(any(
            v.check == "delegation-contract" and "grammar_marker is not physically present" in v.message
            for v in violations), [str(v) for v in violations])


if __name__ == "__main__":
    unittest.main()
