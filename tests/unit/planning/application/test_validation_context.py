"""Unit tests for assembling ValidationContext in planning application (planning §5.3, §5.8, §5.11)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.application_bus.context import CommandContext
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Conflict, NotFound, PreconditionFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import (
    EntityId,
    FileVersionId,
    PlanId,
    PrincipalId,
    ProjectId,
    ScopeId,
    WorkspaceId,
)
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef
from skm.modules.artifacts import public as artifacts
from skm.modules.extensions import public as extensions
from skm.modules.extensions.domain.resource import RuntimeCatalogEntry, RuntimeCatalogView
from skm.modules.planning.application.validation_context import build_validation_context
from skm.modules.planning.domain.plan import Plan, PlanLifecycle, PlanPurpose
from skm.modules.planning.domain.specification import EntityKind, from_document
from skm.modules.planning.domain.validation.context import (
    FileVersionObservation,
    FileVersionStatus,
)
from skm.modules.planning.domain.validation.pipeline import validate
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import PlanRepository, RevisionRepository
from skm.modules.workspace import public as workspace

NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)
URN = "urn:skm:planning:specification:v1"
WS_ID = WorkspaceId(UUID("0192f5c3-0000-7000-8000-000000000001"))
PROJ_ID = ProjectId(UUID("0192f5c3-0000-7000-8000-000000000002"))
PLAN_ID = PlanId(UUID("0192f5c3-0000-7000-8000-000000000003"))
OTHER_PLAN_ID = PlanId(UUID("0192f5c3-0000-7000-8000-000000000004"))
ACTOR_ID = PrincipalId(UUID("0192f5c3-0000-7000-8000-000000000005"))

PHASE_ID = UUID("0192f5c3-0000-7000-8000-000000000010")
ITEM_ID = UUID("0192f5c3-0000-7000-8000-000000000011")
CHECK_ID = UUID("0192f5c3-0000-7000-8000-000000000012")
MAT_READY_ID = UUID("0192f5c3-0000-7000-8000-000000000020")
MAT_MISSING_ID = UUID("0192f5c3-0000-7000-8000-000000000021")
MAT_OTHER_WS_ID = UUID("0192f5c3-0000-7000-8000-000000000022")
MAT_NOT_READY_ID = UUID("0192f5c3-0000-7000-8000-000000000023")

FV_READY = FileVersionId(UUID("0192f5c3-0000-7000-8000-000000000101"))
FV_MISSING = FileVersionId(UUID("0192f5c3-0000-7000-8000-000000000102"))
FV_OTHER_WS = FileVersionId(UUID("0192f5c3-0000-7000-8000-000000000103"))
FV_NOT_READY = FileVersionId(UUID("0192f5c3-0000-7000-8000-000000000104"))


def _default_settings(
    *,
    warn_unknown_skills: bool = True,
    warn_unknown_models: bool = True,
) -> PlanningSettings:
    return PlanningSettings.from_json(
        {
            "validation": {
                "require_acceptance_links": True,
                "warn_unknown_skills": warn_unknown_skills,
                "warn_unknown_models": warn_unknown_models,
                "external_checks": True,
                "external_failure": "warn",
                "code_suffixes": [".py", ".sql"],
                "heavy_check_markers": ["docker", "e2e"],
                "heavy_text_bytes": 4096,
            },
            "references": {"max_supersede_chain": 8},
            "design_audit": "none",
            "defaults": {
                "route_class": "implementation",
                "route_effort": "high",
                "review_mode": "required",
            },
            "drafts": {"max_document_bytes": 8388608, "max_open": 20},
            "aliases": {"prefix": "PLAN"},
            "display": {"tree_depth": 3},
        }
    )


def _make_plan() -> Plan:
    return Plan(
        id=PLAN_ID,
        workspace_id=WS_ID,
        project_id=PROJ_ID,
        alias="PLAN1",
        purpose=PlanPurpose.STANDARD,
        title="Webhooks",
        lifecycle=PlanLifecycle.ACTIVE,
        current_revision_id=None,
        next_revision_no=1,
        row_version=1,
        created_by=ACTOR_ID,
        created_at=NOW,
        updated_at=NOW,
        archived_at=None,
    )


def _base_doc(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema": URN,
        "title": "Webhooks",
        "goal": "Reliable delivery",
        "phases": [
            {
                "id": str(PHASE_ID),
                "key": "P1",
                "title": "Phase 1",
                "goal": "Core logic",
                "design_state": "detailed",
            }
        ],
        "items": [
            {
                "id": str(ITEM_ID),
                "key": "P1.1",
                "phase": "P1",
                "title": "Retry loop",
                "summary": "Implement retry loop",
                "why": "Resilience",
                "review": {"mode": "required", "max_rounds": 2},
                "verification": ["V1"],
            }
        ],
        "checks": [
            {
                "id": str(CHECK_ID),
                "key": "V1",
                "owner": "P1.1",
                "title": "Unit tests",
                "category": "acceptance",
                "kind": "command",
                "required": True,
                "definition": {"argv": ["pytest"], "cwd": {"mount": "api", "path": "."}},
            }
        ],
    }
    doc.update(overrides)
    return doc


class _FakeConfig:
    def __init__(self, settings: PlanningSettings) -> None:
        self._settings = settings

    def section(self, view_type: type[Any]) -> Any:
        assert view_type is PlanningSettings
        return self._settings


class _FakeRevisionRepo:
    def __init__(self, identities_map: Mapping[EntityId, EntityKind] | None = None) -> None:
        self._identities = dict(identities_map or {})
        self.called_with: list[PlanId] = []

    def identities(self, plan_id: PlanId) -> Mapping[EntityId, EntityKind]:
        self.called_with.append(plan_id)
        return self._identities


class _FakePlanRepo:
    def __init__(self, refs_map: Mapping[str, PlanId] | None = None) -> None:
        self._refs = dict(refs_map or {"PLAN1": PLAN_ID, "webhooks": PLAN_ID})
        self.called_with: list[ProjectId] = []

    def project_plan_refs(self, project_id: ProjectId) -> Mapping[str, PlanId]:
        self.called_with.append(project_id)
        return self._refs


class _FakeUoW:
    def __init__(
        self,
        revision_repo: _FakeRevisionRepo | None = None,
        plan_repo: _FakePlanRepo | None = None,
    ) -> None:
        self.revision_repo = revision_repo or _FakeRevisionRepo()
        self.plan_repo = plan_repo or _FakePlanRepo()

    def repo(self, port: type[Any]) -> Any:
        if port is RevisionRepository:
            return self.revision_repo
        if port is PlanRepository:
            return self.plan_repo
        raise KeyError(port)


def _make_ctx(
    settings: PlanningSettings | None = None,
    *,
    now: datetime = NOW,
) -> CommandContext:
    cfg = _FakeConfig(settings or _default_settings())
    inst_id = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
    scope_chain = (
        ScopeRecord(inst_id, ScopeKind.INSTANCE, None, None, now),
        ScopeRecord(ScopeId(WS_ID), ScopeKind.WORKSPACE, None, WS_ID, now),
        ScopeRecord(ScopeId(PROJ_ID), ScopeKind.PROJECT, ScopeId(WS_ID), WS_ID, now),
        ScopeRecord(ScopeId(PLAN_ID), ScopeKind.PLAN, ScopeId(PROJ_ID), WS_ID, now),
    )
    return CommandContext(
        actor=Actor(principal_id=ACTOR_ID, kind=PrincipalKind.HUMAN, display_name="owner"),
        scope=ScopeRef(ScopeKind.PLAN, ScopeId(PLAN_ID)),
        scope_chain=scope_chain,
        meta=RequestMeta("req_01", Surface.TEST, None, now),
        config=cast("Any", cfg),
        clock=FrozenClock(now),
        ids=SequentialIds(),
        entropy=DeterministicEntropy(),
        gateways=GatewayTable({}, "control_plane_gateway"),
        log=cast("Any", object()),
    )


@dataclass(frozen=True)
class _FakeFileVersionView:
    file_version_id: UUID
    created_at: datetime


def test_build_validation_context_populates_mounts_identities_and_project_plans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = {EntityId(PHASE_ID): EntityKind.PHASE, EntityId(ITEM_ID): EntityKind.ITEM}
    plan_refs = {"PLAN1": PLAN_ID, "webhooks": PLAN_ID, "PLAN2": OTHER_PLAN_ID, "auth": OTHER_PLAN_ID}
    uow = _FakeUoW(_FakeRevisionRepo(identities), _FakePlanRepo(plan_refs))
    ctx = _make_ctx()
    plan = _make_plan()

    monkeypatch.setattr(
        workspace,
        "project_mounts",
        lambda _u, pid: frozenset({"api", "web"}) if pid == PROJ_ID else frozenset(),
    )
    monkeypatch.setattr(extensions, "known_keys", lambda _u, _k, config=None: frozenset({"python", "sql"}))
    monkeypatch.setattr(extensions, "runtime_catalog", lambda _u, _sc, _cfg: None)

    doc = _base_doc()
    vctx = build_validation_context(cast("Any", uow), ctx, plan, document=doc)

    assert vctx.project_mounts == frozenset({"api", "web"})
    assert vctx.known_identities == identities
    assert vctx.project_plans == plan_refs
    assert vctx.known_skills == frozenset({"python", "sql"})
    assert vctx.runtime_catalog is None
    assert vctx.now == NOW
    assert vctx.document == doc
    assert vctx.spec.title == "Webhooks"
    assert uow.revision_repo.called_with == [PLAN_ID]
    assert uow.plan_repo.called_with == [PROJ_ID]


def test_build_validation_context_distinguishes_all_four_file_version_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = _FakeUoW()
    ctx = _make_ctx(
        _default_settings(warn_unknown_skills=False, warn_unknown_models=False),
    )
    plan = _make_plan()

    created_ready = NOW - timedelta(minutes=10)
    created_not_ready = NOW - timedelta(minutes=5)
    created_other_ws = NOW - timedelta(minutes=20)

    def fake_get_file_version(_uow: Any, version_id: FileVersionId) -> Any:
        if version_id == FV_READY:
            return _FakeFileVersionView(UUID(str(FV_READY)), created_ready)
        if version_id == FV_OTHER_WS:
            return _FakeFileVersionView(UUID(str(FV_OTHER_WS)), created_other_ws)
        if version_id == FV_NOT_READY:
            return _FakeFileVersionView(UUID(str(FV_NOT_READY)), created_not_ready)
        raise NotFound(ErrorCode.NOT_FOUND, "missing")

    def fake_require_ready(_uow: Any, ws_id: WorkspaceId, ids: tuple[FileVersionId, ...]) -> Any:
        assert ws_id == WS_ID
        vid = ids[0]
        if vid == FV_READY:
            return (_FakeFileVersionView(UUID(str(FV_READY)), created_ready),)
        if vid == FV_OTHER_WS:
            raise NotFound(ErrorCode.NOT_FOUND, "other workspace")
        if vid == FV_NOT_READY:
            raise PreconditionFailed(ErrorCode.FILE_VERSION_NOT_READY, "trashed or bytes unavailable")
        raise AssertionError(f"unexpected call for {vid}")

    monkeypatch.setattr(workspace, "project_mounts", lambda _u, _p: frozenset({"api"}))
    monkeypatch.setattr(artifacts, "get_file_version", fake_get_file_version)
    monkeypatch.setattr(artifacts, "require_ready_versions", fake_require_ready)

    materials = [
        {
            "id": str(MAT_READY_ID),
            "key": "m-ready",
            "title": "Ready file",
            "kind": "file_version",
            "file_version_id": str(FV_READY),
            "role": "input",
            "why": "Spec",
        },
        {
            "id": str(MAT_MISSING_ID),
            "key": "m-missing",
            "title": "Missing file",
            "kind": "file_version",
            "file_version_id": str(FV_MISSING),
            "role": "input",
            "why": "Spec",
        },
        {
            "id": str(MAT_OTHER_WS_ID),
            "key": "m-other-ws",
            "title": "Foreign file",
            "kind": "file_version",
            "file_version_id": str(FV_OTHER_WS),
            "role": "input",
            "why": "Spec",
        },
        {
            "id": str(MAT_NOT_READY_ID),
            "key": "m-not-ready",
            "title": "Trashed file",
            "kind": "file_version",
            "file_version_id": str(FV_NOT_READY),
            "role": "input",
            "why": "Spec",
        },
    ]
    doc = _base_doc(materials=materials)
    vctx = build_validation_context(cast("Any", uow), ctx, plan, document=doc)

    assert vctx.file_versions == {
        UUID(str(FV_READY)): FileVersionObservation(
            status=FileVersionStatus.READY,
            created_at=created_ready,
        ),
        UUID(str(FV_MISSING)): FileVersionObservation(
            status=FileVersionStatus.MISSING,
            created_at=None,
        ),
        UUID(str(FV_OTHER_WS)): FileVersionObservation(
            status=FileVersionStatus.OTHER_WORKSPACE,
            created_at=None,
        ),
        UUID(str(FV_NOT_READY)): FileVersionObservation(
            status=FileVersionStatus.NOT_READY,
            created_at=created_not_ready,
        ),
    }

    report = validate(vctx)
    unavailable_findings = [f for f in report.findings if f.code == "material_unavailable"]
    assert len(unavailable_findings) == 3
    by_key = {f.entity_key: f.details["status"] for f in unavailable_findings if f.details}
    assert by_key == {
        "material/m-missing": "missing",
        "material/m-other-ws": "other_workspace",
        "material/m-not-ready": "not_ready",
    }


def test_known_skills_respects_setting_and_fails_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    uow = _FakeUoW()
    plan = _make_plan()
    doc = _base_doc()
    monkeypatch.setattr(workspace, "project_mounts", lambda _u, _p: frozenset({"api"}))
    monkeypatch.setattr(extensions, "runtime_catalog", lambda _u, _sc, _cfg: None)

    called = 0

    def fake_known_keys(_u: Any, kind: Any, *, config: Any = None) -> frozenset[str]:
        nonlocal called
        called += 1
        assert kind is extensions.ResourceKind.SKILL
        return frozenset({"skill-a", "skill-b"})

    monkeypatch.setattr(extensions, "known_keys", fake_known_keys)

    # Disabled: known_keys not called, returns None
    ctx_off = _make_ctx(_default_settings(warn_unknown_skills=False, warn_unknown_models=False))
    vctx_off = build_validation_context(cast("Any", uow), ctx_off, plan, document=doc)
    assert vctx_off.known_skills is None
    assert called == 0

    # Enabled: returns frozenset
    ctx_on = _make_ctx(_default_settings(warn_unknown_skills=True, warn_unknown_models=False))
    vctx_on = build_validation_context(cast("Any", uow), ctx_on, plan, document=doc)
    assert vctx_on.known_skills == frozenset({"skill-a", "skill-b"})
    assert called == 1

    # Exception in known_keys -> fail-safe None
    def broken_known_keys(_u: Any, _k: Any, *, config: Any = None) -> frozenset[str]:
        raise NotImplementedError("extensions unavailable")

    monkeypatch.setattr(extensions, "known_keys", broken_known_keys)
    vctx_err = build_validation_context(cast("Any", uow), ctx_on, plan, document=doc)
    assert vctx_err.known_skills is None


def test_runtime_catalog_parses_toml_entries_and_respects_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = _FakeUoW()
    plan = _make_plan()
    doc = _base_doc()
    monkeypatch.setattr(workspace, "project_mounts", lambda _u, _p: frozenset({"api"}))
    monkeypatch.setattr(extensions, "known_keys", lambda _u, _k, config=None: None)

    toml_entry_1 = """
