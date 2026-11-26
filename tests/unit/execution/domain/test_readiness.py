"""Readiness rules and exact prospective-input freshness."""

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.errors import SkmError
from skm.modules.execution.domain.readiness import (
    READINESS_VALIDATOR_VERSION,
    RULES,
    ReadinessInputs,
    ReadinessSnapshot,
    ReadinessStatus,
    canonical_digest,
    canonical_start_request,
    changed_inputs,
    evaluate_readiness,
    freshness,
    readiness_inputs_digest,
    require_fresh,
    snapshot_readiness_inputs,
    write_scope_overlaps,
)
from skm.modules.execution.domain.work_policy import (
    WorkPolicySettings,
    resolve_work_policy,
    work_policy_to_json,
)

NOW = datetime(2026, 11, 15, tzinfo=UTC)
DIGEST = canonical_digest({"revision": "one"})


def document(**changes: Any) -> Any:
    value = {
        "id": str(UUID(int=1)),
        "workspace_id": str(UUID(int=2)),
        "project_id": str(UUID(int=3)),
        "plan_id": str(UUID(int=4)),
        "revision_id": str(UUID(int=5)),
        "revision_digest": DIGEST,
        "created_by": str(UUID(int=6)),
        "created_at": NOW.isoformat(),
        "tasks": [{"task_key": "P1.1", "review": "required"}],
        "edges": [],
        "phases": [{"detail_state": "detailed"}],
        "checks": [],
        "criteria": [],
        "requirements": [],
        "items": [],
        "materials": [],
        "routing": {"executor": {"available": True}},
        "policy_live_ok": True,
        "start_request": {"overrides": {}, "selection": None},
        "work_policies": {
            "@default": work_policy_to_json(resolve_work_policy(WorkPolicySettings.defaults()))
        },
        "material_inputs": dict.fromkeys(ReadinessInputs.__dataclass_fields__, DIGEST),
    }
    value.update(changes)
    return value


def test_ready_report_has_every_rule_and_exact_policy_preview() -> None:
    report = evaluate_readiness(document())
    assert report.status is ReadinessStatus.READY
    assert tuple(result.rule_id for result in report.results) == RULES
    assert report.results[11].outcome == "skipped"
    assert report.work_policies is not None
    policy = report.work_policies["@default"]
    assert policy.role_warn_seconds["reviewer"] == 300
    assert policy.emergency_role_seconds["reviewer"] is None
    assert report.inputs_digest == readiness_inputs_digest(report.inputs, READINESS_VALIDATOR_VERSION)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"tasks": []}, "NO_TASKS"),
        ({"edges": [{"dependent": "P1.1", "prerequisite": "P1.1"}]}, "DEPENDENCY_CYCLE"),
        ({"phases": [{"detail_state": "skeleton"}]}, "PHASE_SKELETON"),
        ({"criteria": [{"id": str(UUID(int=7))}]}, "CRITERION_UNVERIFIED"),
        ({"requirements": [{"id": str(UUID(int=8))}], "require_coverage": True}, "REQUIREMENT_UNCOVERED"),
        ({"materials": [{"required_for": ["execution"], "available": False}]}, "FILE_VERSION_NOT_READY"),
        (
            {"materials": [{"required_for": ["execution"], "available": True, "fresh": False}]},
            "MATERIAL_STALE",
        ),
        ({"routing": {"reviewer": {"available": False}}}, "CAPABILITY_UNAVAILABLE"),
        ({"estimate_over": True, "block_on_over": True}, "BUDGET_ESTIMATE_OVER"),
        ({"policy_live_ok": False}, "POLICY_DENIES"),
        ({"work_policies": None}, "POLICY_DENIES"),
        ({"audit": {"verdict": "red"}}, "SEMANTIC_AUDIT_RED"),
        ({"tasks": [{"task_key": "gate", "gate_required": True}]}, "GATE_UNSUPPORTED_BY_WORKFLOW"),
    ],
)
def test_each_required_rule_independently_refuses_admission(change: Any, code: str) -> None:
    report = evaluate_readiness(document(**change))
    assert report.status is ReadinessStatus.NOT_READY
    assert code in {finding.code for finding in report.findings}


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"requirements": [{"id": str(UUID(int=8))}]}, "REQUIREMENT_UNCOVERED"),
        ({"checks": [{"kind": "command"}]}, "CHECKOUT_UNBOUND"),
        ({"write_scope_overlaps": ["P1.1 and P1.2"]}, "WRITE_SCOPE_OVERLAP"),
        ({"estimate_over": True}, "BUDGET_ESTIMATE_OVER"),
        ({"checks": [{"kind": "manual", "actor_role": "verifier"}]}, "NO_VERIFIER"),
        ({"audit": {"verdict": "attention"}}, "SEMANTIC_AUDIT_ATTENTION"),
    ],
)
def test_advisory_is_visible_and_does_not_waive_other_rules(change: Any, code: str) -> None:
    report = evaluate_readiness(document(**change))
    assert report.status is ReadinessStatus.READY_WITH_ADVISORIES
    assert code in {finding.code for finding in report.findings}
    assert evaluate_readiness(document(**change, policy_live_ok=False)).status is ReadinessStatus.NOT_READY


