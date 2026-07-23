"""Conformance tests for P2.2 fail-closed artifact lock lifecycle."""
import json
import os
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core.provider_lock as provider_lock
from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, ArtifactActionKind, CapabilityId, CapabilityRequirement,
                  BootstrapTransferAdmission, ChainedBootstrapTransferAdmission, DriftObservation,
                  ProviderId, SupportLevel, apply_plan, parse_lock, plan_artifact_lock,
                  plan_artifact_render, plan_bootstrap_transfer,
                  plan_chained_bootstrap_transfer,
                  rollback_chained_bootstrap_transfer, serialize_lock)


HASH = "sha256:" + "a" * 64
REAL_SHA256_DIGEST = provider_lock.sha256_digest
BOOTSTRAP_PREIMAGE = b'{"hooks":{"SessionStart":["memory"]}}\n'
BOOTSTRAP_DIGEST = "sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db"
MCP_PREIMAGE = (b'{"mcpServers":{"maind":{"command":"maind"},'
                b'"perplexity-web":{"command":"perplexity-web"},'
                b'"serena":{"command":"serena"}}}\n')
MCP_DIGEST = "sha256:cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283"


def result(*, body=b"managed\n", artifact_id="task.plan-exec.codex-skill",
           target=".agents/skills/task-plan-exec/SKILL.md", adapter_version="1.0.0",
           boundary=("whole-file", ()), contract_version="1.0.0",
           semantic_parameters=None):
    adapter = ArtifactAdapterIdentity(
        "task.codex-skill", adapter_version, ProviderId.CODEX, "1.0.0",
        (CapabilityRequirement(CapabilityId("skills.repository"), (SupportLevel.NATIVE,)),),
    )
    return plan_artifact_render(ArtifactRenderRequest(
        artifact_id, (ArtifactSource("task.command.plan-exec", "packages/task/commands/plan-exec.md", HASH),),
        ArtifactTarget(target, boundary), adapter, (),
        semantic_parameters or {"title": "Plan exec"}, lambda _request: body,
        contract_version,
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

    def bootstrap_results(self):
        return (
            result(body=b'{"hooks":{"SessionStart":["memory","lifecycle"]}}\n',
                   artifact_id="harness.codex.lifecycle.hooks", target=".codex/hooks.json"),
            result(body=b"def lifecycle(event):\n    return event\n",
                   artifact_id="harness.codex.lifecycle.handler",
                   target=".codex/hooks/lifecycle.py"),
        )

    def bootstrap_admission(self, digest=BOOTSTRAP_DIGEST):
        return BootstrapTransferAdmission(
            "D104", ".codex/hooks.json", digest,
            ".codex/hooks/lifecycle.py", "harness.codex.lifecycle.hooks",
            "harness.codex.lifecycle.handler")

    def chained_results(self):
        return self.bootstrap_results() + (
            result(body=MCP_PREIMAGE, artifact_id="maind.provider-deploy.claude-code",
                   target=".mcp.json"),
        )

    def chained_admission(self, predecessor, bootstrap_digest, mcp_digest):
        return ChainedBootstrapTransferAdmission(
            self.bootstrap_admission(bootstrap_digest), predecessor, "D108", ".mcp.json", mcp_digest,
            "maind.provider-deploy.claude-code", ("whole-file", ()),
            ("maind", "perplexity-web", "serena"))

    def chained_predecessor(self, root, bootstrap_digest):
        return plan_bootstrap_transfer(
            root, self.bootstrap_results(), lock_bytes=None,
            admission=self.bootstrap_admission(bootstrap_digest))

    @contextmanager
    def chained_exact_vectors(self):
        bootstrap_digest = REAL_SHA256_DIGEST(BOOTSTRAP_PREIMAGE)
        mcp_digest = REAL_SHA256_DIGEST(MCP_PREIMAGE)
        with patch.object(provider_lock, "_BOOTSTRAP_PREIMAGE", bootstrap_digest), patch.object(
                provider_lock, "_CHAINED_MCP_PREIMAGE", mcp_digest):
            yield bootstrap_digest, mcp_digest

    @staticmethod
    def bootstrap_digest(value):
        if value == BOOTSTRAP_PREIMAGE:
            return BOOTSTRAP_DIGEST
        if value == MCP_PREIMAGE:
            return MCP_DIGEST
        return REAL_SHA256_DIGEST(value)

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

    def test_malformed_provenance_and_override_lock_records_refuse(self):
        initial = self.plan()
        apply_plan(self.root, initial)
        raw = json.loads(serialize_lock(initial.next_lock))
        malformed_records = []
        no_sources = json.loads(json.dumps(raw))
        no_sources["records"][0]["canonical_sources"] = []
        malformed_records.append(no_sources)
        malformed_override = json.loads(json.dumps(raw))
        malformed_override["records"][0]["override_layers"] = [{"id": "project", "order": 0}]
        malformed_records.append(malformed_override)
        for value in malformed_records:
            with self.subTest(value=value):
                lock = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
                plan = self.plan(lock_bytes=lock)
                self.assertEqual((plan.actions[0].observation, plan.actions[0].action),
                                 (DriftObservation.PROVENANCE_INVALID, ArtifactActionKind.REFUSE))

    def test_clean_noop_apply_never_calls_writer_or_replaces_lock(self):
        initial = self.plan()
        apply_plan(self.root, initial)
        lock = serialize_lock(initial.next_lock)
        clean = self.plan(lock_bytes=lock)
        before = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                              for path in self.root.rglob("*") if path.is_file()))
        with patch.object(provider_lock, "_atomic_write_bytes", wraps=provider_lock._atomic_write_bytes) as writer:
            self.assertIs(apply_plan(self.root, clean), clean)
        self.assertEqual(writer.call_count, 0)
        after = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                             for path in self.root.rglob("*") if path.is_file()))
        self.assertEqual(after, before)

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
        self.assertNotIn(b"semantic_metadata", raw)
        self.assertRaises(ValueError, parse_lock, raw.replace(b'"records"', b'"z_records"'))

    def test_v1_1_lock_round_trip_emits_semantic_metadata(self):
        expected = result(
            contract_version="1.1.0",
            semantic_parameters={"semantic_sections": {"common": ["task.identity"]},
                                 "artifact_kind": "instruction-projection"})
        raw = serialize_lock(self.plan(expected).next_lock)
        value = json.loads(raw)
        self.assertEqual(value["records"][0]["semantic_metadata"], {
            "artifact_kind": "instruction-projection",
            "semantic_sections": {"common": ["task.identity"]},
        })
        self.assertEqual(parse_lock(raw).records, (expected.provenance,))

    def test_malformed_metadata_and_version_combinations_refuse(self):
        old = json.loads(serialize_lock(self.plan().next_lock))
        old["records"][0]["semantic_metadata"] = {}
        new = json.loads(serialize_lock(self.plan(result(
            contract_version="1.1.0")).next_lock))
        missing = json.loads(json.dumps(new))
        missing["records"][0].pop("semantic_metadata")
        floating = json.loads(json.dumps(new))
        floating["records"][0]["semantic_metadata"] = {"weight": 1.5}
        for value in (old, missing, floating):
            with self.subTest(value=value):
                raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
                with self.assertRaises(ValueError):
                    parse_lock(raw)

    def test_semantic_metadata_change_is_not_clean(self):
        expected = result(contract_version="1.1.0")
        initial = self.plan(expected)
        apply_plan(self.root, initial)
        value = json.loads(serialize_lock(initial.next_lock))
        value["records"][0]["semantic_metadata"]["title"] = "Changed"
        changed_lock = json.dumps(
            value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        planned = self.plan(expected, changed_lock)
        self.assertEqual(
            (planned.actions[0].observation, planned.actions[0].action),
            (DriftObservation.PROVENANCE_INVALID, ArtifactActionKind.REFUSE))

    def test_d104_bootstrap_transfer_then_normal_second_plan_is_noop(self):
        hooks = self.root / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        results = self.bootstrap_results()
        admission = self.bootstrap_admission()
        original_digest = provider_lock.sha256_digest

        def digest(value):
            return BOOTSTRAP_DIGEST if value == BOOTSTRAP_PREIMAGE else original_digest(value)

        with patch.object(provider_lock, "sha256_digest", side_effect=digest):
            planned = plan_bootstrap_transfer(self.root, results, lock_bytes=None, admission=admission)
            self.assertEqual([action.action for action in planned.actions],
                             [ArtifactActionKind.UPDATE, ArtifactActionKind.CREATE])
            applied = apply_plan(self.root, planned)
        self.assertTrue((hooks.with_name("hooks.json.provider-artifact.bootstrap-transfer.bak")).exists())
        self.assertEqual(hooks.read_bytes(), results[0].managed_bytes)
        self.assertEqual((self.root / results[1].target.path).read_bytes(), results[1].managed_bytes)
        second = plan_artifact_lock(
            self.root, results,
            lock_bytes=(self.root / ".swissknifeman/provider-artifacts.lock.json").read_bytes())
        self.assertEqual([action.action for action in second.actions],
                         [ArtifactActionKind.NOOP, ArtifactActionKind.NOOP])

    def test_d104_altered_admission_refuses_without_writes(self):
        hooks = self.root / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        results = self.bootstrap_results()
        original_digest = provider_lock.sha256_digest

        def digest(value):
            return BOOTSTRAP_DIGEST if value == BOOTSTRAP_PREIMAGE else original_digest(value)

        for admission in (
                replace(self.bootstrap_admission(), decision_id="D105"),
                replace(self.bootstrap_admission(), existing_preimage_sha256=HASH),
                replace(self.bootstrap_admission(), created_target_path=".codex/hooks/other.py")):
            with self.subTest(admission=admission), patch.object(provider_lock, "sha256_digest", side_effect=digest):
                before = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                                      for path in self.root.rglob("*") if path.is_file()))
                planned = plan_bootstrap_transfer(self.root, results, lock_bytes=None, admission=admission)
                self.assertTrue(all(action.action is ArtifactActionKind.REFUSE for action in planned.actions))
                with self.assertRaises(ValueError):
                    apply_plan(self.root, planned)
                after = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                                     for path in self.root.rglob("*") if path.is_file()))
                self.assertEqual(after, before)

    def test_d105_reconstructed_transfer_cannot_bypass_sealed_dispatch(self):
        hooks = self.root / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        results = self.bootstrap_results()
        original_digest = provider_lock.sha256_digest

        def digest(value):
            return BOOTSTRAP_DIGEST if value == BOOTSTRAP_PREIMAGE else original_digest(value)

        with patch.object(provider_lock, "sha256_digest", side_effect=digest):
            planned = plan_bootstrap_transfer(self.root, results, lock_bytes=None,
                                              admission=self.bootstrap_admission())
            reconstructed = (
                replace(planned, lock_path=".swissknifeman/rogue-lock.json"),
                replace(planned, bootstrap_transfer=None),
            )
            for mutated in reconstructed:
                with self.subTest(mutated=mutated):
                    before = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                                          for path in self.root.rglob("*") if path.is_file()))
                    with self.assertRaisesRegex(ValueError, "bootstrap transfer"):
                        apply_plan(self.root, mutated)
                    after = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                                         for path in self.root.rglob("*") if path.is_file()))
                    self.assertEqual(after, before)

    def test_d104_transfer_rechecks_changed_target_before_backup_write(self):
        hooks = self.root / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        results = self.bootstrap_results()
        original_digest = provider_lock.sha256_digest

        def digest(value):
            return BOOTSTRAP_DIGEST if value == BOOTSTRAP_PREIMAGE else original_digest(value)

        with patch.object(provider_lock, "sha256_digest", side_effect=digest):
            planned = plan_bootstrap_transfer(self.root, results, lock_bytes=None,
                                              admission=self.bootstrap_admission())
            hooks.write_bytes(b"raced\n")
            with self.assertRaisesRegex(ValueError, "bootstrap-preimage-mismatch"):
                apply_plan(self.root, planned)
        self.assertFalse(hooks.with_name("hooks.json.provider-artifact.bootstrap-transfer.bak").exists())
        self.assertFalse((self.root / ".swissknifeman/provider-artifacts.lock.json").exists())

    def test_d104_transfer_failure_rolls_back_only_transaction_created_state(self):
        hooks = self.root / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        results = self.bootstrap_results()
        original_digest = provider_lock.sha256_digest

        def digest(value):
            return BOOTSTRAP_DIGEST if value == BOOTSTRAP_PREIMAGE else original_digest(value)

        with patch.object(provider_lock, "sha256_digest", side_effect=digest):
            planned = plan_bootstrap_transfer(self.root, results, lock_bytes=None,
                                              admission=self.bootstrap_admission())
            writer = provider_lock._atomic_write_bytes
            calls = 0

            def fail_on_third(path, value):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("stop")
                writer(path, value)

            with patch.object(provider_lock, "_atomic_write_bytes", side_effect=fail_on_third):
                with self.assertRaisesRegex(OSError, "stop"):
                    apply_plan(self.root, planned)
        self.assertEqual(hooks.read_bytes(), BOOTSTRAP_PREIMAGE)
        self.assertFalse((self.root / ".codex/hooks/lifecycle.py").exists())
        self.assertFalse((self.root / ".swissknifeman/provider-artifacts.lock.json").exists())

    def test_d108_chained_transfer_preserves_mcp_and_second_plan_is_noop(self):
        hooks = self.root / ".codex/hooks.json"
        mcp = self.root / ".mcp.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        mcp.write_bytes(MCP_PREIMAGE)
        results = self.chained_results()
        with self.chained_exact_vectors() as (bootstrap_digest, mcp_digest):
            predecessor = self.chained_predecessor(self.root, bootstrap_digest)
            planned = plan_chained_bootstrap_transfer(
                self.root, results, lock_bytes=None,
                admission=self.chained_admission(predecessor, bootstrap_digest, mcp_digest))
            self.assertEqual(
                {action.target_path: action.action for action in planned.actions},
                {".codex/hooks.json": ArtifactActionKind.UPDATE,
                 ".codex/hooks/lifecycle.py": ArtifactActionKind.CREATE,
                 ".mcp.json": ArtifactActionKind.NOOP})
            applied = apply_plan(self.root, planned)
        self.assertEqual(mcp.read_bytes(), MCP_PREIMAGE)
        self.assertEqual(
            mcp.with_name(".mcp.json.provider-artifact.bootstrap-transfer.bak").read_bytes(),
            MCP_PREIMAGE)
        lock = parse_lock((self.root / ".swissknifeman/provider-artifacts.lock.json").read_bytes())
        self.assertEqual(
            [record.artifact_id for record in lock.records],
            ["harness.codex.lifecycle.handler", "harness.codex.lifecycle.hooks",
             "maind.provider-deploy.claude-code"])
        second = plan_artifact_lock(
            self.root, results,
            lock_bytes=(self.root / ".swissknifeman/provider-artifacts.lock.json").read_bytes())
        self.assertTrue(all(action.action is ArtifactActionKind.NOOP for action in second.actions))

    def test_d108_chained_admission_mutations_refuse_before_writer(self):
        hooks = self.root / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        (self.root / ".mcp.json").write_bytes(MCP_PREIMAGE)
        results = self.chained_results()
        with self.chained_exact_vectors() as (bootstrap_digest, mcp_digest):
            predecessor = self.chained_predecessor(self.root, bootstrap_digest)
            admission = self.chained_admission(predecessor, bootstrap_digest, mcp_digest)
            mutations = (
                replace(admission, decision_id="D109"),
                replace(admission, mcp_target_path="other.mcp.json"),
                replace(admission, mcp_preimage_sha256=HASH),
                replace(admission, mcp_artifact_id="maind.other"),
                replace(admission, mcp_managed_boundary=("managed-blocks", ("mcp",))),
                replace(admission, mcp_server_ids=("maind", "serena")),
            )
            for altered in mutations:
                with self.subTest(admission=altered), patch.object(
                        provider_lock, "_atomic_write_bytes", wraps=provider_lock._atomic_write_bytes) as writer:
                    planned = plan_chained_bootstrap_transfer(
                        self.root, results, lock_bytes=None, admission=altered)
                    self.assertTrue(all(action.action is ArtifactActionKind.REFUSE for action in planned.actions))
                    with self.assertRaises(ValueError):
                        apply_plan(self.root, planned)
                    self.assertEqual(writer.call_count, 0)
            changed_boundary = list(results)
            changed_boundary[2] = result(body=MCP_PREIMAGE,
                                         artifact_id="maind.provider-deploy.claude-code",
                                         target=".mcp.json", boundary=("managed-blocks", ("mcp",)))
            planned = plan_chained_bootstrap_transfer(
                self.root, changed_boundary, lock_bytes=None, admission=admission)
            self.assertTrue(all(action.action is ArtifactActionKind.REFUSE for action in planned.actions))
            locked = plan_chained_bootstrap_transfer(
                self.root, results, lock_bytes=b"{}", admission=admission)
            self.assertTrue(all(action.action is ArtifactActionKind.REFUSE for action in locked.actions))
            for index, changed in (
                    (0, result(body=b'{"hooks":{"SessionStart":["changed"]}}\n',
                               artifact_id="harness.codex.lifecycle.hooks",
                               target=".codex/hooks.json")),
                    (1, result(body=b"def lifecycle(event):\n    return 'changed'\n",
                               artifact_id="harness.codex.lifecycle.handler",
                               target=".codex/hooks/lifecycle.py"))):
                with self.subTest(predecessor_index=index), patch.object(
                        provider_lock, "_atomic_write_bytes", wraps=provider_lock._atomic_write_bytes) as writer:
                    mutated_predecessor = list(results)
                    mutated_predecessor[index] = changed
                    planned = plan_chained_bootstrap_transfer(
                        self.root, mutated_predecessor, lock_bytes=None, admission=admission)
                    self.assertTrue(all(action.action is ArtifactActionKind.REFUSE for action in planned.actions))
                    with self.assertRaises(ValueError):
                        apply_plan(self.root, planned)
                    self.assertEqual(writer.call_count, 0)

    def test_d108_chained_apply_refuses_stale_mcp_before_writer(self):
        hooks = self.root / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        mcp = self.root / ".mcp.json"
        mcp.write_bytes(MCP_PREIMAGE)
        with self.chained_exact_vectors() as (bootstrap_digest, mcp_digest):
            predecessor = self.chained_predecessor(self.root, bootstrap_digest)
            planned = plan_chained_bootstrap_transfer(
                self.root, self.chained_results(), lock_bytes=None,
                admission=self.chained_admission(predecessor, bootstrap_digest, mcp_digest))
            mcp.write_bytes(b"stale\n")
            with patch.object(provider_lock, "_atomic_write_bytes", wraps=provider_lock._atomic_write_bytes) as writer:
                with self.assertRaisesRegex(ValueError, "chained-bootstrap-mcp-preimage-mismatch"):
                    apply_plan(self.root, planned)
        self.assertEqual(writer.call_count, 0)

    def test_d108_reconstructed_chain_cannot_bypass_sealed_dispatch(self):
        hooks = self.root / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        (self.root / ".mcp.json").write_bytes(MCP_PREIMAGE)
        with self.chained_exact_vectors() as (bootstrap_digest, mcp_digest):
            predecessor = self.chained_predecessor(self.root, bootstrap_digest)
            planned = plan_chained_bootstrap_transfer(
                self.root, self.chained_results(), lock_bytes=None,
                admission=self.chained_admission(predecessor, bootstrap_digest, mcp_digest))
            mcp_action = next(action for action in planned.actions if action.target_path == ".mcp.json")
            reconstructed = (
                replace(planned, chained_bootstrap_transfer=None),
                replace(planned, actions=(replace(mcp_action, action=ArtifactActionKind.UPDATE),),
                        chained_bootstrap_transfer=None),
            )
            before = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                                  for path in self.root.rglob("*") if path.is_file()))
            for mutated in reconstructed:
                with self.subTest(mutated=mutated), patch.object(
                        provider_lock, "_atomic_write_bytes", wraps=provider_lock._atomic_write_bytes) as writer:
                    with self.assertRaisesRegex(ValueError, "chained bootstrap transfer"):
                        apply_plan(self.root, mutated)
                    self.assertEqual(writer.call_count, 0)
        after = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                             for path in self.root.rglob("*") if path.is_file()))
        self.assertEqual(after, before)

    def test_d108_chained_write_failures_restore_exact_prestate(self):
        for failing_write in range(1, 6):
            with self.subTest(failing_write=failing_write), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                hooks = root / ".codex/hooks.json"
                hooks.parent.mkdir(parents=True)
                hooks.write_bytes(BOOTSTRAP_PREIMAGE)
                (root / ".mcp.json").write_bytes(MCP_PREIMAGE)
                before = tuple(sorted((path.relative_to(root).as_posix(), path.read_bytes())
                                      for path in root.rglob("*") if path.is_file()))
                with self.chained_exact_vectors() as (bootstrap_digest, mcp_digest):
                    predecessor = self.chained_predecessor(root, bootstrap_digest)
                    planned = plan_chained_bootstrap_transfer(
                        root, self.chained_results(), lock_bytes=None,
                        admission=self.chained_admission(predecessor, bootstrap_digest, mcp_digest))
                    writer = provider_lock._atomic_write_bytes
                    calls = 0

                    def fail_on_requested_write(path, value):
                        nonlocal calls
                        calls += 1
                        if calls == failing_write:
                            raise OSError("stop")
                        writer(path, value)

                    with patch.object(provider_lock, "_atomic_write_bytes", side_effect=fail_on_requested_write):
                        with self.assertRaisesRegex(OSError, "stop"):
                            apply_plan(root, planned)
                after = tuple(sorted((path.relative_to(root).as_posix(), path.read_bytes())
                                     for path in root.rglob("*") if path.is_file()))
                self.assertEqual(after, before)

    def test_d123_rolls_back_only_the_completed_exact_d108_state(self):
        hooks = self.root / ".codex/hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_bytes(BOOTSTRAP_PREIMAGE)
        (self.root / ".mcp.json").write_bytes(MCP_PREIMAGE)
        before = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                              for path in self.root.rglob("*") if path.is_file()))
        with self.chained_exact_vectors() as (bootstrap_digest, mcp_digest):
            predecessor = self.chained_predecessor(self.root, bootstrap_digest)
            planned = plan_chained_bootstrap_transfer(
                self.root, self.chained_results(), lock_bytes=None,
                admission=self.chained_admission(predecessor, bootstrap_digest, mcp_digest))
            apply_plan(self.root, planned)
            self.assertIs(rollback_chained_bootstrap_transfer(self.root, planned), planned)
        after = tuple(sorted((path.relative_to(self.root).as_posix(), path.read_bytes())
                             for path in self.root.rglob("*") if path.is_file()))
        self.assertEqual(after, before)

    def test_d123_refuses_nonexact_completed_d108_state_before_writer(self):
        cases = (
            ("missing-backup", lambda root: (root / ".codex/hooks.json.provider-artifact.bootstrap-transfer.bak").unlink()),
            ("extra-backup", lambda root: (root / ".codex/hooks/lifecycle.py.provider-artifact.bootstrap-transfer.bak").write_bytes(b"extra\n")),
            ("different-backup", lambda root: (root / ".mcp.json.provider-artifact.bootstrap-transfer.bak").write_bytes(b"different\n")),
            ("changed-lock", lambda root: (root / ".swissknifeman/provider-artifacts.lock.json").write_bytes(b"changed\n")),
            ("changed-handler", lambda root: (root / ".codex/hooks/lifecycle.py").write_bytes(b"changed\n")),
        )
        for name, mutate in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                hooks = root / ".codex/hooks.json"
                hooks.parent.mkdir(parents=True)
                hooks.write_bytes(BOOTSTRAP_PREIMAGE)
                (root / ".mcp.json").write_bytes(MCP_PREIMAGE)
                with self.chained_exact_vectors() as (bootstrap_digest, mcp_digest):
                    predecessor = self.chained_predecessor(root, bootstrap_digest)
                    planned = plan_chained_bootstrap_transfer(
                        root, self.chained_results(), lock_bytes=None,
                        admission=self.chained_admission(predecessor, bootstrap_digest, mcp_digest))
                    apply_plan(root, planned)
                    mutate(root)
                    before = tuple(sorted((path.relative_to(root).as_posix(), path.read_bytes())
                                          for path in root.rglob("*") if path.is_file()))
                    with patch.object(provider_lock, "_atomic_write_bytes",
                                      wraps=provider_lock._atomic_write_bytes) as writer:
                        with self.assertRaisesRegex(ValueError, "chained bootstrap rollback"):
                            rollback_chained_bootstrap_transfer(root, planned)
                    self.assertEqual(writer.call_count, 0)
                    after = tuple(sorted((path.relative_to(root).as_posix(), path.read_bytes())
                                         for path in root.rglob("*") if path.is_file()))
                    self.assertEqual(after, before)

    def test_ordinary_plan_retains_unrelated_lock_records(self):
        first = self.plan()
        apply_plan(self.root, first)
        other = result(artifact_id="harness.other", target=".codex/other.py")
        retained = plan_artifact_lock(
            self.root, (other,), lock_bytes=serialize_lock(first.next_lock),
            retain_unexpected_records=True)
        apply_plan(self.root, retained)
        lock = parse_lock((self.root / ".swissknifeman/provider-artifacts.lock.json").read_bytes())
        self.assertEqual({record.artifact_id for record in lock.records},
                         {self.expected.provenance.artifact_id, other.provenance.artifact_id})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
