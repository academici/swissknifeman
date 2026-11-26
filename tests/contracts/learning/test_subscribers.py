"""Outcome attribution and duplicate delivery over both learning stores."""

from datetime import timedelta
from typing import cast
from uuid import uuid4

import pytest

from contracts.knowledge.harness import KnowledgeSide, knowledge_side
from skm.application_bus.context import SubscriberContext
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import EventId, ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.learning.application import subscribers
from skm.modules.learning.application.commands.extract_candidates import ActivityStorage, CandidateExtracted
from skm.modules.learning.ports import ActivityRecordRepository, CandidateRepository, SignalRepository
from skm.platform.config import ConfigStore, ScopeTree
from skm.platform.config.effective import EffectiveConfig
from skm.platform.logging.logger import get_logger
from skm.platform.system_ids import Uuid7Generator
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "knowledge_side", "pg_session", "test_database"]


def test_task_accepted_keeps_each_attempt_outcome_and_deduplicates(
    knowledge_side: KnowledgeSide, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = knowledge_side
    task, run, output, failed, superseded, accepted = (str(uuid4()) for _ in range(6))
    attempts: dict[str, JsonObject] = {
        attempt: {
            "attempt_id": attempt,
            "run_id": run,
            "state": state,
            "accepted": attempt == accepted,
            "activity_complete": True,
            "changed_paths": [],
            "source_step_ids": [],
            "activities": [{"workarounds": ["Wait for the local dependency to start"]}],
            "exposure_coverage": "complete",
            "exposed_lesson_refs": [],
        }
        for attempt, state in ((failed, "failed"), (superseded, "superseded"), (accepted, "finished"))
    }
    now = side.clock.now()
    monkeypatch.setattr(
        subscribers, "list_task_attempts_for_learning", lambda _uow, _task: tuple(attempts.values())
    )
    monkeypatch.setattr(subscribers, "get_attempt_activity", lambda _uow, attempt: attempts[str(attempt)])
    monkeypatch.setattr(subscribers, "list_check_executions", lambda _uow, _attempt: ())
    monkeypatch.setattr(
        subscribers,
        "get_attempt_summary",
        lambda _uow, attempt: {
            "current_output_id": output if str(attempt) == accepted else None,
            "finished_at": (now - timedelta(seconds=1)).isoformat(),
        },
    )
    event = EventEnvelope(
        id=EventId(uuid4()),
        type="urn:skm:execution:event:task-accepted:v1",
        schema_version=1,
        workspace_id=side.workspace,
        stream_kind="run",
        stream_id=side.project,
        stream_seq=1,
        workspace_seq=1,
        global_position=None,
        actor_id=None,
        request_id=None,
        correlation_id=side.meta().request_id,
        causation_id=None,
        occurred_at=now,
        recorded_at=now,
        payload={
            "project_id": str(side.project),
            "task_id": task,
            "attempt_id": accepted,
            "output_id": output,
        },
    )
    ids = Uuid7Generator(side.clock)
    spec = side.app.bus._registry.subscribers()
    (subscriber,) = [item for item in spec if item.consumer_id == "learning.task_outcome_signals"]
    assert event.type in subscriber.event_types
    for delivery in range(1, 4):
        with side.uow() as uow:

            def config(scope: ScopeRef) -> EffectiveConfig:
                return side.app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), scope)

            project = ScopeRef(ScopeKind.PROJECT, ScopeId(side.project))
            subscriber.handler(
                event,
                SubscriberContext(
                    subscriber.consumer_id,
                    delivery,
                    side.clock,
                    ids,
                    get_logger("tests.learning"),
                    config(project),
                    side.app.gateways,
                    config,
                ),
                uow,
            )
            uow.commit()

    with side.uow(readonly=True) as uow:
        (candidate,) = (
            uow.repo(CandidateRepository)
            .list((ScopeId(side.project),), states=frozenset(), after=None, limit=3)
            .items
        )
        signals = uow.repo(SignalRepository).for_candidate(candidate.id)
        repo = cast("ActivityStorage", uow.repo(ActivityRecordRepository))
        records = (repo.get(signal.activity_record_id) for signal in signals)
        outcomes = {row.source_key: row.outcome for row in records}
        assert outcomes == {failed: "failure", superseded: "unknown", accepted: "success"}
        assert len(signals) == 3
        assert repo.count_for_project(side.project) == 3
        assert candidate.n_total == 3
        assert candidate.known_outcome_total == candidate.independent_known_total == 2
        assert candidate.independent_success_total == 1
    events = list(
        side.app.client(actor=side.owner, surface=Surface.TEST).events(
            workspace_id=side.workspace, after=0, types=frozenset({CandidateExtracted.event_type})
        )
    )
    (extracted,) = events
    assert extracted.stream_id == candidate.id
    assert extracted.payload["consolidation"] == "add"
