"""Conformance tests for P2.2 fail-closed artifact lock lifecycle."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core.provider_lock as provider_lock
from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, ArtifactActionKind, CapabilityId, CapabilityRequirement,
                  DriftObservation, ProviderId, SupportLevel, apply_plan,
                  parse_lock, plan_artifact_lock, plan_artifact_render, serialize_lock)


HASH = "sha256:" + "a" * 64


def result(*, body=b"managed\n", artifact_id="task.plan-exec.codex-skill",
           target=".agents/skills/task-plan-exec/SKILL.md", adapter_version="1.0.0",
           boundary=("whole-file", ())):
    adapter = ArtifactAdapterIdentity(
        "task.codex-skill", adapter_version, ProviderId.CODEX, "1.0.0",
        (CapabilityRequirement(CapabilityId("skills.repository"), (SupportLevel.NATIVE,)),),
    )
    return plan_artifact_render(ArtifactRenderRequest(
        artifact_id, (ArtifactSource("task.command.plan-exec", "packages/task/commands/plan-exec.md", HASH),),
        ArtifactTarget(target, boundary), adapter, (), {"title": "Plan exec"}, lambda _request: body,
    ))


class ProviderLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.expected = result()

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, expected=None, lock_bytes=None, **kwargs):
        return plan_artifact_lock(self.root, (expected or self.expected,), lock_bytes=lock_bytes, **kwargs)

    def test_absent_create_apply_and_second_plan_is_noop(self):
        planned = self.plan()
        self.assertEqual(planned.actions[0].observation, DriftObservation.MISSING)
        self.assertEqual(planned.actions[0].action, ArtifactActionKind.CREATE)
        applied = apply_plan(self.root, planned)
        self.assertEqual(applied.actions[0].action, ArtifactActionKind.NOOP)
        lock = parse_lock((self.root / ".swissknifeman/provider-artifacts.lock.json").read_bytes())
        self.assertEqual(lock.records, (self.expected.provenance,))

    def test_each_frozen_drift_state_has_one_action(self):
        initial = self.plan()
        apply_plan(self.root, initial)
        lock = serialize_lock(initial.next_lock)
        target = self.root / self.expected.target.path
        changed = result(body=b"new managed\n", adapter_version="1.0.1")
        cases = (
            ("clean", self.expected, lock, None, DriftObservation.CLEAN, ArtifactActionKind.NOOP),
            ("stale-source", changed, lock, None, DriftObservation.STALE_SOURCE, ArtifactActionKind.UPDATE),
            ("managed-drift", self.expected, lock, b"manual edit\n", DriftObservation.MANAGED_DRIFT, ArtifactActionKind.REFUSE),
        )
        for name, expected, lock_bytes, disk, observation, action in cases:
            with self.subTest(name=name):
                target.write_bytes(self.expected.managed_bytes if disk is None else disk)
                actual = self.plan(expected, lock_bytes)
                self.assertEqual((actual.actions[0].observation, actual.actions[0].action), (observation, action))
        target.write_bytes(b"manual edit\n")
        repair = self.plan(self.expected, lock, repair_artifact_ids=(self.expected.provenance.artifact_id,))
        self.assertEqual(repair.actions[0].action, ArtifactActionKind.REPAIR)
        apply_plan(self.root, repair)
        self.assertEqual(target.read_bytes(), self.expected.managed_bytes)
        self.assertEqual(target.with_name(target.name + ".provider-artifact.bak").read_bytes(), b"manual edit\n")

    def test_missing_target_with_matching_lock_is_create(self):
        first = self.plan()
        apply_plan(self.root, first)
        (self.root / self.expected.target.path).unlink()
        plan = self.plan(lock_bytes=serialize_lock(first.next_lock))
        self.assertEqual((plan.actions[0].observation, plan.actions[0].action),
                         (DriftObservation.MISSING, ArtifactActionKind.CREATE))

    def test_unmanaged_and_duplicate_targets_fail_closed(self):
        target = self.root / self.expected.target.path
        target.parent.mkdir(parents=True)
        target.write_bytes(self.expected.managed_bytes)
        unmanaged = self.plan()
        self.assertEqual(unmanaged.actions[0].observation, DriftObservation.OWNERSHIP_CONFLICT)
        other = result(artifact_id="task.other.codex-skill", target=self.expected.target.path)
        with self.assertRaises(ValueError):
            plan_artifact_lock(self.root, (self.expected, other), lock_bytes=None)

    def test_corrupt_and_newer_locks_refuse_without_writes(self):
        for raw in (b"{", b'{"records":[],"schema_version":2}\n'):
            with self.subTest(raw=raw):
                plan = self.plan(lock_bytes=raw)
                self.assertEqual(plan.actions[0].observation, DriftObservation.PROVENANCE_INVALID)
                self.assertEqual(plan.actions[0].action, ArtifactActionKind.REFUSE)
                with self.assertRaises(ValueError):
                    apply_plan(self.root, plan)

    def test_unsafe_paths_and_symlink_escape_refuse(self):
        outside = self.root.parent / "outside-provider-lock"
        outside.mkdir(exist_ok=True)
        link_parent = self.root / ".agents"
        os.symlink(outside, link_parent)
        plan = self.plan()
        self.assertEqual(plan.actions[0].observation, DriftObservation.BOUNDARY_INVALID)
        for unsafe in ("../outside", "/tmp/outside", "a/../b"):
            with self.subTest(path=unsafe):
                with self.assertRaises(ValueError):
                    result(target=unsafe)

    def test_managed_blocks_fail_closed_without_caller_extractor(self):
        block_result = result(target="CLAUDE.md", boundary=("managed-blocks", ("codex",)))
        plan = self.plan(block_result)
        self.assertEqual((plan.actions[0].observation, plan.actions[0].action),
                         (DriftObservation.BOUNDARY_INVALID, ArtifactActionKind.REFUSE))

    def test_apply_rechecks_precondition_and_leaves_lock_unwritten(self):
        plan = self.plan()
        target = self.root / self.expected.target.path
        target.parent.mkdir(parents=True)
        target.write_bytes(b"raced\n")
        with self.assertRaisesRegex(ValueError, "target changed after planning"):
            apply_plan(self.root, plan)
        self.assertFalse((self.root / ".swissknifeman/provider-artifacts.lock.json").exists())

    def test_interrupted_atomic_write_removes_only_its_temp_file(self):
        target = self.root / "generated.txt"
        temporary = self.root / "generated.tmp"
        descriptor = os.open(temporary, os.O_CREAT | os.O_WRONLY, 0o600)
        with patch.object(provider_lock.tempfile, "mkstemp", return_value=(descriptor, str(temporary))), \
             patch.object(provider_lock.os, "replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                provider_lock._atomic_write_bytes(target, b"new\n")
        self.assertFalse(temporary.exists())
        self.assertFalse(target.exists())

    def test_canonical_lock_round_trip_and_rejects_noncanonical_order(self):
        plan = self.plan()
        raw = serialize_lock(plan.next_lock)
        self.assertEqual(serialize_lock(parse_lock(raw)), raw)
        self.assertRaises(ValueError, parse_lock, raw.replace(b'"records"', b'"z_records"'))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
