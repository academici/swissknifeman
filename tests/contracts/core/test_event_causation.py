"""Causal metadata of events through the bus and the memory UoW (kernel §2.9, §2.11 rule 2).

``E → C → F``: the event ``F`` of command ``C`` keeps ``causation_id = C.request_id`` and
``parent_causation_id = E.id`` in the envelope itself, so the chain survives without operational logs.
Correlation and causation ids from a client are diagnostics: they never choose the scope or the authorization.
The PostgreSQL side of the same envelope is checked in ``integration/postgres/test_uow.py``.
"""

from dataclasses import replace
from typing import Any

import pytest

from fakes.app import Harness, build_harness, request_id
from fakes.demo_module import ECHO, Echo, EchoResult, handle_echo, manifest
from skm.application_bus.ports import EventReader
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, InternalError
from skm.kernel.events import EventEnvelope


def echo(h: Harness, text: str = "hello", *, workspace: Any = None) -> Echo:
    return Echo(workspace_id=workspace or h.seed.workspace_id, text=text)


def test_chain_e_c_f_keeps_distinct_immediate_and_parent_causes() -> None:
    h = build_harness()
    h.bus.dispatch(echo(h, "e"), actor=h.actor, meta=h.meta(request=request_id(1)))
    (first,) = h.events()
    assert (first.request_id, first.causation_id, first.correlation_id) == (request_id(1),) * 3
    assert first.parent_causation_id is None

    # What a subscriber does: a verified event E becomes the cause of a new command C.
    meta_c = h.meta(request=request_id(2), correlation_id=first.correlation_id, causation_id=str(first.id))
    h.bus.dispatch(echo(h, "f"), actor=h.actor, meta=meta_c)
    _, second = h.events()
    assert second.request_id == request_id(2)
    assert second.causation_id == request_id(2)  # F.causation_id = C.request_id
    assert second.parent_causation_id == str(first.id)  # F.parent_causation_id = E.id
    assert second.correlation_id == first.correlation_id  # the root of the chain is kept
    assert second.causation_id != second.parent_causation_id


def test_chain_survives_serialization_and_a_reader_without_any_logs() -> None:
    h = build_harness()
    h.bus.dispatch(echo(h, "e"), actor=h.actor, meta=h.meta(request=request_id(1)))
    (first,) = h.events()
    meta_c = h.meta(request=request_id(2), correlation_id=first.correlation_id, causation_id=str(first.id))
    h.bus.dispatch(echo(h, "f"), actor=h.actor, meta=meta_c)
    with h.uow_factory(h.meta(), readonly=True) as uow:
        read = uow.repo(EventReader).after_workspace_seq(h.seed.workspace_id, 0, types=None, limit=10)
    restored = [EventEnvelope.from_json(envelope.to_json()) for envelope in read]
    assert restored == list(read)
    assert restored[1].causation_id == request_id(2)
    assert restored[1].parent_causation_id == str(restored[0].id)


def test_old_and_parentless_envelopes_read_as_none() -> None:
    h = build_harness()
    h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    (envelope,) = h.events()
    document = envelope.to_json()
    assert document["parent_causation_id"] is None
    del document["parent_causation_id"]  # an envelope written before the field existed
    assert EventEnvelope.from_json(document).parent_causation_id is None


def test_embedded_client_roots_the_chain_at_its_own_request() -> None:
    h = build_harness()
    h.client.dispatch(echo(h))
    (envelope,) = h.events()
    assert envelope.request_id is not None
    assert envelope.request_id.startswith("req_")
    assert len(envelope.request_id) == 30
    assert envelope.correlation_id == envelope.causation_id == envelope.request_id
    assert envelope.parent_causation_id is None


def test_rolled_back_attempt_leaves_no_event_and_the_retry_is_the_first_event() -> None:
    attempts: list[int] = []

    def failing(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        handle_echo(cmd, ctx, uow)
        attempts.append(1)
        raise RuntimeError("after record")

    h = build_harness(manifests=(manifest(commands=(replace(ECHO, handler=failing),)),))
    with pytest.raises(InternalError):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta(request=request_id(1), causation_id="parent-1"))
    assert h.events() == []
    assert h.backend.committed.core.outbox == {}
    assert h.backend.committed.core.feed_seq.get(h.seed.workspace_id) is None  # no number was consumed

    good = build_harness()
    good.bus.dispatch(
        echo(good), actor=good.actor, meta=good.meta(request=request_id(2), causation_id="parent-1")
    )
    (retried,) = good.events()
    assert (retried.workspace_seq, retried.stream_seq) == (1, 1)
    assert (retried.causation_id, retried.parent_causation_id) == (request_id(2), "parent-1")


def test_serialization_failure_retry_keeps_the_causal_ids_and_commits_once() -> None:
    calls: list[int] = []

    def flaky(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        calls.append(1)
        result = handle_echo(cmd, ctx, uow)
        if len(calls) == 1:
            raise Conflict(ErrorCode.SERIALIZATION_FAILURE, "40001", retryable=True)
        return result

    h = build_harness(manifests=(manifest(commands=(replace(ECHO, handler=flaky),)),))
    h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta(request=request_id(4), causation_id="parent-9"))
    assert len(calls) == 2
    (envelope,) = h.events()
    assert (envelope.workspace_seq, envelope.causation_id, envelope.parent_causation_id) == (
        1,
        request_id(4),
        "parent-9",
    )
    assert len(h.backend.committed.core.outbox) == 2  # rows of the committed attempt only


def test_forged_client_ids_are_recorded_verbatim_but_decide_neither_scope_nor_authz() -> None:
    h = build_harness()
    h.bus.dispatch(
        echo(h, "other", workspace=h.seed.other_workspace_id),
        actor=h.actor,
        meta=h.meta(request=request_id(1)),
    )
    (foreign,) = h.events()
    other_seq_before = h.backend.committed.core.feed_seq[h.seed.other_workspace_id]

    forged = h.meta(
        request=request_id(2), correlation_id=foreign.correlation_id, causation_id=str(foreign.id)
    )
    h.bus.dispatch(echo(h, "mine"), actor=h.actor, meta=forged)
    mine = h.events()[-1]
    assert mine.workspace_id == h.seed.workspace_id  # the DTO scope decides, not the forged parent
    assert mine.parent_causation_id == str(foreign.id)  # stored as given: diagnostic, not a verified edge
    assert h.backend.committed.core.feed_seq[h.seed.other_workspace_id] == other_seq_before
    assert {call.scope_id for call in h.authorizer.calls} == {h.seed.workspace_id, h.seed.other_workspace_id}
    assert h.authorizer.calls[-1].scope_id == h.seed.workspace_id

    # Authorization does not look at the forged ids: a denial stops the command before anything is written.
    h.authorizer.deny_all()
    with pytest.raises(Forbidden):
        h.bus.dispatch(
            echo(h, "denied"), actor=h.actor, meta=h.meta(request=request_id(3), causation_id=str(foreign.id))
        )
    assert len(h.events()) == 2
    assert h.audit()[-1].decision == "denied"
    with h.uow_factory(h.meta(), readonly=True) as uow:
        reader = uow.repo(EventReader)
        assert [
            e.payload["text"]
            for e in reader.after_workspace_seq(h.seed.other_workspace_id, 0, types=None, limit=9)
        ] == ["other"]


def test_overlong_forged_causation_is_refused_and_writes_nothing() -> None:
    h = build_harness()
    with pytest.raises(InternalError):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta(causation_id="x" * 65))
    assert h.events() == []
