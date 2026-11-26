"""Complete bus → HTTP ownership ledger; deferred leaves add declarations, never stubs."""

import json
import re
from pathlib import Path
from typing import Any, cast

from skm.bootstrap.modules import MANIFESTS
from skm.bootstrap.platform_module import PLATFORM_MANIFEST
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.cli.parser import build_parser
from skm.entrypoints.mcp.registry import TOOLS
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[2]

# operation: (owner leaf, canonical method/path aliases from API §3).
SURFACES = {
    "access.create_principal": ("P11.02.b", (("POST", "/api/v1/principals"),)),
    "access.create_token": ("P11.02.b", (("POST", "/api/v1/tokens"),)),
    "access.disable_principal": ("P11.02.b", (("POST", "/api/v1/principals/{principal_id}/disable"),)),
    "access.get_principal": ("P11.02.b", (("GET", "/api/v1/principals/{principal_id}"),)),
    "access.grant_membership": ("P11.02.b", (("POST", "/api/v1/memberships"),)),
    "access.list_memberships": ("P11.02.b", (("GET", "/api/v1/memberships"),)),
    "access.list_principals": ("P11.02.b", (("GET", "/api/v1/principals"),)),
    "access.list_tokens": ("P11.02.b", (("GET", "/api/v1/tokens"),)),
    "access.revoke_membership": ("P11.02.b", (("DELETE", "/api/v1/memberships/{scope_id}/{principal_id}"),)),
    "access.revoke_token": ("P11.02.b", (("POST", "/api/v1/tokens/{token_id}/revoke"),)),
    "access.rotate_token": ("P11.02.b", (("POST", "/api/v1/tokens/{token_id}/rotate"),)),
    "access.whoami": ("P11.02.b", (("GET", "/api/v1/me"),)),
    "artifacts.add_file": (
        "P11.02.b",
        (
            ("POST", "/api/v1/projects/{project_id}/files"),
            ("POST", "/api/v1/workspaces/{workspace_id}/files"),
        ),
    ),
    "artifacts.add_file_version": ("P11.02.b", (("POST", "/api/v1/files/{file_id}/versions"),)),
    "artifacts.find_orphan_blobs": ("P15", (("GET", "/api/v1/admin/orphan-blobs"),)),
    "artifacts.get_file": ("P11.02.b", (("GET", "/api/v1/files/{file_id}"),)),
    "artifacts.get_file_version": ("P11.02.b", (("GET", "/api/v1/file-versions/{file_version_id}"),)),
    "artifacts.list_file_versions": ("P11.02.b", (("GET", "/api/v1/files/{file_id}/versions"),)),
    "artifacts.list_files": ("P11.02.b", (("GET", "/api/v1/files"),)),
    "artifacts.open_file_version_content": (
        "P11.02.b",
        (("GET", "/api/v1/file-versions/{file_version_id}/content"),),
    ),
    "artifacts.prune_orphan_objects": ("P15", (("POST", "/api/v1/admin/orphan-blobs/prune"),)),
    "artifacts.record_staged_blob": ("P11.02.b", (("POST", "/api/v1/workspaces/{workspace_id}/blobs"),)),
    "artifacts.restore_file": ("P11.02.b", (("POST", "/api/v1/files/{file_id}/restore"),)),
    "artifacts.trash_file": ("P11.02.b", (("POST", "/api/v1/files/{file_id}/trash"),)),
    "context.assemble_context": ("I-08.2", (("POST", "/api/v1/projects/{project_id}/context-manifests"),)),
    "context.diff_contexts": (
        "P11.02.e",
        (
            ("GET", "/api/v1/projects/{project_id}/steps/{step_id}/context/diff"),
            ("GET", "/api/v1/projects/{project_id}/context-manifests/{target_manifest_id}/diff"),
        ),
    ),
    "context.explain_context": (
        "P11.02.e",
        (
            ("GET", "/api/v1/steps/{step_id}/context"),
            ("GET", "/api/v1/projects/{project_id}/context-manifests/{manifest_id}"),
        ),
    ),
    "context.finalize_manifest": (
        "P11.02.e",
        (("POST", "/api/v1/context-manifests/{manifest_id}/finalize"),),
    ),
    "context.check_research_access": ("I-11.2", (("GET", "/api/v1/projects/{project_id}/research-access"),)),
    "context.find_research_cache": ("P11.02.e", (("GET", "/api/v1/projects/{project_id}/research-queries"),)),
    "context.get_context_text": (
        "P11.02.e",
        (("GET", "/api/v1/projects/{project_id}/context-manifests/{manifest_id}/text"),),
    ),
    "context.get_research_query": (
        "P11.02.e",
        (("GET", "/api/v1/projects/{project_id}/research-queries/{query_id}"),),
    ),
    "context.list_external_sources": (
        "P11.02.e",
        (("GET", "/api/v1/projects/{project_id}/external-sources"),),
    ),
    "context.record_research_result": (
        "P11.02.e",
        (("POST", "/api/v1/projects/{project_id}/research-queries"),),
    ),
    "execution.accept_deviation": ("P11.02.e", (("POST", "/api/v1/deviations"),)),
    "execution.acquire_integration_slot": ("P11.02.c", (("POST", "/api/v1/worker/integration-slots"),)),
    "execution.answer_decision_request": (
        "P11.02.e",
        (("POST", "/api/v1/decision-requests/{request_id}/answer"),),
    ),
    "execution.begin_stage": ("P11.02.c", (("POST", "/api/v1/worker/assignments/{assignment_id}/stages"),)),
    "execution.cancel_run": ("P11.02.e", (("POST", "/api/v1/runs/{run_id}/cancel"),)),
    "execution.carry_forward_result": ("P11.02.e", (("POST", "/api/v1/tasks/{task_id}/carry-forward"),)),
    "execution.claim_assignment": ("P11.02.c", (("POST", "/api/v1/worker/assignments/claim"),)),
    "execution.drain_autopilot": ("P11.02.e", (("POST", "/api/v1/projects/{project_id}/autopilot/drain"),)),
    "execution.explain_autopilot": (
        "P11.02.e",
        (("GET", "/api/v1/projects/{project_id}/autopilot/explain"),),
    ),
    "execution.get_attempt": ("P11.02.e", (("GET", "/api/v1/attempts/{attempt_id}"),)),
    "execution.get_autopilot_status": ("P11.02.e", (("GET", "/api/v1/projects/{project_id}/autopilot"),)),
    "execution.get_fix_brief": ("P11.02.e", (("GET", "/api/v1/fix-briefs/{fix_brief_id}"),)),
    "execution.get_readiness_report": ("P11.02.e", (("GET", "/api/v1/readiness-reports/{report_id}"),)),
    "execution.get_revision_visa": (
        "I-11.4",
        (("GET", "/api/v1/plans/{plan_id}/revisions/{revision_id}/visa"),),
    ),
    "execution.get_review_receipt": ("P11.02.e", (("GET", "/api/v1/runs/{run_id}/review-receipt"),)),
    "execution.get_review_roi": ("I-12.3", (("GET", "/api/v1/runs/{run_id}/analytics/review-roi"),)),
    "execution.get_run": ("P11.02.e", (("GET", "/api/v1/runs/{run_id}"),)),
    "execution.get_execution_detail": ("P12.05.a", (("GET", "/api/v1/execution/detail"),)),
    "execution.get_run_budget": ("P11.02.e", (("GET", "/api/v1/runs/{run_id}/budget"),)),
    "execution.get_run_health": ("P11.02.e", (("GET", "/api/v1/runs/{run_id}/health"),)),
    "execution.get_run_history": ("P11.02.e", (("GET", "/api/v1/runs/{run_id}/history"),)),
    "execution.get_run_timeline": ("P11.02.e", (("GET", "/api/v1/runs/{run_id}/timeline"),)),
    "execution.get_step": ("P11.02.e", (("GET", "/api/v1/steps/{step_id}"),)),
    "execution.verify_stage_access": (
        "P11.04.b",
        (("GET", "/api/v1/worker/stages/{stage_record_id}/access"),),
    ),
    "execution.get_task": ("P11.02.e", (("GET", "/api/v1/tasks/{task_id}"),)),
    "execution.list_decision_requests": ("P11.02.e", (("GET", "/api/v1/inbox"),)),
    "execution.list_execution_environments": (
        "P11.02.e",
        (("GET", "/api/v1/hosts/{host_id}/execution-environments"),),
    ),
    "execution.list_runs": ("P11.02.e", (("GET", "/api/v1/projects/{project_id}/runs"),)),
    "execution.list_task_attempts": ("P11.02.e", (("GET", "/api/v1/tasks/{task_id}/attempts"),)),
    "execution.list_tasks": ("P11.02.e", (("GET", "/api/v1/runs/{run_id}/tasks"),)),
    "execution.mark_environments_removed": (
        "P11.02.e",
        (("POST", "/api/v1/hosts/{host_id}/execution-environments/removed"),),
    ),
    "execution.pause_autopilot": ("P11.02.e", (("POST", "/api/v1/projects/{project_id}/autopilot/pause"),)),
    "execution.pause_run": ("P11.02.e", (("POST", "/api/v1/runs/{run_id}/pause"),)),
    "execution.reconcile_external_effect": (
        "P11.02.e",
        (("POST", "/api/v1/admin/external-effects/{effect_id}/reconcile"),),
    ),
    "execution.abort_step": ("I-12.2", (("POST", "/api/v1/runs/{run_id}/tasks/{task_id}/abort-step"),)),
    "execution.override_actor": (
        "I-12.2",
        (("POST", "/api/v1/runs/{run_id}/tasks/{task_id}/override-actor"),),
    ),
    "execution.reroute_task": ("I-12.2", (("POST", "/api/v1/runs/{run_id}/tasks/{task_id}/reroute"),)),
    "execution.steer_task": ("I-12.2", (("POST", "/api/v1/runs/{run_id}/tasks/{task_id}/steer"),)),
    "execution.get_task_live_control": (
        "I-12.2",
        (("GET", "/api/v1/runs/{run_id}/tasks/{task_id}/live-control"),),
    ),
    "execution.reconfigure_run": ("P11.02.e", (("POST", "/api/v1/runs/{run_id}/reconfigure"),)),
    "execution.record_external_effect": (
        "P11.02.c",
        (("POST", "/api/v1/worker/assignments/{assignment_id}/external-effects"),),
    ),
    "execution.record_manual_verdict": (
        "P11.02.e",
        (("POST", "/api/v1/check-executions/{check_execution_id}/verdict"),),
    ),
    "execution.record_stage_result": (
        "P11.02.c",
        (("POST", "/api/v1/worker/assignments/{assignment_id}/stages/{stage_record_id}/result"),),
    ),
    "execution.record_step_note": ("P11.02.c", (("POST", "/api/v1/runs/{run_id}/steps/{step_id}/notes"),)),
    "execution.release_assignment": (
        "P11.02.c",
        (("POST", "/api/v1/worker/assignments/{assignment_id}/release"),),
    ),
    "execution.release_integration_slot": (
        "P11.02.c",
        (("DELETE", "/api/v1/worker/integration-slots/{slot_id}"),),
    ),
    "execution.renew_lease": (
        "P11.02.c",
        (("POST", "/api/v1/worker/assignments/{assignment_id}/heartbeat"),),
    ),
    "execution.report_attempt_failure": (
        "P11.02.c",
        (("POST", "/api/v1/worker/assignments/{assignment_id}/failure"),),
    ),
    "execution.request_review": ("P11.02.e", (("POST", "/api/v1/projects/{project_id}/review-requests"),)),
    "execution.restart_task": ("P11.02.e", (("POST", "/api/v1/tasks/{task_id}/restart"),)),
    "execution.resume_run": ("P11.02.e", (("POST", "/api/v1/runs/{run_id}/resume"),)),
    "execution.run_adhoc": ("I-08.2", (("POST", "/api/v1/projects/{project_id}/runs/adhoc"),)),
    "execution.seal_output": ("P11.02.c", (("POST", "/api/v1/worker/assignments/{assignment_id}/outputs"),)),
    "execution.skip_task": ("P11.02.e", (("POST", "/api/v1/tasks/{task_id}/skip"),)),
    "execution.start_autopilot": ("P11.02.e", (("POST", "/api/v1/projects/{project_id}/autopilot/start"),)),
    "execution.approve_revision": ("I-11.1", (("POST", "/api/v1/plans/{plan_id}/revision-visas"),)),
    "execution.start_run": ("P11.02.e", (("POST", "/api/v1/plans/{plan_id}/runs"),)),
    "execution.stop_autopilot": ("P11.02.e", (("POST", "/api/v1/projects/{project_id}/autopilot/stop"),)),
    "execution.validate_for_execution": (
        "P11.02.e",
        (("POST", "/api/v1/plans/{plan_id}/revisions/{revision_id}/readiness"),),
    ),
    "exports.list_pending_notes": (
        "P13",
        (("GET", "/api/v1/workspaces/{workspace_id}/vault-notes/pending"),),
    ),
    "exports.list_vault_notes": ("P13", (("GET", "/api/v1/projects/{project_id}/vault-notes"),)),
    "exports.record_note_written": (
        "P13",
        (("POST", "/api/v1/projects/{project_id}/vault-notes/{note_id}/writes"),),
    ),
    "exports.render_plan_markdown": ("P13", (("GET", "/api/v1/plans/{plan_id}/export.md"),)),
    "exports.render_run_report": ("P13", (("GET", "/api/v1/runs/{run_id}/report.md"),)),
    "exports.requeue_note": (
        "P13",
        (("POST", "/api/v1/projects/{project_id}/vault-notes/{note_id}/requeue"),),
    ),
    "extensions.get_pack": ("P11.02.f", (("GET", "/api/v1/extensions/packs/{pack_id}"),)),
    "extensions.get_resource_version": (
        "P11.02.f",
        (("GET", "/api/v1/extensions/resource-versions/{resource_version_id}"),),
    ),
    "extensions.install_pack": ("P11.02.f", (("POST", "/api/v1/extensions/packs"),)),
    "extensions.list_packs": ("P11.02.f", (("GET", "/api/v1/extensions/packs"),)),
    "extensions.list_resources": ("P11.02.f", (("GET", "/api/v1/extensions/resources"),)),
    "extensions.quarantine_resource": (
        "P11.02.f",
        (("POST", "/api/v1/extensions/resource-versions/{resource_version_id}/quarantine"),),
    ),
    "extensions.release_quarantine": (
        "P11.02.f",
        (("POST", "/api/v1/extensions/resource-versions/{resource_version_id}/release"),),
    ),
    "extensions.resolve_resource": ("P11.02.f", (("GET", "/api/v1/extensions/resolve"),)),
    "extensions.sync_builtin_packs": ("P11.02.f", (("POST", "/api/v1/extensions/packs/sync-builtin"),)),
    "extensions.uninstall_pack_version": (
        "P11.02.f",
        (("DELETE", "/api/v1/extensions/pack-versions/{pack_version_id}"),),
    ),
    "integrations.get_applied_state": (
        "P11.02.f",
        (("GET", "/api/v1/projects/{project_id}/projections/applied"),),
    ),
    "integrations.get_desired_projection": (
        "P11.02.f",
        (("GET", "/api/v1/projects/{project_id}/integrations/desired-projection"),),
    ),
    "integrations.get_hook_policy": (
        "P11.02.f",
        (("GET", "/api/v1/projects/{project_id}/integrations/hook-policy"),),
    ),
    "integrations.list_hook_deliveries": (
        "P11.02.f",
        (("GET", "/api/v1/workspaces/{workspace_id}/hook-deliveries"),),
    ),
    "integrations.list_hook_subscriptions": (
        "P11.02.f",
        (("GET", "/api/v1/workspaces/{workspace_id}/hook-subscriptions"),),
    ),
    "integrations.list_projections": ("P11.02.f", (("GET", "/api/v1/projects/{project_id}/projections"),)),
    "integrations.record_drift": ("P11.02.f", (("POST", "/api/v1/projects/{project_id}/projections/drift"),)),
    "integrations.record_projection_applied": (
        "P11.02.f",
        (
            ("POST", "/api/v1/projects/{project_id}/projections/applied"),
            ("POST", "/api/v1/projects/{project_id}/projections"),
        ),
    ),
    "integrations.remove_projection": (
        "P11.02.f",
        (("POST", "/api/v1/projects/{project_id}/projections/{projection_id}/removal"),),
    ),
    "integrations.retry_hook_deliveries": (
        "P11.02.f",
        (("POST", "/api/v1/workspaces/{workspace_id}/hook-deliveries/retry"),),
    ),
    "integrations.test_hook_subscription": (
        "P11.02.f",
        (("POST", "/api/v1/workspaces/{workspace_id}/hook-subscriptions/{subscription_id}/test"),),
    ),
    "knowledge.deprecate_lesson": (
        "P13.01.c",
        (("POST", "/api/v1/workspaces/{workspace_id}/lessons/{lesson_id}/deprecate"),),
    ),
    "knowledge.forget": ("P13.01.c", (("POST", "/api/v1/projects/{project_id}/memory/{entry_id}/forget"),)),
    "knowledge.get_lesson": ("P13.01.c", (("GET", "/api/v1/workspaces/{workspace_id}/lessons/{lesson_id}"),)),
    "knowledge.graph_neighbors": (
        "P13.02.b",
        (("GET", "/api/v1/workspaces/{workspace_id}/graph/neighbors"),),
    ),
    "knowledge.graph_path": ("P13.02.b", (("GET", "/api/v1/workspaces/{workspace_id}/graph/path"),)),
    "knowledge.graph_stats": ("P13.02.b", (("GET", "/api/v1/workspaces/{workspace_id}/graph/stats"),)),
    "knowledge.graph_subgraph": ("P13", (("GET", "/api/v1/workspaces/{workspace_id}/graph/subgraph"),)),
    "knowledge.import_graph": ("P13.02.b", (("POST", "/api/v1/workspaces/{workspace_id}/graph/import"),)),
    "knowledge.list_graph_indexes": ("P13", (("GET", "/api/v1/workspaces/{workspace_id}/graph/indexes"),)),
    "knowledge.list_lessons": ("P13.01.c", (("GET", "/api/v1/workspaces/{workspace_id}/lessons"),)),
    "knowledge.list_memory": ("P13.01.c", (("GET", "/api/v1/projects/{project_id}/memory/entries"),)),
    "knowledge.remember": ("P13.01.c", (("POST", "/api/v1/projects/{project_id}/memory"),)),
    "knowledge.search_memory": ("P13.01.c", (("GET", "/api/v1/projects/{project_id}/memory"),)),
    "learning.get_candidate": (
        "P13.03.c",
        (("GET", "/api/v1/workspaces/{workspace_id}/lesson-candidates/{candidate_id}"),),
    ),
    "learning.list_candidates": (
        "P13.03.c",
        (("GET", "/api/v1/workspaces/{workspace_id}/lesson-candidates"),),
    ),
    "learning.list_signals": (
        "P13.03.c",
        (("GET", "/api/v1/workspaces/{workspace_id}/lesson-candidates/{candidate_id}/signals"),),
    ),
    "learning.pathology_stats": (
        "P13.03.c",
        (("GET", "/api/v1/projects/{project_id}/learning/pathology-stats"),),
    ),
    "learning.promote_candidate": (
        "P13.03.c",
        (("POST", "/api/v1/workspaces/{workspace_id}/lesson-candidates/{candidate_id}/promote"),),
    ),
    "learning.record_activity": ("P13.03.c", (("POST", "/api/v1/projects/{project_id}/learning/activity"),)),
    "learning.recompute_confidence": (
        "P13.03.c",
        (("POST", "/api/v1/workspaces/{workspace_id}/learning/recompute"),),
    ),
    "learning.review_candidate": (
        "P13.03.c",
        (("POST", "/api/v1/workspaces/{workspace_id}/lesson-candidates/{candidate_id}/reviews"),),
    ),
    "planning.abandon_draft": ("P11.02.e", (("POST", "/api/v1/plans/{plan_id}/drafts/{draft_id}/abandon"),)),
    "planning.archive_plan": ("P11.02.e", (("POST", "/api/v1/plans/{plan_id}/archive"),)),
    "planning.design_plan": ("I-11.1", (("POST", "/api/v1/plans/{plan_id}/design-briefs"),)),
    "planning.create_plan": ("P11.02.e", (("POST", "/api/v1/projects/{project_id}/plans"),)),
    "planning.diff_revisions": (
        "P11.02.e",
        (
            ("GET", "/api/v1/plans/{plan_id}/revisions/{revision_id}/diff"),
            ("GET", "/api/v1/plans/{plan_id}/drafts/{draft_id}/diff"),
        ),
    ),
    "planning.export_specification": (
        "P11.02.e",
        (
            ("GET", "/api/v1/plans/{plan_id}/drafts/{draft_id}/export"),
            ("GET", "/api/v1/plans/{plan_id}/revisions/{revision_id}/export"),
        ),
    ),
    "planning.get_draft": ("P11.02.e", (("GET", "/api/v1/plans/{plan_id}/drafts/{draft_id}"),)),
    "planning.get_entity": (
        "P11.02.e",
        (
            ("GET", "/api/v1/plans/{plan_id}/revisions/{revision_id}/entities/{ref}"),
            ("GET", "/api/v1/plans/{plan_id}/drafts/{draft_id}/entities/{ref}"),
        ),
    ),
    "planning.get_plan": ("P11.02.e", (("GET", "/api/v1/plans/{plan_id}"),)),
    "planning.get_revision": ("P11.02.e", (("GET", "/api/v1/plans/{plan_id}/revisions/{revision_id}"),)),
    "planning.import_specification": ("P11.02.e", (("POST", "/api/v1/projects/{project_id}/plans/import"),)),
    "planning.list_drafts": ("P11.02.e", (("GET", "/api/v1/plans/{plan_id}/drafts"),)),
    "planning.list_entities": ("P11.02.e", (("GET", "/api/v1/plans/{plan_id}/entities"),)),
    "planning.list_plans": ("P11.02.e", (("GET", "/api/v1/projects/{project_id}/plans"),)),
    "planning.list_revisions": ("P11.02.e", (("GET", "/api/v1/plans/{plan_id}/revisions"),)),
    "planning.open_draft": ("P11.02.e", (("POST", "/api/v1/plans/{plan_id}/drafts"),)),
    "planning.plan_stats": (
        "P11.02.e",
        (
            ("GET", "/api/v1/plans/{plan_id}/revisions/{revision_id}/stats"),
            ("GET", "/api/v1/plans/{plan_id}/drafts/{draft_id}/stats"),
        ),
    ),
    "planning.preview_publication": (
        "P11.02.e",
        (("POST", "/api/v1/plans/{plan_id}/drafts/{draft_id}/publication-preview"),),
    ),
    "planning.publish_revision": (
        "P11.02.e",
        (("POST", "/api/v1/plans/{plan_id}/drafts/{draft_id}/publish"),),
    ),
    "planning.read_text": ("P11.02.e", (("GET", "/api/v1/plans/{plan_id}/text"),)),
    "planning.ready_preview": (
        "P11.02.e",
        (
            ("GET", "/api/v1/plans/{plan_id}/revisions/{revision_id}/ready-preview"),
            ("GET", "/api/v1/plans/{plan_id}/drafts/{draft_id}/ready-preview"),
        ),
    ),
    "planning.rebase_draft": ("P11.02.e", (("POST", "/api/v1/plans/{plan_id}/drafts/{draft_id}/rebase"),)),
    "planning.resolve_plan_ref": ("P11.02.e", (("GET", "/api/v1/plans/resolve"),)),
    "planning.restore_revision": ("P11.02.e", (("POST", "/api/v1/plans/{plan_id}/restore"),)),
    "planning.save_draft": (
        "P11.02.e",
        (
            ("PUT", "/api/v1/plans/{plan_id}/drafts/{draft_id}"),
            ("PATCH", "/api/v1/plans/{plan_id}/drafts/{draft_id}"),
            ("POST", "/api/v1/plans/{plan_id}/drafts/{draft_id}/changes"),
        ),
    ),
    "planning.simulate": (
        "I-11.4",
        (
            ("GET", "/api/v1/plans/{plan_id}/revisions/{revision_id}/simulate"),
            ("GET", "/api/v1/plans/{plan_id}/drafts/{draft_id}/simulate"),
        ),
    ),
    "planning.validate_draft": (
        "P11.02.e",
        (("POST", "/api/v1/plans/{plan_id}/drafts/{draft_id}/validate"),),
    ),
    "platform.doctor": ("P11.02.f", (("GET", "/health/details"), ("GET", "/api/v1/doctor"))),
    "platform.list_dead_outbox": ("P11.02.f", (("GET", "/api/v1/admin/outbox/dead"),)),
    "platform.migration_status": ("P11.02.f", (("GET", "/api/v1/admin/migrations"),)),
    "platform.repair_storage_safe": ("P15.01.a", (("POST", "/api/v1/admin/storage/repair"),)),
    "platform.retry_outbox": ("P11.02.f", (("POST", "/api/v1/admin/outbox/{outbox_id}/retry"),)),
    "platform.verify_storage": ("P15.01.a", (("GET", "/api/v1/admin/storage/verify"),)),
    "policy.approve_intent": ("P11.02.f", (("POST", "/api/v1/policy/intents/{intent_id}/approve"),)),
    "policy.check_tool_call": ("P11.02.f", (("POST", "/api/v1/policy/check-tool-call"),)),
    "policy.deny_intent": ("P11.02.f", (("POST", "/api/v1/policy/intents/{intent_id}/deny"),)),
    "policy.effective_permissions": ("P11.02.f", (("GET", "/api/v1/policy/effective"),)),
    "policy.explain_permissions": ("P11.02.f", (("GET", "/api/v1/policy/explain"),)),
    "policy.get_intent": ("P11.02.f", (("GET", "/api/v1/policy/intents/{intent_id}"),)),
    "policy.list_intents": ("P11.02.f", (("GET", "/api/v1/policy/intents"),)),
    "policy.list_profiles": ("P11.02.f", (("GET", "/api/v1/policy/profiles"),)),
    "policy.propose_intent": ("P11.02.f", (("POST", "/api/v1/worker/intents"),)),
    "policy.record_intent_outcome": ("P11.02.f", (("POST", "/api/v1/worker/intents/{intent_id}/outcome"),)),
    "policy.record_tool_decisions": ("P11.02.f", (("POST", "/api/v1/policy/tool-decisions"),)),
    "policy.start_intent_execution": ("P11.02.f", (("POST", "/api/v1/worker/intents/{intent_id}/start"),)),
    "runtimes.explain_routing": ("P11.02.f", (("GET", "/api/v1/runtimes/routing"),)),
    "runtimes.get_capabilities": ("P11.02.f", (("GET", "/api/v1/runtimes/{runtime_id}/capabilities"),)),
    "runtimes.list_models": ("P11.02.f", (("GET", "/api/v1/runtimes/models"),)),
    "runtimes.list_runtimes": ("P11.02.f", (("GET", "/api/v1/runtimes"),)),
    "runtimes.record_capability_verification": (
        "P11.02.f",
        (("POST", "/api/v1/runtimes/{runtime_id}/capability-verifications"),),
    ),
    "runtimes.record_host_runtimes": ("P11.02.f", (("POST", "/api/v1/hosts/{host_id}/runtimes"),)),
    "settings.explain_config": (
        "P11.02.b",
        (("GET", "/api/v1/config/effective"), ("GET", "/api/v1/config/explain")),
    ),
    "settings.export_config": (
        "P11.02.b",
        (("GET", "/api/v1/config/export"), ("GET", "/api/v1/projects/{project_id}/config")),
    ),
    "settings.get_generation": ("P11.02.b", (("GET", "/api/v1/config/generation"),)),
    "settings.get_history": ("P11.02.b", (("GET", "/api/v1/config/history"),)),
    "settings.get_host_config": ("P11.02.c", (("GET", "/api/v1/worker/hosts/{host_id}/config"),)),
    "settings.get_schema": ("P11.02.b", (("GET", "/api/v1/config/schema"),)),
    "settings.get_value": ("P11.02.b", (("GET", "/api/v1/config/entries/{scope}/{key}"),)),
    "settings.import_config": (
        "P11.02.b",
        (("POST", "/api/v1/config/import"), ("PUT", "/api/v1/projects/{project_id}/config")),
    ),
    "settings.list_entries": ("P11.02.b", (("GET", "/api/v1/config/entries"),)),
    "settings.lock_value": ("P11.02.b", (("POST", "/api/v1/config/entries/{scope}/{key}/lock"),)),
    "settings.remove_value": ("P11.02.b", (("DELETE", "/api/v1/config/entries/{scope}/{key}"),)),
    "settings.set_value": ("P11.02.b", (("PUT", "/api/v1/config/entries/{scope}/{key}"),)),
    "settings.unlock_value": ("P11.02.b", (("POST", "/api/v1/config/entries/{scope}/{key}/unlock"),)),
    "settings.unset_value": ("P11.02.b", (("POST", "/api/v1/config/entries/{scope}/{key}/unset"),)),
    "workspace.add_repository_remote": (
        "P11.02.b",
        (("POST", "/api/v1/repositories/{repository_id}/remotes"),),
    ),
    "workspace.archive_project": ("P11.02.b", (("POST", "/api/v1/projects/{project_id}/archive"),)),
    "workspace.archive_workspace": ("P11.02.b", (("POST", "/api/v1/workspaces/{workspace_id}/archive"),)),
    "workspace.attach_repository": ("P11.02.b", (("POST", "/api/v1/projects/{project_id}/repositories"),)),
    "workspace.bind_checkout": ("P11.02.b", (("POST", "/api/v1/checkout-bindings"),)),
    "workspace.create_project": ("P11.02.b", (("POST", "/api/v1/workspaces/{workspace_id}/projects"),)),
    "workspace.create_workspace": ("P11.02.b", (("POST", "/api/v1/workspaces"),)),
    "workspace.detach_repository": (
        "P11.02.b",
        (("DELETE", "/api/v1/projects/{project_id}/repositories/{mount_name}"),),
    ),
    "workspace.get_host": ("P11.02.b", (("GET", "/api/v1/hosts/{host_id}"),)),
    "workspace.get_project": ("P11.02.b", (("GET", "/api/v1/projects/{project_id}"),)),
    "workspace.get_workspace": ("P11.02.b", (("GET", "/api/v1/workspaces/{workspace_id}"),)),
    "workspace.list_hosts": ("P11.02.b", (("GET", "/api/v1/hosts"),)),
    "workspace.list_project_repositories": (
        "P11.02.b",
        (("GET", "/api/v1/projects/{project_id}/repositories"),),
    ),
    "workspace.list_projects": ("P11.02.b", (("GET", "/api/v1/workspaces/{workspace_id}/projects"),)),
    "workspace.list_repositories": ("P11.02.b", (("GET", "/api/v1/workspaces/{workspace_id}/repositories"),)),
    "workspace.list_workers": ("P11.02.b", (("GET", "/api/v1/workspaces/{workspace_id}/workers"),)),
    "workspace.list_workspaces": ("P11.02.b", (("GET", "/api/v1/workspaces"),)),
    "workspace.match_checkout": ("P11.02.b", (("POST", "/api/v1/checkout-bindings/match"),)),
    "workspace.record_checkout_verification": (
        "P11.02.b",
        (("POST", "/api/v1/checkout-bindings/{binding_id}/verification"),),
    ),
    "workspace.record_worker_heartbeat": ("P11.02.c", (("POST", "/api/v1/worker/heartbeat"),)),
    "workspace.register_host": ("P11.02.b", (("POST", "/api/v1/hosts"),)),
    "workspace.register_repository": (
        "P11.02.b",
        (("POST", "/api/v1/workspaces/{workspace_id}/repositories"),),
    ),
    "workspace.register_worker": ("P11.02.b", (("POST", "/api/v1/workspaces/{workspace_id}/workers"),)),
    "workspace.resolve_checkout": ("P11.02.b", (("GET", "/api/v1/projects/{project_id}/checkout"),)),
    "workspace.set_worker_state": ("P11.02.b", (("POST", "/api/v1/workers/{worker_id}/state"),)),
}

