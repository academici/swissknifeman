"""P00 inventory and wire contracts; behavior is proved by the owner implementation leaves."""

from __future__ import annotations

import ast
import importlib
import json
import pkgutil
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[3]
GROUP = ("integrations", "knowledge", "learning", "exports")
UUID = "00000000-0000-0000-0000-000000000001"
DIGEST = "sha256:" + "a" * 64


def load_schemas(root: Path) -> dict[str, Any]:
    result = {}
    for path in root.rglob("*.json"):
        schema = json.loads(path.read_text())
        if isinstance(schema, dict) and "$id" in schema:
            assert schema["$id"] not in result, path
            result[schema["$id"]] = schema
    return result


CURRENT = load_schemas(ROOT / "src/skm/schemas")
EXAMPLES = load_schemas(ROOT / "tests/fixtures/corpus/examples/schemas")
OWNED = {urn: schema for urn, schema in CURRENT.items() if urn.split(":")[2] in GROUP}
REGISTRY = Registry().with_resources((urn, Resource.from_contents(schema)) for urn, schema in CURRENT.items())


def validator(urn: str) -> Draft202012Validator:
    return Draft202012Validator(CURRENT[urn], registry=REGISTRY)


def resolve_reference(reference: str, base: str) -> tuple[str, Any]:
    urn, _, fragment = reference.partition("#")
    urn = urn or base
    assert urn in CURRENT or urn in EXAMPLES, reference
    target = (EXAMPLES | CURRENT)[urn]
    for part in fragment.split("/")[1:]:
        target = target[part.replace("~1", "/").replace("~0", "~")]
    assert isinstance(target, (dict, bool)), reference
    return urn, target


def references(node: Any, base: str) -> set[str]:
    result = set()
    if isinstance(node, dict):
        if "$ref" in node:
            urn, _ = resolve_reference(node["$ref"], base)
            if urn not in CURRENT:
                result.add(node["$ref"])
        for child in node.values():
            result.update(references(child, base))
    elif isinstance(node, list):
        for child in node:
            result.update(references(child, base))
    return result


@pytest.mark.parametrize("urn", OWNED)
def test_schema_syntax_and_closed_reference_inventory(urn: str) -> None:
    Draft202012Validator.check_schema(OWNED[urn])
    # All current references are materialized; no example/network fallback at runtime.
    assert references(OWNED[urn], urn) == set()


def test_reference_inventory_rejects_unknown_urn_and_fragment() -> None:
    with pytest.raises(AssertionError):
        resolve_reference("urn:skm:unknown:document:v1", "")
    with pytest.raises(KeyError):
        resolve_reference("urn:skm:integrations:defs:v1#/$defs/not-declared", "")


