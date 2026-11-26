"""Task contract digest and scout reuse key (runtimes §4.11 rule 4, execution §5.2)."""

from __future__ import annotations

import copy
import re
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.modules.execution.domain.contract_digest import (
    SCOUT_REUSE_FIELDS,
    TASK_CONTRACT_FIELDS,
    scout_reuse_key,
    task_contract_digest,
)

POLICY_DIGEST = "sha256:" + "a1" * 32
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def entity(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "goal": "rotate tokens",
        "instructions": ["read the spec", "write the code"],
        "deliverables": ["src/auth/rotation.py"],
        "outputs": [{"kind": "code"}],
        "declared_write_scope": [
            {"mount": "api", "pattern": "src/auth/**"},
            {"mount": "api", "pattern": "tests/auth/**"},
        ],
        "criteria": [{"id": "AC1", "text": "tokens rotate"}, {"id": "AC2", "text": "old tokens die"}],
        "check_specs": [
            {"id": "V1", "kind": "command", "definition": {"argv": ["pytest", "tests/auth"]}},
            {"id": "V2", "kind": "manual", "definition": {"procedure": "look at the page"}},
        ],
        "review_requirement": {"mode": "required"},
        "declared_work_policy": {"role_intensity": {"executor": "heavy"}},
    }
    return {**base, **changes}


def digest(**changes: Any) -> str:
    return task_contract_digest(entity(**changes), POLICY_DIGEST)


# ---------------------------------------------------------------- task_contract_digest


def test_digest_is_stable_and_well_formed() -> None:
    first = task_contract_digest(entity(), POLICY_DIGEST)
    assert DIGEST.fullmatch(first)
    assert first == task_contract_digest(copy.deepcopy(entity()), POLICY_DIGEST)
    reordered = dict(reversed(list(entity().items())))
    assert task_contract_digest(reordered, POLICY_DIGEST) == first  # key order is not content


@pytest.mark.parametrize(
    "changes",
    [
        {"goal": "rotate the tokens"},
        {"instructions": ["read the spec"]},
        {"deliverables": ["src/auth/other.py"]},
        {"outputs": [{"kind": "docs"}]},
        {"declared_write_scope": [{"mount": "api", "pattern": "src/**"}]},
        {"declared_write_scope": None},
        {"criteria": [{"id": "AC1", "text": "tokens rotate"}]},
        {"review_requirement": {"mode": "self"}},
        {"declared_work_policy": {"role_intensity": {"executor": "light"}}},
        {"check_specs": [{"id": "V1", "kind": "command", "definition": {"argv": ["pytest"]}}]},
        {"check_specs": [{"id": "V1", "kind": "manual", "definition": {"argv": ["pytest", "tests/auth"]}}]},
    ],
)
def test_every_contract_field_changes_the_digest(changes: dict[str, Any]) -> None:
    assert digest(**changes) != digest()


def test_every_declared_field_is_covered() -> None:
    assert set(TASK_CONTRACT_FIELDS) == {
        "goal",
        "instructions",
        "deliverables",
        "outputs",
        "declared_write_scope",
        "criteria",
        "check_specs",
        "review_requirement",
        "declared_work_policy",
    }
    for field in TASK_CONTRACT_FIELDS:
        without = {key: value for key, value in entity().items() if key != field}
        assert task_contract_digest(without, POLICY_DIGEST) != digest(), (
            field
        )  # absent is null, not the same value


def test_wording_of_guidance_and_rules_is_not_contract() -> None:
    base = digest()
    assert digest(guidance="try the new helper", rules=["be brief"], display_key="P7.3", notes="x") == base


def test_clock_and_remaining_time_do_not_change_the_digest() -> None:
    base = digest()
    assert (
        digest(
            deadline="2026-11-01T00:00:00Z", remaining_seconds=1234, now="2026-10-31T12:00:00Z", attempt_no=3
        )
        == base
    )


def test_effective_work_policy_digest_is_part_of_the_contract() -> None:
    other = "sha256:" + "b2" * 32
    assert task_contract_digest(entity(), other) != task_contract_digest(entity(), POLICY_DIGEST)
    with pytest.raises(ValueError, match="work policy digest"):
        task_contract_digest(entity(), "")


def test_sets_are_sorted_and_lists_keep_their_order() -> None:
    base = digest()
    scope = list(reversed(entity()["declared_write_scope"]))
    checks = list(reversed(entity()["check_specs"]))
    assert digest(declared_write_scope=scope, check_specs=checks) == base
    assert digest(criteria=list(reversed(entity()["criteria"]))) != base
    assert digest(declared_write_scope=[]) != digest(declared_write_scope=None)  # no writes is not unknown