INTERNAL = {
    "exports.purge_notes": "Background vault note expiry and retention.",
    "knowledge.expire_memory": "Background memory sweep and retention.",
    "access.bootstrap_local_owner": "Local bootstrap only; cannot mint owners over HTTP.",
    "workspace.exchange_pairing_token": "System-authenticated pairing exchange with a separate bearer proof.",
    "artifacts.expire_staged_blobs": "Background staged upload garbage collection.",
    "policy.expire_intents": "Background intent expiry.",
    "execution.autopilot_tick": "Background autopilot scheduler tick.",
    "execution.schedule_ready_tasks": "Background assignment scheduler.",
    "learning.extract_candidates": "Internal activity extraction for learning.",
    "execution.expire_leases": "Background lease sweeper.",
    "execution.enforce_timeouts": "Background timeout enforcer.",
    "execution.detect_stalls": "Background stall detector.",
    "integrations.record_hook_delivery_failure": "Outbox delivery callback only.",
}

DEFERRED_INTERNAL: dict[str, tuple[str, str]] = {}


def test_every_registered_operation_has_an_explicit_surface_or_internal_reason():
    operations = {
        cast("Any", s).name: cast("Any", s)
        for m in (*MANIFESTS, PLATFORM_MANIFEST)
        for s in (*m.commands, *m.queries)
    }
    internal = set(INTERNAL) | set(DEFERRED_INTERNAL)
    registered_internal = set(INTERNAL) | set(DEFERRED_INTERNAL).intersection(operations)
    assert {name for name, s in operations.items() if s.internal} == registered_internal
    assert all(INTERNAL.values())
    assert all(owner == "P13" and reason for owner, reason in DEFERRED_INTERNAL.values())
    assert not internal & set(SURFACES)
    assert set(operations) <= set(SURFACES) | internal
    assert "artifacts.record_staged_blob" in SURFACES
    assert all(".host." not in name for name in SURFACES)


