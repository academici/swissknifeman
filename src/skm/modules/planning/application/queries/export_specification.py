"""``planning.export_specification`` (planning §8.4): portable specification export."""

from __future__ import annotations

import copy
import fnmatch
import unicodedata
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm import __version__
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import FileVersionId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.artifacts import public as artifacts
from skm.modules.planning.application.source_reader import LoadedSource, read_source
from skm.modules.planning.domain.material import MaterialKind
from skm.modules.planning.generated.queries import ExportSpecification
from skm.modules.planning.generated.views import (
    SpecificationExportView,
    SpecificationExportViewDefsExportMeta,
    SpecificationExportViewDefsExportMetaMaterialsItem,
    SpecificationExportViewDefsExportMetaSourceVariant1,
    SpecificationExportViewDefsExportMetaSourceVariant2,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from skm.application_bus.context import QueryContext
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]

_MASK = "\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK}redacted\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"
_UNALLOCATED_VID = FileVersionId(UUID(int=0))


def scope_of(query: ExportSpecification) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def _iter_strings(value: JsonValue, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield pointer or "/", value
    elif isinstance(value, dict):
        for k, v in value.items():
            esc = k.replace("~", "~0").replace("/", "~1")
            yield from _iter_strings(v, f"{pointer}/{esc}")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from _iter_strings(item, f"{pointer}/{idx}")


def _matches_secret_name(
    candidate_str: str, globs: tuple[str, ...], *, allow_spaces: bool = False
) -> str | None:
    if not candidate_str:
        return None
    base = candidate_str.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    folded = unicodedata.normalize("NFKC", base).casefold()
    trimmed = folded.rstrip(". ")
    if not trimmed or (not allow_spaces and any(ch.isspace() for ch in trimmed)):
        return None
    candidates = {folded, trimmed}
    for glob in globs:
        if any(fnmatch.fnmatchcase(c, glob.casefold()) for c in candidates if c):
            return glob
    return None


def _require_portable_safety(
    ctx: QueryContext,
    document: JsonObject,
    materials: Sequence[SpecificationExportViewDefsExportMetaMaterialsItem],
) -> None:
    rules = artifacts.build_safety_rules(ctx.config)
    report = artifacts.scan_document(document, rules)
    findings: list[JsonValue] = [f.to_json() for f in report.findings if str(f.level) == "block"]

    for pointer, text in _iter_strings(document):
        matched_glob = _matches_secret_name(text, rules.secret_name_globs)
        if matched_glob is not None:
            findings.append(
                {
                    "rule": "CS-SECRET-NAME",
                    "level": "block",
                    "detail": f"the file name is a secret file name ({matched_glob}): {_MASK}",
                    "line": None,
                    "pointer": pointer,
                }
            )
    for idx, mat in enumerate(materials):
        matched_glob = _matches_secret_name(mat.original_filename, rules.secret_name_globs, allow_spaces=True)
        if matched_glob is not None:
            findings.append(
                {
                    "rule": "CS-SECRET-NAME",
                    "level": "block",
                    "detail": f"the file name is a secret file name ({matched_glob}): {_MASK}",
                    "line": None,
                    "pointer": f"/export_meta/materials/{idx}/original_filename",
                }
            )

    if report.verdict() == "block" or findings:
        raise ValidationFailed(
            ErrorCode.CONTENT_UNSAFE,
            "the content failed the content-safety rules",
            details={"reason": "portable_document_blocked", "findings": findings},
        )


def _collect_materials(
    uow: UnitOfWork,
    ctx: QueryContext,
    source: LoadedSource,
) -> tuple[SpecificationExportViewDefsExportMetaMaterialsItem, ...]:
    default_scope = ScopeRef(ScopeKind.PROJECT, ScopeId(source.plan.project_id))
    items: list[SpecificationExportViewDefsExportMetaMaterialsItem] = []
    for mat in source.spec.materials:
        if mat.kind is not MaterialKind.FILE_VERSION or mat.file_version_id is None:
            continue
        vid = FileVersionId(mat.file_version_id)
        try:
            artifacts.file_id_of_version(uow, source.plan.workspace_id, vid)
        except NotFound:
            artifacts.require_version_read(
                uow,
                ctx.actor,
                ctx.clock,
                _UNALLOCATED_VID,
                default_scope=default_scope,
                reported_version_id=vid,
            )
            continue
        artifacts.require_version_read(uow, ctx.actor, ctx.clock, vid, default_scope=default_scope)
        view = artifacts.get_file_version(uow, vid)
        items.append(
            SpecificationExportViewDefsExportMetaMaterialsItem(
                material_key=mat.key,
                file_version_id=view.file_version_id,
                content_digest=view.digest,
                original_filename=view.original_filename,
                media_type=view.declared_media_type or view.detected_media_type,
                size=view.size_bytes,
            )
        )
    return tuple(items)


def _build_source_meta(
    source: LoadedSource,
) -> (
    SpecificationExportViewDefsExportMetaSourceVariant1 | SpecificationExportViewDefsExportMetaSourceVariant2
):
    if source.kind == "revision" and source.revision is not None:
        return SpecificationExportViewDefsExportMetaSourceVariant1(
            kind="revision",
            plan_id=source.plan.id,
            plan_alias=source.plan.alias,
            revision_id=source.revision.id,
            revision_no=source.revision.revision_no,
        )
    if source.draft is None:
        raise ValueError("draft source requires draft metadata")
    return SpecificationExportViewDefsExportMetaSourceVariant2(
        kind="draft",
        plan_id=source.plan.id,
        plan_alias=source.plan.alias,
        draft_id=source.draft.id,
        edit_version=source.draft.edit_version,
        base_revision_id=source.draft.base_revision_id,
    )


def handle(query: ExportSpecification, ctx: QueryContext, uow: UnitOfWork) -> SpecificationExportView:
    source = read_source(
        uow,
        plan_id=query.plan_id,
        revision_id=query.revision_id,
        draft_id=query.draft_id,
        expected_edit_version=query.expected_edit_version,
    )
    materials = _collect_materials(uow, ctx, source)
    _require_portable_safety(ctx, source.document, materials)
    export_meta = SpecificationExportViewDefsExportMeta(
        format="urn:skm:planning:specification:v1",
        source=_build_source_meta(source),
        content_digest=source.document_digest,
        exported_at=ctx.clock.now(),
        exported_by=UUID(str(ctx.actor.principal_id)),
        skm_version=__version__,
        materials=materials,
    )
    return SpecificationExportView(
        document=cast("Any", copy.deepcopy(source.document)),
        export_meta=export_meta,
    )


SPEC = QuerySpec(
    name="planning.export_specification",
    dto=ExportSpecification,
    result=SpecificationExportView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
