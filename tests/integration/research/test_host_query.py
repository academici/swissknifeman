"""Host cache, ladder, redaction, captures and cancellation boundaries."""

from typing import override
from uuid import uuid4

import pytest

from skm.adapters.research.retry import SourceFailed
from skm.kernel.cancel import Cancelled, CancelSource
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.modules.context.domain.research import RawDocument, RawSourceReply, result_to_json
from skm.modules.context.host.research_query import research_query

from ._support import host, spec

WID, PID = WorkspaceId(uuid4()), ProjectId(uuid4())


def execute(ctx, request=None):
    return research_query(ctx, request or spec(), workspace_id=WID, project_id=PID, step_ref=None, mounts={})


def test_host_real_command_cache_hit_does_not_query_or_capture_again():
    ctx = host()
    first = execute(ctx, spec(save_as_material=True))
    assert first.results[0].status == "ok"
    assert ctx.client.uploads == [b"research evidence"]
    assert len(ctx.client.commands) == 1
    assert ctx.client.commands[0][0].to_json()["results"][0]["documents"][0]["staged_blob"]
    ctx.client.cached = {"hit": True, "result": result_to_json(first.results[0])}
    again = execute(ctx, spec(save_as_material=True))
    assert again.results[0].cache_status == "hit"
    assert len(ctx.client.uploads) == 1
    assert len(ctx.client.commands) == 1
    assert again.results[0].query_id == first.results[0].query_id


def test_host_ladder_stops_only_after_whole_tier_and_explicit_sources_bypass_stop():
    sources = {
        name: {"kind": "command", "tier": tier, "argv": ["unavailable"]}
        for name, tier in (("a", "local_docs"), ("b", "local_docs"), ("c", "external_search"))
    }
    calls = []

    class Adapter:
        kind = "command"

        def validate_config(self, config):
            return ()

        def search(self, config, query, *, cancel):
            calls.append(config.source_id)
            return RawSourceReply(
                (RawDocument("mcp:" + config.source_id, "Evidence", "text", {}),), None, (), None, ""
            )

    ctx = host(
        sources=sources, adapters={"command": Adapter()}, settings={"context.research.min_documents": 1}
    )
    batch = execute(ctx)
    assert calls == ["a", "b"]
    assert "ladder_stopped_at:local_docs" in batch.results[-1].limitations
    calls.clear()
    execute(ctx, spec(sources=("a", "c")))
    assert calls == ["a", "c"]


def test_source_error_is_not_empty_or_cached_and_diagnostics_are_redacted():
    class Failed:
        kind = "command"

        def validate_config(self, config):
            return ()

        def search(self, config, query, *, cancel):
            raise SourceFailed()

    ctx = host(adapters={"command": Failed()})
    result = execute(ctx).results[0]
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "RESEARCH_SOURCE_UNAVAILABLE"
    assert result.expires_at is None
    assert result.limitations == ("source_unavailable",)


def test_cancel_after_source_prevents_every_upload_and_dispatch():
    source = CancelSource()

    class Cancels:
        kind = "command"

        def validate_config(self, config):
            return ()

        def search(self, config, query, *, cancel):
            source.cancel("lease_lost")
            return RawSourceReply((RawDocument("mcp:evidence", "Evidence", "text", {}),), None, (), None, "")

    ctx = host(adapters={"command": Cancels()}, cancel=source.token)
    with pytest.raises(Cancelled):
        execute(ctx, spec(save_as_material=True))
    assert ctx.client.commands == []
    assert ctx.client.uploads == []


def test_invalid_source_config_is_recorded_without_executing():
    ctx = host(sources={"docs": {"kind": "command", "tier": "local_docs", "argv": []}})
    result = execute(ctx).results[0]
    assert result.error is not None
    assert result.error.code == "RESEARCH_SOURCE_INVALID"
    assert not result.documents


def test_checkout_source_bypasses_unknown_state_and_no_cache_disables_lookup():
    ctx = host(
        settings={
            "context.research.sources": {
                "docs": {"kind": "filesystem", "tier": "local_docs", "roots": ["repo:."]}
            }
        }
    )
    result = execute(ctx, spec(use_cache=False)).results[0]
    assert result.cache_status == "bypass"
    assert result.expires_at is None
    assert not ctx.client.queries


def test_retry_lost_record_response_reuses_exact_body_without_duplicate_capture():
    from ._support import Client

    class LostResponse(Client):
        @override
        def dispatch(self, request, *, idempotency_key=None):
            response = super().dispatch(request, idempotency_key=idempotency_key)
            if len(self.commands) == 1:
                raise ConnectionError("response lost")
            return response

    ctx = host(client=LostResponse())
    options = {
        "workspace_id": WID,
        "project_id": PID,
        "step_ref": "step:01900000-0000-7000-8000-000000000555",
        "mounts": {},
    }
    request = spec(save_as_material=True)
    with pytest.raises(ConnectionError, match="response lost"):
        research_query(ctx, request, **options)
    fresh = host(client=ctx.client, sources=ctx.config["context.research.sources"])
    result = research_query(fresh, request, **options)
    assert result.results[0].status == "ok"
    assert len(ctx.client.uploads) == 1
    assert len(ctx.client.commands) == 1