def _blob_method_paths() -> set[tuple[str, str]]:
    text = (ROOT / "src/skm/entrypoints/api/blobs.py").read_text(encoding="utf-8")
    constants = dict(re.findall(r'^(_(?:UPLOAD|CONTENT)) = "([^"]+)"', text, re.M))
    mount = text.split("def mount_blobs", 1)[1]
    found: set[tuple[str, str]] = set()
    for name, method in (("_UPLOAD", "POST"), ("_CONTENT", "GET")):
        if f"Route({name}," in mount:
            found.add((method, constants[name]))
    return found


def _publication_contract() -> dict[str, Any]:
    return json.loads(
        (Path(__file__).parent / "fixtures" / "surface_publication_contract.json").read_text(encoding="utf-8")
    )


def test_surface_ledger_matches_canonical_api_and_owner_leaves() -> None:
    contract = _publication_contract()
    owners = set(contract["owners"])
    expected: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {}
    seen: set[tuple[str, str]] = set()
    wired: set[tuple[str, str]] = set()
    for row in contract["routes"]:
        operation = str(row["operation"])
        method_path = (str(row["method"]), str(row["path"]))
        assert method_path not in seen, (operation, *method_path)
        seen.add(method_path)
        owner, routes = expected.get(operation, (str(row["owner"]), ()))
        assert owner == row["owner"]
        assert owner in owners
        expected[operation] = (owner, (*routes, method_path))
        if row["wired"] != "missing":
            wired.add(method_path)
    assert set(SURFACES) == set(expected)
    for name, (owner, routes) in SURFACES.items():
        assert (owner, routes) == expected[name]
    published = {(route.method, route.path) for route in build_route_table(MODULE_IDS).describe()}
    published |= _blob_method_paths()
    assert not wired - published, sorted(wired - published)


