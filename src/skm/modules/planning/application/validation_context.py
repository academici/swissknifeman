"""Assemble the validation context for a plan specification (planning §5.3, §5.8, §5.11)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Final
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.scopes import ScopeRef
from skm.modules.artifacts import public as artifacts
from skm.modules.extensions import public as extensions
from skm.modules.planning.domain.material import MaterialKind
from skm.modules.planning.domain.specification import Specification, from_document, to_document
from skm.modules.planning.domain.validation.context import (
    FileVersionObservation,
    FileVersionStatus,
    ValidationContext,
)
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import PlanRepository, RevisionRepository
from skm.modules.workspace import public as workspace
from skm.platform.config.sources.document import decode_document

if TYPE_CHECKING:
    from datetime import datetime

    from skm.application_bus.context import CommandContext, QueryContext
    from skm.kernel.ids import FileVersionId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.planning.domain.plan import Plan

__all__ = ["build_validation_context"]

_TOML_DATE_LINE_RE: Final = re.compile(
    r"^(\s*[A-Za-z0-9_.-]+\s*=\s*)"
    r"(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?)"
    r"(\s*(?:#.*)?)$",
    re.MULTILINE,
)


def _resolve_spec_and_document(
    spec: Specification | JsonObject | None,
    document: JsonObject | None,
) -> tuple[Specification, JsonObject]:
    if isinstance(spec, Mapping):
        resolved_doc: JsonObject = dict(spec)
        resolved_spec, _ = from_document(resolved_doc)
        return resolved_spec, resolved_doc
    if spec is None and document is not None:
        resolved_spec, _ = from_document(document)
        return resolved_spec, document
    if spec is not None and document is None:
        return spec, to_document(spec)
    if spec is not None and document is not None:
        return spec, document
    raise ValueError("either spec or document must be provided")


def _resolve_settings(
    ctx: CommandContext | QueryContext,
    settings: PlanningSettings | Mapping[str, JsonValue] | None,
) -> tuple[JsonObject, bool, bool]:
    resolved = ctx.config.section(PlanningSettings) if settings is None else settings
    if isinstance(resolved, PlanningSettings):
        return (
            resolved.to_json(),
            resolved.validation.warn_unknown_skills,
            resolved.validation.warn_unknown_models,
        )
    settings_json: JsonObject = dict(resolved)
    validation_sec = settings_json.get("validation")
    if isinstance(validation_sec, Mapping):
        warn_skills = bool(validation_sec.get("warn_unknown_skills", True))
        warn_models = bool(validation_sec.get("warn_unknown_models", True))
    else:
        warn_skills = True
        warn_models = True
    return settings_json, warn_skills, warn_models


def _observe_file_versions(
    uow: UnitOfWork,
    plan: Plan,
    spec: Specification,
) -> dict[UUID, FileVersionObservation]:
    version_ids: list[FileVersionId] = []
    seen: set[UUID] = set()
    for material in spec.materials:
        if material.kind is MaterialKind.FILE_VERSION and material.file_version_id is not None:
            raw_uuid = UUID(str(material.file_version_id))
            if raw_uuid not in seen:
                seen.add(raw_uuid)
                version_ids.append(material.file_version_id)

    observations: dict[UUID, FileVersionObservation] = {}
    for version_id in version_ids:
        raw_uuid = UUID(str(version_id))
        try:
            view = artifacts.get_file_version(uow, version_id)
        except NotFound:
            observations[raw_uuid] = FileVersionObservation(
                status=FileVersionStatus.MISSING,
                created_at=None,
            )
            continue

        try:
            ready_views = artifacts.require_ready_versions(uow, plan.workspace_id, (version_id,))
        except NotFound:
            observations[raw_uuid] = FileVersionObservation(
                status=FileVersionStatus.OTHER_WORKSPACE,
                created_at=None,
            )
        except PreconditionFailed:
            observations[raw_uuid] = FileVersionObservation(
                status=FileVersionStatus.NOT_READY,
                created_at=view.created_at,
            )
        else:
            created_at = ready_views[0].created_at if ready_views else view.created_at
            observations[raw_uuid] = FileVersionObservation(
                status=FileVersionStatus.READY,
                created_at=created_at,
            )

    return observations


def _resolve_known_skills(
    uow: UnitOfWork,
    ctx: CommandContext | QueryContext,
    *,
    enabled: bool,
) -> frozenset[str] | None:
    if not enabled:
        return None
    try:
        raw_keys = extensions.known_keys(
            uow,
            extensions.ResourceKind.SKILL,
            config=ctx.config,
        )
        return frozenset(str(key) for key in raw_keys)
    except PreconditionFailed as exc:
        if exc.code is ErrorCode.SCHEMA_NOT_MIGRATED:
            raise
        return None
    except (NotFound, ValidationFailed, LookupError, NotImplementedError, ValueError, TypeError):
        return None


def _decode_catalog_toml(body: str) -> Mapping[str, JsonValue] | None:
    normalized = _TOML_DATE_LINE_RE.sub(r'\1"\2"\3', body)
    try:
        return decode_document(normalized, "toml")
    except (ValidationFailed, LookupError, ValueError, TypeError):
        return None


def _extract_entry_runtimes(entry: extensions.RuntimeCatalogEntry) -> Mapping[str, JsonValue] | None:
    manifest: Mapping[str, JsonValue] | None = getattr(entry, "manifest", None)
    if isinstance(manifest, Mapping):
        manifest_runtimes = manifest.get("runtimes")
        if isinstance(manifest_runtimes, Mapping):
            return manifest_runtimes
    body: str | None = getattr(entry, "body", None)
    if isinstance(body, str) and body.strip():
        doc = _decode_catalog_toml(body)
        if isinstance(doc, Mapping):
            body_runtimes = doc.get("runtimes")
            if isinstance(body_runtimes, Mapping):
                return body_runtimes
    return None


def _merge_runtimes(parsed_catalog: dict[str, set[str]], runtimes: Mapping[str, JsonValue]) -> None:
    for rt_id, rt_info in runtimes.items():
        if not isinstance(rt_info, Mapping):
            continue
        models_set = parsed_catalog.setdefault(str(rt_id), set())
        models = rt_info.get("models")
        if isinstance(models, Mapping):
            for model_id in models:
                models_set.add(str(model_id))
        elif isinstance(models, Iterable) and not isinstance(models, (str, bytes)):
            for model in models:
                if isinstance(model, Mapping) and model.get("id") is not None:
                    models_set.add(str(model["id"]))
                elif isinstance(model, str):
                    models_set.add(model)


def _resolve_runtime_catalog(
    uow: UnitOfWork,
    ctx: CommandContext | QueryContext,
    *,
    enabled: bool,
) -> dict[str, frozenset[str]] | None:
    if not enabled:
        return None
    scope_refs = tuple(ScopeRef(s.kind, s.id) for s in ctx.scope_chain)
    try:
        catalog_view = extensions.runtime_catalog(
            uow,
            scope_refs,
            ctx.config,
        )
    except PreconditionFailed as exc:
        if exc.code is ErrorCode.SCHEMA_NOT_MIGRATED:
            raise
        return None
    except (NotFound, ValidationFailed, LookupError, NotImplementedError, ValueError, TypeError):
        return None
    if catalog_view is None:
        return None

    parsed_catalog: dict[str, set[str]] = {}
    decoded_any = False
    for entry in catalog_view.entries:
        runtimes = _extract_entry_runtimes(entry)
        if runtimes is None:
            continue
        decoded_any = True
        _merge_runtimes(parsed_catalog, runtimes)

    if len(catalog_view.entries) > 0 and not decoded_any:
        return None

    return {rt_id: frozenset(models) for rt_id, models in parsed_catalog.items()}


def build_validation_context(
    uow: UnitOfWork,
    ctx: CommandContext | QueryContext,
    plan: Plan,
    spec: Specification | JsonObject | None = None,
    document: JsonObject | None = None,
    *,
    settings: PlanningSettings | Mapping[str, JsonValue] | None = None,
    now: datetime | None = None,
) -> ValidationContext:
    """Gather cross-module facts and assemble a ``ValidationContext`` for ``validate``."""
    resolved_spec, resolved_doc = _resolve_spec_and_document(spec, document)
    settings_json, warn_skills, warn_models = _resolve_settings(ctx, settings)
    resolved_now = ctx.clock.now() if now is None else now

    project_mounts = workspace.project_mounts(uow, plan.project_id)
    known_identities = uow.repo(RevisionRepository).identities(plan.id)
    project_plans = uow.repo(PlanRepository).project_plan_refs(plan.project_id)
    file_versions = _observe_file_versions(uow, plan, resolved_spec)
    known_skills = _resolve_known_skills(uow, ctx, enabled=warn_skills)
    runtime_catalog = _resolve_runtime_catalog(uow, ctx, enabled=warn_models)

    return ValidationContext(
        spec=resolved_spec,
        document=resolved_doc,
        project_mounts=project_mounts,
        known_identities=known_identities,
        file_versions=file_versions,
        known_skills=known_skills,
        runtime_catalog=runtime_catalog,
        project_plans=project_plans,
        now=resolved_now,
        settings=settings_json,
    )