@pytest.mark.parametrize("part", ReadinessInputs.__dataclass_fields__)
def test_every_material_part_invalidates_preview(part: str) -> None:
    report = evaluate_readiness(document())
    current = replace(report.inputs, **{part: canonical_digest({"changed": part})})
    assert changed_inputs(report, current) == (part,)
    assert not freshness(report, current)
    with pytest.raises(SkmError):
        require_fresh(
            report,
            current,
            now=NOW,
            revision_digest=report.revision_digest,
            max_age_seconds=600,
            start_request=document()["start_request"],
        )


def test_start_request_a_cannot_start_b_with_same_report_id() -> None:
    report = evaluate_readiness(document())
    with pytest.raises(SkmError) as caught:
        require_fresh(
            report,
            report.inputs,
            now=NOW,
            revision_digest=report.revision_digest,
            max_age_seconds=600,
            start_request={"overrides": {"budgets.run.max_usd": 20}, "selection": None},
        )
    assert caught.value.details["stale_parts"] == ["start_request_changed"]


def test_freshness_checks_age_version_and_historical_nulls() -> None:
    report = evaluate_readiness(document())
    assert freshness(report, report.inputs)
    for historical in (
        replace(report, start_request=None),
        replace(report, work_policies=None),
        replace(report, validator_version=0),
    ):
        assert not freshness(historical, report.inputs)
    require_fresh(
        report,
        report.inputs,
        now=NOW,
        revision_digest=report.revision_digest,
        max_age_seconds=600,
        start_request=document()["start_request"],
    )
    with pytest.raises(SkmError):
        require_fresh(
            report,
            report.inputs,
            now=NOW + timedelta(seconds=601),
            revision_digest=report.revision_digest,
            max_age_seconds=600,
            start_request=document()["start_request"],
        )


def test_canonical_request_normalizes_sets_and_preserves_overrides() -> None:
    first = canonical_start_request({"a": 1}, {"task_keys": ["B", "A", "A"]})
    second = canonical_start_request({"a": 1}, {"task_keys": ["A", "B"], "phases": []})
    assert first == second
    assert canonical_digest(first) == canonical_digest(second)
    assert canonical_start_request({}, None) != canonical_start_request({}, {})


def test_runtime_availability_does_not_change_material_freshness() -> None:
    ready = evaluate_readiness(document())
    offline = evaluate_readiness(document(routing={"executor": {"available": False}}))
    assert offline.status is ReadinessStatus.NOT_READY
    assert asdict(ready.inputs) == asdict(offline.inputs)
    assert ready.inputs_digest == offline.inputs_digest


def snapshot(**changes: Any) -> ReadinessSnapshot:
    values: dict[str, Any] = {
        "revision": {"requirements": [], "criteria": [], "items": [], "checks": []},
        "graph": {"edges": [], "tasks": [], "batch_groups": []},
        "selection": None,
        "compiled_keys": ("P1.1",),
        "satisfied": {},
        "capability_requirements": {"executor": {"class": "implementation"}},
        "policy_digest": DIGEST,
        "config_snapshot": {"registry_digest": DIGEST, "values": {"budgets.run.max_usd": 10}},
        "resource_pins": {"resources": [], "packs": {"core": "v1"}},
        "materials": {"source": {"file_version_id": "v1", "digest": DIGEST, "available": True}},
        "start_request": {"overrides": {}, "selection": None},
        "work_policies": {"@default": resolve_work_policy(WorkPolicySettings.defaults())},
    }
    values.update(changes)
    return ReadinessSnapshot(**values)


@pytest.mark.parametrize(
    ("change", "part"),
    [
        ({"resource_pins": {"resources": [], "packs": {"core": "v2"}}}, "resources"),
        (
            {"materials": {"source": {"file_version_id": "v2", "digest": DIGEST, "available": True}}},
            "materials",
        ),
        ({"capability_requirements": {"executor": {"class": "reasoning"}}}, "capability_requirements"),
        ({"compiled_keys": ("P1.1", "P1.2")}, "dependencies"),
        ({"start_request": {"overrides": {"budgets.run.max_usd": 20}, "selection": None}}, "config"),
        (
            {"satisfied": {"P1.0": {"source_task_id": "other", "compatibility_digest": DIGEST}}},
            "dependencies",
        ),
    ],
)
def test_snapshot_digest_binds_material_versions_packs_routing_and_request(change: Any, part: str) -> None:
    original = snapshot_readiness_inputs(snapshot())
    current = snapshot_readiness_inputs(snapshot(**change))
    differing = [key for key in asdict(original) if getattr(original, key) != getattr(current, key)]
    assert differing == [part]


