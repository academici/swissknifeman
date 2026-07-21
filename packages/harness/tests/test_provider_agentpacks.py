"""P5.4 role catalog: all real consumers, never a representative shortcut."""
import re
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import ArtifactActionKind, apply_plan, plan_artifact_lock, serialize_lock
from harness.agentpacks import (agent_model_trace, compare_agent_inventory, expected_agent_inventory,
                                load_claude_role_bindings, plan_agent_artifact, project_agent_role,
                                semantic_agent_roles)
import tests.fixtures as fx


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "configs/common/agent-packs/roles.json"
BINDINGS = ROOT / "configs/claude-code/agent-packs/role-bindings.json"
FORBIDDEN = re.compile(r"\.claude(?:/|\b)|(?<![\w-])/(?:task:[a-z-]+|effort|clear)\b|"
                       r"\bWorkflow\b|\bSubagentStop\b|"
                       r"(?<![\w-])(?:Read|Grep|Glob|Bash|Edit|Write)(?![\w-])")


def legacy_source(role):
    return (ROOT / "configs/claude-code/agent-packs" / role.pack_id / "agents" /
            f"{role.role_id}.md").read_text(encoding="utf-8")


def body(text):
    return text.split("---\n", 2)[2]


class ProviderAgentpackCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = fx.real_env(Path(self._tmp.name))
        self.roles = semantic_agent_roles(CATALOG)
        self.claude_bindings = load_claude_role_bindings(BINDINGS, self.roles)

    def tearDown(self):
        self._tmp.cleanup()

    def test_independent_inventory_has_all_44_roles_once(self):
        expected = expected_agent_inventory(self.env)
        report = compare_agent_inventory(self.roles, expected)
        self.assertEqual(len(expected), 44)
        self.assertEqual(report, {"missing": (), "extra": (), "duplicates": ()})

    def test_model_trace_resolves_every_binding_through_pack_defaults(self):
        clean = {"missing": (), "extra": (), "duplicates": (), "unknown_selector": (),
                 "model_class_mismatch": ()}
        self.assertEqual(agent_model_trace(self.roles, BINDINGS, self.env), clean)
        source = json.loads(BINDINGS.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "bindings.json"
            value = json.loads(json.dumps(source))
            value["roles"] = value["roles"][1:]
            altered.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(agent_model_trace(self.roles, altered, self.env)["missing"],
                             (("_common", "orchestrator"),))
            value = json.loads(json.dumps(source))
            value["roles"].append({"pack_id": "unknown", "role_id": "role",
                                   "model_selector": "opus", "color": "blue"})
            altered.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(agent_model_trace(self.roles, altered, self.env)["extra"],
                             (("unknown", "role"),))
            value = json.loads(json.dumps(source))
            value["roles"].append(dict(value["roles"][0]))
            altered.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(agent_model_trace(self.roles, altered, self.env)["duplicates"],
                             (("_common", "orchestrator"),))
            value = json.loads(json.dumps(source))
            value["roles"][0]["model_selector"] = "not-a-selector"
            altered.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(agent_model_trace(self.roles, altered, self.env)["unknown_selector"],
                             (("_common", "orchestrator", "not-a-selector"),))
            value = json.loads(json.dumps(source))
            value["roles"][0]["model_selector"] = "haiku"
            altered.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(agent_model_trace(self.roles, altered, self.env)["model_class_mismatch"],
                             (("_common", "orchestrator", "implementation", "economy"),))

    def test_claude_projection_equals_every_legacy_consumer_before_wrapper(self):
        """Legacy files are compatibility assets, not renderer inputs or a second canon."""
        for role in self.roles:
            rendered = project_agent_role(role, "claude-code",
                                          claude_bindings=self.claude_bindings).rendered.decode("utf-8")
            legacy = legacy_source(role)
            self.assertEqual(rendered, legacy, f"{role.pack_id}/{role.role_id}")

    def test_every_role_renders_or_qualified_blocks_and_inspects_consumers(self):
        rendered, blocked = [], []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for role in self.roles:
                key = f"{role.pack_id}/{role.role_id}"
                try:
                    projection = project_agent_role(role, "codex")
                except ValueError as error:
                    blocked.append((key, str(error)))
                    continue
                target = root / projection.target_path.replace("{{PACK_PREFIX}}", "fixture")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(projection.rendered)
                actual = target.read_bytes()
                self.assertIsNone(FORBIDDEN.search(actual.decode("utf-8")), key)
                parsed = tomllib.loads(actual.decode("utf-8"))
                self.assertEqual(parsed["model"], {"economy": "gpt-5.6-luna",
                                                   "implementation": "gpt-5.6-terra",
                                                   "frontier": "gpt-5.6-sol"}[role.model_class])
                self.assertEqual(parsed["skills"], list(role.skills))
                self.assertEqual(parsed["command_requirements"], list(role.command_ids))
                rendered.append(key)
        self.assertEqual(len(rendered), 43)
        self.assertEqual(blocked, [("_common/orchestrator",
                                    "HARNESS_ACTIVATION_UNSUPPORTED:codex:command.workflow-carrier:P4")])

    def test_codex_role_uses_p2_plan_and_lock_not_an_untracked_write(self):
        role = next(role for role in self.roles if role.role_id == "blade-review")
        expected = plan_agent_artifact(role, provider_id="codex", catalog_path=CATALOG,
                                       pack_prefix="fixture")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = plan_artifact_lock(root, (expected,), lock_bytes=None)
            apply_plan(root, plan)
            self.assertTrue((root / expected.target.path).exists())
            self.assertIn(b"harness.agent-role.catalog", serialize_lock(plan.next_lock))
            clean = plan_artifact_lock(root, (expected,), lock_bytes=serialize_lock(plan.next_lock))
            self.assertEqual(clean.actions[0].action, ArtifactActionKind.NOOP)
            (root / expected.target.path).write_text("managed drift\n", encoding="utf-8")
            repaired = plan_artifact_lock(root, (expected,), lock_bytes=serialize_lock(plan.next_lock),
                                          repair_artifact_ids=(expected.provenance.artifact_id,))
            self.assertEqual(repaired.actions[0].action, ArtifactActionKind.REPAIR)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            claude_expected = plan_agent_artifact(role, provider_id="claude-code",
                                                   catalog_path=CATALOG,
                                                   claude_bindings_path=BINDINGS)
            claude_plan = plan_artifact_lock(root, (claude_expected,), lock_bytes=None)
            apply_plan(root, claude_plan)
            self.assertEqual((root / claude_expected.target.path).read_text(encoding="utf-8"),
                             legacy_source(role))


if __name__ == "__main__":
    unittest.main()
