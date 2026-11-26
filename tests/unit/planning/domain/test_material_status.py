"""Unit tests for material availability and freshness assessment (planning §5.11)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.ids import EntityId, FileVersionId
from skm.modules.planning.domain.material import (
    Freshness,
    FreshnessPolicy,
    Material,
    MaterialKind,
    MaterialStage,
    material_to_doc,
)
from skm.modules.planning.domain.material_status import (
    MaterialAssessment,
    MaterialObservation,
    MaterialState,
    assess_material,
)
from skm.modules.planning.domain.validation.context import FileVersionObservation, FileVersionStatus

NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)
MAT_ID = EntityId(UUID("0192f5c3-0000-7000-8000-000000000010"))
FV_ID = FileVersionId(UUID("0192f5c3-0000-7000-8000-000000000099"))


def _make_material(
    kind: MaterialKind = MaterialKind.FILE_VERSION,
    *,
    policy: FreshnessPolicy = FreshnessPolicy.PINNED,
    max_age_seconds: int | None = None,
    required_for: tuple[MaterialStage, ...] = (MaterialStage.EXECUTION, MaterialStage.REVIEW),
    retrieved_at: datetime | None = None,
) -> Material:
    return Material(
        id=MAT_ID,
        key="mat-1",
        title="Material 1",
        kind=kind,
        file_version_id=FV_ID if kind is MaterialKind.FILE_VERSION else None,
        mount="repo" if kind is MaterialKind.REPOSITORY_PATH else None,
        path="docs/spec.md" if kind is MaterialKind.REPOSITORY_PATH else None,
        url="https://example.com/spec" if kind is MaterialKind.EXTERNAL_SOURCE else None,
        retrieved_at=retrieved_at,
        content_digest="sha256:" + "a" * 64 if kind is MaterialKind.EXTERNAL_SOURCE else None,
        selector=None,
        role="input",
        required_for=required_for,
        freshness=Freshness(policy=policy, max_age_seconds=max_age_seconds),
        why="Needed for execution",
        applies_to=("P1.1",),
        is_global=False,
    )


def _obs_fv(status: FileVersionStatus, created_at: datetime | None = None) -> MaterialObservation:
    return MaterialObservation(
        file_version=FileVersionObservation(status=status, created_at=created_at),
        checkout_has_path=None,
    )


def _obs_path(checkout_has_path: bool | None) -> MaterialObservation:
    return MaterialObservation(
        file_version=None,
        checkout_has_path=checkout_has_path,
    )


@pytest.mark.parametrize(
    "policy",
    [FreshnessPolicy.PINNED, FreshnessPolicy.LATEST_AT_PUBLISH],
)
def test_file_version_ready_pinned_and_latest_at_publish_are_available(policy: FreshnessPolicy) -> None:
    created = NOW - timedelta(days=30)
    mat = _make_material(MaterialKind.FILE_VERSION, policy=policy)
    obs = _obs_fv(FileVersionStatus.READY, created)

    result = assess_material(mat, obs, now=NOW)
    assert result.material_id == MAT_ID
    assert result.state is MaterialState.AVAILABLE
    assert result.age_seconds == int(timedelta(days=30).total_seconds())
    assert result.blocks == frozenset()
    assert assess_material(material_to_doc(mat), obs, now=NOW) == result


def test_file_version_ready_must_refresh_within_max_age_is_available() -> None:
    created = NOW - timedelta(seconds=300)
    mat = _make_material(
        MaterialKind.FILE_VERSION,
        policy=FreshnessPolicy.MUST_REFRESH,
        max_age_seconds=300,
    )
    obs = _obs_fv(FileVersionStatus.READY, created)

    result = assess_material(mat, obs, now=NOW)
    assert result.state is MaterialState.AVAILABLE
    assert result.age_seconds == 300
    assert result.blocks == frozenset()
    assert assess_material(material_to_doc(mat), obs, now=NOW) == result


def test_file_version_ready_must_refresh_exceeding_max_age_is_stale_and_blocks() -> None:
    created = NOW - timedelta(seconds=301)
    mat = _make_material(
        MaterialKind.FILE_VERSION,
        policy=FreshnessPolicy.MUST_REFRESH,
        max_age_seconds=300,
        required_for=(MaterialStage.EXECUTION, MaterialStage.ACCEPTANCE),
    )
    obs = _obs_fv(FileVersionStatus.READY, created)

    result = assess_material(mat, obs, now=NOW)
    assert result.state is MaterialState.STALE
    assert result.age_seconds == 301
    assert result.blocks == frozenset({MaterialStage.EXECUTION, MaterialStage.ACCEPTANCE})
    assert "301s" in result.reason
    assert assess_material(material_to_doc(mat), obs, now=NOW) == result


def test_file_version_ready_must_refresh_with_unknown_timestamp_is_stale() -> None:
    mat = _make_material(
        MaterialKind.FILE_VERSION,
        policy=FreshnessPolicy.MUST_REFRESH,
        max_age_seconds=300,
        required_for=(MaterialStage.EXECUTION,),
    )
    obs = _obs_fv(FileVersionStatus.READY, None)

    result = assess_material(mat, obs, now=NOW)
    assert result.state is MaterialState.STALE
    assert result.age_seconds is None
    assert result.blocks == frozenset({MaterialStage.EXECUTION})
    assert assess_material(material_to_doc(mat), obs, now=NOW) == result


def test_file_version_not_ready_blocks_required_stages() -> None:
    mat = _make_material(
        MaterialKind.FILE_VERSION,
        required_for=(MaterialStage.REVIEW,),
    )
    obs = _obs_fv(FileVersionStatus.NOT_READY, NOW - timedelta(seconds=10))

    result = assess_material(mat, obs, now=NOW)
    assert result.state is MaterialState.NOT_READY
    assert result.age_seconds is None
    assert result.blocks == frozenset({MaterialStage.REVIEW})
    assert assess_material(material_to_doc(mat), obs, now=NOW) == result


@pytest.mark.parametrize(
    "observation",
    [
        None,
        MaterialObservation(file_version=None, checkout_has_path=None),
        _obs_fv(FileVersionStatus.MISSING, None),
        _obs_fv(FileVersionStatus.OTHER_WORKSPACE, None),
    ],
)
def test_file_version_missing_or_other_workspace_is_missing_and_blocks(
    observation: MaterialObservation | None,
) -> None:
    mat = _make_material(
        MaterialKind.FILE_VERSION,
        required_for=(MaterialStage.EXECUTION, MaterialStage.REVIEW),
    )

    result = assess_material(mat, observation, now=NOW)
    assert result.state is MaterialState.MISSING
    assert result.age_seconds is None
    assert result.blocks == frozenset({MaterialStage.EXECUTION, MaterialStage.REVIEW})
    assert assess_material(material_to_doc(mat), observation, now=NOW) == result


@pytest.mark.parametrize("observation", [None, _obs_path(None)])
def test_repository_path_without_checkout_observation_is_unknown_and_never_blocks(
    observation: MaterialObservation | None,
) -> None:
    mat = _make_material(
        MaterialKind.REPOSITORY_PATH,
        required_for=(MaterialStage.EXECUTION, MaterialStage.REVIEW, MaterialStage.ACCEPTANCE),
    )

    result = assess_material(mat, observation, now=NOW)
    assert result.state is MaterialState.UNKNOWN
    assert result.age_seconds is None
    assert result.blocks == frozenset()
    assert assess_material(material_to_doc(mat), observation, now=NOW) == result


def test_repository_path_present_in_checkout_is_available() -> None:
    mat = _make_material(
        MaterialKind.REPOSITORY_PATH,
        required_for=(MaterialStage.EXECUTION,),
    )
    obs = _obs_path(True)

    result = assess_material(mat, obs, now=NOW)
    assert result.state is MaterialState.AVAILABLE
    assert result.age_seconds is None
    assert result.blocks == frozenset()
    assert assess_material(material_to_doc(mat), obs, now=NOW) == result


def test_repository_path_absent_in_checkout_is_missing_and_blocks() -> None:
    mat = _make_material(
        MaterialKind.REPOSITORY_PATH,
        required_for=(MaterialStage.EXECUTION, MaterialStage.ACCEPTANCE),
    )
    obs = _obs_path(False)

    result = assess_material(mat, obs, now=NOW)
    assert result.state is MaterialState.MISSING
    assert result.age_seconds is None
    assert result.blocks == frozenset({MaterialStage.EXECUTION, MaterialStage.ACCEPTANCE})
    assert assess_material(material_to_doc(mat), obs, now=NOW) == result


@pytest.mark.parametrize(
    "policy",
    [FreshnessPolicy.PINNED, FreshnessPolicy.LATEST_AT_PUBLISH],
)
def test_external_source_pinned_and_latest_at_publish_are_available(policy: FreshnessPolicy) -> None:
    mat = _make_material(
        MaterialKind.EXTERNAL_SOURCE,
        policy=policy,
        retrieved_at=NOW - timedelta(days=365),
    )

    result = assess_material(mat, None, now=NOW)
    assert result.state is MaterialState.AVAILABLE
    assert result.age_seconds == int(timedelta(days=365).total_seconds())
    assert result.blocks == frozenset()
    assert assess_material(material_to_doc(mat), None, now=NOW) == result


def test_external_source_must_refresh_fresh_vs_stale_vs_missing_timestamp() -> None:
    fresh_mat = _make_material(
        MaterialKind.EXTERNAL_SOURCE,
        policy=FreshnessPolicy.MUST_REFRESH,
        max_age_seconds=3600,
        retrieved_at=NOW - timedelta(seconds=1800),
        required_for=(MaterialStage.EXECUTION,),
    )
    fresh_res = assess_material(fresh_mat, None, now=NOW)
    assert fresh_res == MaterialAssessment(
        material_id=MAT_ID,
        state=MaterialState.AVAILABLE,
        age_seconds=1800,
        reason="material is fresh",
        blocks=frozenset(),
    )
    assert assess_material(material_to_doc(fresh_mat), None, now=NOW) == fresh_res

    stale_mat = replace(fresh_mat, retrieved_at=NOW - timedelta(seconds=3601))
    stale_res = assess_material(stale_mat, None, now=NOW)
    assert stale_res.state is MaterialState.STALE
    assert stale_res.age_seconds == 3601
    assert stale_res.blocks == frozenset({MaterialStage.EXECUTION})
    assert assess_material(material_to_doc(stale_mat), None, now=NOW) == stale_res

    unretrieved_mat = replace(fresh_mat, retrieved_at=None)
    unretrieved_res = assess_material(unretrieved_mat, None, now=NOW)
    assert unretrieved_res.state is MaterialState.STALE
    assert unretrieved_res.age_seconds is None
    assert unretrieved_res.blocks == frozenset({MaterialStage.EXECUTION})
    assert assess_material(material_to_doc(unretrieved_mat), None, now=NOW) == unretrieved_res


def test_material_ref_dict_with_material_id_and_default_freshness() -> None:
    raw_ref: dict[str, Any] = {
        "material_id": str(MAT_ID),
        "kind": "external_source",
        "required_for": ["review"],
    }
    res = assess_material(raw_ref, None, now=NOW)
    assert res.material_id == MAT_ID
    assert res.state is MaterialState.AVAILABLE
    assert res.age_seconds is None
    assert res.blocks == frozenset()


def test_sub_second_staleness_boundary_is_stale_and_consistent() -> None:
    created = NOW - timedelta(seconds=300, milliseconds=500)
    mat = _make_material(
        MaterialKind.FILE_VERSION,
        policy=FreshnessPolicy.MUST_REFRESH,
        max_age_seconds=300,
        required_for=(MaterialStage.EXECUTION,),
    )
    obs = _obs_fv(FileVersionStatus.READY, created)

    result = assess_material(mat, obs, now=NOW)
    assert result.state is MaterialState.STALE
    assert result.age_seconds == 301
    assert "301s" in result.reason
    assert result.blocks == frozenset({MaterialStage.EXECUTION})
    assert assess_material(material_to_doc(mat), obs, now=NOW) == result


def test_missing_material_id_in_mapping_raises_clear_value_error() -> None:
    with pytest.raises(ValueError, match="material id is required"):
        assess_material({"kind": "external_source"}, None, now=NOW)

    with pytest.raises(ValueError, match="material id is required"):
        assess_material({"id": None, "material_id": None, "kind": "external_source"}, None, now=NOW)
