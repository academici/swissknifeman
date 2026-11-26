"""Regressions for the five confirmed P00.04.e review findings."""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from skm.kernel.actor import PrincipalKind
from skm.modules.integrations.domain.budget import FirstTurnVerdict
from skm.modules.integrations.domain.desired import ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookSurfaceId
from skm.modules.integrations.domain.target import TargetId

INTEGRATION_DEFS = "urn:skm:integrations:defs:v1"
UUID = "00000000-0000-0000-0000-000000000001"
DIGEST = "sha256:" + "a" * 64


def product_schemas() -> dict[str, Any]:
    result = {}
    for path in (Path(__file__).resolve().parents[3] / "src/skm/schemas").rglob("*.json"):
        schema = json.loads(path.read_text())
        if isinstance(schema, dict) and "$id" in schema:
            result[schema["$id"]] = schema
    return result


CURRENT = product_schemas()
REGISTRY = Registry().with_resources((urn, Resource.from_contents(schema)) for urn, schema in CURRENT.items())


def checked(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema, registry=REGISTRY, format_checker=FormatChecker())


def host_subscription() -> dict[str, Any]:
    return {
        "id": "guard",
        "class": "enforcement",
        "event_types": ["client:pre_shell"],
        "argv": ["guard-command", "--check"],
        "cwd": "checkout",
        "env_allow": ["PATH"],
        "env_refs": {"TOKEN": "secret://env/GUARD_TOKEN"},
        "timeout_ms": 100,
        "retry": {"max_attempts": 1, "backoff": {"initial_ms": 100, "factor": 2, "max_ms": 1000}},
        "failure_policy": "deny",
        "digest": DIGEST,
    }


def hook_policy(subscription: dict[str, Any]) -> dict[str, Any]:
    return {
        "hook_modes": {},
        "permissions": {},
        "reserved_paths": [],
        "managed_file_paths": [],
        "changelog": {"code_globs": [], "changelog_path": "CHANGELOG.md", "skip_marker": "[skip]"},
        "subscriptions": [subscription],
        "generation": 1,
        "ttl_seconds": 30,
    }


@pytest.mark.parametrize(
    ("verdict", "total"), [("ok", 10000), ("elevated", 20000), ("warn", 24000), ("incomplete", None)]
)
def test_f1_full_budget_report_accepts_approved_verdicts(verdict: str, total: int | None) -> None:
    schema = CURRENT["urn:skm:integrations:host-result:first-turn-budget:v1"]
    report = {
        "schema": schema["$id"],
        "project_id": UUID,
        "target": "codex",
        "thresholds": {"target": 16000, "warn": 23000},
        "sources": [],
        "total": total,
        "verdict": verdict,
    }
    check = checked(schema)
    check.validate(report)
    approved = {"ok", "elevated", "warn", "incomplete"}
    assert set(schema["properties"]["verdict"]["enum"]) == approved
    assert {value.value for value in FirstTurnVerdict} == approved
    assert set(CURRENT[INTEGRATION_DEFS]["$defs"]["FirstTurnVerdict"]["enum"]) == approved
    for invalid in ("target", "warning", "over", "over_budget", "unknown"):
        with pytest.raises(ValidationError):
            check.validate({**report, "verdict": invalid})


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("ProjectionInputs", "target"),
        ("TargetCapabilities", "target"),
        ("CheckResult", "target"),
        ("Projection", "target"),
        ("ProjectionPlan", "target"),
        ("ApplyOutcome", "target"),
        ("NormalizedHookEvent", "target"),
        ("DesiredFile", "target"),
        ("DesiredProjection", "targets"),
        ("HookDecision", "surface"),
    ],
)
def test_f2_target_and_hook_surface_fields_use_enums(name: str, field: str) -> None:
    schema = CURRENT[INTEGRATION_DEFS]["$defs"][name]["properties"][field]
    check = checked(schema)
    values = HookSurfaceId if field == "surface" else TargetId
    for value in values:
        check.validate([value.value] if field == "targets" else value.value)
    for invalid in (UUID, "unknown"):
        with pytest.raises(ValidationError):
            check.validate([invalid] if field == "targets" else invalid)


