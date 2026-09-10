#!/usr/bin/env python3
"""Acceptance tests for the P5 fleet transaction runner."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("p5-consumer-reconcile.py")
SPEC = importlib.util.spec_from_file_location("p5_consumer_reconcile", SCRIPT)
p5 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(p5)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(p5.pretty_bytes(value))


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


@contextmanager
def environment(**values):
    patch = {key: value for key, value in values.items() if value is not None}
    removed = [key for key, value in values.items() if value is None]
    with mock.patch.dict(os.environ, patch, clear=False):
        prior = {key: os.environ.pop(key, None) for key in removed}
        try:
            yield
        finally:
            for key, value in prior.items():
                if value is not None:
                    os.environ[key] = value


class PlanFixture:
    def __init__(self, base: Path):
        self.base = base
        self.root = base / "consumer"
        self.root.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "P5 Test")
        git(self.root, "config", "user.email", "p5@example.invalid")
        target = self.root / ".agents" / "skill.txt"
        target.parent.mkdir()
        target.write_text("sealed\n", encoding="utf-8")
        git(self.root, "add", ".agents/skill.txt")
        git(self.root, "commit", "-qm", "fixture")
        self.record = {
            "path": str(self.root),
            "provider": "codex",
            "channel": "marketplace",
        }
        self.project_id = p5.stable_project_id(self.root, [self.record])
        self.registry = base / "projects.json"
        write_json(self.registry, {"version": 1, "projects": [self.record]})

        sealed = p5.observe_node(target, self.root)
        assert sealed is not None
        sealed["artifact_id"] = "artifact-fixture"
        sealed["tracked"] = True
        self.evidence = base / "evidence"
        self.evidence.mkdir()
        write_json(self.evidence / "provider-fleet-inventory.json", {
            "schema_version": 2,
            "registry": {"project_count": 1, "record_count": 1, "version": 1},
            "provider_rows": [
                {"artifact_id": f"{self.project_id}:claude-code", "project_id": self.project_id,
                 "provider": "claude-code", "selected": False, "status": "not-selected",
                 "carrier_paths": [], "diagnostics": []},
                {"artifact_id": f"{self.project_id}:codex", "project_id": self.project_id,
                 "provider": "codex", "selected": True, "status": "green",
                 "carrier_paths": [".agents/skill.txt"], "diagnostics": []},
            ],
        })
        write_json(self.evidence / "provider-source-snapshot.json", {
            "schema_version": 2,
            "projects": [{
                "project_id": self.project_id,
                "repository": {"state": "available", "head": git(self.root, "rev-parse", "HEAD"),
                               "dirty_tracked": [], "untracked": []},
                "provider_paths": [sealed],
            }],
        })
        self.p0_manifest = self.evidence / "manifest.json"
        write_json(self.p0_manifest, {
            "bundle_id": "fixture",
            "files": ["provider-fleet-inventory.json", "provider-source-snapshot.json"],
            "privacy": {"minimized": True},
        })
        self.classification = base / "classification.json"
        write_json(self.classification, {
            "schema_version": 1,
            "source": {}, "policy": {}, "known_cases": [],
            "summary": {"ambiguous": 1},
            "classifications": [{
                "artifact_id": f"{self.project_id}:.agents/skill.txt",
                "project_id": self.project_id,
                "path": ".agents/skill.txt",
                "providers": ["codex"],
                "node": "file", "managed": True, "tracked": True,
                "target_state": None, "classification": "ambiguous",
                "owner": "unknown", "action": "no-op",
                "rollback": "not-applicable: no write is proposed",
                "destination": "no-op",
                "evidence": ["sha256:" + "a" * 64, f"snapshot-path:{self.project_id}:.agents/skill.txt"],
            }],
        })
        self.recovery_contract = base / "recovery.md"
        self.control_contract = base / "control.md"
        contract = "**Version:** v1.0.0\n\n**Status:** frozen\n\n**Approval:** D1\n"
        self.recovery_contract.write_text(contract, encoding="utf-8")
        self.control_contract.write_text(contract, encoding="utf-8")
        self.acceptance = base / "acceptance.json"
        write_json(self.acceptance, {"schema_version": "p4-compact-field-acceptance/v1"})
        self.manifest = base / "manifest.json"
        self.journal = base / "journal.jsonl"

    def kwargs(self):
        return {
            "p0_manifest": self.p0_manifest,
            "classification": self.classification,
            "recovery_contract": self.recovery_contract,
            "control_plane_contract": self.control_contract,
            "repository_acceptance": self.acceptance,
            "registry": self.registry,
        }

    def build(self):
        return p5.build_manifest(**self.kwargs())

    def run_plan(self, command="plan"):
        return p5.main([
            command,
            "--p0-manifest", str(self.p0_manifest),
            "--classification", str(self.classification),
            "--recovery-contract", str(self.recovery_contract),
            "--control-plane-contract", str(self.control_contract),
            "--repository-acceptance", str(self.acceptance),
            "--manifest", str(self.manifest),
            "--journal", str(self.journal),
            "--registry", str(self.registry),
        ])


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = PlanFixture(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def test_plan_is_exact_deterministic_and_consumer_no_write(self):
        before = {path.relative_to(self.fixture.root): path.read_bytes()
                  for path in self.fixture.root.rglob("*") if path.is_file()}
        self.assertEqual(self.fixture.run_plan(), 0)
        first_manifest = self.fixture.manifest.read_bytes()
        first_journal = self.fixture.journal.read_bytes()
        self.assertEqual(self.fixture.run_plan(), 0)
        self.assertEqual(self.fixture.manifest.read_bytes(), first_manifest)
        self.assertEqual(self.fixture.journal.read_bytes(), first_journal)
        self.assertEqual(self.fixture.run_plan("check"), 0)
        after = {path.relative_to(self.fixture.root): path.read_bytes()
                 for path in self.fixture.root.rglob("*") if path.is_file()}
        self.assertEqual(after, before)
        manifest = json.loads(first_manifest)
        self.assertEqual(manifest["summary"]["rows"], 1)
        self.assertEqual(manifest["summary"]["actions"], {"no-op-unresolved": 1})
        self.assertEqual(manifest["summary"]["consumer_writes"], 0)
        self.assertEqual(manifest["summary"]["preimage_rebind"], {"exact": 1})

    def test_missing_extra_and_duplicate_rows_fail_closed(self):
        original = json.loads(self.fixture.classification.read_text())
        cases = []
        missing = json.loads(json.dumps(original)); missing["classifications"] = []
        cases.append(missing)
        extra = json.loads(json.dumps(original)); extra["classifications"].append({**extra["classifications"][0], "artifact_id": "extra"})
        cases.append(extra)
        duplicate = json.loads(json.dumps(original)); duplicate["classifications"].append(duplicate["classifications"][0])
        cases.append(duplicate)
        for value in cases:
            with self.subTest(rows=len(value["classifications"])):
                write_json(self.fixture.classification, value)
                with self.assertRaises(p5.Refusal):
                    self.fixture.build()
        write_json(self.fixture.classification, original)

    def test_locator_and_repository_identity_drift_fail_or_stay_explicit(self):
        data = json.loads(self.fixture.registry.read_text())
        data["projects"][0]["channel"] = "vendor"
        write_json(self.fixture.registry, data)
        with self.assertRaisesRegex(p5.Refusal, "P5_PROJECT_SET_MISMATCH"):
            self.fixture.build()
        data["projects"][0]["channel"] = "marketplace"
        write_json(self.fixture.registry, data)
        git(self.fixture.root, "init", "-q")
        manifest = self.fixture.build()
        self.assertIn(manifest["rows"][0]["preimage_rebind"], {"exact", "repository-mismatch"})

    def test_preimage_drift_cannot_authorize_mutation(self):
        classification = json.loads(self.fixture.classification.read_text())
        row = classification["classifications"][0]
        row.update({"classification": "broken-link", "owner": "skm", "action": "relink"})
        write_json(self.fixture.classification, classification)
        (self.fixture.root / ".agents" / "skill.txt").write_text("drifted\n", encoding="utf-8")
        with self.assertRaisesRegex(p5.Refusal, "P5_MUTATION_PREIMAGE_DRIFT"):
            self.fixture.build()

    def test_class_action_and_cross_provider_contradictions_fail(self):
        classification = json.loads(self.fixture.classification.read_text())
        classification["classifications"][0]["action"] = "relink"
        write_json(self.fixture.classification, classification)
        with self.assertRaisesRegex(p5.Refusal, "P5_CLASS_ACTION_CONTRADICTION"):
            self.fixture.build()
        classification["classifications"][0]["action"] = "no-op"
        classification["classifications"][0]["providers"] = ["claude-code"]
        write_json(self.fixture.classification, classification)
        with self.assertRaisesRegex(p5.Refusal, "P5_CROSS_PROVIDER_TARGET"):
            self.fixture.build()

    def test_root_secret_and_destructive_nonowner_are_rejected(self):
        with self.assertRaises(p5.Refusal):
            p5.normalized_target("/home/example/secret.txt")
        self.assertEqual(
            p5.normalized_target(
                ".agents/plugins/bundles/architect/figma-mcp-core/snippets/tokens.json"
            ),
            ".agents/plugins/bundles/architect/figma-mcp-core/snippets/tokens.json",
        )
        manifest = self.fixture.build()
        row = manifest["rows"][0]
        row.update({"action": "quarantine-remove", "owner": "unknown", "rollback": ""})
        payload = dict(manifest); payload.pop("manifest_sha256")
        manifest["manifest_sha256"] = p5.digest_value(payload)
        with self.assertRaisesRegex(p5.Refusal, "P5_DESTRUCTIVE_OWNERSHIP"):
            p5.validate_manifest(manifest)

    def test_two_pass_convergence_and_exact_aggregate_results(self):
        manifest = self.fixture.build()
        write_json(self.fixture.manifest, manifest)
        self.fixture.journal.write_bytes(b"")
        approval = self.fixture.base / "approval.md"
        approval.write_text(
            "# Approval\n\nStatus: frozen\n"
            f"Manifest SHA-256: {manifest['manifest_sha256']}\n"
            "Owner decision: D99\n" + "".join(
                f"{item}: {value['action_set_id']}\n"
                for item, value in manifest["action_sets"].items()
            ),
            encoding="utf-8",
        )
        results = []
        for item in p5.ACTION_SETS:
            path = self.fixture.base / f"{item}-results.json"
            args = argparse.Namespace(
                manifest=str(self.fixture.manifest), approval=str(approval),
                recovery_contract=str(self.fixture.recovery_contract),
                action_set=item, journal=str(self.fixture.journal),
                results=str(path), adapter_state=None,
            )
            self.assertEqual(p5.execute(args, mode="apply"), 0)
            results.append(str(path))
        convergence = self.fixture.base / "fleet-convergence.json"
        convergence_command = [
            "convergence", "--manifest", str(self.fixture.manifest),
            "--approval", str(approval), "--recovery-contract",
            str(self.fixture.recovery_contract), "--p0-manifest",
            str(self.fixture.p0_manifest), "--journal", str(self.fixture.journal),
            "--passes", "2", "--output", str(convergence),
        ]
        self.assertEqual(p5.main(convergence_command), 0)
        value = json.loads(convergence.read_text())
        self.assertTrue(value["stable"])
        self.assertTrue(value["complete_p0_coverage"])
        self.assertEqual(value["migration_readiness"], "held-unresolved")
        verify = argparse.Namespace(
            manifest=str(self.fixture.manifest), approval=str(approval),
            recovery_contract=str(self.fixture.recovery_contract),
            journal=str(self.fixture.journal), action_set=None,
            all_action_sets=[], results=results,
            convergence=str(convergence),
        )
        self.assertEqual(p5.verify_results(verify), 0)
        exact = [
            "verify-results", "--manifest", str(self.fixture.manifest),
            "--approval", str(approval), "--recovery-contract",
            str(self.fixture.recovery_contract), "--all-action-sets",
            "--journal", str(self.fixture.journal), "--results",
            str(self.fixture.base / "P5.4-results.json"),
            "--convergence", str(convergence),
        ]
        self.assertEqual(p5.main(exact), 0)
        value["approval_decision"] = "D98"
        value["convergence_sha256"] = p5.digest_value({
            key: nested for key, nested in value.items()
            if key != "convergence_sha256"
        })
        write_json(convergence, value)
        with self.assertRaisesRegex(p5.Refusal, "P5_CONVERGENCE_MISMATCH"):
            p5.verify_results(verify)
        self.assertEqual(p5.main(convergence_command), 0)
        value = json.loads(convergence.read_text())
        value["observations"][1]["observation"]["unresolved_rows"] = 0
        write_json(convergence, value)
        with self.assertRaisesRegex(p5.Refusal, "P5_CONVERGENCE_MISMATCH"):
            p5.verify_results(verify)


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "journal.jsonl"
        self.path.write_bytes(b"")
        self.base = {
            "transaction_id": "transaction-test",
            "manifest_sha256": "sha256:" + "a" * 64,
            "action_set": "P5.3",
            "action_set_id": "action-set-test",
            "project_id": "project-test",
            "action_ids": ["action-test"],
            "preimage_sha256": "sha256:" + "b" * 64,
            "postimage_sha256": "sha256:" + "c" * 64,
            "backup_identities": {"action-test": "backup-test"},
            "provider_readback": None,
        }

    def tearDown(self):
        self.temporary.cleanup()

    def _two_events(self):
        p5.append_event(self.path, {**self.base, "event": "before"})
        p5.append_event(self.path, {**self.base, "event": "applied"})
        return self.path.read_bytes().splitlines()

    def test_torn_truncated_reordered_duplicate_and_bad_hash_are_rejected(self):
        self.path.write_bytes(b'{"schema_version":')
        with self.assertRaises(p5.Refusal): p5.validate_journal(self.path)
        self.path.write_bytes(b"")
        lines = self._two_events()
        for value in (
            b"\n".join(reversed(lines)) + b"\n",
            b"\n".join([lines[0], lines[0]]) + b"\n",
        ):
            self.path.write_bytes(value)
            with self.assertRaises(p5.Refusal): p5.validate_journal(self.path)
        event = json.loads(lines[1]); event["prev_event_sha256"] = "f" * 64
        self.path.write_bytes(lines[0] + b"\n" + p5.canonical_bytes(event) + b"\n")
        with self.assertRaisesRegex(p5.Refusal, "P5_JOURNAL_PREVIOUS_HASH"):
            p5.validate_journal(self.path)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.recovery = self.base / "recovery.md"
        self.recovery.write_text("**Version:** v1.0.0\n\n**Status:** frozen\n\n**Approval:** D1\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def _case(self):
        case = Path(tempfile.mkdtemp(dir=self.base))
        row = {
            "source_artifact_id": "source-a",
            "sealed_artifact_id": "sealed-a",
            "project_id": "project-a",
            "provider_ids": ["claude-code", "codex"],
            "relative_target": "shared/provider-target",
            "classification": "canonical-equivalent",
            "owner": "skm",
            "evidence": ["sha256:" + "a" * 64],
            "action": "relink",
            "action_reason": "test",
            "sealed_preimage_sha256": "sha256:" + "1" * 64,
            "planned_postimage_sha256": "sha256:" + "2" * 64,
            "preimage_rebind": "exact",
            "backup": "backup-a",
            "rollback": "rollback-a",
            "expected_readback": "provider-qualified-clean",
            "destination_item": "P5.3",
            "action_id": "action-a",
        }
        action_sets = {
            item: {
                "action_ids": ["action-a"] if item == "P5.3" else [],
                "action_set_id": "action-set-" + item.lower().replace(".", "-"),
            }
            for item in p5.ACTION_SETS
        }
        manifest = {
            "schema_version": p5.MANIFEST_VERSION,
            "plan_id": p5.PLAN_ID,
            "source_identities": {"fixture": {"sha256": "sha256:" + "a" * 64}},
            "project_ids": ["project-a"],
            "protected_project_ids": [],
            "repository_mismatch_project_ids": [],
            "action_sets": action_sets,
            "rows": [row],
            "summary": {"projects": 1, "rows": 1, "actions": {"relink": 1},
                        "preimage_rebind": {"exact": 1}, "consumer_writes": 0},
        }
        manifest["manifest_sha256"] = p5.digest_value(manifest)
        manifest_path = case / "manifest.json"; write_json(manifest_path, manifest)
        approval = case / "approval.md"
        approval.write_text(
            "# Approval\n\nStatus: frozen\n"
            f"Manifest SHA-256: {manifest['manifest_sha256']}\n"
            "Owner decision: D99\n" + "".join(
                f"{item}: {value['action_set_id']}\n" for item, value in action_sets.items()
            ), encoding="utf-8",
        )
        journal = case / "journal.jsonl"; journal.write_bytes(b"")
        state = case / "state.json"
        preimage = p5._project_image([row], "sealed_preimage_sha256")
        write_json(state, {"project-a": preimage})
        results = case / "results.json"
        args = argparse.Namespace(
            manifest=str(manifest_path), approval=str(approval),
            recovery_contract=str(self.recovery), action_set="P5.3",
            journal=str(journal), results=str(results), adapter_state=str(state),
        )
        return args, manifest, row, journal, state

    def test_apply_requires_exact_frozen_owner_approval(self):
        args, _, _, _, _ = self._case()
        Path(args.approval).write_text("Status: pending\n", encoding="utf-8")
        with environment(P5_ALLOW_FAKE_ADAPTER="1"):
            with self.assertRaises(p5.Refusal):
                p5.execute(args, mode="apply")

    def test_every_success_boundary_resumes_without_replay(self):
        boundaries = [
            "append-before", "public-apply", "append-applied", "public-readback",
            "append-readback-passed", "append-accepted",
        ]
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                args, _, _, journal, _ = self._case()
                with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER=boundary,
                                 P5_FAKE_READBACK_FAIL=None):
                    with self.assertRaises(p5.InjectedCrash):
                        p5.execute(args, mode="apply")
                with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER=None,
                                 P5_FAKE_READBACK_FAIL=None):
                    self.assertEqual(p5.execute(args, mode="resume"), 0)
                latest = p5._latest_by_transaction(p5.validate_journal(journal))
                expected = "rolled-back" if boundary == "append-before" else "accepted"
                self.assertEqual({event["event"] for event in latest.values()}, {expected})

    def test_every_failed_readback_boundary_rolls_back_exactly(self):
        boundaries = [
            "append-readback-failed", "append-rollback-started", "public-rollback",
            "append-rolled-back",
        ]
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                args, _, row, journal, state = self._case()
                with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER=boundary,
                                 P5_FAKE_READBACK_FAIL="1"):
                    with self.assertRaises(p5.InjectedCrash):
                        p5.execute(args, mode="apply")
                with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER=None,
                                 P5_FAKE_READBACK_FAIL="1"):
                    self.assertEqual(p5.execute(args, mode="resume"), 0)
                latest = p5._latest_by_transaction(p5.validate_journal(journal))
                self.assertEqual({event["event"] for event in latest.values()}, {"rolled-back"})
                self.assertEqual(json.loads(state.read_text())["project-a"],
                                 p5._project_image([row], "sealed_preimage_sha256"))

    def test_exact_preimage_postimage_and_third_state_reconcile(self):
        args, _, row, journal, state = self._case()
        with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER="append-before"):
            with self.assertRaises(p5.InjectedCrash): p5.execute(args, mode="apply")
        with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER=None):
            self.assertEqual(p5.execute(args, mode="resume"), 0)
        self.assertEqual(list(p5._latest_by_transaction(p5.validate_journal(journal)).values())[0]["event"], "rolled-back")

        args, _, row, journal, state = self._case()
        with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER="public-apply"):
            with self.assertRaises(p5.InjectedCrash): p5.execute(args, mode="apply")
        with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER=None):
            self.assertEqual(p5.execute(args, mode="resume"), 0)
        self.assertEqual(list(p5._latest_by_transaction(p5.validate_journal(journal)).values())[0]["event"], "accepted")

        args, _, _, _, state = self._case()
        with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER="append-before"):
            with self.assertRaises(p5.InjectedCrash): p5.execute(args, mode="apply")
        write_json(state, {"project-a": "sha256:" + "f" * 64})
        with environment(P5_ALLOW_FAKE_ADAPTER="1", P5_CRASH_AFTER=None):
            with self.assertRaisesRegex(p5.Refusal, "P5_RECONCILE_THIRD_STATE"):
                p5.execute(args, mode="resume")


if __name__ == "__main__":
    unittest.main(verbosity=2)
