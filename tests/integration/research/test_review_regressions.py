"""Research review regressions: durable identity, host mounts and source isolation."""

from types import SimpleNamespace
from typing import Any, cast, override
from uuid import uuid4

import pytest

from skm.adapters.research.filesystem import FilesystemResearchSource
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.modules.context.host.research_query import research_query, run
from skm.modules.context.ports import ResearchSourceRegistry
from skm.modules.workspace.public import GetProject, ResolveCheckout

from ._support import Client, host, json_script, spec
from .test_filesystem_adapter import git

WID, PID = WorkspaceId(uuid4()), ProjectId(uuid4())
STEP = "step:01900000-0000-7000-8000-000000000777"


def test_service_recreation_uses_persisted_step_result_without_upload_or_dispatch():
    first = host()
    batch = research_query(
        first, spec(save_as_material=True), workspace_id=WID, project_id=PID, step_ref=STEP, mounts={}
    )
    fresh = host(client=first.client, sources=first.config["context.research.sources"])
    again = research_query(
        fresh, spec(save_as_material=True), workspace_id=WID, project_id=PID, step_ref=STEP, mounts={}
    )
    assert [r.query_id for r in again.results] == [r.query_id for r in batch.results]
    assert len(first.client.commands) == 1
    assert len(first.client.uploads) == 1


def test_exact_text_and_parameters_do_not_collide_after_normalization():
    ctx = host()
    batches = [
        research_query(ctx, request, workspace_id=WID, project_id=PID, step_ref=STEP, mounts={})
        for request in (
            spec("research evidence", use_cache=False),
            spec("research  evidence", use_cache=False),
            spec("research evidence", use_cache=False, max_documents=2),
        )
    ]
    assert batches[0].query_digest == batches[1].query_digest
    assert len({r.results[0].query_id for r in batches}) == 3
    assert len({key for _, key in ctx.client.commands}) == 3


def test_absolute_host_roots_bypass_mount_only_cache_and_observe_edits(tmp_path):
    mount, external = tmp_path / "mount", tmp_path / "external"
    mount.mkdir()
    external.mkdir()
    git(mount, "init", "-q")
    (mount / "tracked.md").write_text("research baseline")
    git(mount, "add", ".")
    git(mount, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
    document = external / "guide.md"
    document.write_text("research first")
    ctx = host(
        sources={"docs": {"kind": "filesystem", "tier": "local_docs", "roots": [str(external)]}},
        adapters={"filesystem": FilesystemResearchSource(fs_roots_allow=(str(external),))},
    )
    options = {"workspace_id": WID, "project_id": PID, "step_ref": None, "mounts": {"repo": str(mount)}}
    first = research_query(ctx, spec(), **options)
    assert first.results[0].cache_status == "bypass"
    assert first.results[0].expires_at is None
    document.write_text("research second")
    second = research_query(ctx, spec(), **options)
    assert "second" in second.results[0].documents[0].excerpt
    assert second.results[0].documents[0].content_digest != first.results[0].documents[0].content_digest
    assert not ctx.client.queries


def test_cli_host_operation_resolves_only_authorized_project_mounts(tmp_path):
    (tmp_path / "guide.md").write_text("research local source")

    class MountClient(Client):
        @override
        def ask(self, request):
            if isinstance(request, GetProject):
                assert request.project_id == PID
                return SimpleNamespace(project_id=PID, mounts=(SimpleNamespace(mount_name="repo"),))
            if isinstance(request, ResolveCheckout):
                assert request.project_id == PID
                assert request.host_id == ctx.host_id
                return SimpleNamespace(state="active", is_stale=False, local_locator=str(tmp_path))
            return super().ask(request)

    ctx = host(
        client=MountClient(),
        sources={"docs": {"kind": "filesystem", "tier": "local_docs", "roots": ["repo:."]}},
    )
    batch = cast(
        "dict[str, Any]", run(ctx, {"workspace_id": str(WID), "project_id": str(PID), "text": "research"})
    )
    assert batch["results"][0]["status"] == "ok"
    assert batch["results"][0]["documents"][0]["origin"] == "repo:repo/guide.md"


@pytest.mark.parametrize(
    "locator", [{"page": 0}, {"line_from": -1}, {"page": True}, {"unknown": "bad"}, [], 7]
)
def test_invalid_locator_is_only_one_source_error(locator):
    import sys

    sources = {
        name: {
            "kind": "command",
            "tier": "local_docs",
            "argv": [
                sys.executable,
                "-c",
                json_script(
                    {
                        "documents": [
                            {"origin": "mcp:" + name, "title": name, "text": "research", "locator": loc}
                        ]
                    }
                ),
            ],
        }
        for name, loc in (("bad", locator), ("good", {"page": 1}))
    }
    ctx = host(sources=sources)
    result = research_query(
        ctx, spec(sources=("bad", "good")), workspace_id=WID, project_id=PID, step_ref=None, mounts={}
    )
    assert [r.status for r in result.results] == ["error", "ok"]
    assert result.results[0].error is not None
    assert result.results[0].error.code == "RESEARCH_SOURCE_UNAVAILABLE"
    assert len(ctx.client.commands[0][0]["results"]) == 2


def test_clock_and_ids_are_injected_dependencies():
    from fakes.clock import FrozenClock
    from fakes.ids import SequentialIds
    from skm.adapters.research.retry import ResearchSources

    clock = FrozenClock()
    ctx = host(clock=clock)
    registry = ctx.gateways.get(ResearchSourceRegistry)
    assert isinstance(registry, ResearchSources)
    registry.ids = SequentialIds()
    batch = research_query(
        ctx, spec(use_cache=False), workspace_id=WID, project_id=PID, step_ref=None, mounts={}
    )
    assert batch.results[0].retrieved_at == clock.now()
