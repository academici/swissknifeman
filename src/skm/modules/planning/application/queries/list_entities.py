"""``planning.list_entities`` (planning §8.1): keyset-paginated entity outlines of a source."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.pagination import CURSOR_MAX_LENGTH
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import (
    KIND_ORDER,
    LoadedSource,
    build_entity_outlines,
    read_source,
)
from skm.modules.planning.domain.specification import EntityKind
from skm.modules.planning.generated.queries import ListEntities
from skm.modules.planning.generated.views import (
    EntityPageView,
    entity_page_view_defs_source_view_from_json,
)

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]

_MAX_LIMIT = 200
_ORDER_VERSION = 1
_KIND_RANK: dict[str, int] = {k.value: idx for idx, k in enumerate(KIND_ORDER)}


def scope_of(query: ListEntities) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def _bad_cursor() -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.INVALID_REFERENCE,
        "cursor is not valid for this query",
        details={"field": "after"},
    )


def _cursor_binding(ctx: QueryContext, source: LoadedSource, canonical_kinds: list[str]) -> str:
    raw = json.dumps(
        {
            "w": str(source.plan.workspace_id),
            "p": str(source.plan.id),
            "a": str(ctx.actor.principal_id),
            "s": source.source_view_json(),
            "k": canonical_kinds,
            "v": _ORDER_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _encode_cursor(binding: str, kind_rank: int, position: int, entity_id: UUID) -> str:
    payload = json.dumps(
        {"b": binding, "last": [kind_rank, position, str(entity_id)]},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(after: str | None, expected_binding: str) -> tuple[int, int, UUID] | None:
    if after is None:
        return None
    if not 1 <= len(after) <= CURSOR_MAX_LENGTH or not after.isascii():
        raise _bad_cursor()
    try:
        raw = base64.urlsafe_b64decode(after + "=" * (-len(after) % 4))
        doc: object = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("not dict")
        body = cast("dict[str, object]", doc)
        if body.get("b") != expected_binding:
            raise ValueError("binding mismatch")
        last_obj = body.get("last")
        if not isinstance(last_obj, list):
            raise ValueError("last shape")
        last = cast("list[object]", last_obj)
        if len(last) != 3:
            raise ValueError("last shape")
        k_rank, pos, eid_str = last[0], last[1], last[2]
        if (
            isinstance(k_rank, bool)
            or not isinstance(k_rank, int)
            or isinstance(pos, bool)
            or not isinstance(pos, int)
            or not isinstance(eid_str, str)
        ):
            raise ValueError("last types")
        return k_rank, pos, UUID(eid_str)
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        raise _bad_cursor() from None


def _validate_kinds(kinds: tuple[str, ...] | None) -> tuple[set[str], list[str]]:
    if kinds is None:
        all_vals = [k.value for k in KIND_ORDER]
        return set(all_vals), all_vals
    if len(kinds) == 0 or len(set(kinds)) != len(kinds):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "kinds must be a non-empty unique tuple of entity kinds",
            details={"field": "kinds"},
        )
    allowed = {k.value for k in EntityKind}
    for k in kinds:
        if k not in allowed:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"unknown entity kind: {k}",
                details={"field": "kinds"},
            )
    wanted = set(kinds)
    canonical = [k.value for k in KIND_ORDER if k.value in wanted]
    return wanted, canonical


def handle(query: ListEntities, ctx: QueryContext, uow: UnitOfWork) -> EntityPageView:
    source = read_source(
        uow,
        plan_id=query.plan_id,
        revision_id=query.revision_id,
        draft_id=query.draft_id,
        expected_edit_version=query.expected_edit_version,
    )
    if isinstance(query.limit, bool) or not 1 <= query.limit <= _MAX_LIMIT:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"limit must be between 1 and {_MAX_LIMIT}",
            details={"field": "limit"},
        )

    wanted_kinds, canonical_kinds = _validate_kinds(query.kinds)
    binding = _cursor_binding(ctx, source, canonical_kinds)
    bound = _decode_cursor(query.after, binding)

    all_outlines = build_entity_outlines(source)
    filtered = [item for item in all_outlines if item.entity_kind in wanted_kinds]
    if bound is not None:
        filtered = [
            item for item in filtered if (_KIND_RANK[item.entity_kind], item.position, item.entity_id) > bound
        ]

    sliced = filtered[: query.limit + 1]
    items = tuple(sliced[: query.limit])
    next_cursor: str | None = None
    if len(sliced) > query.limit and items:
        last_item = items[-1]
        next_cursor = _encode_cursor(
            binding,
            _KIND_RANK[last_item.entity_kind],
            last_item.position,
            last_item.entity_id,
        )

    return EntityPageView(
        source=entity_page_view_defs_source_view_from_json(source.source_view_json()),
        items=items,
        next_cursor=next_cursor,
    )


SPEC = QuerySpec(
    name="planning.list_entities",
    dto=ListEntities,
    result=EntityPageView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
