"""Module settings.py: view reexports, VALIDATORS and the pure section validators (settings §B.8.3)."""

import importlib
from collections.abc import Mapping
from functools import cache
from typing import Any, cast

import pytest

from skm.kernel.json_types import JsonValue
from skm.platform.config.registry import SectionValidatorFn
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator

MODULES = [
    "access",
    "workspace",
    "artifacts",
    "policy",
    "execution",
    "runtimes",
    "extensions",
    "planning",
    "context",
    "integrations",
    "knowledge",
    "learning",
    "exports",
]
ROLES = ("scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar")
NO_VALIDATOR_MODULES = ("workspace", "artifacts", "policy", "runtimes", "extensions", "planning", "context")


@cache
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def settings_of(module: str) -> Any:
    return importlib.import_module(f"skm.modules.{module}.settings")


def all_validators() -> dict[str, SectionValidatorFn]:
    found: dict[str, SectionValidatorFn] = {}
    for module in MODULES:
        found.update(settings_of(module).VALIDATORS)
    return found


def leaf_node(key: str) -> Mapping[str, Any]:
    section, *path = key.split(".")
    node: Any = schemas().get(f"urn:skm:settings:{section}:v1")
    for name in path:
        node = node["properties"][name]
    return cast("Mapping[str, Any]", node)


def default_of(key: str) -> JsonValue:
    return cast("JsonValue", leaf_node(key)["default"])


def values_for(validator_id: str, **override: JsonValue) -> dict[str, JsonValue]:
    """Defaults of the validator's keys; ``override`` is keyed by the last key segment."""
    declared = declared_validators()[validator_id]
    values = {key: default_of(key) for key in cast("list[str]", declared["keys"])}
    for key in values:
        short = key.rsplit(".", 1)[-1]
        if short in override:
            values[key] = override[short]
    return values


@cache
def declared_validators() -> dict[str, Mapping[str, Any]]:
    found: dict[str, Mapping[str, Any]] = {}
    for urn in schemas().urns():
        meta = cast("Mapping[str, Any] | None", schemas().get(urn).get("x-skm-section"))
        if meta:
            for item in meta.get("validators", []):
                found[item["id"]] = item
    return found


def verdict(validator_id: str, **override: JsonValue) -> str | None:
    return all_validators()[validator_id](values_for(validator_id, **override))


def test_sections_and_views_match_the_generated_catalog() -> None:
    for module in MODULES:
        mod = settings_of(module)
        assert mod.SECTION_URNS, module
        assert set(mod.VIEWS) == {urn.split(":")[-2] for urn in mod.SECTION_URNS}
        for section_id, view in mod.VIEWS.items():
            assert section_id == view.SECTION
            assert f"urn:skm:settings:{section_id}:v1" == view.SCHEMA_URN
            assert view.__module__ == f"skm.modules.{module}.generated.settings"
            assert (
                cast("Mapping[str, Any]", schemas().get(view.SCHEMA_URN)["x-skm-section"])["owner"] == module
            )
        for urn in mod.SECTION_URNS:
            assert cast("Mapping[str, Any]", schemas().get(urn)["x-skm-section"])["owner"] == module


def test_settings_module_has_no_section() -> None:
    mod = importlib.import_module("skm.modules.settings.settings")
    assert mod.SECTION_URNS == ()
    assert not hasattr(mod, "VALIDATORS")


def test_every_declared_module_validator_has_one_callable_and_none_is_extra() -> None:
    declared = set(declared_validators())
    callbacks = all_validators()
    # platform validators and the parametrized hook callback are registered elsewhere
    assert declared - set(callbacks) == {"plugins.subsets", "integrations.hook_subscriptions"}
    assert set(callbacks) <= declared
    for module in NO_VALIDATOR_MODULES:
        assert dict(settings_of(module).VALIDATORS) == {}
    for module in MODULES:
        for validator_id in settings_of(module).VALIDATORS:
            owner = schemas().get(f"urn:skm:settings:{validator_id.split('.')[0]}:v1")
            assert cast("Mapping[str, Any]", owner["x-skm-section"])["owner"] == module