@pytest.mark.parametrize("module", GROUP)
def test_imports_and_manifest_inventory(module: str) -> None:
    package = importlib.import_module(f"skm.modules.{module}")
    for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        importlib.import_module(info.name)
    manifest = importlib.import_module(package.__name__ + ".module").MODULE
    assert manifest.id == module
    assert manifest.optional is (module != "integrations")
    assert manifest.db_schema == f"skm_{module}"
    assert manifest.settings_sections == ((module, "hooks") if module == "integrations" else (module,))
    if module == "integrations":
        assert tuple(spec.consumer_id for spec in manifest.subscribers) == (
            "integrations.fan_out_hook_deliveries",
        )
        assert manifest.subscribers[0].event_types == frozenset(
            {
                "urn:skm:integrations:event:projection-drift-detected:v1",
                "urn:skm:integrations:event:hook-test-requested:v1",
                "urn:skm:policy:event:intent-proposed:v1",
                "urn:skm:policy:event:intent-approved:v1",
                "urn:skm:policy:event:intent-denied:v1",
            }
        )
        assert manifest.subscribers[0].handler.__name__ == "fan_out_hook_deliveries"
        assert tuple(spec.name for spec in manifest.host_operations) == (
            "integrations.host.plan_projection",
            "integrations.host.apply_projection",
            "integrations.host.detect_drift",
            "integrations.host.adopt_file",
            "integrations.host.remove_projection",
            "integrations.host.run_doctor",
            "integrations.host.first_turn_budget",
            "integrations.host.evaluate_hook",
            "integrations.host.trust_hook_subscription",
            "integrations.host.test_host_subscription",
            "integrations.host.drain_hook_spool",
            "integrations.host.sync_projections",
            "integrations.host.untrack_service_files",
        )
        assert tuple(spec.name for spec in manifest.commands) == (
            "integrations.record_projection_applied",
            "integrations.record_drift",
            "integrations.remove_projection",
            "integrations.record_hook_delivery_failure",
            "integrations.test_hook_subscription",
            "integrations.retry_hook_deliveries",
        )
        assert tuple(spec.name for spec in manifest.queries) == (
            "integrations.get_desired_projection",
            "integrations.get_applied_state",
            "integrations.list_projections",
            "integrations.list_hook_subscriptions",
            "integrations.list_hook_deliveries",
            "integrations.get_hook_policy",
        )
        assert tuple(ev.__name__ for ev in manifest.events) == (
            "ProjectionApplied",
            "ProjectionDriftDetected",
            "ProjectionRemoved",
            "HookDeliveryFailed",
            "HookTestRequested",
        )
        assert tuple(c.prefix for c in manifest.external_consumers) == ("hook",)
        assert manifest.doctor_checks == ()
    elif module == "knowledge":
        assert manifest.subscribers == ()
        assert tuple(spec.name for spec in manifest.host_operations) == (
            "knowledge.host.import_code_graph",
            "knowledge.host.derive_project_graph",
        )
        assert tuple(spec.name for spec in manifest.commands) == (
            "knowledge.import_graph",
            "knowledge.remember",
            "knowledge.forget",
            "knowledge.expire_memory",
            "knowledge.deprecate_lesson",
        )
        assert tuple(spec.name for spec in manifest.queries) == (
            "knowledge.search_memory",
            "knowledge.list_memory",
            "knowledge.list_lessons",
            "knowledge.get_lesson",
            "knowledge.graph_neighbors",
            "knowledge.graph_path",
            "knowledge.graph_stats",
            "knowledge.graph_subgraph",
            "knowledge.list_graph_indexes",
        )
        assert tuple(ev.__name__ for ev in manifest.events) == (
            "MemoryRemembered",
            "MemoryForgotten",
            "LessonPromoted",
            "LessonDeprecated",
            "GraphImported",
        )
        assert manifest.external_consumers == manifest.doctor_checks == ()
    elif module == "learning":
        assert tuple(spec.consumer_id for spec in manifest.subscribers) == ("learning.task_outcome_signals",)
        assert manifest.host_operations == ()
        assert tuple(spec.name for spec in manifest.commands) == (
            "learning.review_candidate",
            "learning.promote_candidate",
            "learning.recompute_confidence",
            "learning.record_activity",
            "learning.extract_candidates",
        )
        assert tuple(spec.name for spec in manifest.queries) == (
            "learning.list_candidates",
            "learning.get_candidate",
            "learning.list_signals",
            "learning.pathology_stats",
        )
        assert tuple(ev.__name__ for ev in manifest.events) == (
            "CandidateExtracted",
            "CandidatePromoted",
            "CandidateReviewed",
            "CandidateStateChanged",
        )
        assert manifest.external_consumers == manifest.doctor_checks == ()
    else:
        assert tuple(spec.consumer_id for spec in manifest.subscribers) == (
            "exports.plan_archived_note",
            "exports.run_finished_note",
        )
        assert tuple(spec.name for spec in manifest.host_operations) == (
            "exports.host.locate_vault",
            "exports.host.push_vault_notes",
            "exports.host.push_vault_docs",
        )
        assert tuple(spec.name for spec in manifest.commands) == (
            "exports.record_note_written",
            "exports.requeue_note",
            "exports.purge_notes",
        )
        assert tuple(spec.name for spec in manifest.queries) == (
            "exports.render_plan_markdown",
            "exports.render_run_report",
            "exports.list_pending_notes",
            "exports.list_vault_notes",
        )
        assert tuple(ev.__name__ for ev in manifest.events) == ("VaultNoteQueued", "VaultNoteWritten")
        assert manifest.external_consumers == manifest.doctor_checks == ()
    expected = {
        "integrations": (
            {"ProjectionRepository"},
            {
                "IntegrationTarget",
                "IntegrationTargetRegistry",
                "CheckoutFs",
                "CheckoutGitExcludes",
                "ProjectionConfig",
                "LocalCheckoutProjections",
                "UserHomeReader",
                "HostCommandRunner",
            },
            ("workspace", "artifacts", "extensions", "policy", "runtimes"),
        ),
        "knowledge": (
            {"MemoryRepository", "LessonRepository", "GraphRepository"},
            {"CodeGraphReader", "GraphCheckoutResolver", "ManifestReader", "LocalEpisodicMemory"},
            ("access", "workspace"),
        ),
        "learning": (
            {
                "ActivityRecordRepository",
                "CandidateRepository",
                "SignalRepository",
                "CandidateReviewRepository",
                "CandidateProposalRepository",
            },
            set(),
            ("access", "workspace", "runtimes", "execution", "knowledge"),
        ),
        "exports": ({"VaultNoteRepository"}, {"VaultFs"}, ("access", "workspace", "planning", "execution")),
    }
    repositories, gateways, dependencies = expected[module]
    assert manifest.depends_on == dependencies
    assert {port.__name__ for port in manifest.repository_ports} == repositories
    assert {port.__name__ for port in manifest.gateway_ports} == gateways
    for port in manifest.repository_ports:
        assert port.__skm_port_kind__ == "repository"
    for port in manifest.gateway_ports:
        assert port.__skm_port_kind__ == "host_gateway"
    for path in (ROOT / "src/skm/modules" / module / "host").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                registered = [
                    spec for spec in manifest.host_operations if spec.run.__module__.endswith("." + path.stem)
                ]
                assert len(registered) == 1, path
                assert registered[0].run.__name__ == node.name
                assert [arg.arg for arg in node.args.args] == ["ctx", "request"], path
            if isinstance(node, ast.ImportFrom):
                assert not any(n.name == "UnitOfWork" or n.name.endswith("Repository") for n in node.names)