def test_adhoc_cli_and_mcp_publication_contract() -> None:
    contract = _publication_contract()
    uid = "01900000-0000-7000-8000-000000000001"
    arguments = {
        "exec": ["prompt"],
        "pipe": ["workflow.json", "prompt"],
        "route pick": ["executor"],
        "context assemble": ["--runtime", "codex", "--model", "test", "--context-window", "32000"],
        "context explain": [uid],
        "context diff": [uid, uid],
        "plan simulate": [uid],
    }
    parser = build_parser()
    assert {row["command"] for row in contract["cli"]} == set(arguments)
    for row in contract["cli"]:
        assert row["owner"] in contract["owners"]
        assert row["operation"] in SURFACES
        args = parser.parse_args([*row["command"].split(), *arguments[row["command"]]])
        assert args.command_name == row["operation"]

    commands = {cast("Any", spec).name: cast("Any", spec) for mod in MANIFESTS for spec in mod.commands}
    tools = {tool.name: tool for tool in TOOLS}
    schemas = SchemaRegistry.load_default()
    assert {row["tool"] for row in contract["mcp"]} == {"skm_run_adhoc", "skm_context_assemble"}
    for row in contract["mcp"]:
        assert row["owner"] in contract["owners"]
        operation = commands[row["operation"]]
        tool = tools[row["tool"]]
        assert tool.permission == operation.permission == row["permission"]
        assert not tool.assignment_write
        assert schemas.get(tool.output_schema_urn)["$ref"] == operation.result.SCHEMA_URN


