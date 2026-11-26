"""Record selection for ``MemoryExecutionQueries`` documents (execution §6.2, §8).

The documents themselves come from ``skm.modules.execution.domain.read_documents``; this module only picks
and orders the records of the memory state the way the PostgreSQL queries do.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from skm.modules.execution.domain.read_documents import (
    AttemptDetailParts,
)
from skm.modules.execution.domain.read_documents import (
    build_attempt_detail_doc as _attempt_detail_doc,
)
from skm.modules.execution.domain.read_documents import (
    build_attempt_summary_doc as _attempt_summary_doc,
)
from skm.modules.execution.domain.read_documents import (
    build_task_doc as _task_doc,
)

if TYPE_CHECKING:
    from skm.adapters.memory.execution.state import MemoryExecutionState
    from skm.kernel.json_types import JsonObject
    from skm.modules.execution.domain.attempt import Attempt
    from skm.modules.execution.domain.output import Output
    from skm.modules.execution.domain.task import Task

__all__: list[str] = []

_NO_START: datetime = datetime(1970, 1, 1, tzinfo=UTC)


def _attempt_outputs(st: MemoryExecutionState, att: Attempt) -> list[Output]:
    return sorted((o for o in st.outputs.values() if o.attempt_id == att.id), key=lambda o: o.seq)


def build_attempt_summary_doc(st: MemoryExecutionState, att: Attempt) -> JsonObject:
    return _attempt_summary_doc(att, _attempt_outputs(st, att))


def build_task_doc(st: MemoryExecutionState, task: Task, *, summary_only: bool) -> JsonObject:
    attempts = (
        ()
        if summary_only
        else tuple(
            sorted((a for a in st.attempts.values() if a.task_id == task.id), key=lambda a: a.attempt_no)
        )
    )
    return _task_doc(
        task,
        bundle=st.bundles.get(task.run_id),
        tasks_by_id={t.id: t for t in st.tasks.values() if t.run_id == task.run_id},
        edges=tuple(e for e in st.task_edges.values() if e.run_id == task.run_id),
        attempts=attempts,
        outputs_by_attempt={a.id: _attempt_outputs(st, a) for a in attempts},
        summary_only=summary_only,
    )


def build_attempt_detail_doc(st: MemoryExecutionState, att: Attempt) -> JsonObject:
    revs = sorted(
        (r for r in st.reviews.values() if r.attempt_id == att.id),
        key=lambda r: (r.round_no, str(r.id)),
    )
    rev_ids = {r.id for r in revs}
    parts = AttemptDetailParts(
        env=next((e for e in st.environments.values() if e.attempt_id == att.id), None),
        stages=sorted(
            (s for s in st.stages.values() if s.attempt_id == att.id),
            key=lambda s: (s.seq, s.started_at, str(s.id)),
        ),
        steps=sorted(
            (s for s in st.steps.values() if s.attempt_id == att.id),
            key=lambda s: (s.started_at, str(s.id)),
        ),
        outs=_attempt_outputs(st, att),
        checks=sorted(
            (c for c in st.checks.values() if c.attempt_id == att.id),
            key=lambda c: (c.started_at or _NO_START, str(c.id)),
        ),
        revs=revs,
        fnds=sorted((f for f in st.findings.values() if f.review_id in rev_ids), key=lambda f: str(f.id)),
        effs=sorted(
            (e for e in st.effects.values() if e.attempt_id == att.id),
            key=lambda e: (e.created_at, str(e.id)),
        ),
        recs=sorted(
            (r for r in st.recoveries.values() if r.attempt_id == att.id), key=lambda r: (r.at, str(r.id))
        ),
    )
    return _attempt_detail_doc(att, parts)
