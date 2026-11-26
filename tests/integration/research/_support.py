"""Real process fixtures and minimal host-client evidence collectors."""

import hashlib
import json
import sys
from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

from skm.adapters.research.command import CommandResearchSource
from skm.adapters.research.filesystem import FilesystemResearchSource
from skm.adapters.research.retry import ResearchSources
from skm.application_bus.client import StagedBlobRef
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.modules.context.domain.research import ResearchQuerySpec, SourceQuery
from skm.modules.context.domain.research_rules import source_config
from skm.modules.context.ports import ResearchSourceRegistry
from skm.platform.logging.logger import get_logger
from skm.platform.logging.redaction import Redactor


def config(**changes):
    return source_config(
        "docs",
        {
            "kind": "command",
            "tier": "local_docs",
            "capabilities": ["search", "citations", "synthesis"],
            "trust_cap": "repository",
            "classification": "internal",
            **changes,
        },
        {},
    )


def command(script, **changes):
    return config(argv=[sys.executable, "-c", script], **changes)


def query(text="research", **changes):
    return replace(SourceQuery(text, 10, "standard", {}), **changes)


def spec(text="research", **changes):
    return replace(ResearchQuerySpec(text, (), "standard", 10, True, False), **changes)


class Client:
    def __init__(self):
        self.commands = []
        self.queries = []
        self.uploads = []
        self.cached = None
        self.records = {}

    def ask(self, request):
        self.queries.append(request)
        if request.SCHEMA_URN.endswith(":get-research-query:v1"):
            if request["query_id"] not in self.records:
                raise NotFound(ErrorCode.NOT_FOUND, "not recorded")
            return {"result": self.records[request["query_id"]]}
        return self.cached or {"hit": False}

    def dispatch(self, request, *, idempotency_key=None):
        self.commands.append((request, idempotency_key))
        for result in request["results"]:
            self.records[result["query_id"]] = {
                **result,
                "documents": [{**doc, "staged_blob": None} for doc in result["documents"]],
            }
        return {
            "results": [
                {
                    "query_id": r["query_id"],
                    "source_id": r["source_id"],
                    "status": r["status"],
                    "documents": [{"document_id": d["document_id"]} for d in r["documents"]],
                }
                for r in request["results"]
            ]
        }

    def upload_blob(self, workspace, chunks, *, size, **kwargs):
        data = b"".join(chunks)
        assert len(data) == size
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        assert digest == kwargs.get("expected_digest", digest)
        self.uploads.append(data)
        return StagedBlobRef(uuid4(), workspace, digest, size, "text/plain")


def host(*, sources=None, adapters=None, client=None, cancel=None, settings=None, clock=None) -> Any:
    raw = sources or {
        "docs": {
            "kind": "command",
            "tier": "local_docs",
            "argv": [
                sys.executable,
                "-c",
                "import json; print(json.dumps({'documents':["
                "{'origin':'repo:repo/guide.md','title':'Guide','text':'research evidence'}]}))",
            ],
            "capabilities": ["search", "citations"],
            "trust_cap": "repository",
        }
    }
    registry = ResearchSources(
        adapters or {"command": CommandResearchSource(), "filesystem": FilesystemResearchSource()},
        clock=clock,
    )
    registry.redactor = Redactor()
    values = {"context.research.sources": raw, **(settings or {})}
    return HostContext(
        cast(Any, client or Client()),
        GatewayTable({ResearchSourceRegistry: registry}, "host_gateway"),
        HostId(uuid4()),
        values,
        get_logger("test.research"),
        cancel or CancelSource().token,
    )


def json_script(value):
    return "import sys; sys.stdin.read(); print(" + repr(json.dumps(value)) + ")"
