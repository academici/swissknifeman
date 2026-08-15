"""Normative D86 semantic/API/P2 lifecycle tests; every target is temporary."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from core.provider.artifact import sha256_digest
from core.provider.lock import serialize_lock
from harness.instructions import (
    CATALOG_VERSION, COMMON_IDS, CONTRACT_VERSION, DIAGNOSTIC_CODES, EXTENSION_IDS,
    PROVIDERS, SCOPES, TARGETS, InstructionDiagnostic, InstructionRequest,
    adopt_instructions, apply_instructions, check_instructions, load_catalog,
    plan_instructions, repair_instructions,
)
from harness.provider_render import render_locale_context
from core.locale import resolve_locale


def request(operation, root, **changes):
    base = InstructionRequest(
        CONTRACT_VERSION, CATALOG_VERSION, operation, SCOPES, PROVIDERS, str(root),
        (("config_id", "test-config"), ("source", "contract-fixture")),
        (("authority", "synthetic-temp-root"),),
    )
    return replace(base, **changes)


def snapshot(root):
    return tuple((path.relative_to(root).as_posix(), path.read_bytes(),
                  path.stat().st_mtime_ns) for path in sorted(root.rglob("*")) if path.is_file())


def diagnostic_codes(result):
    return tuple(item.code for item in result.diagnostics)


def altered_result(mutator):
    catalog = deepcopy(load_catalog())
    mutator(catalog)
    with tempfile.TemporaryDirectory() as temp:
        return plan_instructions(request("plan", Path(temp).resolve()), catalog=catalog)


def root_records(catalog):
    return catalog["scopes"][0]["sections"]


def set_conflict(catalog, *, common_modality="must", extension_modality="must",
                 extension_boundary=None, equivalent=False, shadow=False):
    common = root_records(catalog)[0]["obligations"][0]
    extension = root_records(catalog)[21]["obligations"][0]
    common["modality"] = common_modality
    extension.update({
        "modality": extension_modality,
        "subject": common["subject"],
        "action": common["action"],
        "object": common["object"] if not shadow else "root.replacement.requirements",
        "boundary": common["boundary"] if equivalent else (
            extension_boundary or extension["boundary"]),
    })


class SemanticCatalogTests(unittest.TestCase):
    def test_locale_context_keeps_provider_output_ownership(self):
        registry = Path(__file__).resolve().parents[3] / "core/locale/data/language-subtag-registry.txt"
        result = resolve_locale(({"contract_version": "1.0.0", "rank": 5, "kind": "built-in", "locale": {"response": "en", "plan": "en", "diagnostics": "en"}},), registry_path=registry)
        self.assertEqual(render_locale_context(result)["provider_boundary"], "harness")
    def test_exact_62_common_22_extension_84_total_and_fourteen_targets(self):
        catalog = load_catalog()
        common = sum(record["kind"] == "common" for scope in catalog["scopes"]
                     for record in scope["sections"])
        extensions = sum(record["kind"] == "provider-extension" for scope in catalog["scopes"]
                         for record in scope["sections"])
        self.assertEqual((common, extensions, common + extensions), (62, 22, 84))
        with tempfile.TemporaryDirectory() as temp:
            result = plan_instructions(request("plan", Path(temp).resolve()))
        self.assertEqual(
            tuple((item.scope_id, item.provider_id, item.target_path) for item in result.targets),
            tuple((scope, provider, TARGETS[scope][provider])
                  for scope in SCOPES for provider in PROVIDERS))
        self.assertEqual(len(result.targets), 14)

    def test_positive_parity_and_allowed_provider_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            result = plan_instructions(request("plan", Path(temp).resolve()))
        for scope in SCOPES:
            claude, codex = [item for item in result.targets if item.scope_id == scope]
            common = COMMON_IDS[scope]
            self.assertEqual(claude.ordered_semantic_ids[:len(common)], common)
            self.assertEqual(codex.ordered_semantic_ids[:len(common)], common)
            self.assertEqual(
                claude.ordered_semantic_ids[len(common):],
                EXTENSION_IDS[(scope, "claude-code")])
            self.assertEqual(
                codex.ordered_semantic_ids[len(common):],
                EXTENSION_IDS[(scope, "codex")])

    def test_missing_id_refuses_before_p2(self):
        result = altered_result(lambda value: root_records(value).pop(0))
        self.assertIn("INSTRUCTION_SEMANTIC_ID_MISSING", diagnostic_codes(result))
        self.assertIsNone(result.artifact_plan)

    def test_duplicate_id_refuses_before_p2(self):
        def mutate(value):
            root_records(value).insert(1, deepcopy(root_records(value)[0]))
        result = altered_result(mutate)
        self.assertIn("INSTRUCTION_SEMANTIC_ID_DUPLICATE", diagnostic_codes(result))
        self.assertIsNone(result.artifact_plan)

    def test_reordered_id_refuses_before_p2(self):
        def mutate(value):
            records = root_records(value)
            records[0], records[1] = records[1], records[0]
        result = altered_result(mutate)
        self.assertIn("INSTRUCTION_SEMANTIC_ORDER_INVALID", diagnostic_codes(result))
        self.assertIsNone(result.artifact_plan)

    def test_extra_common_id_refuses_before_p2(self):
        def mutate(value):
            extra = deepcopy(root_records(value)[0])
            extra["id"] = "root.extra"
            extra["order"] = 12
            extra["obligations"][0]["object"] = "root.extra.requirements"
            root_records(value).insert(11, extra)
        result = altered_result(mutate)
        self.assertIn("INSTRUCTION_SEMANTIC_ORDER_INVALID", diagnostic_codes(result))
        self.assertIsNone(result.artifact_plan)

    def test_provider_mismatch_and_namespace_refuse_before_p2(self):
        def mismatch(value):
            record = root_records(value)[21]
            record["provider_id"] = "claude-code"
        result = altered_result(mismatch)
        self.assertIn("INSTRUCTION_EXTENSION_ID_INVALID", diagnostic_codes(result))
        self.assertIsNone(result.artifact_plan)

    def test_explicit_catalog_is_always_semantically_validated(self):
        catalog = deepcopy(load_catalog())
        root_records(catalog)[0]["sources"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp:
            result = plan_instructions(request("plan", Path(temp).resolve()), catalog=catalog)
        self.assertIn("INSTRUCTION_PROVENANCE_INVALID", diagnostic_codes(result))
        self.assertIsNone(result.artifact_plan)

    def test_fragment_assertion_mismatch_refuses_before_p2(self):
        catalog = deepcopy(load_catalog())
        root_records(catalog)[0]["compatibility_assertions"].append("not in frozen fragment")
        with tempfile.TemporaryDirectory() as temp:
            result = plan_instructions(request("plan", Path(temp).resolve()), catalog=catalog)
        self.assertIn("INSTRUCTION_COMPATIBILITY_MISMATCH", diagnostic_codes(result))
        self.assertIsNone(result.artifact_plan)

    def test_normalized_obligations_and_fragment_only_record_sources(self):
        for scope in load_catalog()["scopes"]:
            for record in scope["sections"]:
                obligation = record["obligations"][0]
                self.assertRegex(obligation["subject"], r"^[a-z][a-z0-9.-]+$")
                self.assertRegex(obligation["action"], r"^[a-z][a-z0-9-]*$")
                self.assertRegex(obligation["object"], r"^[a-z][a-z0-9.-]+$")
                self.assertNotIn(" ", obligation["boundary"])
                self.assertEqual(len(record["sources"]), 1)
                self.assertIn("/instructions/", record["sources"][0]["path"])
                self.assertNotIn("CLAUDE.md", record["sources"][0]["path"])
                self.assertNotIn("AGENTS.md", record["sources"][0]["path"])

    def test_duplicate_normalized_common_obligation_fails(self):
        def mutate(value):
            root_records(value)[1]["obligations"] = deepcopy(
                root_records(value)[0]["obligations"])
        result = altered_result(mutate)
        self.assertIn("INSTRUCTION_SEMANTIC_ID_DUPLICATE", diagnostic_codes(result))

    def test_conflict_opposite_modality(self):
        result = altered_result(lambda value: set_conflict(
            value, common_modality="must", extension_modality="must-not",
            extension_boundary="root.all"))
        self.assertIn("INSTRUCTION_EXTENSION_CONFLICT", diagnostic_codes(result))

    def test_conflict_broader_permission(self):
        result = altered_result(lambda value: set_conflict(
            value, common_modality="must-not", extension_modality="may",
            extension_boundary="root.all"))
        self.assertIn("INSTRUCTION_EXTENSION_CONFLICT", diagnostic_codes(result))

    def test_conflict_narrower_required_coverage(self):
        result = altered_result(lambda value: set_conflict(
            value, common_modality="must", extension_modality="must",
            extension_boundary="root.provider.codex"))
        self.assertIn("INSTRUCTION_EXTENSION_CONFLICT", diagnostic_codes(result))

    def test_conflict_common_owner_replacement_shadow(self):
        result = altered_result(lambda value: set_conflict(
            value, shadow=True, extension_boundary="root.all"))
        self.assertIn("INSTRUCTION_EXTENSION_CONFLICT", diagnostic_codes(result))

    def test_conflict_equivalent_obligation_under_another_id(self):
        result = altered_result(lambda value: set_conflict(value, equivalent=True))
        self.assertIn("INSTRUCTION_EXTENSION_CONFLICT", diagnostic_codes(result))


class PublicOperationTests(unittest.TestCase):
    def test_request_requires_absolute_root_versions_scopes_providers_and_provenance(self):
        invalid = InstructionRequest(
            "2.0.0", "2.0.0", "plan", ("unknown",), ("other",), "relative",
            (), ())
        result = plan_instructions(invalid)
        self.assertFalse(result.green)
        self.assertIn("INSTRUCTION_PROVENANCE_INVALID", diagnostic_codes(result))
        self.assertIn("INSTRUCTION_SCOPE_INVALID", diagnostic_codes(result))

    def test_plan_and_check_are_strictly_no_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            sentinel = root / "sentinel"
            sentinel.write_bytes(b"unchanged")
            before = snapshot(root)
            planned = plan_instructions(request("plan", root))
            checked = check_instructions(request("check", root))
            self.assertEqual(snapshot(root), before)
            self.assertFalse(planned.green)
            self.assertFalse(checked.green)
            self.assertTrue(all(item.observation == "missing" for item in checked.targets))

    def test_explicit_create_boundary_then_clean_two_run_determinism(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(request("plan", root))
            targets = tuple(action.target_path for action in planned.artifact_plan.actions)
            applied = apply_instructions(request(
                "apply", root, authorized_target_paths=targets))
            self.assertTrue(applied.green)
            self.assertTrue(all(item.changed for item in applied.targets))
            first = check_instructions(request("check", root)).as_dict()
            second = check_instructions(request("check", root)).as_dict()
            self.assertEqual(first, second)
            self.assertTrue(first["green"])

    def test_missing_package_agents_is_structured_non_green(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            result = check_instructions(request(
                "check", root, scope_ids=("analyst",), provider_ids=("codex",)))
        self.assertEqual(len(result.targets), 1)
        self.assertEqual(result.targets[0].target_path, "packages/analyst/AGENTS.md")
        self.assertEqual(result.targets[0].observation, "missing")
        self.assertEqual(diagnostic_codes(result), ("INSTRUCTION_TARGET_MISSING",))

    def test_unmanaged_existing_target_refuses_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            target = root / "AGENTS.md"
            target.write_bytes(b"user-owned\n")
            result = check_instructions(request(
                "check", root, scope_ids=("root",), provider_ids=("codex",)))
            self.assertEqual(result.targets[0].observation, "ownership-conflict")
            self.assertEqual(diagnostic_codes(result), ("INSTRUCTION_OWNERSHIP_CONFLICT",))
            refused = apply_instructions(request(
                "apply", root, scope_ids=("root",), provider_ids=("codex",),
                authorized_target_paths=("AGENTS.md",)))
            self.assertIn("INSTRUCTION_WRITE_FORBIDDEN", diagnostic_codes(refused))
            self.assertEqual(target.read_bytes(), b"user-owned\n")

    def test_create_requires_exact_authorized_target_set(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            result = apply_instructions(request(
                "apply", root, authorized_target_paths=("AGENTS.md",)))
            self.assertFalse(result.green)
            self.assertEqual(diagnostic_codes(result)[-1], "INSTRUCTION_WRITE_FORBIDDEN")
            self.assertEqual(snapshot(root), ())

    def test_authorize_order_mismatch_message_shows_copyable_expected_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(request("plan", root, scope_ids=("root",)))
            expected_order = tuple(action.target_path for action in planned.artifact_plan.actions)
            self.assertGreater(len(expected_order), 1)
            wrong_order = tuple(reversed(expected_order))
            self.assertNotEqual(wrong_order, expected_order)
            refused = apply_instructions(request(
                "apply", root, scope_ids=("root",), authorized_target_paths=wrong_order))
            self.assertFalse(refused.green)
            diagnostic = next(item for item in refused.diagnostics
                              if item.code == "INSTRUCTION_WRITE_FORBIDDEN")
            self.assertIsNotNone(diagnostic.message)
            self.assertIn("алфавитный по target_path", diagnostic.message)
            self.assertTrue(diagnostic.message.endswith(",".join(expected_order)))
            self.assertEqual(snapshot(root), ())
            copied = apply_instructions(request(
                "apply", root, scope_ids=("root",), authorized_target_paths=expected_order))
            self.assertTrue(copied.green)

    def test_authorize_order_message_derived_not_hardcoded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(request(
                "plan", root, scope_ids=("root", "harness"), provider_ids=("codex",)))
            expected_order = tuple(action.target_path for action in planned.artifact_plan.actions)
            self.assertEqual(expected_order, ("AGENTS.md", "packages/harness/AGENTS.md"))
            refused = apply_instructions(request(
                "apply", root, scope_ids=("root", "harness"), provider_ids=("codex",),
                authorized_target_paths=tuple(reversed(expected_order))))
            diagnostic = next(item for item in refused.diagnostics
                              if item.code == "INSTRUCTION_WRITE_FORBIDDEN")
            self.assertEqual(diagnostic.message.rsplit(": ", 1)[-1], ",".join(expected_order))

    def test_other_write_refusal_call_sites_leave_message_unset(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(request("plan", root))
            targets = tuple(action.target_path for action in planned.artifact_plan.actions)
            self.assertTrue(apply_instructions(request(
                "apply", root, authorized_target_paths=targets)).green)
            target = root / "AGENTS.md"
            target.write_bytes(b"user before\n" + target.read_bytes() + b"user after\n")
            target.write_bytes(target.read_bytes().replace(b"<!-- semantic:", b"<!-- local:", 1))
            wrong_hash_repair = repair_instructions(request(
                "repair", root, authorized_target_paths=("AGENTS.md",),
                observed_hashes=(("AGENTS.md", "not-the-real-hash"),),
                preimage_destination="adjacent-backup"))
            self.assertFalse(wrong_hash_repair.green)
            repair_diag = next(item for item in wrong_hash_repair.diagnostics
                               if item.code == "INSTRUCTION_WRITE_FORBIDDEN")
            self.assertIsNone(repair_diag.message)
            adopt_refused = adopt_instructions(request("adopt", root))
            self.assertFalse(adopt_refused.green)
            adopt_diag = next(item for item in adopt_refused.diagnostics
                              if item.code == "INSTRUCTION_WRITE_FORBIDDEN")
            self.assertIsNone(adopt_diag.message)

    def test_managed_drift_update_refuses_and_explicit_repair_preserves_outside(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            initial = plan_instructions(request("plan", root))
            create_targets = tuple(action.target_path for action in initial.artifact_plan.actions)
            self.assertTrue(apply_instructions(request(
                "apply", root, authorized_target_paths=create_targets)).green)
            target = root / "AGENTS.md"
            target.write_bytes(b"user before\n" + target.read_bytes() + b"user after\n")
            target.write_bytes(target.read_bytes().replace(b"<!-- semantic:", b"<!-- local:", 1))
            drift = plan_instructions(request("plan", root))
            action = next(item for item in drift.artifact_plan.actions
                          if item.target_path == "AGENTS.md")
            self.assertEqual(action.observation.value, "managed-drift")
            update = apply_instructions(request(
                "update", root, authorized_target_paths=("AGENTS.md",)))
            self.assertIn("INSTRUCTION_WRITE_FORBIDDEN", diagnostic_codes(update))
            repaired = repair_instructions(request(
                "repair", root, authorized_target_paths=("AGENTS.md",),
                observed_hashes=(("AGENTS.md", action.observed_hash),),
                preimage_destination="adjacent-backup"))
            self.assertTrue(repaired.green)
            self.assertTrue((root / "AGENTS.md.provider-artifact.bak").is_file())
            self.assertEqual(target.read_bytes().splitlines()[0], b"user before")
            self.assertEqual(target.read_bytes().splitlines()[-1], b"user after")

    def test_stale_source_update_is_explicit_and_preserves_outside_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            original = load_catalog()
            created = plan_instructions(request("plan", root), catalog=original)
            create_targets = tuple(action.target_path for action in created.artifact_plan.actions)
            self.assertTrue(apply_instructions(request(
                "apply", root, authorized_target_paths=create_targets), catalog=original).green)
            target = root / "CLAUDE.md"
            target.write_bytes(b"before\n" + target.read_bytes() + b"after\n")
            changed = deepcopy(original)
            root_records(changed)[0]["intent"] += " Compatible native wording remains allowed."
            stale = plan_instructions(request("plan", root), catalog=changed)
            self.assertTrue(all(item.observation == "stale-source" for item in stale.targets))
            update_targets = tuple(action.target_path for action in stale.artifact_plan.actions)
            updated = apply_instructions(request(
                "update", root, authorized_target_paths=update_targets), catalog=changed)
            self.assertTrue(updated.green)
            self.assertEqual(target.read_bytes().splitlines()[0], b"before")
            self.assertEqual(target.read_bytes().splitlines()[-1], b"after")

    def test_corrupt_and_newer_locks_fail_closed(self):
        for raw in (b"{bad", b'{"records":[],"schema_version":2}\n'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                lock = root / ".swissknifeman/provider-artifacts.lock.json"
                lock.parent.mkdir()
                lock.write_bytes(raw)
                result = check_instructions(request("check", root))
                self.assertTrue(all(item.observation == "provenance-invalid"
                                    for item in result.targets))
                self.assertEqual(set(diagnostic_codes(result)),
                                 {"INSTRUCTION_PROVENANCE_INVALID"})

    def test_boundary_invalid_maps_to_instruction_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(request("plan", root))
            targets = tuple(action.target_path for action in planned.artifact_plan.actions)
            apply_instructions(request("apply", root, authorized_target_paths=targets))
            target = root / "AGENTS.md"
            raw = target.read_bytes()
            marker = b"<!-- swissknifeman:instructions:root:codex:common:begin -->"
            target.write_bytes(marker + b"\n" + raw)
            result = check_instructions(request("check", root))
            selected = next(item for item in result.targets if item.target_path == "AGENTS.md")
            self.assertEqual(selected.observation, "boundary-invalid")
            self.assertEqual(selected.diagnostics[0].code, "INSTRUCTION_BOUNDARY_INVALID")

    def test_target_result_schema_diagnostics_order_and_unknown_codes_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            result = plan_instructions(request("plan", Path(temp).resolve()))
        target_keys = set(result.targets[0].as_dict())
        self.assertEqual(target_keys, {
            "artifact_id", "scope_id", "provider_id", "target_path",
            "ordered_semantic_ids", "observation", "action", "source_hash",
            "render_hash", "marker_ids", "block_ids", "diagnostics", "changed",
        })
        self.assertEqual(tuple((item.scope_id, item.provider_id) for item in result.diagnostics),
                         tuple((scope, provider) for scope in SCOPES for provider in PROVIDERS))
        self.assertTrue(all(set(item.as_dict()) == {
            "severity", "code", "scope_id", "provider_id", "target_path", "artifact_id",
            "observation", "semantic_id", "expected", "observed", "next_action", "message",
        } for item in result.diagnostics))
        with self.assertRaisesRegex(ValueError, "unknown instruction diagnostic"):
            InstructionDiagnostic("error", "UNKNOWN", None, None, None, None,
                                  None, None, None, None, None, None)
        self.assertEqual(DIAGNOSTIC_CODES, set(DIAGNOSTIC_CODES))

    def test_serialized_p2_lock_has_exact_targets_sources_boundaries_and_capability(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            planned = plan_instructions(request("plan", root))
            lock = json.loads(serialize_lock(planned.artifact_plan.next_lock))
        self.assertEqual(len(lock["records"]), 14)
        expected_records = tuple(
            (provider, TARGETS[scope][provider])
            for _artifact_id, provider, scope in sorted(
                (f"harness.instruction-projection.{scope}.{provider}", provider, scope)
                for scope in SCOPES for provider in PROVIDERS))
        self.assertEqual(
            tuple((item["provider_id"], item["target_path"]) for item in lock["records"]),
            expected_records)
        for record in lock["records"]:
            self.assertEqual(record["contract_version"], "1.1.0")
            self.assertEqual(len(record["canonical_sources"]), 4)
            self.assertEqual(
                tuple(item["source_id"] for item in record["canonical_sources"]),
                tuple(sorted(item["source_id"] for item in record["canonical_sources"])))
            for source in record["canonical_sources"]:
                source_path = Path(__file__).resolve().parents[3] / source["path"]
                self.assertEqual(source["hash"], sha256_digest(source_path.read_bytes()))
            self.assertEqual(
                record["capability_requirements"],
                [{"id": "instructions.project", "accepted_levels": ["adapted", "native"]}])
            self.assertEqual(record["managed_boundary"]["mode"], "managed-blocks")
            self.assertEqual(len(record["managed_boundary"]["block_ids"]), 2)
            metadata = record["semantic_metadata"]
            self.assertEqual(set(metadata), {
                "artifact_kind", "block_ids", "capabilities", "catalog_version",
                "instruction_contract_version", "marker_ids", "provider_id", "registry",
                "scope_id", "semantic_sections",
            })
            self.assertEqual(metadata["artifact_kind"], "instruction-projection")
            self.assertEqual(metadata["instruction_contract_version"], CONTRACT_VERSION)
            self.assertEqual(metadata["catalog_version"], CATALOG_VERSION)
            self.assertEqual(metadata["provider_id"], record["provider_id"])
            self.assertEqual(metadata["block_ids"], record["managed_boundary"]["block_ids"])
            self.assertEqual(metadata["capabilities"], ["instructions.project"])
            self.assertEqual(metadata["registry"], "explicit")
            self.assertEqual(metadata["semantic_sections"], {
                "common": list(COMMON_IDS[metadata["scope_id"]]),
                "provider_extension": list(EXTENSION_IDS[
                    (metadata["scope_id"], metadata["provider_id"])]),
            })
            self.assertRegex(record["source_hash"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(record["rendered_hash"], r"^sha256:[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