def test_f3_hook_policy_requires_flat_host_subscription_view() -> None:
    schema = CURRENT["urn:skm:integrations:view:hook-policy:v1"]
    check = checked(schema)
    subscription = host_subscription()
    check.validate(hook_policy(subscription))
    assert schema["properties"]["subscriptions"]["items"] == {
        "$ref": INTEGRATION_DEFS + "#/$defs/HostSubscriptionView"
    }
    for field in subscription:
        with pytest.raises(ValidationError):
            check.validate(hook_policy({key: value for key, value in subscription.items() if key != field}))
    internal = {
        key: value
        for key, value in subscription.items()
        if key not in {"class", "argv", "cwd", "env_allow", "env_refs"}
    }
    internal.update(
        enabled=True,
        hook_class=subscription["class"],
        kind="command",
        execution_location="host",
        defined_at="project",
        target={key: subscription[key] for key in ("argv", "cwd", "env_allow", "env_refs")},
    )
    checked({"$ref": INTEGRATION_DEFS + "#/$defs/HookSubscription"}).validate(internal)
    with pytest.raises(ValidationError):
        check.validate(hook_policy(internal))


def desired_projection() -> dict[str, Any]:
    return {
        "project_id": UUID,
        "target": "codex",
        "instructions_core": {},
        "instructions_project": {},
        "skills": [],
        "permissions": {},
        "profile": "workspace_contained",
        "hook_modes": {},
        "mcp_servers": {},
        "agents": [],
        "inputs_digest": DIGEST,
        "config_generation": 1,
        "diagnostics": [],
        "host_subscription_events": [],
    }


def test_f4_projection_inputs_declare_host_subscription_events() -> None:
    from skm.modules.integrations.domain.desired import HostSubscriptionEvent
    from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind

    assert "host_subscription_events" in {field.name for field in fields(ProjectionInputs)}
    assert {field.name for field in fields(HostSubscriptionEvent)} == {"kind", "classes"}
    event = HostSubscriptionEvent(kind=HookEventKind.PRE_SHELL, classes=(HookClass.ENFORCEMENT,))
    assert event.kind is HookEventKind.PRE_SHELL
    check = checked(CURRENT["urn:skm:integrations:view:desired-projection:v1"])
    full = desired_projection()
    check.validate(full)
    check.validate(
        {
            **full,
            "host_subscription_events": [{"kind": "pre_shell", "classes": ["enforcement", "observation"]}],
        }
    )
    for invalid in (
        [{"kind": "unknown", "classes": ["enforcement"]}],
        [{"kind": "pre_shell", "classes": ["unknown"]}],
        [{"kind": "pre_shell"}],
        [{"classes": ["enforcement"]}],
    ):
        with pytest.raises(ValidationError):
            check.validate({**full, "host_subscription_events": invalid})
    with pytest.raises(ValidationError):
        check.validate({key: value for key, value in full.items() if key != "host_subscription_events"})


def candidate_with_review(kind: str) -> dict[str, Any]:
    review = {
        "id": UUID,
        "candidate_id": UUID,
        "reviewer_id": UUID,
        "reviewer_kind": kind,
        "verdict": "approve",
        "note": None,
        "edited_trigger": None,
        "edited_action": None,
        "edited_kind": None,
        "proposal_id": None,
        "created_at": "2026-10-27T00:00:00Z",
    }
    return {
        "id": UUID,
        "workspace_id": UUID,
        "project_id": UUID,
        "scope_id": UUID,
        "display_key": "LC-1",
        "detector": "workaround",
        "pathology_code": None,
        "kind": "gotcha",
        "trigger": "A check failed",
        "action": "Investigate the failure",
        "review_hint": None,
        "meta": {},
        "evidence": [],
        "fingerprint": DIGEST,
        "state": "candidate",
        "s_total": 0,
        "n_total": 0,
        "known_outcome_total": 0,
        "unknown_outcome_total": 0,
        "independent_known_total": 0,
        "independent_success_total": 0,
        "exposed_total": 0,
        "exposure_unknown_total": 0,
        "tests_total": 0,
        "tests_passed": 0,
        "days_since": 0,
        "support_score": 0,
        "freshness": 0,
        "stale": False,
        "review_status": "approved",
        "confidence": 0,
        "confidence_tier": "none",
        "curated_ready": False,
        "conflicts_with_id": None,
        "proposed_update": None,
        "lesson_id": None,
        "recomputed_at": None,
        "row_version": 1,
        "gates": {},
        "reviews": [review],
        "proposals": [],
        "similar": [],
    }


@pytest.mark.parametrize("kind", ["human", "service", "worker"])
def test_f5_candidate_view_review_uses_principal_kind(kind: str) -> None:
    check = checked(CURRENT["urn:skm:learning:view:candidate:v1"])
    candidate = candidate_with_review(kind)
    check.validate(candidate)
    schema = CURRENT["urn:skm:learning:defs:v1"]["$defs"]["CandidateReview"]
    assert set(schema["properties"]["reviewer_kind"]["enum"]) == {value.value for value in PrincipalKind}
    for invalid in ({}, "unknown"):
        candidate["reviews"][0]["reviewer_kind"] = invalid
        with pytest.raises(ValidationError):
            check.validate(candidate)
