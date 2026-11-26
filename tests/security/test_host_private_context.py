"""HOST_PRIVATE episodes are excluded before manifest persistence and cloud launch."""

from pathlib import Path
from uuid import uuid4

import pytest

from contracts.context import harness
from contracts.context.harness import ContextSide
from contracts.context.harness import ctx_side as ctx_side
from contracts.context.test_repositories import _resolve_host_inputs
from integration.runtimes.test_codex_argv import _make_request
from skm.adapters.knowledge.local_sqlite_memory import LocalSqliteMemoryStore
from skm.adapters.runtimes.codex.launch import build_launch_plan
from skm.kernel.gateways import GatewayTable
from skm.kernel.json_types import JsonObject
from skm.modules.context import public as context
from skm.modules.context.domain.finalize import sha256_text
from skm.modules.context.ports import MemoryRetriever, TextStore
from skm.modules.extensions.public import SyncBuiltinPacks
from skm.modules.knowledge.ports import EpisodeScope
from skm.modules.knowledge.public import MemoryKind
from skm.modules.runtimes.domain.request import ProcessOwnership
from skm.modules.settings.public import SetValue
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def test_episode_canary_never_enters_hub_run_or_cloud_prompt(
    ctx_side: ContextSide, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = ctx_side
    canary = f"host-private-canary-{uuid4()}"
    store = LocalSqliteMemoryStore(tmp_path / "private" / "episodes.sqlite3", side.clock)
    scope, session_id = EpisodeScope(side.ws, side.proj), uuid4()
    store.record(scope, session_id, MemoryKind.FACT, canary)
    (episode,) = store.search(scope, session_id)
    assert episode.text == canary

    shared = "shared memory can be rendered"
    private_ref = f"memory:{episode.id}"

    class InjectMarkedEpisode:
        def search(self, *_args: object, **_kwargs: object) -> tuple[JsonObject, ...]:
            return (
                {"text": episode.text, "classification": episode.classification, "source_ref": private_ref},
                {"text": shared, "classification": "private", "source_ref": "memory:shared"},
            )

    # Exercise defense in depth if a shared retriever ever receives a classified local episode.
    gateways = GatewayTable(
        {**side.app.gateways.entries, MemoryRetriever: InjectMarkedEpisode()}, "control_plane_gateway"
    )
    make_profile = harness._profile_toml
    monkeypatch.setattr(
        harness,
        "_profile_toml",
        lambda role, version: make_profile(role, version).replace("memory_top_k = 0", "memory_top_k = 4"),
    )
    side.builtin.current = (*side.builtin.current, harness.core_pack("2.0.0"))
    side.client.dispatch(SyncBuiltinPacks(), idempotency_key=side.client.new_idempotency_key())
    side.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(side.proj)},
                "key": "context.memory.enabled",
                "value": True,
            }
        )
    )

    with side.uow() as uow:
        config = side.effective_config(uow)
        default_request = side.make_request(uow, config=config, step_ref="run:1/step:default")
        request = side.make_request(uow, config=config, step_ref="run:1/step:filtered")
        default_draft = context.assemble_draft(
            uow,
            side.app.gateways,
            default_request,
            config=config,
            owner_ref=f"step:{default_request.purpose.step_ref}",
            actor=side.owner,
        )
        draft = context.assemble_draft(
            uow,
            gateways,
            request,
            config=config,
            owner_ref=f"step:{request.purpose.step_ref}",
            actor=side.owner,
        )
        uow.commit()
    with side.uow(readonly=True) as uow:
        for manifest_id in (default_draft.manifest_id, draft.manifest_id):
            manifest = context.get_manifest(uow, manifest_id)
            assert canary not in repr(manifest)
            assert private_ref not in {block.source_ref for block in manifest.blocks}
        assert uow.repo(TextStore).get_many((sha256_text(canary),)) == {}
        uow.rollback()

    blocks, _, facts = _resolve_host_inputs(draft, side)
    final = context.finalize(draft, blocks, facts, side.estimator)
    assert shared in final.rendered_prompt
    assert canary not in final.rendered_prompt
    runtime = _make_request(tmp_path / "runtime", prompt=final.rendered_prompt, config_mode="inherit")
    launch = build_launch_plan(
        runtime,
        binary_path="codex",
        step_dir=tmp_path / "runtime" / "step",
        ownership=ProcessOwnership(runtime.process_owner, "pgroup_best_effort", "codex/host-private"),
        host_environ={},
    )
    assert shared.encode() in launch.stdin
    assert canary.encode() not in launch.stdin
    assert all(canary not in arg for arg in launch.codex_argv)
