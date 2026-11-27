"""Context/execution contract inventory; these checks do not prove M3 behavior."""

# ruff: noqa: PT009, PT027

from __future__ import annotations

import ast
import importlib
import json
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from jsonschema.protocols import Validator
from referencing import Registry, Resource
from referencing.jsonschema import Schema

from contracts.execution._schema_assignments import codegen_collisions
from skm.application_bus.registry import SubscriberSpec
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import PORT_KIND_ATTRIBUTE
from skm.modules.context.domain.blocks import BLOCK_SPECS, BlockType
from skm.modules.context.ports import ContextOwnerClaim
from skm.modules.execution.ports import StageClient, StageDeps

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "src/skm/schemas"
MODULES = ROOT / "src/skm/modules"
GROUP = ("context", "execution")
UUID = "01900000-0000-7000-8000-000000000001"
DIGEST = "sha256:" + "a" * 64


def documents(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in root.rglob("*.json"):
        doc = cast(dict[str, Any], json.loads(path.read_text()))
        if "$id" in doc:
            result[str(doc["$id"])] = doc
    return result


CURRENT = documents(SCHEMAS)
EXAMPLES = documents(ROOT / "tests/fixtures/corpus/examples/schemas")
GROUP_SCHEMAS = {urn: doc for urn, doc in CURRENT.items() if urn.split(":")[2] in GROUP}
REGISTRY = Registry[Schema]().with_resources(
    (urn, Resource[Schema].from_contents(doc)) for urn, doc in CURRENT.items()
)


def validator_for(urn: str) -> Validator:
    return cast(
        Validator,
        Draft202012Validator(CURRENT[urn], registry=REGISTRY, format_checker=FormatChecker()),
    )


class GroupContractsTest(unittest.TestCase):
    def test_all_declarations_import_and_implemented_operations_are_registered(self) -> None:
        deps_exec = "access workspace artifacts extensions policy runtimes planning context"
        dependencies = {
            "context": ("access", "workspace", "planning", "extensions", "artifacts"),
            "execution": tuple(deps_exec.split()),
        }
        q_names = (
            "get_autopilot_status explain_autopilot get_run get_execution_detail get_review_receipt "
            "list_runs get_task get_task_live_control list_tasks list_task_attempts "
            "get_attempt get_step verify_stage_access get_fix_brief "
            "list_decision_requests get_readiness_report get_revision_visa get_review_roi get_run_budget "
            "get_run_timeline get_run_history get_run_health list_execution_environments"
        )
        commands = {
            "context": "assemble_context finalize_manifest record_research_result",
            "execution": (
                "start_autopilot pause_autopilot drain_autopilot stop_autopilot autopilot_tick "
                "acquire_integration_slot record_external_effect reconcile_external_effect "
                "release_integration_slot claim_assignment schedule_ready_tasks expire_leases "
                "enforce_timeouts detect_stalls renew_lease begin_stage seal_output record_stage_result "
                "release_assignment report_attempt_failure record_step_note validate_for_execution "
                "approve_revision start_run run_adhoc request_review pause_run resume_run cancel_run "
                "restart_task skip_task "
                "record_manual_verdict answer_decision_request accept_deviation reconfigure_run "
                "reroute_task override_actor steer_task abort_step "
                "carry_forward_result mark_environments_removed"
            ),
        }
        queries = {
            "execution": q_names,
            "context": (
                "explain_context diff_contexts get_context_text check_research_access find_research_cache "
                "get_research_query list_external_sources"
            ),
        }
        subscribers = {
            "context": "",
            "execution": (
                "intent_resolved_resume plan_archived_guard material_available escalate_blocking_hook_failure"
            ),
        }
        for module in GROUP:
            with self.subTest(module=module):
                for path in (MODULES / module).rglob("*.py"):
                    if "tests" not in path.parts:
                        mod_name = ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
                        importlib.import_module(mod_name)
                mod = importlib.import_module(f"skm.modules.{module}.module")
                manifest = cast(ModuleManifest, mod.MODULE)
                self.assertEqual(manifest.depends_on, dependencies[module])
                self.assertEqual(manifest.db_schema, "skm_" + module)
                self.assertFalse(manifest.optional)
                for name, expected in (("commands", commands), ("queries", queries)):
                    self.assertEqual(
                        tuple(op.name for op in getattr(manifest, name)),
                        tuple(f"{module}.{op}" for op in expected[module].split()),
                    )
                self.assertEqual(
                    tuple(cast(SubscriberSpec, s).consumer_id for s in manifest.subscribers),
                    tuple(f"{module}.{s}" for s in subscribers[module].split()),
                )
                self.assertEqual(
                    tuple(op.name for op in manifest.host_operations),
                    (
                        "execution.host.request_review",
                        "execution.host.local_ask",
                        "execution.host.local_do",
                        "execution.host.local_deliberate",
                    )
                    if module == "execution"
                    else (
                        "context.host.research_query",
                        "context.host.codegraph",
                        "context.host.pack_context",
                    ),
                )
                for port in manifest.repository_ports:
                    self.assertEqual(getattr(port, PORT_KIND_ATTRIBUTE), "repository")
                for port in manifest.gateway_ports:
                    self.assertIn(
                        getattr(port, PORT_KIND_ATTRIBUTE), {"control_plane_gateway", "host_gateway"}
                    )
                inventory = importlib.import_module(f"skm.modules.{module}.domain.events").EVENT_TYPES
                self.assertEqual(
                    set(inventory), {u for u in GROUP_SCHEMAS if u.startswith(f"urn:skm:{module}:event:")}
                )
                self.assertEqual(
                    {event.event_type for event in manifest.events},
                    set() if module == "context" else set(inventory),
                )

    def test_schema_syntax_and_all_reference_fragments(self) -> None:
        self.assertGreater(len(GROUP_SCHEMAS), 100)
        for urn, document in GROUP_SCHEMAS.items():
            with self.subTest(urn=urn):
                Draft202012Validator.check_schema(document)
                self._check_references(document, urn)

    def _check_references(self, value: Any, base: str) -> None:
        if isinstance(value, dict):
            node = cast(dict[str, Any], value)
            if "$ref" in node:
                target_urn, _, fragment = str(node["$ref"]).partition("#")
                target_urn = target_urn or base
                # Future targets must be known normative URNs/fragments, never retrieved over the network.
                self.assertIn(target_urn, CURRENT | EXAMPLES)
                resolved: Any = (EXAMPLES | CURRENT)[target_urn]
                for key in fragment.split("/")[1:]:
                    resolved = resolved[key.replace("~1", "/").replace("~0", "~")]
                self.assertIsInstance(resolved, (dict, bool))
                # This group currently has no deferred targets.
                self.assertIn(target_urn, CURRENT)
            for child in node.values():
                self._check_references(child, base)
        elif isinstance(value, list):
            for child in cast(list[Any], value):
                self._check_references(child, base)

    def test_stage_dependencies_and_client_have_only_the_narrow_surface(self) -> None:
        deps = (
            "worker environment runtimes check_runners isolation vcs uploader config "
            "clock monotonic log cancel"
        )
        client = "report_progress seal_output record_effect acquire_integration_slot release_integration_slot"
        self.assertTrue(is_dataclass(StageDeps))
        self.assertEqual(
            {field.name for field in fields(StageDeps)},
            set(deps.split()),
        )
        self.assertEqual(
            {
                name
                for name, value in vars(StageClient).items()
                if callable(value) and not name.startswith("_")
            },
            set(client.split()),
        )
        self.assertEqual(
            {field.name for field in fields(ContextOwnerClaim)},
            {"assignment_id", "attempt_id", "worker_id", "fencing_token"},
        )
        self.assertEqual(set(BLOCK_SPECS), set(BlockType))

    def test_host_declarations_do_not_import_uow_or_repositories(self) -> None:
        for module in GROUP:
            for path in (MODULES / module / "host").rglob("*.py"):
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        self.assertFalse(
                            any(a.name == "UnitOfWork" or a.name.endswith("Repository") for a in node.names),
                            str(path),
                        )
                        if "stages" in path.parts:
                            self.assertFalse(
                                any(a.name in {"HostContext", "SkmClient"} for a in node.names), str(path)
                            )
                            self.assertNotIn("application", (node.module or "").split("."), str(path))
                    if isinstance(node, ast.Attribute) and "stages" in path.parts:
                        self.assertNotEqual(node.attr, "client", str(path))
                    if isinstance(node, ast.ClassDef) and "stages" in path.parts:
                        for member in node.body:
                            if isinstance(member, ast.FunctionDef) and member.name == "run":
                                self.assertEqual(
                                    [a.arg for a in member.args.args], ["self", "request", "deps"], str(path)
                                )

    def test_researcher_uses_document_ids_and_follow_up_queries(self) -> None:
        validator = validator_for("urn:skm:execution:role-result:researcher:v1")
        valid: dict[str, Any] = {
            "schema": "urn:skm:execution:role-result:researcher:v1",
            "status": "complete",
            "query": "Research the task",
            "claims": [{"text": "A fact", "document_ids": [UUID]}],
            "contradictions": [],
            "unknowns": [],
            "sources_used": ["local-docs"],
            "follow_up_queries": [],
        }
        for status in ("complete", "partial", "blocked"):
            with self.subTest(status=status):
                validator.validate({**valid, "status": status})
        invalids: list[dict[str, Any]] = [
            {**valid, "claims": [{"text": "A fact", "source_ids": ["S1"]}]},
            {**valid, "claims": [{"text": "A fact", "document_ids": []}]},
            {key: value for key, value in valid.items() if key != "follow_up_queries"},
            {key: value for key, value in valid.items() if key != "status"},
            {**valid, "status": "unknown"},
        ]
        for invalid in invalids:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validator.validate(invalid)

    def test_begin_stage_requires_a_complete_claim_and_digest(self) -> None:
        validator = validator_for("urn:skm:execution:command:begin-stage:v1")
        claim = {"assignment_id": UUID, "attempt_id": UUID, "worker_id": UUID, "fencing_token": 1}
        valid: dict[str, Any] = {"claim": claim, "stage_id": "execute", "round_no": 1, "input_digest": DIGEST}
        validator.validate(valid)
        for invalid in (
            {**valid, "claim": {**claim, "fencing_token": 0}},
            {**valid, "input_digest": "wrong"},
            {**valid, "claim": {key: value for key, value in claim.items() if key != "assignment_id"}},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validator.validate(invalid)

    def test_finalize_manifest_validates_an_execution_claim_when_supplied(self) -> None:
        schema = CURRENT["urn:skm:context:command:finalize-manifest:v1"]
        claim_validator = cast(Validator, Draft202012Validator(schema["properties"]["claim"]))
        claim = {"assignment_id": UUID, "attempt_id": UUID, "worker_id": UUID, "fencing_token": 1}
        claim_validator.validate(claim)
        with self.assertRaises(ValidationError):
            claim_validator.validate({**claim, "fencing_token": 0})
        with self.assertRaises(ValidationError):
            claim_validator.validate({key: value for key, value in claim.items() if key != "worker_id"})
        self.assertEqual(schema["x-skm"]["idempotency"], "FORBIDDEN")

    def test_complete_repository_and_gateway_inventory(self) -> None:
        context_gateways = (
            "ContextOwnerGuard MemoryRetriever CheckoutReader CodeGraphIndex "
            "ResearchSource ResearchSourceRegistry"
        )
        repo_names = (
            "Run Bundle Readiness Task Attempt Stage Step Assignment Environment "
            "Output Check Review Acceptance Budget Decision Effect IntegrationSlot "
            "ReviewRequest Autopilot Recovery EvidenceBinding"
        )
        expected = {
            "context": {
                "repositories": {"ContextRepository", "TextStore", "ResearchRepository"},
                "gateways": set(context_gateways.split()),
            },
            "execution": {
                "repositories": {f"{n}Repository" for n in repo_names.split()} | {"ExecutionQueries"},
                "gateways": {
                    "ExecutionEnvironmentManager",
                    "Vcs",
                    "CheckRunner",
                    "CheckRunnerRegistry",
                    "IsolationRegistry",
                    "Isolation",
                    "ReviewCheckoutPathResolver",
                    "UserSchemaValidator",
                    "GateCommandRunner",
                    "LocalRuntimePool",
                },
            },
        }
        for module, inventory in expected.items():
            manifest = cast(ModuleManifest, importlib.import_module(f"skm.modules.{module}.module").MODULE)
            self.assertEqual({port.__name__ for port in manifest.repository_ports}, inventory["repositories"])
            self.assertEqual({port.__name__ for port in manifest.gateway_ports}, inventory["gateways"])

    def test_readiness_query_requires_exactly_one_selector(self) -> None:
        validator = cast(
            Validator,
            Draft202012Validator(
                CURRENT["urn:skm:execution:query:get-readiness-report:v1"], registry=REGISTRY
            ),
        )
        validator.validate({"report_id": UUID})
        validator.validate({"revision_id": UUID})
        for invalid in ({}, {"report_id": UUID, "revision_id": UUID}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validator.validate(invalid)

    def test_schema_ids_match_canonical_paths(self) -> None:
        directories = {
            "command": "commands",
            "result": "results",
            "query": "queries",
            "view": "views",
            "event": "events",
            "host": "host",
            "host-result": "host-results",
        }
        for urn in GROUP_SCHEMAS:
            parts = urn.split(":")
            module = parts[2]
            if len(parts) == 5:
                path = SCHEMAS / module / (parts[3] + ".v1.json")
            elif parts[3] == "role-result":
                path = SCHEMAS / module / ("role-result-" + parts[4] + ".v1.json")
            else:
                self.assertIn(parts[3], directories)
                path = SCHEMAS / module / directories[parts[3]] / (parts[4] + ".v1.json")
            self.assertEqual(json.loads(path.read_text())["$id"], urn)

    def test_seal_output_supports_range_without_an_agent_step(self) -> None:
        manifest: dict[str, Any] = {
            "algorithm": "skm-output-v2",
            "mounts": [
                {
                    "mount": "main",
                    "repository_id": UUID,
                    "object_format": "sha1",
                    "base_commit": "a" * 40,
                    "head_commit": "b" * 40,
                    "tree_sha": "c" * 40,
                }
            ],
            "changed_paths": [],
            "outside_write_scope": [],
            "excluded_paths": [],
            "tree_digest": DIGEST,
            "diff_stats": {"files": 0, "insertions": 0, "deletions": 0},
            "empty": True,
        }
        validator = validator_for("urn:skm:execution:command:seal-output:v1")
        base: dict[str, Any] = {
            "claim": {"assignment_id": UUID, "attempt_id": UUID, "worker_id": UUID, "fencing_token": 1},
            "stage_record_id": UUID,
            "manifest": manifest,
        }
        validator.validate({**base, "source": "range"})
        validator.validate({**base, "source": "executor", "step_id": UUID})
        for invalid in (
            {**base, "source": "executor"},
            {**base, "source": "unknown", "step_id": UUID},
            {**base, "step_id": UUID},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validator.validate(invalid)

    def test_renew_lease_represents_committed_handoff_refusal(self) -> None:
        validator = validator_for("urn:skm:execution:result:renew-lease:v1")
        normal: dict[str, Any] = {
            "lease_expires_at": "2026-10-27T00:00:00Z",
            "cancel_requested": False,
            "snapshot_requested": False,
        }
        refusal: dict[str, Any] = {
            **normal,
            "cancel_requested": True,
            "refusal": {"code": "BUDGET_EXHAUSTED", "details": {}},
            "next": {"kind": "release", "release_reason": "waiting"},
        }
        validator.validate(normal)
        validator.validate(refusal)
        invalids: tuple[dict[str, Any], ...] = (
            {**refusal, "refusal": "BUDGET_EXHAUSTED"},
            {**refusal, "refusal": {"details": {}}},
            {**refusal, "refusal": {"code": "BUDGET_EXHAUSTED"}},
            {**refusal, "refusal": {"code": 1, "details": {}}},
            {**refusal, "refusal": {"code": "BUDGET_EXHAUSTED", "details": []}},
            {**refusal, "refusal": {"code": "BUDGET_EXHAUSTED", "details": {}, "extra": True}},
            {**refusal, "next": {}},
            {**refusal, "next": {"kind": "unknown"}},
            {**refusal, "next": {"kind": "release", "release_reason": "unknown"}},
            {**refusal, "next": "release"},
        )
        for invalid in invalids:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validator.validate(invalid)

    def test_codegen_assignments_do_not_conflict(self) -> None:
        self.assertEqual(codegen_collisions(GROUP_SCHEMAS), [])

    def test_codegen_collision_diagnostic_rejects_different_forms(self) -> None:
        metadata = {
            "python": {"module": "test.generated", "class": "Shared"},
            "typescript": {"file": "test.ts", "name": "Shared"},
        }
        first: dict[str, Any] = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "x-skm-codegen": metadata,
        }
        second: dict[str, Any] = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "x-skm-codegen": metadata,
        }
        self.assertEqual(len(codegen_collisions({"first": first, "second": second})), 2)
        self.assertEqual(
            codegen_collisions({"first": first, "alias": {"$ref": "first", "x-skm-codegen": metadata}}), []
        )

    def test_research_locators_are_scalars_through_the_context_request(self) -> None:
        document: dict[str, Any] = {
            "document_id": UUID,
            "origin": "repo:main/README.md",
            "url": None,
            "title": "README",
            "retrieved_at": "2026-10-27T00:00:00Z",
            "content_digest": DIGEST,
            "locator": {},
            "excerpt": "A fact",
            "trust_class": "repository",
            "classification": "internal",
            "staged_blob": None,
        }
        item: dict[str, Any] = {
            "step_ref": "step:" + UUID,
            "query": "Research the task",
            "claims": [{"text": "A fact", "document_ids": [UUID]}],
            "unknowns": [],
            "contradictions": [],
            "documents": [],
        }
        request: dict[str, Any] = {
            "workspace_id": UUID,
            "project_id": UUID,
            "plan_id": UUID,
            "revision_id": UUID,
            "entity_id": UUID,
            "project_slug": "example",
            "purpose": {
                "role": "executor",
                "stage_id": "execute",
                "step_ref": "step:" + UUID,
                "attempt_no": 1,
                "round_no": 1,
            },
            "agent_profile_version_id": UUID,
            "runtime": {
                "runtime_id": "fake",
                "model": "fake-model",
                "context_window_tokens": 100000,
                "capabilities": [],
                "tools": [],
                "notes": [],
                "route_source": "role_routing",
                "operation": "new_implementation",
                "config_mode": "isolated",
                "self_loads": [],
                "degraded": [],
                "self_loaded_instruction_files": [],
            },
            "permissions": {
                "write_scope": [],
                "read_scope": [],
                "commands_allowed": [],
                "commands_denied": [],
                "network": "none",
                "network_allow": [],
                "external_effects": [],
            },
            "run": {
                "run_id": UUID,
                "workflow_key": "default",
                "attempt_no": 1,
                "round_no": 1,
                "integration_branch": None,
                "commit_policy": "final_only",
                "progress_format": "plain",
                "output_language": "en",
                "rules_extra": [],
            },
            "execution_blocks": {
                "work_policy": {},
                "decision_answers": [],
                "review_feedback": None,
                "previous_attempt": None,
                "candidate": None,
                "findings_under_review": [],
                "context_map": None,
                "research": [],
                "history": [],
            },
            "resume": None,
            "task_risk": "low",
            "research_queries": [],
            "pack_pins": None,
        }
        locator_schema = CURRENT["urn:skm:context:defs:v1"]["$defs"]["ResearchDocument"]["properties"][
            "locator"
        ]
        locator_validator = cast(Validator, Draft202012Validator(locator_schema))
        validator = validator_for("urn:skm:context:assemble-request:v1")
        for locator in (
            {"line_from": 1, "line_to": 10},
            {"fragment": "overview"},
            {"page": 2},
            {"offset": 1.5, "available": True, "unknown": None},
        ):
            with self.subTest(locator=locator):
                locator_validator.validate(locator)
                request["execution_blocks"]["research"] = [
                    {**item, "documents": [{**document, "locator": locator}]}
                ]
                validator.validate(request)
        invalid_locators: tuple[dict[str, Any], ...] = ({"page": {}}, {"lines": [1, 10]})
        for locator in invalid_locators:
            with self.subTest(locator=locator), self.assertRaises(ValidationError):
                locator_validator.validate(locator)
            request["execution_blocks"]["research"] = [
                {**item, "documents": [{**document, "locator": locator}]}
            ]
            with self.subTest(nested=locator), self.assertRaises(ValidationError):
                validator.validate(request)

    def test_event_workflow_stage_keys_are_strings_and_record_ids_remain_uuids(self) -> None:
        for event, field, valid in (
            ("stage-started", "stage_id", "execute"),
            ("stage-completed", "stage_id", "execute"),
            ("attempt-ownership-lost", "stage_id", "execute"),
            ("stage-started", "skipped_stage_ids", ["checks"]),
        ):
            with self.subTest(event=event, field=field):
                schema = CURRENT[f"urn:skm:execution:event:{event}:v1"]
                validator = cast(
                    Validator,
                    Draft202012Validator(
                        schema["properties"][field], registry=REGISTRY, format_checker=FormatChecker()
                    ),
                )
                validator.validate(valid)
                invalid = [1] if field == "skipped_stage_ids" else 1
                with self.assertRaises(ValidationError):
                    validator.validate(invalid)
                if event == "attempt-ownership-lost":
                    validator.validate(None)
                    self.assertNotIn("stage_id", schema["required"])
                else:
                    record_validator = cast(
                        Validator,
                        Draft202012Validator(
                            schema["properties"]["stage_record_id"],
                            registry=REGISTRY,
                            format_checker=FormatChecker(),
                        ),
                    )
                    record_validator.validate(UUID)
                    with self.assertRaises(ValidationError):
                        record_validator.validate("execute")
