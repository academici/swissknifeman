"""P6.2 public temporary-root conformance for provider provisioning."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from maind.doctor import provider_trust_report
from maind.health import health_report
from maind.provision import sync
from maind.provision.onboard import _unmet_steps
from tests.fixtures import capture
from tests.test_sync import _setup


def _providers(config, selection):
    config["projects"][0]["providers"] = {
        "contract_version": "1.0.0", "selection": selection,
    }


EXPECTED_MATRIX_CLASSES = (
    ("mcp", "adapter-projected", "planned", "none"),
    ("code-graph", "provider-neutral", "not-applicable", "MAIND_PROVIDER_NEUTRAL"),
    ("graph", "provider-neutral", "not-applicable", "MAIND_PROVIDER_NEUTRAL"),
    ("memory", "provider-neutral", "not-applicable", "MAIND_PROVIDER_NEUTRAL"),
    ("memory-hook", "delegated", "not-observed", "MAIND_DELEGATED:memory-context"),
    ("health-hook", "delegated", "not-observed", "MAIND_DELEGATED:health"),
    ("health-doc", "delegated", "not-observed", "MAIND_DELEGATED:health"),
    ("feature-log-hook", "delegated", "not-observed", "MAIND_DELEGATED:health"),
    ("ecosystem-skill", "delegated", "not-observed", "MAIND_DELEGATED:skills"),
    ("setup-skill", "delegated", "not-observed", "MAIND_DELEGATED:skills"),
    ("skills-catalog", "delegated", "not-observed", "MAIND_DELEGATED:skills"),
    ("agent-pack", "delegated", "not-observed", "MAIND_DELEGATED:agent-pack"),
    ("output-style", "delegated", "not-observed", "MAIND_DELEGATED:memory-context"),
    ("router-config", "delegated", "not-observed", "MAIND_DELEGATED:router"),
    ("instructions", "adapter-projected", "planned", "none"),
)


class TestProviderProvisionConformance(unittest.TestCase):
    def test_sync_health_and_doctor_cover_legacy_codex_and_dual_targets(self):
        cases = (
            ("legacy-claude", None, ("CLAUDE.md",)),
            ("codex", {"claude-code": {"enabled": False}, "codex": {"enabled": True}},
             ("AGENTS.md",)),
            ("dual", {"claude-code": {"enabled": True}, "codex": {"enabled": True}},
             ("CLAUDE.md", "AGENTS.md")),
        )
        for _name, selection, names in cases:
            with self.subTest(case=_name), tempfile.TemporaryDirectory() as tmp:
                env, config, root = _setup(tmp)
                if selection is not None:
                    _providers(config, selection)
                first = sync.run_sync(env, config, config["projects"], only="instructions", mode="auto")[0]
                self.assertEqual(first["status"], "ok")
                self.assertEqual(len(first["providers"]), len(names))
                for scope in ("", "packages/skiller", "packages/harness", "packages/maind",
                              "packages/analyst", "packages/task"):
                    for name in names:
                        self.assertTrue((root / scope / name).is_file(), (scope, name))
                # P5 owns the blocks, so unrelated user bytes remain clean and untouched.
                target = root / names[0]
                target.write_text("user prefix\n" + target.read_text(encoding="utf-8")
                                  + "\nuser suffix\n", encoding="utf-8")
                second = sync.run_sync(env, config, config["projects"], only="instructions", mode="auto")[0]
                self.assertEqual(second["status"], "ok")
                self.assertFalse(second["changed"])
                self.assertTrue(target.read_text(encoding="utf-8").startswith("user prefix\n"))
                context = sync.contexts(env, config, config["projects"])[0]
                health = health_report(env, config, config["projects"][0], memory_reachable=False,
                                       provider_context=context)
                self.assertEqual(len(health["provider_trust"]), len(names))
                doctor = provider_trust_report(env, config)
                self.assertEqual(len(doctor), len(names))
                self.assertTrue(all(not row["green"] for row in doctor))  # untrusted is non-green

    def test_unknown_provider_fails_before_sync_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, root = _setup(tmp)
            _providers(config, {"unsupported-provider": {"enabled": True}})
            with self.assertRaises(ValueError):
                sync.run_sync(env, config, config["projects"], only="instructions")
            self.assertFalse((root / "CLAUDE.md").exists())

    def test_independent_provisioner_provider_matrix_is_complete_and_honest(self):
        """The oracle is test-owned, never copied from PROVISIONERS or rendered rows."""
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _root = _setup(tmp)
            _providers(config, {"claude-code": {"enabled": True}, "codex": {"enabled": True}})
            context = sync.contexts(env, config, config["projects"])[0]
            rows = sync.provisioner_provider_matrix(
                sync.run_sync_contexts(env, config, [context], dry=True),
                context.effective_provider_ids)
        expected = tuple(
            {"provisioner": provisioner, "provider_id": provider_id,
             "support": support, "activation": activation, "diagnostic": diagnostic}
            for provisioner, support, activation, diagnostic in EXPECTED_MATRIX_CLASSES
            for provider_id in ("claude-code", "codex"))
        self.assertEqual(rows, expected)

    def test_instruction_contract_negative_matrix_and_critical_partial_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, root = _setup(tmp)
            _providers(config, {"claude-code": {"enabled": True}, "codex": {"enabled": True}})
            context = sync.contexts(env, config, config["projects"])[0]
            from harness.instructions import (apply_instructions, load_catalog, plan_instructions,
                                              repair_instructions)
            request = sync._instruction_request(context, "plan")

            missing = plan_instructions(replace(request, scope_ids=()))
            duplicate = plan_instructions(replace(request, scope_ids=("root", "root")))
            self.assertIn("INSTRUCTION_SCOPE_INVALID", {item.code for item in missing.diagnostics})
            self.assertIn("INSTRUCTION_SCOPE_INVALID", {item.code for item in duplicate.diagnostics})

            created = plan_instructions(request)
            targets = tuple(action.target_path for action in created.artifact_plan.actions)
            applied = apply_instructions(replace(request, operation_id="apply",
                                                 authorized_target_paths=targets))
            self.assertTrue(applied.green)

            changed = deepcopy(load_catalog())
            changed["scopes"][0]["sections"][0]["intent"] += " Contract-derived stale source."
            stale = plan_instructions(request, catalog=changed)
            self.assertTrue(any(item.observation == "stale-source" for item in stale.targets))
            self.assertIn("INSTRUCTION_STALE_SOURCE", {item.code for item in stale.diagnostics})

            target = root / "AGENTS.md"
            target.write_bytes(b"outside-before\n" + target.read_bytes().replace(
                b"<!-- semantic:", b"<!-- local:", 1) + b"\noutside-after\n")
            drift = plan_instructions(request)
            action = next(item for item in drift.artifact_plan.actions
                          if item.target_path == "AGENTS.md")
            repaired = repair_instructions(replace(
                request, operation_id="repair", authorized_target_paths=("AGENTS.md",),
                observed_hashes=(("AGENTS.md", action.observed_hash),),
                preimage_destination="adjacent-backup"))
            self.assertTrue(repaired.green)
            self.assertTrue(target.read_bytes().startswith(b"outside-before\n"))
            self.assertTrue(target.read_bytes().endswith(b"\noutside-after\n"))

        aggregate = sync.ProviderProvisionAggregate((
            {"provider_id": "claude-code", "status": "planned", "required": True,
             "diagnostic": None},
            {"provider_id": "codex", "status": "failed", "required": True,
             "diagnostic": "HARNESS_TRUST_REQUIRED"},
        ))
        self.assertFalse(aggregate.green)  # one-provider failure blocks a critical aggregate
        self.assertEqual(_unmet_steps({"steps": [{"name": "instructions", "status": "failed",
                                                   "detail": "Codex trust missing"}]}, dry=False),
                         [{"name": "instructions", "status": "failed",
                           "detail": "Codex trust missing"}])

    def test_public_conformance_command_generates_the_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(__file__).resolve().parents[3]
            maind = repo_root / "packages/maind/bin/maind"
            output = Path(tmp) / "provider-conformance-1.md"
            repeated = Path(tmp) / "provider-conformance-2.md"
            first = subprocess.run(
                [str(maind), "sync", "--conformance", str(output)], cwd=repo_root,
                text=True, capture_output=True, check=False)
            second = subprocess.run(
                [str(maind), "sync", "--conformance", str(repeated)], cwd=repo_root,
                text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            output_text = first.stdout + first.stderr + second.stdout + second.stderr
            self.assertNotIn("swissknifeman не найден", output_text)
            self.assertNotIn("harness не найден", output_text)
            self.assertEqual(output.read_bytes(), repeated.read_bytes())
            generated = output.read_text(encoding="utf-8")
            self.assertIn("Dual-provider", generated)
            self.assertIn("harness semantic parity/extensions", generated)
            self.assertIn("managed drift and explicit repair", generated)
            self.assertIn("independent provisioner/provider matrix", generated)
            self.assertIn("MAIND_PROVIDER_NEUTRAL", generated)
            self.assertIn("missing/duplicate instruction scope", generated)
            self.assertIn("stale source hash", generated)
            self.assertIn("one-provider partial failure critical aggregate/allow-partial", generated)
            for case in ("Claude-only legacy", "Codex-only", "Dual-provider"):
                row = next(line for line in generated.splitlines()
                           if line.startswith(f"| {case} |"))
                self.assertTrue(row.endswith("| GREEN |"), row)
            instruction_rows = [line for line in generated.splitlines()
                                if line.startswith("| instructions |")]
            self.assertEqual(len(instruction_rows), 2)
            self.assertTrue(all("| failed |" not in row and
                                ("| planned |" in row or "| dry |" in row)
                                for row in instruction_rows), instruction_rows)
            self.assertIn("| public onboard critical environment/instruction operations | GREEN |",
                          generated)
