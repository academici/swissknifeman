"""MCP tool registration, schema export and discovery digest."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.access.public import WhoAmIView
from skm.platform.jsonc.digest import digest
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import scope as schema_scope

from .session import McpSession
from .tools import adhoc, local_memory, memory, notes, plan, questions, task
from .truncation import AUTHORING_READS

__all__ = ["TOOLS", "ToolSpec", "export_tool", "lookup_tool", "published_tools", "tools_digest"]

_SCHEMA_MAPS = frozenset({"properties", "patternProperties", "dependentSchemas"})
_SCHEMA_ARRAYS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_SCHEMA_VALUES = frozenset(
    {
        "additionalProperties",
        "contains",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
_SCHEMA_METADATA = frozenset({"$id", "$schema", "$defs", "$anchor", "$dynamicAnchor", "$ref"})
_GRAPH_GUIDANCE = (
    "Check freshness.state and completeness before concluding a symbol is unused or a link is absent. "
    "Require fresh, complete evidence and check for MCP truncation receipts."
)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema_urn: str
    output_schema_urn: str
    permission: str
    module: str | None
    handler: Callable[[McpSession, JsonObject], JsonValue]
    # Write handlers may opt in when the owner binds the write to the session run or its descendants.
    assignment_write: bool = False
    required_permissions: tuple[str, ...] = ()
    local_only: bool = False

    def visible_in(self, session: McpSession) -> bool:
        return self.local_only is (session.local_memory is not None)

    def enabled(self, identity: WhoAmIView) -> bool:
        return self.module is None or identity.modules.get(self.module, False)

    def permitted(self, session: McpSession, identity: WhoAmIView) -> bool:
        if not self.visible_in(session) or not session.allows_tool(self.name):
            return False
        required = {self.permission, *self.required_permissions}
        granted = set(identity.effective_permissions)
        if session.is_assignment:
            if not (
                self.permission.endswith(".read") or self.permission == "step.note" or self.assignment_write
            ):
                return False
            granted.update(identity.permissions_by_scope.get(str(session.run_id), ()))
        elif self.permission == "step.note":
            return False
        token = identity.token
        return (
            token is not None
            and (token.permissions is None or required.issubset(token.permissions))
            and required.issubset(granted)
        )


def _tool(
    stem: str,
    description: str,
    permission: str,
    handler: Callable[[McpSession, JsonObject], JsonValue],
    *,
    required_permissions: tuple[str, ...] = (),
    module: str | None = None,
    local_only: bool = False,
) -> ToolSpec:
    return ToolSpec(
        "skm_" + stem.replace("-", "_"),
        description,
        f"urn:skm:mcp:tool-input:{stem}:v1",
        f"urn:skm:mcp:tool-output:{stem}:v1",
        permission,
        module,
        handler,
        required_permissions=required_permissions,
        local_only=local_only,
    )


TOOLS: tuple[ToolSpec, ...] = (
    _tool(
        "plan-list", "List plans of this project with their current revision.", "plan.read", plan.list_plans
    ),
    _tool(
        "plan-show",
        "Show a plan revision: goal and the tree of phases, items and units.",
        "plan.read",
        plan.show,
    ),
    _tool("plan-entity", "Read an entity from a plan revision or draft.", "plan.read", plan.entity),
    _tool(
        "plan-entities", "Page through the entities of a plan revision or draft.", "plan.read", plan.entities
    ),
    _tool(
        "plan-read-text",
        "Read a bounded text fragment from a plan revision or draft.",
        "plan.read",
        plan.read_text,
    ),
    _tool("plan-draft-open", "Open a plan draft.", "plan.edit", plan.draft_open),
    _tool(
        "plan-draft-save",
        "Save changes to a plan draft at an expected edit version.",
        "plan.edit",
        plan.draft_save,
    ),
    _tool("plan-draft-rebase", "Rebase a plan draft onto a revision.", "plan.edit", plan.draft_rebase),
    _tool(
        "plan-publication-preview",
        "Preview the exact candidate for publication.",
        "plan.read",
        plan.publication_preview,
    ),
    _tool(
        "plan-publish",
        "Publish a draft with its expected content digest.",
        "plan.publish",
        plan.publish,
        required_permissions=("plan.read",),
    ),
    _tool("plan-draft-abandon", "Abandon a plan draft.", "plan.edit", plan.draft_abandon),
    _tool(
        "memory-search",
        "Search unexpired working memory of this project.",
        "memory.read",
        memory.search,
        module="knowledge",
    ),
    _tool(
        "memory-remember",
        "Remember a short entry in this project.",
        "memory.write",
        memory.remember,
        module="knowledge",
    ),
    _tool(
        "memory-forget",
        "Forget an entry of this project.",
        "memory.write",
        memory.forget,
        module="knowledge",
    ),
    _tool(
        "local-memory-record",
        "Record a HOST_PRIVATE episode in the local project.",
        "memory.write",
        local_memory.record,
        module="knowledge",
        local_only=True,
    ),
    _tool(
        "local-memory-search",
        "Search HOST_PRIVATE episodes in the local project.",
        "memory.read",
        local_memory.search,
        module="knowledge",
        local_only=True,
    ),
    _tool(
        "local-memory-summarize",
        "Summarize HOST_PRIVATE episodes from one local project session.",
        "memory.read",
        local_memory.summarize,
        module="knowledge",
        local_only=True,
    ),
    _tool(
        "lessons-list",
        "List curated lessons of this project with source association scores.",
        "lesson.read",
        memory.lessons_list,
        module="knowledge",
    ),
    _tool(
        "graph-neighbors",
        "Inspect neighbors of a graph node in the session project. " + _GRAPH_GUIDANCE,
        "memory.read",
        memory.graph_neighbors,
        module="knowledge",
    ),
    _tool(
        "graph-path",
        "Find a graph path between two nodes in the session project. " + _GRAPH_GUIDANCE,
        "memory.read",
        memory.graph_path,
        module="knowledge",
    ),
    _tool("task-context", "Read a task contract and its execution context.", "run.read", task.task_context),
    _tool(
        "run-adhoc",
        "Start an ad hoc task in the session project.",
        "run.start",
        adhoc.run_adhoc,
    ),
    _tool(
        "context-assemble",
        "Assemble a standalone project context draft.",
        "context.assemble",
        adhoc.context_assemble,
    ),
    _tool("run-status", "Read a run's status, waiting decisions and budget.", "run.read", task.run_status),
    _tool("run-history", "Read a bounded page of run history.", "run.read", task.run_history),
    _tool("task-status", "Read a task's execution status and attempts.", "run.read", task.task_status),
    _tool(
        "ask-question",
        "Ask a question from the current assignment step.",
        "step.note",
        questions.ask_question,
    ),
    _tool("inbox-list", "List open decision requests.", "inbox.read", questions.inbox_list),
    _tool("record-note", "Record a note on the current assignment step.", "step.note", notes.record_note),
)


def published_tools(session: McpSession, schemas: SchemaRegistry) -> list[JsonObject]:
    identity = session.refresh()
    listed = [
        export_tool(schemas, tool.name, tool.description, tool.input_schema_urn)
        for tool in TOOLS
        if tool.enabled(identity) and tool.permitted(session, identity)
    ]
    if session.allows_tool("skm_fetch") and any(tool["name"] in AUTHORING_READS for tool in listed):
        listed.append(
            export_tool(
                schemas,
                "skm_fetch",
                "Continue a pinned authoring read using its authoring_receipt.",
                "urn:skm:mcp:tool-input:fetch:v1",
            )
        )
    return listed


def lookup_tool(tools: Sequence[ToolSpec], name: str) -> ToolSpec | None:
    return next((tool for tool in tools if tool.name == name), None)


def _schema_child(value: JsonValue, resolver: Any, seen: frozenset[int]) -> JsonValue:
    return _inline(value, resolver, seen) if isinstance(value, dict) else value


def _local_keywords(schema: Mapping[str, JsonValue], resolver: Any, seen: frozenset[int]) -> JsonObject:
    exported: JsonObject = {}
    for key, value in schema.items():
        if key in _SCHEMA_METADATA or key.startswith("x-skm"):
            continue
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            exported[key] = {name: _schema_child(child, resolver, seen) for name, child in value.items()}
        elif key in _SCHEMA_ARRAYS and isinstance(value, list):
            exported[key] = [_schema_child(child, resolver, seen) for child in value]
        elif key in _SCHEMA_VALUES:
            exported[key] = _schema_child(value, resolver, seen)
        else:
            exported[key] = value
    return exported


def _inline(schema: Mapping[str, JsonValue], resolver: Any, seen: frozenset[int]) -> JsonObject:
    if id(schema) in seen:
        raise ValueError("recursive MCP input schema cannot be inlined")
    seen = seen | {id(schema)}
    resolver = schema_scope(schema, resolver)
    exported = _local_keywords(schema, resolver, seen)
    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved = resolver.lookup(ref)
        target = _schema_child(cast("JsonValue", resolved.contents), resolved.resolver, seen)
        if not exported and isinstance(target, dict):
            return target
        # Draft 2020-12 applies both $ref and siblings, even when they share a keyword.
        siblings = exported.get("allOf")
        exported["allOf"] = [target, *(siblings if isinstance(siblings, list) else ())]
    return exported


def export_tool(schemas: SchemaRegistry, name: str, description: str, input_schema_urn: str) -> JsonObject:
    schema = schemas.get(input_schema_urn)
    exported = _inline(schema, schemas.resolver_for(schema), frozenset())
    return {"name": name, "description": description, "inputSchema": exported}


def tools_digest(tools: Sequence[JsonObject]) -> str:
    """Tagged SHA-256 of the published tools in list order, independent of object key order."""
    return digest(list(tools))
