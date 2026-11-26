"""Real command adapters persist through the bus and capture once, on both backends."""

from integration.context.test_research_repository import source_setting
from skm.modules.context.host.research_query import research_query
from skm.modules.context.ports import ResearchRepository

from ._support import host, spec


def test_host_records_and_reads_cache_through_real_bus(ctx_side, monkeypatch):
    ctx = host(client=ctx_side.client, clock=ctx_side.clock)
    source_setting(ctx_side, **ctx.config["context.research.sources"]["docs"])
    first = research_query(
        ctx,
        spec(save_as_material=True),
        workspace_id=ctx_side.ws,
        project_id=ctx_side.proj,
        step_ref=None,
        mounts={},
    )
    assert first.results[0].status == "ok"
    assert first.results[0].documents[0].staged_blob is not None
    with ctx_side.uow(readonly=True) as uow:
        row = uow.repo(ResearchRepository).get(first.results[0].query_id)
        captured = row["documents"][0]["captured_file_version_id"]
        assert captured
    second = research_query(
        ctx,
        spec(save_as_material=True),
        workspace_id=ctx_side.ws,
        project_id=ctx_side.proj,
        step_ref=None,
        mounts={},
    )
    assert second.results[0].cache_status == "hit"
    assert second.results[0].query_id == first.results[0].query_id
    with ctx_side.uow(readonly=True) as uow:
        assert (
            uow.repo(ResearchRepository).get(second.results[0].query_id)["documents"][0][
                "captured_file_version_id"
            ]
            == captured
        )
