"""Implemented context operations; preserve guarded finalization from P09.04.d."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from skm.kernel.generated._codec import record_from_json

from .commands.assemble_context import SPEC as ASSEMBLE_CONTEXT
from .commands.finalize_manifest import SPEC as FINALIZE_MANIFEST
from .commands.record_research_result import SPEC as RECORD_RESEARCH_RESULT
from .queries.diff_contexts import SPEC as DIFF_CONTEXTS
from .queries.explain_context import SPEC as EXPLAIN_CONTEXT
from .queries.find_research_cache import ACCESS_SPEC as CHECK_RESEARCH_ACCESS
from .queries.find_research_cache import SPEC as FIND_RESEARCH_CACHE
from .queries.get_context_text import SPEC as GET_CONTEXT_TEXT
from .queries.get_research_query import SPEC as GET_RESEARCH_QUERY
from .queries.list_external_sources import SPEC as LIST_EXTERNAL_SOURCES


def _model(model: type[Any], urn: str) -> type[Any]:
    if getattr(model, "SCHEMA_URN", None):
        return model

    class JsonDto(dict[str, Any]):
        SCHEMA_URN = urn

        @classmethod
        def from_json(cls, data: Any) -> JsonDto:
            return cls(record_from_json(model, data, json_mode=True))

        def to_json(self) -> Any:
            return record_from_json(model, self, json_mode=True)

    JsonDto.__name__ = model.__name__
    return JsonDto


def _bind(spec: Any, kind: str) -> Any:
    slug = spec.name.split(".")[1].replace("_", "-")
    dto = _model(spec.dto, f"urn:skm:context:{kind}:{slug}:v1")
    result = _model(spec.result, f"urn:skm:context:{'result' if kind == 'command' else 'view'}:{slug}:v1")

    def handle(cmd: Any, ctx: Any, uow: Any) -> Any:
        raw = spec.handler(cmd, ctx, uow)
        return raw if hasattr(raw, "to_json") else result.from_json(raw)

    return replace(spec, dto=dto, result=result, handler=handle)


COMMANDS = (ASSEMBLE_CONTEXT, FINALIZE_MANIFEST, _bind(RECORD_RESEARCH_RESULT, "command"))
QUERIES = tuple(
    _bind(spec, "query")
    for spec in (
        EXPLAIN_CONTEXT,
        DIFF_CONTEXTS,
        GET_CONTEXT_TEXT,
        CHECK_RESEARCH_ACCESS,
        FIND_RESEARCH_CACHE,
        GET_RESEARCH_QUERY,
        LIST_EXTERNAL_SOURCES,
    )
)