def test_discovered_routes_never_publish_host_or_internal_operations():
    for route in build_route_table(MODULE_IDS).describe():
        assert not route.internal
        assert route.bus_name not in INTERNAL
        assert route.bus_name not in DEFERRED_INTERNAL
        owner, canonical = SURFACES[route.bus_name]
        assert owner
        assert (route.method, route.path) in canonical


def test_memory_and_lessons_routes_cover_the_leaf_ledger():
    operations = {name for name, (owner, _) in SURFACES.items() if owner == "P13.01.c"}
    expected = {(name, method, path) for name in operations for method, path in SURFACES[name][1]}
    discovered = build_route_table(("knowledge",)).describe()
    assert len(expected) == 7
    assert expected == {
        (route.bus_name, route.method, route.path) for route in discovered if route.bus_name in operations
    }


def test_graph_reads_use_the_canonical_workspace_routes():
    discovered = {route.bus_name: route for route in build_route_table(("knowledge",)).describe()}
    ops = ("graph_neighbors", "graph_path", "graph_stats", "graph_subgraph", "list_graph_indexes")
    for name in ops:
        operation = f"knowledge.{name}"
        route = discovered[operation]
        assert (route.method, route.path) in SURFACES[operation][1]
        assert route.path_params == {"workspace_id": "workspace_id"}
        assert route.command is None