def test_snapshot_excludes_transient_config_provenance_and_run_identity() -> None:
    original = snapshot()
    moved = replace(
        original,
        config_snapshot={
            **original.config_snapshot,
            "generation": 5,
            "provenance": {"host_time": NOW.isoformat()},
            "run_scope_id": str(UUID(int=99)),
        },
    )
    assert snapshot_readiness_inputs(original) == snapshot_readiness_inputs(moved)


def test_missing_route_observation_and_incomplete_policy_are_not_admission() -> None:
    report = evaluate_readiness(document(required_roles=["executor", "reviewer"], compiled_keys=["P1.1"]))
    assert report.status is ReadinessStatus.NOT_READY
    assert {f.code for f in report.findings} == {"POLICY_DENIES", "CAPABILITY_UNAVAILABLE"}


def test_canonical_owner_spec_design_state_and_criterion_links() -> None:
    report = evaluate_readiness(
        document(
            phases=[{"design_state": "detailed"}],
            requirements=[{"key": "R1"}],
            items=[{"implements": ["R1"]}],
            criteria=[{"key": "C1", "requirements": ["R1"], "checks": ["V1"]}],
            checks=[{"key": "V1", "kind": "external"}],
        )
    )
    assert report.status is ReadinessStatus.READY


def test_missing_check_reference_does_not_verify_a_criterion() -> None:
    report = evaluate_readiness(document(criteria=[{"key": "C1", "checks": ["missing"]}]))
    assert report.status is ReadinessStatus.NOT_READY
    assert {finding.code for finding in report.findings} == {"CRITERION_UNVERIFIED"}


def _scoped(key: str, *patterns: str) -> dict[str, Any]:
    return {"task_key": key, "write_scope": [{"mount": "repo", "pattern": p} for p in patterns]}


def test_write_scope_overlaps_names_independent_writers_of_a_shared_path() -> None:
    tasks = [
        _scoped("A", "src/**"),
        _scoped("B", "src/app/*.py"),
        _scoped("C", "docs/**"),
        {"task_key": "D", "write_scope": None},
        _scoped("G"),
    ]
    assert write_scope_overlaps(tasks, []) == ["A and B may both write repo:src/**"]


def test_write_scope_overlaps_ignores_ordered_tasks_and_other_mounts() -> None:
    tasks = [_scoped("A", "src/**"), _scoped("M", "x/**"), _scoped("B", "src/**")]
    chain = [{"dependent": "M", "prerequisite": "A"}, {"dependent": "B", "prerequisite": "M"}]
    assert write_scope_overlaps(tasks, chain) == []
    other = {"task_key": "B", "write_scope": [{"mount": "docs", "pattern": "src/**"}]}
    assert write_scope_overlaps([tasks[0], other], []) == []


_QUERY_REF = str(UUID(int=9))


@pytest.mark.parametrize(
    ("text", "evidence", "outcome"),
    [
        (None, {}, "skipped"),
        ("", {}, "failed"),
        ("unstructured research text", {}, "failed"),
        ("research-query:fake", {}, "failed"),
        (f"research-query:{_QUERY_REF}", {}, "failed"),
        (f"research-query:{_QUERY_REF}\nresearch-query:{UUID(int=8)}", {_QUERY_REF: DIGEST}, "failed"),
        (f"- research-query:{_QUERY_REF}", {_QUERY_REF: DIGEST}, "passed"),
    ],
)
def test_r15_requires_each_declared_design_query_to_have_admissible_evidence(text, evidence, outcome):
    sections = [] if text is None else [{"id": "design-research", "title": "Design research", "text": text}]
    report = evaluate_readiness(
        document(
            items=[{"id": str(UUID(int=10)), "sections": sections, "research": {"need": "required"}}],
            design_research_evidence=evidence,
        )
    )
    result = next(rule for rule in report.results if rule.rule_id == "R15_design_research")
    assert result.outcome == outcome
    assert (report.status is ReadinessStatus.NOT_READY) == (outcome == "failed")


@pytest.mark.parametrize("field", ["revision_digest", "inputs_digest", "policy_digest"])
def test_signed_report_digests_must_match(field: str) -> None:
    report = evaluate_readiness(document())
    with pytest.raises(SkmError) as stale:
        require_fresh(
            replace(report, **{field: canonical_digest("unexpected")}),
            report.inputs,
            now=NOW,
            revision_digest=report.revision_digest,
            max_age_seconds=600,
            start_request=document()["start_request"],
        )
    assert stale.value.details["stale_parts"] == [field]