def test_declared_validators_accept_the_catalog_defaults() -> None:
    for validator_id in all_validators():
        assert verdict(validator_id) is None, validator_id


def test_validators_treat_absent_nullable_values_as_unknown() -> None:
    for validator_id, validator in all_validators().items():
        if validator_id == "execution.integration_mode_consistent":
            continue
        assert validator(dict.fromkeys(declared_validators()[validator_id]["keys"])) is None


@pytest.mark.parametrize(
    ("validator_id", "good", "bad"),
    [
        (
            "access.ttl_bounds",
            {"default_ttl_days": 30, "max_ttl_days": 30},
            {"default_ttl_days": 31, "max_ttl_days": 30},
        ),
        (
            "access.ttl_bounds",
            {"default_ttl_days": 0, "max_ttl_days": 0},
            {"default_ttl_days": 0, "max_ttl_days": 5},
        ),
        (
            "access.ttl_bounds",
            {"default_ttl_days": 400, "max_ttl_days": 0},
            {"default_ttl_days": 6, "max_ttl_days": 5},
        ),
        (
            "access.worker_rotation",
            {"worker_ttl_hours": 8, "worker_rotate_before_hours": 4},
            {"worker_ttl_hours": 8, "worker_rotate_before_hours": 5},
        ),
        (
            "execution.timeouts_consistent",
            {"idle_seconds": 100, "step_wall_seconds": 100},
            {"idle_seconds": 101, "step_wall_seconds": 100},
        ),
        (
            "execution.timeouts_consistent",
            {"idle_seconds": 500, "step_wall_seconds": 0},
            {"idle_seconds": 2, "step_wall_seconds": 1},
        ),
        (
            "execution.timeouts_consistent",
            {"idle_seconds": 0, "step_wall_seconds": 7},
            {"idle_seconds": 8, "step_wall_seconds": 7},
        ),
        (
            "execution.lease_renewal",
            {"ttl_seconds": 61, "renew_every_seconds": 30},
            {"ttl_seconds": 60, "renew_every_seconds": 30},
        ),
        (
            "execution.health_order",
            {"wait_grace_seconds": 5, "hung_after_seconds": 5, "idle_seconds": 5},
            {"wait_grace_seconds": 6, "hung_after_seconds": 5, "idle_seconds": 9},
        ),
        (
            "execution.health_order",
            {"wait_grace_seconds": 1, "hung_after_seconds": 99, "idle_seconds": 0},
            {"wait_grace_seconds": 1, "hung_after_seconds": 10, "idle_seconds": 9},
        ),
        (
            "execution.handoff_bounds",
            {"max_finding_chars": 100, "max_total_bytes": 100},
            {"max_finding_chars": 101, "max_total_bytes": 100},
        ),
        (
            "execution.integration_mode_consistent",
            {"commit_mode": "final_only", "strategy": "squash"},
            {"commit_mode": "implementation_and_fixes", "strategy": "squash"},
        ),
        (
            "execution.integration_mode_consistent",
            {"commit_mode": "per_stage_attributed", "strategy": "rebase"},
            {"commit_mode": "per_stage_attributed", "strategy": "squash"},
        ),
        (
            "execution.integration_mode_consistent",
            {"commit_mode": "implementation_and_fixes", "strategy": "rebase"},
            {"commit_mode": "implementation_and_fixes", "strategy": None},
        ),
        (
            "execution.integration_mode_consistent",
            {"commit_mode": "implementation_and_fixes", "strategy": "merge"},
            {"commit_mode": "implementation_and_fixes", "strategy": "bogus"},
        ),
        (
            "worker.isolation_default",
            {"available": ["worktree", "container"], "default_profile": "container"},
            {"available": ["worktree"], "default_profile": "container"},
        ),
        ("integrations.budget_order", {"target": 100, "warn": 100}, {"target": 101, "warn": 100}),
        (
            "knowledge.ttl_order",
            {"default_ttl_hours": 5, "max_ttl_hours": 5},
            {"default_ttl_hours": 6, "max_ttl_hours": 5},
        ),
        (
            "learning.pathology_order",
            {"pathology_min_hits": 3, "pathology_window": 3},
            {"pathology_min_hits": 4, "pathology_window": 3},
        ),
        (
            "exports.notes_ttl_order",
            {"pending_ttl_days": 7, "retention_days": 7},
            {"pending_ttl_days": 8, "retention_days": 7},
        ),
    ],
)
def test_boundary_cases(validator_id: str, good: dict[str, JsonValue], bad: dict[str, JsonValue]) -> None:
    for_good = _fill(validator_id, good)
    for_bad = _fill(validator_id, bad)
    validator = all_validators()[validator_id]
    assert validator(for_good) is None
    message = validator(for_bad)
    assert message is not None
    assert declared_validators()[validator_id]["keys"][0].split(".")[0] in message