def test_learning_has_exactly_eight_routes_when_enabled():
    actual = build_route_table(("learning",)).describe()
    expected = {
        (name, method, path)
        for name, (owner, routes) in SURFACES.items()
        if owner == "P13.03.c"
        for method, path in routes
    }
    assert len(expected) == 8
    assert {(route.bus_name, route.method, route.path) for route in actual} == expected
    assert not build_route_table(()).describe()


def test_auth_surface_publication_contract() -> None:
    from skm.entrypoints.api.auth import PUBLIC_ROUTES
    from skm.entrypoints.api.routes.auth import AUTH_ROUTE_SPECS

    contract = _publication_contract()
    owners = set(contract["owners"])
    openapi_doc = json.loads((ROOT / "src/skm/entrypoints/api/openapi.json").read_text(encoding="utf-8"))
    declared = {
        (method, path): (operation_id, public, requires_csrf)
        for method, path, operation_id, public, requires_csrf in AUTH_ROUTE_SPECS
    }
    ledger = contract["auth_routes"]
    assert len(ledger) == len(declared)
    for row in ledger:
        assert row["owner"] in owners
        assert row["wired"] == "route"
        key = (str(row["method"]), str(row["path"]))
        assert key in declared
        operation_id, public, requires_csrf = declared[key]
        assert row["operation_id"] == operation_id
        assert row["public"] is public
        assert row["requires_csrf"] is requires_csrf
        assert (key in PUBLIC_ROUTES) is public
        openapi_path = str(row["path"]).removeprefix("/api/v1")
        operation = openapi_doc["paths"][openapi_path][str(row["method"]).lower()]
        assert operation["operationId"] == operation_id
        if public:
            assert operation["security"] == []
        else:
            assert operation["security"]
            if requires_csrf:
                assert operation["security"] == [{"sessionCookie": [], "csrfToken": []}]


def test_stream_surface_publication_contract() -> None:
    contract = _publication_contract()
    owners = set(contract["owners"])
    openapi_doc = json.loads((ROOT / "src/skm/entrypoints/api/openapi.json").read_text(encoding="utf-8"))
    ledger = contract["stream_routes"]
    assert len(ledger) == 4
    seen: set[tuple[str, str]] = set()
    for row in ledger:
        assert row["owner"] in owners
        assert row["wired"] == "route"
        method = str(row["method"])
        path = str(row["path"])
        key = (method, path)
        assert key not in seen
        seen.add(key)
        openapi_path = path.removeprefix("/api/v1")
        operation = openapi_doc["paths"][openapi_path][method.lower()]
        assert operation["operationId"] == row["operation_id"]
        assert operation["security"] == row["security"]
        if row["worker_only"]:
            assert path.startswith("/api/v1/worker/")
            assert operation["security"] == [{"bearer": []}]
        else:
            assert operation["security"] == [{"bearer": []}, {"sessionCookie": []}]
