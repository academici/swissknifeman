"""Bus identities for the generated context JSON-mode query and view records."""

from typing import Any


class ContextWireRecord(dict[str, Any]):
    SCHEMA_URN: str

    @classmethod
    def from_json(cls, data: Any) -> Any:
        return cls(data)

    def to_json(self) -> Any:
        return dict(self)


class ExplainContextRequest(ContextWireRecord):
    SCHEMA_URN = "urn:skm:context:query:explain-context:v1"


class ContextExplainResponse(ContextWireRecord):
    SCHEMA_URN = "urn:skm:context:view:explain-context:v1"


class DiffContextsRequest(ContextWireRecord):
    SCHEMA_URN = "urn:skm:context:query:diff-contexts:v1"


class ContextDiffResponse(ContextWireRecord):
    SCHEMA_URN = "urn:skm:context:view:diff-contexts:v1"


class GetContextTextRequest(ContextWireRecord):
    SCHEMA_URN = "urn:skm:context:query:get-context-text:v1"


class ContextTextResponse(ContextWireRecord):
    SCHEMA_URN = "urn:skm:context:view:get-context-text:v1"
