"""Verify and retain complete receipts of previously admitted Git effects."""

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import RepositoryId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._json_reads import texts
from skm.modules.execution.application._primitives import attempt_effect_ids
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._worker_dtos import digest, document
from skm.modules.execution.domain.external_effect import EffectKind, EffectState
from skm.modules.execution.domain.ids import OutputId
from skm.modules.execution.ports import (
    EffectRepository,
    EnvironmentRepository,
    IntegrationSlotRepository,
    OutputRepository,
)
from skm.modules.policy.public import record_outcome


def record_integration(uow: UnitOfWork, ctx: Any, fenced: Any, stage: Any, outcome: Any) -> None:
    raw_receipts = outcome.get("integration_receipts")
    if not isinstance(raw_receipts, list) or not raw_receipts:
        raise error_for(ErrorCode.RESULT_INVALID, "integration success requires complete effect receipts")
    receipts = cast("list[Any]", raw_receipts)
    current = uow.repo(OutputRepository).latest(fenced.attempt.id)
    environment = uow.repo(EnvironmentRepository).for_attempt(fenced.attempt.id)
    if current is None or environment is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "integration requires an output and environment")
    repo = uow.repo(EffectRepository)
    effect_ids = sorted(attempt_effect_ids(uow, fenced.attempt.id))
    effects = [repo.get(identity, for_update=True) for identity in effect_ids]
    expected = {m.repository_id for m in current.manifest.mounts}
    baseline = {b.repository_id: b.commit_sha for b in environment.baseline}
    verified: list[Any] = []
    seen: set[Any] = set()
    for receipt in receipts:
        matches = [
            e
            for e in effects
            if e.request_digest == receipt["request_digest"]
            and e.kind is EffectKind.GIT_COMMIT
            and e.state in {EffectState.EXECUTING, EffectState.SUCCEEDED}
        ]
        if len(matches) != 1:
            raise error_for(ErrorCode.INVALID_REFERENCE, "receipt has no unique admitted Git effect")
        effect = matches[0]
        request = effect.request
        repository_id = RepositoryId(UUID(str(request["repository_id"])))
        if (
            (effect.attempt_id, effect.task_id, effect.run_id, effect.workspace_id)
            != (fenced.attempt.id, fenced.task.id, fenced.run.id, fenced.run.workspace_id)
            or repository_id not in expected
            or repository_id in seen
        ):
            raise error_for(ErrorCode.INVALID_REFERENCE, "effect target is foreign or duplicated")
        seen.add(repository_id)
        if (
            digest({"effect_id": str(effect.id), "kind": effect.kind.value, "request": request})
            != effect.request_digest
            or receipt["ref"] != receipt["after_sha"]
            or request["assignment_fencing_token"] != fenced.claim.fencing_token
            or request["baseline_sha"] != baseline.get(repository_id)
            or any(
                receipt[field] != request[field]
                for field in (
                    "before_sha",
                    "after_sha",
                    "tree_sha",
                    "target_branch",
                    "output_ids",
                    "commit_shas",
                    "writer_epoch_sha",
                )
            )
            or (effect.receipt is not None and document(effect.receipt) != receipt)
        ):
            raise error_for(ErrorCode.INVALID_REFERENCE, "receipt differs from the immutable effect request")
        outputs = [
            uow.repo(OutputRepository).get(OutputId(UUID(identity)))
            for identity in texts(request["output_ids"], "request.output_ids")
        ]
        if (
            not outputs
            or len({o.id for o in outputs}) != len(outputs)
            or current.id not in {o.id for o in outputs}
            or any(o.attempt_id != fenced.attempt.id or o.task_id != fenced.task.id for o in outputs)
            or request["output_digests"] != [o.manifest_digest for o in outputs]
            or (not receipt["commit_shas"] and receipt["before_sha"] != receipt["after_sha"])
        ):
            raise error_for(ErrorCode.INVALID_REFERENCE, "receipt outputs are not the admitted output chain")
        verified.append((effect, receipt))
    if seen != expected:
        raise error_for(ErrorCode.RESULT_INVALID, "integration receipts do not cover every target")
    for effect, receipt in verified:
        repo.save(
            replace(effect, state=EffectState.SUCCEEDED, receipt=document(receipt), updated_at=fenced.now)
        )
        if effect.intent_id is not None:
            record_outcome(
                uow, ctx, intent_id=effect.intent_id, outcome="succeeded", receipt=document(receipt)
            )
    uow.repo(IntegrationSlotRepository).release_for_attempt(fenced.attempt.id)
    outcome["effect_ids"] = [str(effect.id) for effect, _ in verified]
    _, values = effective_values(uow, fenced.run.id)
    commit_shas = [sha for receipt in receipts for sha in receipt["commit_shas"]]
    if "commit_shas" in outcome and outcome["commit_shas"] != commit_shas:
        raise error_for(ErrorCode.INVALID_REFERENCE, "integration summary differs from the receipts")
    emit(
        uow,
        fenced.run,
        "integration-completed",
        {
            "task_id": str(fenced.task.id),
            "attempt_id": str(fenced.attempt.id),
            "output_ids": list(dict.fromkeys(i for receipt in receipts for i in receipt["output_ids"])),
            "commit_shas": commit_shas,
            "target_branch": [r["target_branch"] for r in receipts],
            "integration_receipts": document(receipts),
            "commit_mode": values.get("execution.integration.commit_mode", "final_only"),
            "strategy": values.get("execution.integration.strategy", "squash"),
            "excluded_paths_count": len(current.manifest.excluded_paths),
        },
        cause("stage_outcome", refs=[{"kind": "stage", "id": str(stage.id)}]),
    )
