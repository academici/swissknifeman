"""Effective work policy (execution §4.2.1)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.work_policy import (
    DEFAULT_POLICY_KEY,
    DEFAULT_REPRO_WARN_SECONDS,
    DEFAULT_ROLE_WARN_SECONDS,
    ROLE_NAMES,
    EffectiveWorkPolicy,
    HardCeilings,
    Intensity,
    SettingSource,
    WorkPolicyOverride,
    WorkPolicySettings,
    derive_group_policy,
    policy_digest,
    remaining_emergency_seconds,
    resolve_work_policy,
    soft_warnings,
    synthetic_work_policy,
    work_policy_from_json,
    work_policy_to_json,
)
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / "tests/fixtures/corpus/examples/execution/execution-bundle.json"
URN = "urn:skm:execution:work-policy:v1"
L, M, H = Intensity.LIGHT, Intensity.MEDIUM, Intensity.HEAVY
# the frozen hard ceilings behind the example bundle: profile timeouts, role walls and no step wall
CEILINGS = HardCeilings(
    profile_timeout_seconds={
        "scout": 900, "executor": 3600, "reviewer": None, "triager": 900, "advisor": None,
        "researcher": None, "registrar": 300,
    },
    role_wall_seconds={
        "scout": 1800, "executor": 14400, "reviewer": 1800, "triager": 1800, "advisor": 1800,
        "researcher": 1800, "registrar": 1800,
    },
    step_wall_seconds=0,
)  # fmt: skip


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def settings(**changes: Any) -> WorkPolicySettings:
    values: dict[str, Any] = {"role_intensity": dict.fromkeys(ROLE_NAMES, M), "verification_intensity": M}
    values.update(changes)
    return WorkPolicySettings(**values)


def roles(policy: EffectiveWorkPolicy, side: str = "effective") -> dict[str, str]:
    document = cast("JsonObject", getattr(policy, side))
    return cast("dict[str, str]", document["role_intensity"])


# --- defaults


def test_defaults_reproduce_the_example_bundle_policy() -> None:
    policy = resolve_work_policy(WorkPolicySettings.defaults(), ceilings=CEILINGS)
    example = json.loads(BUNDLE.read_text(encoding="utf-8"))["work_policies"][DEFAULT_POLICY_KEY]
    assert work_policy_to_json(policy) == example
    assert registry().validate(URN, work_policy_to_json(policy)) == ()
    assert work_policy_from_json(example) == policy


def test_default_matrix_is_the_soft_warning_table() -> None:
    assert {role: tuple(DEFAULT_ROLE_WARN_SECONDS[role].values()) for role in ROLE_NAMES} == {
        "scout": (300, 600, 900), "executor": (900, 1800, 3600), "reviewer": (180, 300, 600),
        "triager": (90, 180, 300), "advisor": (180, 300, 600), "researcher": (300, 900, 1800),
        "registrar": (30, 60, 90),
    }  # fmt: skip
    assert tuple(DEFAULT_REPRO_WARN_SECONDS.values()) == (30, 60, 90)


# --- settings -> item -> unit


def test_item_then_unit_override_and_unit_inherits_its_item() -> None:
    item = WorkPolicyOverride({"executor": H, "reviewer": H}, verification_intensity=H)
    unit = WorkPolicyOverride({"reviewer": L})
    policy = resolve_work_policy(settings(), item=item, unit=unit, item_ref="P1.1", unit_ref="P1.1/U1")
    assert roles(policy)["executor"] == "heavy"  # inherited from the item
    assert roles(policy)["reviewer"] == "light"  # the unit wins
    assert roles(policy)["scout"] == "medium"
    assert cast("JsonObject", policy.effective)["verification_intensity"] == "heavy"
    assert policy.role_warn_seconds["executor"] == 3600
    assert policy.role_warn_seconds["reviewer"] == 180
    sources = {entry["field"]: (entry["source"], entry["ref"]) for entry in policy.provenance}
    assert sources["role_intensity.executor"] == ("item", "P1.1")
    assert sources["role_intensity.reviewer"] == ("unit", "P1.1/U1")
    assert sources["role_intensity.scout"] == ("default", "execution.work_policy.role_intensity")
    assert sources["verification_intensity"] == ("item", "P1.1")


def test_reset_removes_an_override_and_the_settings_value_returns() -> None:
    overridden = resolve_work_policy(settings(), item=WorkPolicyOverride({"executor": H}))
    reset = resolve_work_policy(settings(), item=WorkPolicyOverride())
    assert roles(overridden)["executor"] == "heavy"
    assert reset == resolve_work_policy(settings())
    assert WorkPolicyOverride.from_json(None) is None
    assert WorkPolicyOverride.from_json({}) == WorkPolicyOverride()
    with pytest.raises(SkmError):
        WorkPolicyOverride.from_json({"role_intensity": {"executor": "heavy"}, "timeout": 5})


def test_locked_fields_keep_the_settings_value_and_say_why() -> None:
    locked = settings(
        role_intensity={**dict.fromkeys(ROLE_NAMES, M), "reviewer": H},
        sources={
            "role_intensity.reviewer": SettingSource(
                "settings", "execution.work_policy.role_intensity@workspace"
            )
        },
        locks={"role_intensity.reviewer": "workspace", "verification_intensity": "instance"},
    )
    item = WorkPolicyOverride({"reviewer": L, "executor": H}, verification_intensity=L)
    policy = resolve_work_policy(locked, item=item, item_ref="P1.1")
    assert roles(policy, "requested")["reviewer"] == "light"
    assert roles(policy)["reviewer"] == "heavy"
    assert roles(policy)["executor"] == "heavy"  # not locked
    assert cast("JsonObject", policy.requested)["verification_intensity"] == "light"
    assert cast("JsonObject", policy.effective)["verification_intensity"] == "medium"
    assert policy.clamps == (
        "locked:role_intensity.reviewer:workspace",
        "locked:verification_intensity:instance",
    )
    sources = {entry["field"]: (entry["source"], entry["ref"]) for entry in policy.provenance}
    assert sources["role_intensity.reviewer"] == (
        "settings",
        "execution.work_policy.role_intensity@workspace",
    )
    whole = settings(locks={"role_intensity": "project"})
    assert roles(resolve_work_policy(whole, item=item)) == dict.fromkeys(ROLE_NAMES, "medium")


def test_provenance_and_digest_are_deterministic() -> None:
    item = WorkPolicyOverride({"triager": H, "scout": L})
    first = resolve_work_policy(settings(), item=item, ceilings=CEILINGS)
    second = resolve_work_policy(
        settings(), item=WorkPolicyOverride({"scout": L, "triager": H}), ceilings=CEILINGS
    )
    assert first == second
    fields = [str(entry["field"]) for entry in first.provenance]
    assert fields == sorted(fields)
    assert policy_digest(first) == first.digest
    moved = resolve_work_policy(settings(), item=item, item_ref="other-ref", ceilings=CEILINGS)
    assert moved.digest == first.digest  # provenance is not part of the digest
    assert moved.provenance != first.provenance


def test_intensity_never_changes_the_emergency_ceilings() -> None:
    light = resolve_work_policy(settings(role_intensity=dict.fromkeys(ROLE_NAMES, L)), ceilings=CEILINGS)
    heavy = resolve_work_policy(settings(role_intensity=dict.fromkeys(ROLE_NAMES, H)), ceilings=CEILINGS)
    assert light.emergency_role_seconds == heavy.emergency_role_seconds
    assert light.emergency_role_seconds["reviewer"] == 1800  # the reviewer wall at every intensity
    assert light.role_warn_seconds["reviewer"] == 180
    assert heavy.role_warn_seconds["reviewer"] == 600
    none = resolve_work_policy(settings())
    assert set(none.emergency_role_seconds.values()) == {None}
    step = resolve_work_policy(
        settings(), ceilings=HardCeilings(role_wall_seconds={"executor": 14400}, step_wall_seconds=600)
    )
    assert step.emergency_role_seconds["executor"] == 600


# --- soft warnings and the clock


def test_an_overrun_is_a_warning_not_a_refusal() -> None:
    policy = resolve_work_policy(settings(), ceilings=CEILINGS)
    assert soft_warnings(policy, "reviewer", elapsed_seconds=200) == ()
    warnings = soft_warnings(policy, "reviewer", elapsed_seconds=301)
    assert [(found.kind, found.expected_seconds, found.actual_seconds) for found in warnings] == [
        ("role", 300, 301)
    ]
    triage = soft_warnings(policy, "triager", elapsed_seconds=10, repro_seconds=61)
    assert [(found.kind, found.expected_seconds) for found in triage] == [("reproduction", 60)]
    # far past the warning the work may still go on: the emergency ceiling is the only hard limit
    started = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    remaining = remaining_emergency_seconds(
        policy, "reviewer", started_at=started, now=started + timedelta(seconds=900)
    )
    assert remaining == 900


def test_a_fake_clock_changes_the_remaining_time_but_not_the_frozen_digest() -> None:
    policy = resolve_work_policy(settings(), ceilings=CEILINGS)
    digest = policy.digest
    started = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    now = started
    seen = []
    for _ in range(3):
        now += timedelta(minutes=20)
        seen.append(remaining_emergency_seconds(policy, "executor", started_at=started, now=now))
        assert policy.digest == digest == policy_digest(policy)
    assert seen == [2400, 1200, 0]
    explicit = remaining_emergency_seconds(
        policy, "executor", started_at=started, now=started, extra_ceilings=(600, None, 0)
    )
    assert explicit == 600
    assert (
        remaining_emergency_seconds(resolve_work_policy(settings()), "executor", started_at=started, now=now)
        is None
    )


# --- synthetic and group tasks


def frozen_policies() -> dict[str, EffectiveWorkPolicy]:
    return {
        DEFAULT_POLICY_KEY: resolve_work_policy(settings(), ceilings=CEILINGS),
        "P1.1/U1": resolve_work_policy(
            settings(), item=WorkPolicyOverride({"executor": H}), ceilings=CEILINGS
        ),
    }


def test_synthetic_tasks_inherit_their_source_or_use_the_default() -> None:
    policies = frozen_policies()
    assert (
        synthetic_work_policy("integration", source_key="P1.1/U1", policies=policies) is policies["P1.1/U1"]
    )
    assert synthetic_work_policy("followup", source_key="P1.1/U1", policies=policies) is policies["P1.1/U1"]
    assert (
        synthetic_work_policy("plan_audit", source_key=None, policies=policies)
        is policies[DEFAULT_POLICY_KEY]
    )
    for source in (None, "P9.9/U1", DEFAULT_POLICY_KEY):
        with pytest.raises(SkmError) as caught:
            synthetic_work_policy("integration", source_key=source, policies=policies)
        assert caught.value.code is ErrorCode.INVALID_REFERENCE


def test_group_review_takes_max_intensity_and_min_emergency() -> None:
    small = HardCeilings(profile_timeout_seconds={"reviewer": 600}, role_wall_seconds={"reviewer": 1800})
    first = resolve_work_policy(
        settings(), item=WorkPolicyOverride({"reviewer": H}, verification_intensity=L), ceilings=CEILINGS
    )
    second = resolve_work_policy(
        settings(),
        item=WorkPolicyOverride({"reviewer": L, "scout": H}, verification_intensity=H),
        ceilings=small,
    )
    group = derive_group_policy({"task-b": second, "task-a": first}, settings())
    assert roles(group)["reviewer"] == "heavy"
    assert roles(group)["scout"] == "heavy"
    assert cast("JsonObject", group.effective)["verification_intensity"] == "heavy"
    assert group.role_warn_seconds["reviewer"] == 600
    assert group.emergency_role_seconds["reviewer"] == 600  # minimum positive member ceiling
    assert group.emergency_role_seconds["executor"] == 3600
    refs = [str(entry["ref"]) for entry in group.provenance]
    assert refs == sorted(refs, key=lambda ref: ref.split(":", 1)[0])
    assert refs[0].startswith("task-a:")
    assert derive_group_policy({"task-a": first, "task-b": second}, settings()) == group
    with pytest.raises(SkmError):
        derive_group_policy({}, settings())


def test_group_requested_and_effective_aggregate_separately() -> None:
    locked = settings(locks={"role_intensity.executor": "instance"})
    member = resolve_work_policy(locked, item=WorkPolicyOverride({"executor": H}))
    group = derive_group_policy({"a": member, "b": resolve_work_policy(locked)}, locked)
    assert roles(group, "requested")["executor"] == "heavy"
    assert roles(group)["executor"] == "medium"
    assert group.clamps == ("locked:role_intensity.executor:instance",)


# --- settings validation


@pytest.mark.parametrize(
    "changes",
    [
        {"role_warn_seconds": {**DEFAULT_ROLE_WARN_SECONDS, "reviewer": {L: 600, M: 300, H: 900}}},
        {"role_warn_seconds": {**DEFAULT_ROLE_WARN_SECONDS, "reviewer": {L: 0, M: 300, H: 600}}},
        {"role_warn_seconds": {role: DEFAULT_ROLE_WARN_SECONDS[role] for role in ROLE_NAMES[:-1]}},
        {"repro_warn_seconds": {L: 30, M: 60}},
        {"repro_warn_seconds": {L: 30, M: 60, H: 4000}},
        {"role_intensity": {"executor": M}},
    ],
)
def test_work_policy_bounds_are_validated(changes: dict[str, Any]) -> None:
    with pytest.raises(SkmError) as caught:
        settings(**changes)
    assert caught.value.code is ErrorCode.CONFIG_INVALID


def test_a_tampered_frozen_policy_is_refused() -> None:
    document = work_policy_to_json(resolve_work_policy(settings(), ceilings=CEILINGS))
    document["role_warn_seconds"] = {**cast("dict[str, int]", document["role_warn_seconds"]), "executor": 1}
    with pytest.raises(SkmError, match="digest"):
        work_policy_from_json(document)


def test_resolved_maps_are_read_only() -> None:
    policy = resolve_work_policy(settings(), ceilings=CEILINGS)
    assert isinstance(policy.role_warn_seconds, MappingProxyType)
    with pytest.raises(TypeError):
        policy.emergency_role_seconds["executor"] = 1  # type: ignore[index]


def test_serialized_and_source_documents_never_change_the_frozen_policy() -> None:
    policy = resolve_work_policy(settings(), ceilings=CEILINGS)
    expected = work_policy_to_json(policy)
    returned = work_policy_to_json(policy)
    effective = cast("dict[str, Any]", returned["effective"])
    effective["role_intensity"]["executor"] = "light"
    cast("dict[str, Any]", returned["requested"])["verification_intensity"] = "heavy"
    cast("list[dict[str, Any]]", returned["provenance"])[0]["ref"] = "forged"
    cast("dict[str, Any]", returned["role_warn_seconds"])["executor"] = 1
    assert work_policy_to_json(policy) == expected
    assert policy_digest(policy) == policy.digest
    # deserialization copies its input too
    source = work_policy_to_json(policy)
    loaded = work_policy_from_json(source)
    cast("dict[str, Any]", source["effective"])["role_intensity"]["executor"] = "light"
    assert work_policy_to_json(loaded) == expected
    assert policy_digest(loaded) == loaded.digest
    assert registry().validate(URN, work_policy_to_json(loaded)) == ()
    roles_map = cast("Any", policy.effective["role_intensity"])
    with pytest.raises(TypeError):
        roles_map["executor"] = "light"
    with pytest.raises(TypeError):
        cast("Any", policy.provenance[0])["ref"] = "forged"
    # a derived group policy still reads the frozen maps
    group = derive_group_policy({"a": policy, "b": loaded}, settings())
    assert policy_digest(group) == group.digest


def test_the_resolver_imports_no_runtime_or_extension_module() -> None:
    probe = (
        "import sys\n"
        "import skm.modules.execution.domain.work_policy\n"
        "names = ('skm.modules.runtimes', 'skm.modules.extensions',\n"
        "         'skm.modules.execution.host', 'skm.modules.execution.generated')\n"
        "bad = sorted(m for m in sys.modules if m.startswith(names))\n"
        "print(bad)\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"