def _fill(validator_id: str, given: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Defaults, then the given values (keyed by short name); ``max_usd``/``max_tokens`` set task and run."""
    values = values_for(validator_id)
    for key in values:
        short = key.rsplit(".", 1)[-1]
        if short in given:
            values[key] = given[short]
    return values


def test_budget_task_le_run_checks_usd_and_tokens_separately() -> None:
    def run(task_usd: float, run_usd: float, task_tokens: int, run_tokens: int) -> str | None:
        return all_validators()["budgets.task_le_run"](
            {
                "budgets.task.max_usd": task_usd,
                "budgets.run.max_usd": run_usd,
                "budgets.task.max_tokens": task_tokens,
                "budgets.run.max_tokens": run_tokens,
            }
        )

    assert run(5.0, 5.0, 10, 10) is None
    assert run(0, 5.0, 0, 10) is None  # task unlimited under a run limit is the tighter run budget's concern
    assert run(9.0, 0, 9, 0) is None  # run unlimited
    usd = run(5.01, 5.0, 1, 10)
    assert usd is not None
    assert "max_usd" in usd
    tokens = run(1.0, 5.0, 11, 10)
    assert tokens is not None
    assert "max_tokens" in tokens


@pytest.mark.parametrize(
    ("changes", "ok"),
    [
        ({}, True),
        ({"deprecate_conf": 0.5, "candidate_min_conf": 0.5}, False),  # strict
        ({"candidate_min_conf": 0.9, "curated_min_conf": 0.8}, False),
        ({"candidate_min_conf": 0.8, "curated_min_conf": 0.8}, True),
        ({"candidate_min_n_floor": 4, "candidate_min_n": 3}, False),
        ({"candidate_min_n": 9, "curated_min_n": 8}, False),
        ({"candidate_min_n_floor": 3, "candidate_min_n": 3, "curated_min_n": 3}, True),
    ],
)
def test_learning_thresholds_order(changes: dict[str, JsonValue], ok: bool) -> None:
    assert (verdict("learning.thresholds_order", **changes) is None) is ok


def good_warn() -> dict[str, JsonValue]:
    return cast("dict[str, JsonValue]", default_of("execution.work_policy.role_warn_seconds"))


def work_policy(
    roles: Mapping[str, JsonValue] | None = None, repro: Mapping[str, JsonValue] | None = None
) -> str | None:
    return all_validators()["execution.work_policy_bounds"](
        {
            "execution.work_policy.role_warn_seconds": cast(
                "JsonValue", roles if roles is not None else good_warn()
            ),
            "execution.work_policy.repro_warn_seconds": cast(
                "JsonValue",
                repro if repro is not None else default_of("execution.work_policy.repro_warn_seconds"),
            ),
        }
    )


def test_work_policy_defaults_cover_seven_roles_with_monotonic_thresholds() -> None:
    warn = good_warn()
    assert set(warn) == set(ROLES)
    for role in ROLES:
        steps = cast("dict[str, int]", warn[role])
        assert 0 < steps["light"] <= steps["medium"] <= steps["heavy"]
    assert work_policy() is None
    repro = cast("dict[str, int]", default_of("execution.work_policy.repro_warn_seconds"))
    assert 0 < repro["light"] <= repro["medium"] <= repro["heavy"]
    assert default_of("execution.work_policy.verification_intensity") == "medium"
    assert default_of("execution.work_policy.role_intensity") == dict.fromkeys(ROLES, "medium")


def test_work_policy_bounds_refuse_broken_thresholds() -> None:
    warn = good_warn()

    def with_role(role: str, steps: JsonValue) -> dict[str, JsonValue]:
        return {**warn, role: steps}

    assert (
        work_policy(with_role("executor", {"light": 10, "medium": 10, "heavy": 10})) is None
    )  # equal is monotonic
    refused = [
        with_role("executor", {"light": 20, "medium": 10, "heavy": 30}),
        with_role("executor", {"light": 10, "medium": 30, "heavy": 20}),
        with_role("executor", {"light": 0, "medium": 10, "heavy": 20}),
        with_role("executor", {"light": -1, "medium": 10, "heavy": 20}),
        with_role("executor", {"light": 10, "medium": 20}),
        with_role("executor", {"light": 10, "medium": 20, "heavy": 30, "extra": 40}),
        with_role("executor", {"light": 1.5, "medium": 20, "heavy": 30}),
        with_role("executor", {"light": True, "medium": 20, "heavy": 30}),
        with_role("executor", "heavy"),
        {**warn, "stranger": {"light": 1, "medium": 2, "heavy": 3}},
        {role: steps for role, steps in warn.items() if role != "registrar"},
    ]
    for roles in refused:
        assert work_policy(roles) is not None, roles
    assert work_policy(repro={"light": 90, "medium": 60, "heavy": 30}) is not None
    assert work_policy(repro={"light": 0, "medium": 60, "heavy": 90}) is not None
    assert work_policy(repro={"light": 30, "medium": 60}) is not None
    assert work_policy(repro={"light": 30, "medium": 60, "heavy": 90, "extreme": 100}) is not None


def leaf_issues(key: str, value: JsonValue) -> int:
    schema = {
        name: item for name, item in leaf_node(key).items() if name not in ("x-skm", "default", "description")
    }
    return len(SchemaValidator(schema, schemas().registry).issues(value))


def test_work_policy_schemas_accept_partial_maps_and_refuse_unknown_names() -> None:
    intensity = "execution.work_policy.role_intensity"
    assert leaf_issues(intensity, {}) == 0
    assert leaf_issues(intensity, {"executor": "heavy"}) == 0  # a partial map is merged over the default
    assert leaf_issues(intensity, {"boss": "light"}) > 0
    assert leaf_issues(intensity, {"executor": "extreme"}) > 0
    verification = "execution.work_policy.verification_intensity"
    assert leaf_issues(verification, "heavy") == 0
    assert leaf_issues(verification, "extreme") > 0
    warn = "execution.work_policy.role_warn_seconds"
    assert leaf_issues(warn, {"executor": {"light": 1, "medium": 2, "heavy": 3}}) == 0
    assert leaf_issues(warn, {"executor": {"light": -1, "medium": 2, "heavy": 3}}) > 0
    assert leaf_issues(warn, {"executor": {"light": 1, "medium": 2}}) > 0
    assert leaf_issues(warn, {"boss": {"light": 1, "medium": 2, "heavy": 3}}) > 0
    repro = "execution.work_policy.repro_warn_seconds"
    assert leaf_issues(repro, {"light": 5}) == 0
    assert leaf_issues(repro, {"extreme": 5}) > 0
    assert leaf_issues(repro, {"light": -5}) > 0


def test_budget_and_timeout_defaults_of_the_work_policy_card() -> None:
    assert default_of("budgets.task.warn_tokens") == 100000
    assert default_of("budgets.task.max_tokens") == 0
    assert default_of("budgets.run.max_tokens") == 0
    walls = cast("dict[str, int]", default_of("execution.timeouts.role_wall_seconds"))
    assert walls["reviewer"] == 1800
    assert default_of("execution.work_policy.role_intensity") == dict.fromkeys(ROLES, "medium")
    # the emergency wall is keyed by role only: no intensity changes it
    assert "light" not in walls
    assert "medium" not in walls
    assert "heavy" not in walls
