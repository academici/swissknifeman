"""Research wire contracts, immutability and untrusted rendering."""

from datetime import UTC, datetime
from uuid import UUID

from skm.kernel.ids import ProjectId, WorkspaceId
from skm.modules.context.domain.research import (
    RawDocument,
    RawSourceReply,
    ResearchSourceConfig,
    SourceQuery,
)
from skm.modules.context.domain.research_rules import normalize_reply, source_config
from skm.platform.logging.redaction import Redactor

NOW = datetime(2026, 11, 16, tzinfo=UTC)
WID = WorkspaceId(UUID("01900000-0000-7000-8000-000000000001"))
PID = ProjectId(UUID("01900000-0000-7000-8000-000000000002"))
QID = "01900000-0000-7000-8000-000000000003"
IDS = tuple(str(UUID(int=UUID(QID).int + n + 1)) for n in range(50))


def config(**overrides) -> ResearchSourceConfig:
    raw = {
        "kind": "command",
        "tier": "local_docs",
        "capabilities": ["search", "citations"],
        "trust_cap": "repository",
        "classification": "internal",
        **overrides,
    }
    return source_config("docs", raw, {})


def normalized(reply=None, *, cfg=None, settings=None, **options):
    return normalize_reply(
        reply
        or RawSourceReply((RawDocument("repo:repo/guide.md", "Guide", "body", {}),), None, (), None, "raw"),
        cfg or config(),
        SourceQuery("Café research", 10, "standard", {"repo": "/checkout"}),
        query_id=QID,
        now=NOW,
        document_ids=IDS,
        settings=settings or {},
        workspace_id=WID,
        project_id=PID,
        redact=Redactor().text,
        **options,
    )