def test_checkout_fs_cas_and_gateway_contract() -> None:
    from skm.modules.integrations.ports import CheckoutFs

    tree = ast.parse((ROOT / "src/skm/modules/integrations/ports.py").read_text())
    port = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CheckoutFs")
    methods = {n.name: n for n in port.body if isinstance(n, ast.FunctionDef)}
    assert set(methods) == {"read", "stat", "write_atomic", "remove", "is_gitignored"}
    assert methods["write_atomic"].args.kwonlyargs[0].arg == "expected_whole_digest"
    assert methods["write_atomic"].args.kw_defaults == [None]
    assert methods["remove"].args.kwonlyargs[0].arg == "expected_whole_digest"
    assert vars(CheckoutFs)["__skm_port_kind__"] == "host_gateway"


def graph_answer() -> dict[str, Any]:
    return {
        "schema": "urn:skm:knowledge:graph-answer:v1",
        "query": {"op": "subgraph", "roots": ["project:example"]},
        "repository_id": None,
        "revision": None,
        "index_generation": None,
        "sources": [],
        "languages": [],
        "relation_kind": "none",
        "completeness": "unknown",
        "limitations": [],
        "freshness": {
            "state": "unknown",
            "indexed_at": None,
            "index_revision": None,
            "at_revision": None,
            "age_seconds": None,
        },
        "basis": None,
        "nodes": [],
        "edges": [],
        "path": None,
        "stats": None,
    }


def test_graph_answer_obeys_approved_owner_contract() -> None:
    from skm.modules.knowledge.public import GraphAnswer, GraphBasis

    check = validator("urn:skm:knowledge:graph-answer:v1")
    valid = graph_answer()
    check.validate(valid)
    for basis in GraphBasis:
        check.validate({**valid, "basis": basis.value})
    assert is_dataclass(GraphAnswer)
    assert {f.name for f in fields(GraphAnswer)} == set(valid) - {"schema"}
    for invalid in (
        {**valid, "query": {"op": "search"}},
        {**valid, "query": {"op": "path", "bogus": True}},
        {**valid, "basis": "manual"},
        {**valid, "index_generation": -1},
        {k: v for k, v in valid.items() if k != "repository_id"},
        {k: v for k, v in valid.items() if k != "basis"},
    ):
        with pytest.raises(ValidationError):
            check.validate(invalid)


def test_activity_identity_envelope_and_unknown_metrics() -> None:
    check = validator("urn:skm:learning:activity-summary:v1")
    valid = {
        "schema": "urn:skm:learning:activity-summary:v1",
        "source_kind": "attempt",
        "source_key": UUID,
        "outcome": "unknown",
        "observed_at": "2026-10-27T00:00:00Z",
    }
    check.validate(valid)
    check.validate({**valid, "tools_total": None, "reads_total": None, "task_outcome": None})
    for invalid in (
        {k: v for k, v in valid.items() if k != "schema"},
        {k: v for k, v in valid.items() if k != "outcome"},
        {**valid, "tools_total": -1},
        {**valid, "exposure_coverage": "trusted"},
    ):
        with pytest.raises(ValidationError):
            check.validate(invalid)
    record = validator("urn:skm:learning:command:record-activity:v1")
    with pytest.raises(ValidationError):
        record.validate({"project_id": UUID, "summary": valid})
    record.validate({"project_id": UUID, "summary": {**valid, "source_kind": "client_session"}})


