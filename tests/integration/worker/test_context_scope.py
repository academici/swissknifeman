"""Frozen control-plane host-input limits remain usable with real host-chain EffectiveConfig."""

from dataclasses import replace

import pytest

from contracts.execution._worker_protocol_support import worker_claim
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.access.public import generate_secret
from skm.modules.context.domain.manifest import ManifestState
from skm.modules.context.ports import ContextRepository
from skm.modules.execution import public as execution
from skm.modules.execution.application._worker_dtos import document
from skm.modules.execution.host.context_inputs import finalize_stage_context
from skm.modules.settings.public import SetValue
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import Chain
from skm.platform.config.store import ConfigStore, ScopeTree

from .test_context_publication import setup_prompt

KEYS = ("context.host_inputs.max_bytes", "context.work_paths.max")


def set_value(side, key, value, *, version=None, host=False):
    return side.client.dispatch(
        SetValue.from_json(
            {
                "scope": {
                    "level": "host" if host else "project",
                    "scope_id": str(side.host1 if host else side.proj),
                },
                "key": key,
                "value": value,
                "expected_row_version": version,
                "reason": "Frozen host-limit regression",
            }
        ),
        idempotency_key=f"config:{side.new_id()}",
    )


@pytest.mark.parametrize("max_bytes", [0, 128])
def test_real_host_config_cannot_read_work_keys_but_finalizes_with_frozen_begin_limits(
    exec_side, tmp_path, monkeypatch, max_bytes
):
    side = exec_side
    set_value(side, KEYS[0], max_bytes)
    set_value(side, KEYS[1], 10)
    case, stage, step, draft, ctx, env, claim, _, inputs = setup_prompt(side, tmp_path, monkeypatch)
    # The live project config changes after the run bundle was frozen.
    set_value(side, KEYS[0], 128 if max_bytes == 0 else 0, version=1)
    set_value(side, KEYS[1], 20, version=1)
    set_value(side, "worker.disk_min_bytes", 0, host=True)
    with side.uow(readonly=True) as uow:
        host_config = side.app.config.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.HOST, ScopeId(side.host1))
        )
        work_config = side.app.config.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.RUN, ScopeId(case.run.id))
        )
        assert work_config.get(KEYS[0]) != max_bytes
        assert work_config.get(KEYS[1]) == 20
    assert isinstance(host_config, EffectiveConfig)
    assert host_config.chain.kind is Chain.HOST
    for key in KEYS:
        with pytest.raises(SkmError) as refused:
            host_config.get(key)
        assert refused.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    command = execution.BeginStage(
        claim=worker_claim(side, case.claimed),
        stage_id=stage.stage_id,
        round_no=stage.round_no,
        input_digest=stage.input_digest,
        runtime_token_secret=str(generate_secret(lambda n: b"g" * n)),
    )
    begin = side.worker1_client.dispatch(command, idempotency_key=f"begin:{side.new_id()}")
    assert begin["step"]["step_id"] == str(step.id)
    assert begin["step"]["context"]["host_limits"] == {"max_bytes": max_bytes, "max_work_paths": 10}
    begin["step"]["context"]["host_limits"]["max_bytes"] = 1234
    begin = side.worker1_client.dispatch(command, idempotency_key=f"begin-again:{side.new_id()}")
    assert begin["step"]["context"]["host_limits"] == {"max_bytes": max_bytes, "max_work_paths": 10}
    # Admission is a fixture; the Phase-A draft is the actual server-assembled manifest for this step.
    begin["step"]["context"]["draft"] = document(draft)
    for n in range(20):
        (case.root / "src" / f"extra{n:02}.py").write_text("value = 1\n")
    finalized = finalize_stage_context(
        replace(ctx, config=host_config),
        claim,
        begin,
        env,
        inputs,
        workspace_id=side.ws,
        path_patterns=(("repo", "src/**"),),
    )
    with side.uow(readonly=True) as uow:
        manifest = uow.repo(ContextRepository).get(draft.manifest_id)
        assert manifest.state is ManifestState.FINAL
        assert manifest.host_facts["work_paths_count"] == 10
        assert manifest.host_facts["work_paths_truncated"] is True
    if max_bytes == 0:
        assert "HOST-INSTRUCTIONS: check the real answer." not in finalized.rendered_prompt
    else:
        assert "HOST-INSTRUCTIONS: check the real answer." in finalized.rendered_prompt
