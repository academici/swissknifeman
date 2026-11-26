"""``planning.read_text`` (planning §8.2): bounded UTF-8 text fragment reader."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import find_raw_entity, read_source
from skm.modules.planning.generated.queries import ReadText
from skm.modules.planning.generated.views import (
    TextFragmentView,
    text_fragment_view_defs_source_view_from_json,
)

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]

_MAX_BYTES_LIMIT = 65536


def scope_of(query: ReadText) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def _resolve_pointer(root: JsonObject, pointer: str, target_ref: str) -> str:
    if not pointer.startswith("/"):
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "JSON pointer must start with '/'",
            details={"target": target_ref, "pointer": pointer},
        )
    current: object = root
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            mapping_cur = cast("Mapping[str, object]", current)
            if token not in mapping_cur:
                raise ValidationFailed(
                    ErrorCode.INVALID_REFERENCE,
                    "pointer target does not exist",
                    details={"target": target_ref, "pointer": pointer},
                )
            current = mapping_cur[token]
        elif isinstance(current, list | tuple):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise ValidationFailed(
                    ErrorCode.INVALID_REFERENCE,
                    "invalid array index in pointer",
                    details={"target": target_ref, "pointer": pointer},
                )
            idx = int(token)
            seq = cast("list[object] | tuple[object, ...]", current)
            if idx < 0 or idx >= len(seq):
                raise ValidationFailed(
                    ErrorCode.INVALID_REFERENCE,
                    "array index out of bounds in pointer",
                    details={"target": target_ref, "pointer": pointer},
                )
            current = seq[idx]
        else:
            raise ValidationFailed(
                ErrorCode.INVALID_REFERENCE,
                "pointer cannot traverse scalar value",
                details={"target": target_ref, "pointer": pointer},
            )

    if not isinstance(current, str):
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "pointer does not resolve to a string field",
            details={"target": target_ref, "pointer": pointer},
        )
    return current


def handle(query: ReadText, _ctx: QueryContext, uow: UnitOfWork) -> TextFragmentView:
    source = read_source(
        uow,
        plan_id=query.plan_id,
        revision_id=query.revision_id,
        draft_id=query.draft_id,
        expected_edit_version=query.expected_edit_version,
    )
    if isinstance(query.offset_bytes, bool) or query.offset_bytes < 0:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "offset_bytes must be >= 0",
            details={"field": "offset_bytes"},
        )
    if isinstance(query.max_bytes, bool) or not 1 <= query.max_bytes <= _MAX_BYTES_LIMIT:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"max_bytes must be between 1 and {_MAX_BYTES_LIMIT}",
            details={"field": "max_bytes"},
        )

    if query.target == "plan":
        target_obj = source.document
        target_entity_id: UUID | None = None
    else:
        eid, _kind, _dkey, raw_obj = find_raw_entity(source, query.target)
        target_obj = raw_obj
        target_entity_id = UUID(str(eid))

    full_text = _resolve_pointer(target_obj, query.pointer, query.target)
    raw_bytes = full_text.encode("utf-8")
    total_bytes = len(raw_bytes)
    text_digest = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"

    offset = query.offset_bytes
    if offset > total_bytes or (0 < offset < total_bytes and (raw_bytes[offset] & 0xC0) == 0x80):
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            "offset_bytes is out of bounds or not on a UTF-8 code point boundary",
            details={"offset_bytes": offset, "total_bytes": total_bytes},
        )

    if offset == total_bytes:
        end_offset = total_bytes
        text_slice = ""
    else:
        end_offset = min(total_bytes, offset + query.max_bytes)
        while end_offset < total_bytes and end_offset > offset and (raw_bytes[end_offset] & 0xC0) == 0x80:
            end_offset -= 1

        if end_offset == offset:
            min_req = 1
            while offset + min_req < total_bytes and (raw_bytes[offset + min_req] & 0xC0) == 0x80:
                min_req += 1
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "max_bytes is smaller than the next UTF-8 code point",
                details={
                    "reason": "invalid_window",
                    "min_required_bytes": min_req,
                    "issues": [
                        {
                            "pointer": "/max_bytes",
                            "message": f"max_bytes must be at least {min_req} bytes",
                            "schema_pointer": "",
                        }
                    ],
                },
            )
        text_slice = raw_bytes[offset:end_offset].decode("utf-8")

    window_bytes = end_offset - offset
    omitted_bytes = total_bytes - window_bytes
    truncated = omitted_bytes > 0
    next_offset = end_offset if end_offset < total_bytes else None

    return TextFragmentView(
        source=text_fragment_view_defs_source_view_from_json(source.source_view_json()),
        target_entity_id=target_entity_id,
        pointer=query.pointer,
        text_digest=text_digest,
        total_bytes=total_bytes,
        offset_bytes=offset,
        end_offset_bytes=end_offset,
        text=text_slice,
        truncated=truncated,
        omitted_bytes=omitted_bytes,
        next_offset_bytes=next_offset,
    )


SPEC = QuerySpec(
    name="planning.read_text",
    dto=ReadText,
    result=TextFragmentView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