def test_export_ack_and_requeue_require_current_generation_and_scope() -> None:
    ack = validator("urn:skm:exports:command:record-note-written:v1")
    valid = {
        "project_id": UUID,
        "note_id": UUID,
        "vault_id": UUID,
        "relative_path": "plans/example.md",
        "generation": 1,
        "outcome": "verified_existing",
        "expected_digest": DIGEST,
        "observed_digest": DIGEST,
    }
    ack.validate(valid)
    for invalid in (
        {**valid, "generation": 0},
        {**valid, "outcome": "written"},
        {**valid, "expected_digest": "invalid"},
        {k: v for k, v in valid.items() if k != "project_id"},
        {k: v for k, v in valid.items() if k != "observed_digest"},
    ):
        with pytest.raises(ValidationError):
            ack.validate(invalid)
    requeue = validator("urn:skm:exports:command:requeue-note:v1")
    requeue.validate({"project_id": UUID, "note_id": UUID, "expected_generation": 1})
    with pytest.raises(ValidationError):
        requeue.validate({"project_id": UUID, "note_id": UUID})


def test_human_review_edit_has_complete_text_fields() -> None:
    check = validator("urn:skm:learning:command:review-candidate:v1")
    valid = {"workspace_id": UUID, "candidate_id": UUID, "verdict": "comment", "expected_row_version": 1}
    check.validate(valid)
    with pytest.raises(ValidationError):
        check.validate({**valid, "verdict": "edit"})
    check.validate(
        {
            **valid,
            "verdict": "edit",
            "edited_trigger": "when",
            "edited_action": "verify",
            "edited_kind": "gotcha",
        }
    )


def test_host_command_output_cannot_grant_permission() -> None:
    check = validator("urn:skm:integrations:host-command-output:v1")
    valid = {"schema": "urn:skm:integrations:host-command-output:v1", "decision": "deny"}
    for decision in ("deny", "ask", "none"):
        check.validate({**valid, "decision": decision})
    with pytest.raises(ValidationError):
        check.validate({**valid, "decision": "allow"})
    with pytest.raises(ValidationError):
        check.validate({"decision": "deny"})


def test_first_turn_budget_request_and_report_have_distinct_contracts() -> None:
    request_urn = "urn:skm:integrations:host:first-turn-budget:v1"
    result_urn = "urn:skm:integrations:host-result:first-turn-budget:v1"
    request = {"project_id": UUID, "target": "codex", "include_plugins": False}
    report = {
        "schema": result_urn,
        "project_id": UUID,
        "target": "codex",
        "thresholds": {"target": 16000, "warn": 23000},
        "sources": [],
        "total": 0,
        "verdict": "ok",
    }
    request_validator = validator(request_urn)
    result_validator = validator(result_urn)
    request_validator.validate(request)
    request_validator.validate({**request, "mount": None})
    request_validator.validate({**request, "mount": "main"})
    result_validator.validate(report)
    for invalid in (
        report,
        {key: value for key, value in request.items() if key != "project_id"},
        {key: value for key, value in request.items() if key != "include_plugins"},
        {**request, "target": "unknown"},
    ):
        with pytest.raises(ValidationError):
            request_validator.validate(invalid)
    for invalid in (
        request,
        {**report, "schema": request_urn},
        {key: value for key, value in report.items() if key != "thresholds"},
    ):
        with pytest.raises(ValidationError):
            result_validator.validate(invalid)
    for urn, class_name in (
        (request_urn, "FirstTurnBudgetRequest"),
        (result_urn, "FirstTurnBudgetResult"),
    ):
        metadata = CURRENT[urn]["x-skm-codegen"]["python"]
        assert metadata["module"] == "skm.modules.integrations.generated.host"
        assert metadata["class"] == class_name


def test_canonical_schema_paths_and_codegen_assignments() -> None:
    directories = {
        "command": "commands",
        "result": "results",
        "query": "queries",
        "view": "views",
        "event": "events",
        "host": "host",
        "host-result": "host-results",
    }
    # The generator declares annotated roots. These roots describe handwritten wire types.
    handwritten = {
        "urn:skm:knowledge:query:graph-neighbors-http:v1",
        "urn:skm:knowledge:view:graph-indexes-result:v1",
        "urn:skm:knowledge:view:graph-indexes:v1",
    }
    assignments = {}
    for urn, schema in OWNED.items():
        parts = urn.split(":")
        tail = f"{parts[3]}.v1.json" if len(parts) == 5 else f"{directories[parts[3]]}/{parts[4]}.v1.json"
        assert (ROOT / "src/skm/schemas" / parts[2] / tail).exists()
        if urn in handwritten and "x-skm-codegen" not in schema:
            continue
        py = schema["x-skm-codegen"]["python"]
        key = (py["module"], py["class"])
        assert key not in assignments, (urn, assignments.get(key))
        assignments[key] = urn
