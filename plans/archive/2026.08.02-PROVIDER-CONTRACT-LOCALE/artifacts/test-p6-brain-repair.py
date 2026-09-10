#!/usr/bin/env python3
"""Deterministic acceptance suite for the P6.1 Brain transaction."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("p6_brain_repair", HERE / "p6-brain-repair.py")
p6 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(p6)
FIXTURES = HERE / "P6" / "fixtures"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


@contextmanager
def environment(**values: str | None):
    old = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class Fixture:
    def __init__(self, base: Path):
        self.base = base
        self.project = base / "consumer"
        self.project.mkdir()
        git(self.project, "init", "-q")
        git(self.project, "config", "user.email", "fixture@example.invalid")
        git(self.project, "config", "user.name", "Fixture")
        (self.project / "README.md").write_text("fixture\n", encoding="utf-8")
        git(self.project, "add", "README.md")
        git(self.project, "commit", "-qm", "fixture")
        self.head = git(self.project, "rev-parse", "HEAD")
        self.sealed_id = "project-fixture"

        self.p0_dir = base / "P0.1"
        self.p0_dir.mkdir()
        self.p0_manifest = self.p0_dir / "manifest.json"
        write_json(self.p0_manifest, {
            "bundle_id": "P0.1-provider-fleet-baseline",
            "files": ["provider-source-snapshot.json", "provider-fleet-inventory.json"],
        })
        write_json(self.p0_dir / "provider-source-snapshot.json", {
            "schema_version": 2,
            "projects": [{
                "project_id": self.sealed_id,
                "repository": {"head": self.head},
                "provider_paths": [],
            }],
        })
        write_json(self.p0_dir / "provider-fleet-inventory.json", {"schema_version": 2})

        self.branch = base / "branch-verdict.json"
        write_json(self.branch, {
            "schema_version": "p0-branch-verdict/v3",
            "branch": "no-op",
            "action_set": [],
        })
        self.p5_manifest = base / "fleet-action-manifest.json"
        manifest = {
            "schema_version": "p5-fleet-action-manifest/v1",
            "rows": [{
                "project_id": self.sealed_id,
                "action": "no-op-unresolved",
                "action_id": "action-fixture",
            }],
        }
        manifest["manifest_sha256"] = p6.digest_value(manifest)
        write_json(self.p5_manifest, manifest)
        self.convergence = base / "fleet-convergence.json"
        write_json(self.convergence, {
            "schema_version": "p5-fleet-convergence/v1",
            "stable": True,
            "manifest_sha256": manifest["manifest_sha256"],
        })
        self.p5_journal = base / "p5-journal.jsonl"
        self.p5_journal.write_bytes(b"")

        self.recovery = base / "recovery.md"
        self.control = base / "control.md"
        contract = "**Version:** v1.0.0\n\n**Status:** frozen\n\n**Approval:** D1\n"
        self.recovery.write_text(contract, encoding="utf-8")
        self.control.write_text(contract, encoding="utf-8")

        fixture = json.loads((FIXTURES / "public-observations.json").read_text(encoding="utf-8"))
        fixture["fixture_root"] = str(self.project)
        self.observations = base / "observations.json"
        write_json(self.observations, fixture)
        self.plan = base / "plan.json"
        self.journal = base / "journal.jsonl"
        self.approval = base / "approval.md"
        self.results = base / "results.json"
        self.state = base / "state.json"

    @contextmanager
    def env(self, **extra: str | None):
        with environment(
            P6_BRAIN_FIXTURE=str(self.observations),
            P6_P0_BRANCH=str(self.branch),
            P6_P5_MANIFEST=str(self.p5_manifest),
            **extra,
        ):
            yield

    def source_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            project_id="brain",
            p0_manifest=str(self.p0_manifest),
            p5_convergence=str(self.convergence),
            p5_journal=str(self.p5_journal),
            recovery_contract=str(self.recovery),
            control_plane_contract=str(self.control),
        )

    def run_plan(self) -> dict:
        args = self.source_args()
        with self.env():
            value = p6.build_plan(args)
        write_json(self.plan, value)
        self.journal.write_bytes(b"")
        return value

    def approve(self, plan: dict, *, approver: str = "repository owner", decision: str = "D99") -> None:
        self.approval.write_text(
            "# Brain repair approval\n\n"
            "Status: approved\n"
            f"Owner decision: {decision}\n"
            f"Plan SHA-256: {plan['plan_sha256']}\n"
            f"Action set ID: {plan['action_set_id']}\n"
            f"Preimage SHA-256: {plan['expected_preimage_sha256']}\n"
            f"Rollback ID: {plan['rollback_id']}\n"
            f"Approver: {approver}\n",
            encoding="utf-8",
        )

    def transaction_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            plan=str(self.plan), approval=str(self.approval), journal=str(self.journal),
            results=str(self.results),
        )

    def arm_state(self, plan: dict, identity: str | None = None) -> None:
        write_json(self.state, {"image_sha256": identity or plan["expected_preimage_sha256"]})


def rehash(plan: dict) -> dict:
    plan = json.loads(json.dumps(plan))
    plan["action_set_id"] = "action-set-" + p6.digest_value(plan["actions"]).removeprefix("sha256:")[:24]
    plan.pop("plan_sha256", None)
    plan["plan_sha256"] = p6.digest_value(plan)
    return plan


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def test_plan_is_deterministic_redacted_and_no_write_to_consumer(self):
        before = git(self.fixture.project, "status", "--short")
        args = self.fixture.source_args()
        with self.fixture.env():
            first = p6.build_plan(args)
            second = p6.build_plan(args)
        self.assertEqual(first, second)
        self.assertEqual(git(self.fixture.project, "status", "--short"), before)
        self.assertEqual(first["actions"], [])
        self.assertEqual(first["sealed_project_id"], self.fixture.sealed_id)
        self.assertEqual({row["provider_id"] for row in first["observations"]["provider_trust"]}, set(p6.PROVIDERS))
        self.assertFalse(p6.ABSOLUTE.search(json.dumps(first)))

    def test_missing_extra_and_duplicate_actions_are_rejected(self):
        plan = self.fixture.run_plan()
        action = {
            "action_id": "action-a", "kind": "fixture", "provider_id": "claude-code",
            "target_owner": "claude-code", "backup_id": "backup-a", "rollback_id": "rollback-a",
        }
        for actions in ([action], [action, action]):
            candidate = json.loads(json.dumps(plan))
            candidate["actions"] = actions
            candidate = rehash(candidate)
            if len(actions) == 2:
                with self.assertRaisesRegex(p6.Refusal, "P6_ACTION_SET_INVALID"):
                    p6.validate_plan(candidate)
            else:
                p6.validate_plan(candidate)
        candidate = json.loads(json.dumps(plan))
        candidate["action_set_id"] = "action-set-extra"
        candidate.pop("plan_sha256")
        candidate["plan_sha256"] = p6.digest_value(candidate)
        with self.assertRaisesRegex(p6.Refusal, "P6_ACTION_SET_DIGEST"):
            p6.validate_plan(candidate)

    def test_identity_drift_fails_closed(self):
        plan = self.fixture.run_plan()
        convergence = json.loads(self.fixture.convergence.read_text())
        convergence["manifest_sha256"] = "sha256:" + "f" * 64
        write_json(self.fixture.convergence, convergence)
        with self.fixture.env(), self.assertRaisesRegex(p6.Refusal, "P6_P5_MANIFEST_DRIFT"):
            p6.build_plan(self.fixture.source_args())
        p6.validate_plan(plan)

    def test_full_access_cross_provider_p5_and_absent_rollback_are_rejected(self):
        plan = self.fixture.run_plan()
        cases = [
            ({"action_id": "a", "kind": "full-access", "provider_id": "codex", "target_owner": "codex", "backup_id": "b", "rollback_id": "r"}, "P6_IMPLICIT_FULL_ACCESS"),
            ({"action_id": "a", "kind": "fixture", "provider_id": "codex", "target_owner": "claude-code", "backup_id": "b", "rollback_id": "r"}, "P6_CROSS_PROVIDER_ACTION"),
            ({"action_id": "a", "kind": "p5-unresolved-repair", "provider_id": "codex", "target_owner": "codex", "backup_id": "b", "rollback_id": "r"}, "P6_P5_UNRESOLVED_MUTATION"),
            ({"action_id": "a", "kind": "fixture", "provider_id": "codex", "target_owner": "codex", "backup_id": "", "rollback_id": ""}, "P6_ACTION_ROLLBACK_MISSING"),
        ]
        for action, code in cases:
            with self.subTest(code=code):
                candidate = json.loads(json.dumps(plan)); candidate["actions"] = [action]
                candidate = rehash(candidate)
                with self.assertRaisesRegex(p6.Refusal, code):
                    p6.validate_plan(candidate)

    def test_root_and_secret_values_are_rejected(self):
        plan = self.fixture.run_plan()
        for value, code in (("/home/example/private", "P6_PRIVACY_ROOT"), ("sk-abcdefghijklmnop", "P6_PRIVACY_SECRET")):
            candidate = json.loads(json.dumps(plan))
            candidate["unresolved"][0]["unsafe"] = value
            candidate = rehash(candidate)
            with self.assertRaisesRegex(p6.Refusal, code):
                p6.validate_plan(candidate)


class ApprovalAndTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temporary.name))
        self.plan = self.fixture.run_plan()
        self.fixture.approve(self.plan)
        self.fixture.arm_state(self.plan)

    def tearDown(self):
        self.temporary.cleanup()

    def test_apply_requires_exact_nonself_owner_approval(self):
        self.fixture.approve(self.plan, approver="executor")
        with self.assertRaisesRegex(p6.Refusal, "P6_APPROVAL_MISMATCH"):
            p6.parse_approval(self.fixture.approval, self.plan)
        self.fixture.approve(self.plan, decision="pending")
        with self.assertRaisesRegex(p6.Refusal, "P6_APPROVAL_DECISION"):
            p6.parse_approval(self.fixture.approval, self.plan)

    def test_empty_exact_action_set_accepts_but_remains_non_green(self):
        with self.fixture.env(P6_FIXTURE_STATE=str(self.fixture.state)):
            self.assertEqual(p6.execute(self.fixture.transaction_args(), "apply"), 0)
            self.assertEqual(p6.verify_results(self.fixture.transaction_args()), 0)
        results = json.loads(self.fixture.results.read_text())
        self.assertEqual(results["terminal_state"], "accepted")
        self.assertEqual(results["aggregate"], "non-green")
        self.assertEqual([row["provider_id"] for row in results["provider_readback"]], list(p6.PROVIDERS))

    def test_every_declared_crash_boundary_resumes_terminally(self):
        scenarios = json.loads((FIXTURES / "transaction-scenarios.json").read_text())
        for boundary in scenarios["crash_boundaries"]:
            with self.subTest(boundary=boundary):
                case = Fixture(Path(tempfile.mkdtemp(dir=self.temporary.name)))
                plan = case.run_plan(); case.approve(plan); case.arm_state(plan)
                with case.env(P6_FIXTURE_STATE=str(case.state), P6_CRASH_AFTER=boundary):
                    with self.assertRaises(p6.InjectedCrash):
                        p6.execute(case.transaction_args(), "apply")
                with case.env(P6_FIXTURE_STATE=str(case.state), P6_CRASH_AFTER=None):
                    self.assertEqual(p6.execute(case.transaction_args(), "resume"), 0)
                    self.assertEqual(p6.verify_results(case.transaction_args()), 0)
                events = p6.validate_journal(case.journal)
                self.assertIn(events[-1]["event"], p6.TERMINAL_EVENTS)

    def test_reconcile_exact_pre_post_and_third_state(self):
        args = self.fixture.transaction_args()
        with self.fixture.env(P6_FIXTURE_STATE=str(self.fixture.state)):
            decision = p6.reconcile_state(self.plan, self.fixture.journal)
            self.assertIn(decision["status"], {"continue-readback", "rollback-exact-preimage"})
            write_json(self.fixture.state, {"image_sha256": "sha256:" + "f" * 64})
            with self.assertRaisesRegex(p6.Refusal, "P6_RECONCILE_THIRD_STATE"):
                p6.reconcile_state(self.plan, self.fixture.journal)

    def test_failed_readback_rolls_back_whole_fixture(self):
        action = {
            "action_id": "action-fixture", "kind": "fixture", "provider_id": "codex",
            "target_owner": "codex", "backup_id": "backup-fixture", "rollback_id": "rollback-fixture",
        }
        self.plan["actions"] = [action]
        self.plan["expected_postimage_sha256"] = "sha256:" + "a" * 64
        self.plan = rehash(self.plan)
        write_json(self.fixture.plan, self.plan)
        self.fixture.approve(self.plan)
        self.fixture.arm_state(self.plan)
        original_current = p6._current_image
        calls = 0

        def drift_after_apply(plan):
            nonlocal calls
            calls += 1
            if calls >= 2:
                return "sha256:" + "b" * 64, json.loads(self.fixture.observations.read_text())["observations"]
            return original_current(plan)

        with self.fixture.env(P6_FIXTURE_STATE=str(self.fixture.state)), mock.patch.object(p6, "_current_image", side_effect=drift_after_apply):
            with self.assertRaisesRegex(p6.Refusal, "P6_ROLLBACK_READBACK_FAILED"):
                p6.execute(self.fixture.transaction_args(), "apply")

    def test_append_flushes_fsyncs_reopens_and_validates(self):
        base = p6._base_event(self.plan, self.fixture.approval)
        with mock.patch.object(p6.os, "fsync", wraps=os.fsync) as fsync:
            p6.append_event(self.fixture.journal, base, "before-apply", "action-set")
        self.assertGreaterEqual(fsync.call_count, 2)
        self.assertEqual(len(p6.validate_journal(self.fixture.journal)), 1)


class JournalCorruptionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temporary.name))
        self.plan = self.fixture.run_plan(); self.fixture.approve(self.plan); self.fixture.arm_state(self.plan)
        base = p6._base_event(self.plan, self.fixture.approval)
        p6.append_event(self.fixture.journal, base, "before-apply", "action-set")
        p6.append_event(self.fixture.journal, base, "after-apply", "action-set")
        self.lines = self.fixture.journal.read_bytes().splitlines()

    def tearDown(self):
        self.temporary.cleanup()

    def test_torn_truncated_reordered_duplicate_and_bad_hash_are_rejected(self):
        values = [
            b'{"schema_version":',
            self.lines[0][:-4] + b"\n",
            b"\n".join(reversed(self.lines)) + b"\n",
            b"\n".join([self.lines[0], self.lines[0]]) + b"\n",
        ]
        bad = json.loads(self.lines[1]); bad["event_sha256"] = "f" * 64
        values.append(self.lines[0] + b"\n" + p6.canonical_bytes(bad) + b"\n")
        for value in values:
            with self.subTest(size=len(value)):
                self.fixture.journal.write_bytes(value)
                with self.assertRaises(p6.Refusal):
                    p6.validate_journal(self.fixture.journal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