[runtimes.rt-alpha]
default_model = "alpha-v1"
models = [
  { id = "alpha-v1", tier = "balanced" },
  { id = "alpha-v2", tier = "deep" },
]
"""
    toml_entry_2 = """
[runtimes.rt-alpha]
models = [
  { id = "alpha-v3", tier = "fast" },
]

[runtimes.rt-beta]
models = []
"""
    malformed_entry = "not = [valid toml"

    view = RuntimeCatalogView(
        entries=(
            RuntimeCatalogEntry(
                resource_version_id=cast("Any", uuid4()),
                key=cast("Any", "base"),
                digest="sha256:" + "1" * 64,
                manifest={},
                body=toml_entry_1,
            ),
            RuntimeCatalogEntry(
                resource_version_id=cast("Any", uuid4()),
                key=cast("Any", "broken"),
                digest="sha256:" + "2" * 64,
                manifest={},
                body=malformed_entry,
            ),
            RuntimeCatalogEntry(
                resource_version_id=cast("Any", uuid4()),
                key=cast("Any", "override"),
                digest="sha256:" + "3" * 64,
                manifest={},
                body=toml_entry_2,
            ),
        ),
        digest="sha256:" + "0" * 64,
    )

    calls = 0

    def fake_runtime_catalog(_u: Any, sc: Any, _cfg: Any) -> RuntimeCatalogView:
        nonlocal calls
        calls += 1
        assert all(isinstance(s, ScopeRef) for s in sc)
        return view

    monkeypatch.setattr(extensions, "runtime_catalog", fake_runtime_catalog)

    # Disabled: runtime_catalog not called, returns None
    ctx_off = _make_ctx(_default_settings(warn_unknown_skills=False, warn_unknown_models=False))
    vctx_off = build_validation_context(cast("Any", uow), ctx_off, plan, document=doc)
    assert vctx_off.runtime_catalog is None
    assert calls == 0

    # Enabled: parses and merges TOML entries, skipping malformed
    ctx_on = _make_ctx(_default_settings(warn_unknown_skills=False, warn_unknown_models=True))
    vctx_on = build_validation_context(cast("Any", uow), ctx_on, plan, document=doc)
    assert calls == 1
    assert vctx_on.runtime_catalog == {
        "rt-alpha": frozenset({"alpha-v1", "alpha-v2", "alpha-v3"}),
        "rt-beta": frozenset(),
    }

    # Empty entries -> empty dict (not None)
    monkeypatch.setattr(
        extensions,
        "runtime_catalog",
        lambda _u, _sc, _cfg: RuntimeCatalogView(entries=(), digest="sha256:" + "0" * 64),
    )
    vctx_empty = build_validation_context(cast("Any", uow), ctx_on, plan, document=doc)
    assert vctx_empty.runtime_catalog == {}

    # Exception -> fail-safe None
    def broken_catalog(_u: Any, _sc: Any, _cfg: Any) -> RuntimeCatalogView:
        raise NotImplementedError("catalog failure")

    monkeypatch.setattr(extensions, "runtime_catalog", broken_catalog)
    vctx_err = build_validation_context(cast("Any", uow), ctx_on, plan, document=doc)
    assert vctx_err.runtime_catalog is None


def test_runtime_catalog_parses_example_models_toml_with_unquoted_dates_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = _FakeUoW()
    plan = _make_plan()
    doc = _base_doc()
    ctx = _make_ctx(_default_settings(warn_unknown_skills=False, warn_unknown_models=True))
    monkeypatch.setattr(workspace, "project_mounts", lambda _u, _p: frozenset({"api"}))
    monkeypatch.setattr(extensions, "known_keys", lambda _u, _k, config=None: None)

    models_toml_path = (
        Path(__file__).resolve().parents[4] / "tests/fixtures/corpus/examples/runtimes/models.toml"
    )
    models_toml_body = models_toml_path.read_text(encoding="utf-8")

    manifest_entry = RuntimeCatalogEntry(
        resource_version_id=cast("Any", uuid4()),
        key=cast("Any", "overlay"),
        digest="sha256:" + "4" * 64,
        manifest={
            "runtimes": {
                "custom_rt": {
                    "models": [{"id": "custom-m1"}, {"id": "custom-m2"}],
                }
            }
        },
        body="",
    )
    body_entry = RuntimeCatalogEntry(
        resource_version_id=cast("Any", uuid4()),
        key=cast("Any", "models"),
        digest="sha256:" + "5" * 64,
        manifest={},
        body=models_toml_body,
    )
    monkeypatch.setattr(
        extensions,
        "runtime_catalog",
        lambda _u, _sc, _cfg: RuntimeCatalogView(
            entries=(body_entry, manifest_entry),
            digest="sha256:" + "6" * 64,
        ),
    )

    vctx = build_validation_context(cast("Any", uow), ctx, plan, document=doc)
    assert vctx.runtime_catalog is not None
    assert vctx.runtime_catalog["claude_code"] == frozenset({"haiku", "sonnet", "opus"})
    assert "gpt-6-luna" in vctx.runtime_catalog["codex"]
    assert vctx.runtime_catalog["grok"] == frozenset({"grok-4.5", "grok-4.6", "grok-4.7"})
    assert "composer-2.5" in vctx.runtime_catalog["cursor"]
    assert vctx.runtime_catalog["custom_rt"] == frozenset({"custom-m1", "custom-m2"})


def test_runtime_catalog_all_entries_failing_decoding_returns_none_and_validates_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = _FakeUoW()
    plan = _make_plan()
    doc = _base_doc()
    doc["items"][0]["route"] = {
        "class": "implementation",
        "effort": "high",
        "runtime": "claude_code",
        "model": "sonnet",
    }
    ctx = _make_ctx(_default_settings(warn_unknown_skills=False, warn_unknown_models=True))
    monkeypatch.setattr(workspace, "project_mounts", lambda _u, _p: frozenset({"api"}))
    monkeypatch.setattr(extensions, "known_keys", lambda _u, _k, config=None: None)

    # (b) Non-empty RuntimeCatalogView whose entries all fail decoding -> returns None
    monkeypatch.setattr(
        extensions,
        "runtime_catalog",
        lambda _u, _sc, _cfg: RuntimeCatalogView(
            entries=(
                RuntimeCatalogEntry(
                    resource_version_id=cast("Any", uuid4()),
                    key=cast("Any", "bad1"),
                    digest="sha256:" + "1" * 64,
                    manifest={},
                    body="not = [valid toml",
                ),
                RuntimeCatalogEntry(
                    resource_version_id=cast("Any", uuid4()),
                    key=cast("Any", "bad2"),
                    digest="sha256:" + "2" * 64,
                    manifest={"other": "key"},
                    body='schema = "urn:skm:runtimes:model-catalog:v1"\n',
                ),
            ),
            digest="sha256:" + "0" * 64,
        ),
    )

    vctx = build_validation_context(cast("Any", uow), ctx, plan, document=doc)
    assert vctx.runtime_catalog is None
    report = validate(vctx)
    assert [f for f in report.findings if f.code == "route_unknown_runtime"] == []

    # (c) A valid catalog with [runtimes] having 0 entries -> returns {}
    monkeypatch.setattr(
        extensions,
        "runtime_catalog",
        lambda _u, _sc, _cfg: RuntimeCatalogView(
            entries=(
                RuntimeCatalogEntry(
                    resource_version_id=cast("Any", uuid4()),
                    key=cast("Any", "empty-runtimes"),
                    digest="sha256:" + "3" * 64,
                    manifest={},
                    body="[runtimes]\n",
                ),
            ),
            digest="sha256:" + "3" * 64,
        ),
    )
    vctx_zero = build_validation_context(cast("Any", uow), ctx, plan, document=doc)
    assert vctx_zero.runtime_catalog == {}


def test_retryable_and_backend_skm_errors_propagate_while_quarantined_fails_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = _FakeUoW()
    plan = _make_plan()
    doc = _base_doc()
    ctx = _make_ctx(_default_settings(warn_unknown_skills=True, warn_unknown_models=True))
    monkeypatch.setattr(workspace, "project_mounts", lambda _u, _p: frozenset({"api"}))

    # PreconditionFailed(RESOURCE_QUARANTINED) fails safe to None on both known_keys and runtime_catalog
    def quarantined_keys(_u: Any, _k: Any, *, config: Any = None) -> frozenset[str]:
        raise PreconditionFailed(ErrorCode.RESOURCE_QUARANTINED, "quarantined skill")

    def quarantined_catalog(_u: Any, _sc: Any, _cfg: Any) -> RuntimeCatalogView:
        raise PreconditionFailed(ErrorCode.RESOURCE_QUARANTINED, "quarantined catalog")

    monkeypatch.setattr(extensions, "known_keys", quarantined_keys)
    monkeypatch.setattr(extensions, "runtime_catalog", quarantined_catalog)
    vctx = build_validation_context(cast("Any", uow), ctx, plan, document=doc)
    assert vctx.known_skills is None
    assert vctx.runtime_catalog is None

    # Retryable / backend / unmigrated errors propagate from known_keys and runtime_catalog
    for fatal_exc in (
        Conflict(ErrorCode.SERIALIZATION_FAILURE, "serialization failure"),
        BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "db down"),
        PreconditionFailed(ErrorCode.SCHEMA_NOT_MIGRATED, "schema not migrated"),
    ):

        def raise_from_keys(
            _u: Any, _k: Any, *, config: Any = None, _e: Exception = fatal_exc
        ) -> frozenset[str]:
            raise _e

        monkeypatch.setattr(extensions, "known_keys", raise_from_keys)
        monkeypatch.setattr(extensions, "runtime_catalog", quarantined_catalog)
        with pytest.raises(type(fatal_exc)) as exc_info:
            build_validation_context(cast("Any", uow), ctx, plan, document=doc)
        assert exc_info.value is fatal_exc

        def raise_from_catalog(_u: Any, _sc: Any, _cfg: Any, _e: Exception = fatal_exc) -> RuntimeCatalogView:
            raise _e

        monkeypatch.setattr(extensions, "known_keys", quarantined_keys)
        monkeypatch.setattr(extensions, "runtime_catalog", raise_from_catalog)
        with pytest.raises(type(fatal_exc)) as exc_info_cat:
            build_validation_context(cast("Any", uow), ctx, plan, document=doc)
        assert exc_info_cat.value is fatal_exc


def test_calling_conventions_spec_or_document_or_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow = _FakeUoW()
    ctx = _make_ctx(_default_settings(warn_unknown_skills=False, warn_unknown_models=False))
    plan = _make_plan()
    monkeypatch.setattr(workspace, "project_mounts", lambda _u, _p: frozenset({"api"}))

    doc = _base_doc()
    spec, _ = from_document(doc)

    # 1. spec only
    c1 = build_validation_context(cast("Any", uow), ctx, plan, spec=spec)
    assert c1.spec == spec
    assert c1.document["title"] == "Webhooks"

    # 2. document only
    c2 = build_validation_context(cast("Any", uow), ctx, plan, document=doc)
    assert c2.spec == spec
    assert c2.document == doc

    # 3. positional dict as spec
    c3 = build_validation_context(cast("Any", uow), ctx, plan, doc)
    assert c3.spec == spec
    assert c3.document == doc

    # 4. both spec and document + explicit settings mapping + explicit now
    custom_now = NOW + timedelta(hours=2)
    settings_dict = _default_settings(warn_unknown_skills=False, warn_unknown_models=False).to_json()
    c4 = build_validation_context(
        cast("Any", uow),
        ctx,
        plan,
        spec=spec,
        document=doc,
        settings=settings_dict,
        now=custom_now,
    )
    assert c4.spec == spec
    assert c4.document is doc
    assert c4.now == custom_now
    assert c4.settings == settings_dict

    # 5. neither spec nor document -> ValueError
    with pytest.raises(ValueError, match="either spec or document"):
        build_validation_context(cast("Any", uow), ctx, plan)


def test_end_to_end_validation_with_built_context_triggers_context_and_routing_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed PHASE_ID as an ITEM in known_identities to trigger identity_kind_changed
    uow = _FakeUoW(
        _FakeRevisionRepo({EntityId(PHASE_ID): EntityKind.ITEM}),
        _FakePlanRepo({"PLAN1": PLAN_ID}),
    )
    ctx = _make_ctx(_default_settings(warn_unknown_skills=True, warn_unknown_models=True))
    plan = _make_plan()

    monkeypatch.setattr(workspace, "project_mounts", lambda _u, _p: frozenset({"api"}))
    monkeypatch.setattr(extensions, "known_keys", lambda _u, _k, config=None: frozenset({"known-skill"}))
    monkeypatch.setattr(
        extensions,
        "runtime_catalog",
        lambda _u, _sc, _cfg: RuntimeCatalogView(
            entries=(
                RuntimeCatalogEntry(
                    resource_version_id=cast("Any", uuid4()),
                    key=cast("Any", "cat"),
                    digest="sha256:" + "a" * 64,
                    manifest={},
                    body='[runtimes.rt-main]\nmodels = [{ id = "model-1" }]\n',
                ),
            ),
            digest="sha256:" + "a" * 64,
        ),
    )

    doc = _base_doc(
        plan_relations=[{"kind": "predecessor", "target": "UNKNOWN-PLAN"}],
        materials=[
            {
                "id": str(uuid4()),
                "key": "stale-ext",
                "title": "Stale external",
                "kind": "external_source",
                "url": "https://example.com/doc",
                "retrieved_at": "2026-10-29T10:00:00Z",
                "content_digest": "sha256:" + "b" * 64,
                "role": "input",
                "freshness": {"policy": "must_refresh", "max_age_seconds": 3600},
                "why": "Freshness check",
            },
            {
                "id": str(uuid4()),
                "key": "bad-mount-mat",
                "title": "Unmounted path",
                "kind": "repository_path",
                "mount": "missing-mount",
                "path": "README.md",
                "role": "reference",
                "why": "Mount check",
            },
        ],
    )
    doc["items"][0]["skills"] = [{"key": "unknown-skill", "required": True}]
    doc["items"][0]["route"] = {
        "class": "implementation",
        "effort": "high",
        "runtime": "rt-main",
        "model": "unknown-model",
    }

    vctx = build_validation_context(cast("Any", uow), ctx, plan, document=doc)
    report = validate(vctx)
    codes = {f.code for f in report.findings}

    assert "entity_kind_changed" in codes
    assert "material_stale" in codes
    assert "mount_unknown" in codes
    assert "plan_relation_unresolved" in codes
    assert "skill_unknown" in codes
    assert "route_unknown_model" in codes
    assert not report.rule_failures