def test_check_spec_enters_as_id_kind_and_definition_digest() -> None:
    inline = digest()
    as_digest = [
        {"id": "V1", "kind": "command", "definition_digest": "sha256:" + "0" * 64},
        {"id": "V2", "kind": "manual", "definition_digest": "sha256:" + "1" * 64},
    ]
    assert digest(check_specs=as_digest) != inline
    noisy = [{**spec, "title": "renamed", "timeout": 99} for spec in entity()["check_specs"]]
    assert digest(check_specs=noisy) == inline  # only (id, kind, definition) is contract
    with pytest.raises(ValueError, match="check spec"):
        digest(check_specs=["V1"])
    with pytest.raises(ValueError, match="check_specs must be a list"):
        digest(check_specs={"id": "V1"})
    with pytest.raises(ValueError, match="declared_write_scope must be a list"):
        digest(declared_write_scope="src/**")


def test_not_a_json_document_is_refused() -> None:
    with pytest.raises(ValueError, match="Out of range"):
        digest(goal=float("nan"))
    with pytest.raises(ValueError, match="object"):
        task_contract_digest(["goal"], POLICY_DIGEST)  # type: ignore[arg-type]


@given(st.text(max_size=30), st.text(max_size=30))
def test_distinct_goals_have_distinct_digests(first: str, second: str) -> None:
    assert (digest(goal=first) == digest(goal=second)) == (first == second)


# ---------------------------------------------------------------- scout_reuse_key


def scout(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "project_id": "0193a000-0000-7000-8000-0000000000a1",
        "task_contract_digest": digest(),
        "baseline": [
            {"mount": "api", "commit_sha": "c" * 40, "dirty_patch_digest": None},
            {"mount": "web", "commit_sha": "d" * 40, "dirty_patch_digest": "sha256:" + "e" * 64},
        ],
        "scout_profile_resource_version_id": "0193a001-0000-7000-8000-000000000002",
        "context_policy_digest": "sha256:" + "f" * 64,
    }
    return {**base, **changes}


def test_scout_key_is_stable_and_well_formed() -> None:
    key = scout_reuse_key(scout())
    assert DIGEST.fullmatch(key)
    assert key == scout_reuse_key(copy.deepcopy(scout()))
    assert key == scout_reuse_key(dict(reversed(list(scout().items()))))
    assert key != digest()  # a key is not the contract digest


@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": "0193a000-0000-7000-8000-0000000000a2"},
        {"task_contract_digest": digest(goal="another goal")},
        {
            "task_contract_digest": task_contract_digest(entity(), "sha256:" + "b2" * 32)
        },  # another effective policy
        {"baseline": scout()["baseline"][:1]},
        {
            "baseline": [
                {"mount": "api", "commit_sha": "9" * 40, "dirty_patch_digest": None},
                scout()["baseline"][1],
            ]
        },
        {
            "baseline": [
                {"mount": "api", "commit_sha": "c" * 40, "dirty_patch_digest": "sha256:" + "1" * 64},
                scout()["baseline"][1],
            ]
        },
        {
            "scout_profile_resource_version_id": "0193a001-0000-7000-8000-000000000003"
        },  # a new profile version
        {"context_policy_digest": "sha256:" + "0" * 64},
    ],
)
def test_any_changed_input_is_a_new_key(changes: dict[str, Any]) -> None:
    assert scout_reuse_key(scout(**changes)) != scout_reuse_key(scout())


def test_baseline_is_a_set_and_accepts_triples() -> None:
    base = scout_reuse_key(scout())
    assert scout_reuse_key(scout(baseline=list(reversed(scout()["baseline"])))) == base
    triples = [["api", "c" * 40, None], ["web", "d" * 40, "sha256:" + "e" * 64]]
    assert scout_reuse_key(scout(baseline=triples)) == base
    assert scout_reuse_key(scout(baseline=[])) != base
    with pytest.raises(ValueError, match="baseline entry"):
        scout_reuse_key(scout(baseline=["api"]))
    with pytest.raises(ValueError, match="baseline must be a list"):
        scout_reuse_key(scout(baseline="api"))


def test_a_missing_or_extra_input_is_an_error() -> None:
    for name in SCOUT_REUSE_FIELDS:
        partial = {key: value for key, value in scout().items() if key != name}
        with pytest.raises(ValueError, match=f"missing \\['{name}'\\]"):
            scout_reuse_key(partial)
    with pytest.raises(ValueError, match="unexpected \\['run_id'\\]"):
        scout_reuse_key(
            scout(run_id="0193a000-0000-7000-8000-000000000001")
        )  # a run is not an input: reuse crosses runs


def test_time_and_attempt_are_not_inputs_of_the_key() -> None:
    """The contract digest the key is built from ignores the clock, so the key repeats between attempts."""
    first = scout(task_contract_digest=digest(remaining_seconds=900))
    later = scout(task_contract_digest=digest(remaining_seconds=10, attempt_no=2))
    assert scout_reuse_key(first) == scout_reuse_key(later)
