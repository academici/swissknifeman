"""Memory repositories for budgets, decisions, and external effects (execution §6.1, DDL ``0016``)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.execution.state import clone_value, execution_state
from skm.modules.execution.domain.budget import (
    BudgetAccount,
    BudgetDimension,
    BudgetReservation,
    record_spend,
)
from skm.modules.execution.domain.decision_request import DecisionAnswer, DecisionRequest, DecisionState
from skm.modules.execution.domain.external_effect import EffectKind, EffectState, ExternalEffect
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.stored_payloads import (
    already_exists,
    field_owned,
    invalid_ref,
    not_found,
    schema_invalid,
)

if TYPE_CHECKING:
    from skm.kernel.ids import ProjectId, RunId, TaskId
    from skm.modules.execution.domain.decision_record import DecisionRecord
    from skm.modules.execution.domain.ids import (
        BudgetReservationId,
        DecisionRequestId,
        ExternalEffectId,
        StepId,
    )

__all__ = [
    "MemoryBudgetRepository",
    "MemoryDecisionRepository",
    "MemoryEffectRepository",
]

_DIGEST_RE: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_COMMIT_KEYS: Final = frozenset(
    {
        "repository_id",
        "target_branch",
        "before_sha",
        "after_sha",
        "tree_sha",
        "baseline_sha",
        "output_ids",
        "output_digests",
        "commit_shas",
        "assignment_fencing_token",
        "slot_fencing_token",
        "writer_epoch_sha",
    }
)
_UNRESOLVED_EFFECTS: Final = frozenset(
    {EffectState.INTENDED, EffectState.EXECUTING, EffectState.OUTCOME_UNKNOWN}
)


class MemoryBudgetRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def add_accounts(self, accounts: Sequence[BudgetAccount]) -> None:
        self._backend.core.require_writable()
        staged: dict[UUID, BudgetAccount] = {}
        for acct in accounts:
            if acct.id in self._state.budget_accounts or acct.id in staged:
                raise already_exists("pk_budget_accounts", id=str(acct.id))
            if acct.run_id not in self._state.runs:
                raise invalid_ref("fk_budget_accounts__runs", run_id=str(acct.run_id))
            if acct.task_id is not None:
                t = self._state.tasks.get(acct.task_id)
                if t is None or t.run_id != acct.run_id:
                    raise invalid_ref("fk_budget_accounts__run_tasks", task_id=str(acct.task_id))
            for other in (*self._state.budget_accounts.values(), *staged.values()):
                if (
                    other.run_id == acct.run_id
                    and other.scope == acct.scope
                    and other.task_id == acct.task_id
                    and other.dimension is acct.dimension
                ):
                    raise already_exists(
                        "uq_budget_accounts__run_id_dimension_run"
                        if acct.scope == "run"
                        else "uq_budget_accounts__task_id_dimension_task",
                        dimension=acct.dimension.value,
                    )
            staged[acct.id] = clone_value(acct)
        self._state.budget_accounts.update(staged)

    def accounts_for(
        self, run_id: RunId, task_id: TaskId | None, dimension: BudgetDimension
    ) -> tuple[BudgetAccount, ...]:
        rows = sorted(
            (
                a
                for a in self._state.budget_accounts.values()
                if a.run_id == run_id
                and a.dimension is dimension
                and (a.task_id is None if task_id is None else a.task_id in (None, task_id))
            ),
            key=lambda a: (0 if a.scope == "run" else 1, str(a.id)),
        )
        return tuple(clone_value(a) for a in rows)

    def record_spend(self, account_ids: Sequence[UUID], amount: Decimal) -> None:
        self._backend.core.require_writable()
        rows = self._state.budget_accounts
        moved, _ = record_spend([rows[account_id] for account_id in account_ids], amount)
        rows.update((account.id, account) for account in moved)

    def reserve(self, account_ids: Sequence[UUID], amount: Decimal) -> bool:
        self._backend.core.require_writable()
        if amount <= 0 or not account_ids:
            raise schema_invalid("reserve amount > 0 and account_ids non-empty")
        ordered_ids = sorted(set(account_ids), key=str)
        accts: list[BudgetAccount] = []
        for aid in ordered_ids:
            found = self._state.budget_accounts.get(aid)
            if found is None:
                raise not_found("budget_account", aid)
            run = self._state.runs.get(found.run_id)
            if run is not None and run.unmetered_at is not None:
                return False
            accts.append(found)
        for acct in accts:
            if acct.limit_value is not None and acct.spent + acct.reserved + amount > acct.limit_value:
                return False
        for acct in accts:
            self._state.budget_accounts[acct.id] = clone_value(
                replace(acct, reserved=acct.reserved + amount, row_version=acct.row_version + 1)
            )
        return True

    def add_reservation(self, reservation: BudgetReservation) -> None:
        self._backend.core.require_writable()
        if reservation.id in self._state.budget_reservations:
            raise already_exists("pk_budget_reservations", id=str(reservation.id))
        for aid in reservation.account_ids:
            if aid not in self._state.budget_accounts:
                raise invalid_ref("fk_budget_reservations__accounts", account_id=str(aid))
        if reservation.step_id is not None and reservation.step_id not in self._state.steps:
            raise invalid_ref("fk_budget_reservations__attempt_steps", step_id=str(reservation.step_id))
        self._state.budget_reservations[reservation.id] = clone_value(reservation)

    def get_reservation(self, reservation_id: BudgetReservationId) -> BudgetReservation:
        found = self._state.budget_reservations.get(reservation_id)
        if found is None:
            raise not_found("budget_reservation", reservation_id)
        return clone_value(found)

    def settle(self, reservation: BudgetReservation, actual: Decimal) -> None:
        self._backend.core.require_writable()
        if actual < 0:
            raise schema_invalid("actual spend >= 0")
        cur = self._state.budget_reservations.get(reservation.id)
        if cur is None:
            raise not_found("budget_reservation", reservation.id)
        if cur.state != "reserved":
            return
        now = (
            self._backend.core.clock.clock.now()
            if self._backend.core.clock.clock is not None
            else (reservation.settled_at or datetime(1970, 1, 1, tzinfo=UTC))
        )
        for aid in sorted(cur.account_ids, key=str):
            acct = self._state.budget_accounts[aid]
            new_res = max(Decimal(0), acct.reserved - cur.amount)
            self._state.budget_accounts[aid] = clone_value(
                replace(acct, reserved=new_res, spent=acct.spent + actual, row_version=acct.row_version + 1)
            )
        self._state.budget_reservations[cur.id] = clone_value(
            replace(cur, state="settled", settled_amount=actual, settled_at=now)
        )

    def release(self, reservation: BudgetReservation) -> None:
        self._backend.core.require_writable()
        cur = self._state.budget_reservations.get(reservation.id)
        if cur is None:
            raise not_found("budget_reservation", reservation.id)
        if cur.state != "reserved":
            return
        now = (
            self._backend.core.clock.clock.now()
            if self._backend.core.clock.clock is not None
            else (reservation.settled_at or datetime(1970, 1, 1, tzinfo=UTC))
        )
        for aid in sorted(cur.account_ids, key=str):
            acct = self._state.budget_accounts[aid]
            new_res = max(Decimal(0), acct.reserved - cur.amount)
            self._state.budget_accounts[aid] = clone_value(
                replace(acct, reserved=new_res, row_version=acct.row_version + 1)
            )
        self._state.budget_reservations[cur.id] = clone_value(
            replace(cur, state="released", settled_amount=None, settled_at=now)
        )

    def open_for_steps(self, step_ids: Sequence[StepId]) -> tuple[BudgetReservation, ...]:
        wanted = set(step_ids)
        rows = sorted(
            (
                r
                for r in self._state.budget_reservations.values()
                if r.state == "reserved" and r.step_id in wanted
            ),
            key=lambda r: (r.created_at, str(r.id)),
        )
        return tuple(clone_value(r) for r in rows)

    def raise_limit(
        self, run_id: RunId, task_id: TaskId | None, dimension: BudgetDimension, new_limit: Decimal | None
    ) -> None:
        self._backend.core.require_writable()
        if new_limit is not None and new_limit <= 0:
            raise schema_invalid("new_limit > 0")
        matched = False
        for acct in list(self._state.budget_accounts.values()):
            if acct.run_id == run_id and acct.task_id == task_id and acct.dimension is dimension:
                self._state.budget_accounts[acct.id] = clone_value(
                    replace(acct, limit_value=new_limit, row_version=acct.row_version + 1)
                )
                matched = True
        if not matched:
            raise not_found("budget_account", f"{run_id}:{task_id}:{dimension.value}")


class MemoryDecisionRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _restore_answer_id(self, req: DecisionRequest) -> DecisionRequest:
        ans_id = next(
            (
                aid
                for aid, (rev, ans) in self._state.decision_answers.items()
                if ans.request_id == req.id and rev == req.revision
            ),
            None,
        )
        return replace(req, answer_id=ans_id)

    def add(self, request: DecisionRequest) -> None:
        self._backend.core.require_writable()
        if request.id in self._state.decision_requests:
            raise already_exists("pk_decision_requests", id=str(request.id))
        run = self._state.runs.get(request.run_id)
        if run is None or run.workspace_id != request.workspace_id:
            raise invalid_ref("fk_decision_requests__runs", run_id=str(request.run_id))
        if request.task_id is not None:
            t = self._state.tasks.get(request.task_id)
            if t is None or t.run_id != request.run_id:
                raise invalid_ref("fk_decision_requests__run_tasks", task_id=str(request.task_id))
        self._state.decision_requests[request.id] = clone_value(request)

    def get(self, request_id: DecisionRequestId, *, for_update: bool = False) -> DecisionRequest:
        del for_update
        found = self._state.decision_requests.get(request_id)
        if found is None:
            raise not_found("decision_request", request_id)
        return clone_value(self._restore_answer_id(found))

    def save(self, request: DecisionRequest) -> None:
        self._backend.core.require_writable()
        cur = self._state.decision_requests.get(request.id)
        if cur is None:
            raise not_found("decision_request", request.id)
        for fname in ("workspace_id", "run_id", "task_id", "kind", "created_at"):
            if getattr(request, fname) != getattr(cur, fname):
                raise field_owned("decision_request", fname)
        self._state.decision_requests[request.id] = clone_value(request)

    def open_for_task(self, task_id: TaskId) -> tuple[DecisionRequest, ...]:
        rows = sorted(
            (
                r
                for r in self._state.decision_requests.values()
                if r.task_id == task_id and r.state is DecisionState.OPEN
            ),
            key=lambda r: (r.created_at, str(r.id)),
        )
        return tuple(clone_value(self._restore_answer_id(r)) for r in rows)

    def add_answer(self, answer: DecisionAnswer) -> None:
        self._backend.core.require_writable()
        if answer.id in self._state.decision_answers:
            raise already_exists("pk_decision_answers", id=str(answer.id))
        req = self._state.decision_requests.get(answer.request_id)
        if req is None:
            raise invalid_ref("fk_decision_answers__decision_requests", request_id=str(answer.request_id))
        if any(
            ans.request_id == req.id and rev == req.revision
            for rev, ans in self._state.decision_answers.values()
        ):
            raise already_exists(
                "uq_decision_answers__request_id_request_revision",
                request_id=str(req.id),
                revision=req.revision,
            )
        self._state.decision_answers[answer.id] = (req.revision, clone_value(answer))

    def answers_for(self, request_id: DecisionRequestId) -> tuple[DecisionAnswer, ...]:
        rows = sorted(
            (pair for pair in self._state.decision_answers.values() if pair[1].request_id == request_id),
            key=lambda pair: (pair[0], pair[1].answered_at, str(pair[1].id)),
        )
        return tuple(clone_value(ans) for _, ans in rows)

    def find_reusable(
        self, project_id: ProjectId, question_key: str, question_digest: str
    ) -> DecisionRecord | None:
        for rec in self._state.decision_records.values():
            if (
                rec.project_id == project_id
                and rec.question_key == question_key
                and rec.question_input_digest == question_digest
                and rec.status == "applied"
            ):
                return clone_value(rec)
        return None

    def add_record(self, record: DecisionRecord) -> None:
        self._backend.core.require_writable()
        if record.id in self._state.decision_records:
            raise already_exists("pk_decision_records", id=str(record.id))
        if record.request_id not in self._state.decision_requests:
            raise invalid_ref("fk_decision_records__decision_requests", request_id=str(record.request_id))
        if record.status == "applied" and any(
            r.project_id == record.project_id
            and r.question_key == record.question_key
            and r.status == "applied"
            for r in self._state.decision_records.values()
        ):
            raise already_exists(
                "uq_decision_records__project_id_question_key_applied", question_key=record.question_key
            )
        self._state.decision_records[record.id] = clone_value(record)

    def supersede_records(self, project_id: ProjectId, question_key: str) -> int:
        self._backend.core.require_writable()
        count = 0
        for rec in list(self._state.decision_records.values()):
            if rec.project_id == project_id and rec.question_key == question_key and rec.status == "applied":
                self._state.decision_records[rec.id] = clone_value(replace(rec, status="superseded"))
                count += 1
        return count

    def count_for_task(self, task_id: TaskId) -> int:
        return sum(1 for r in self._state.decision_requests.values() if r.task_id == task_id)


class MemoryEffectRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _validate_effect(self, effect: ExternalEffect) -> None:
        att = self._state.attempts.get(effect.attempt_id)
        if att is None or (att.run_id, att.task_id, att.workspace_id) != (
            effect.run_id,
            effect.task_id,
            effect.workspace_id,
        ):
            raise invalid_ref("fk_external_effects__attempts", attempt_id=str(effect.attempt_id))
        if not _DIGEST_RE.fullmatch(effect.request_digest):
            raise schema_invalid("request_digest must be sha256:<64 hex>")
        if effect.kind is EffectKind.GIT_COMMIT and not (set(effect.request) >= _GIT_COMMIT_KEYS):
            raise schema_invalid("git_commit effect request lacks required keys")
        if effect.kind is not EffectKind.GIT_COMMIT and effect.intent_id is None:
            raise schema_invalid("non-git_commit effect requires intent_id")
        if effect.state is EffectState.SUCCEEDED and effect.receipt is None:
            raise schema_invalid("succeeded external effect requires receipt")

    def add(self, effect: ExternalEffect) -> None:
        self._backend.core.require_writable()
        if effect.id in self._state.effects:
            raise already_exists("pk_external_effects", id=str(effect.id))
        self._validate_effect(effect)
        if any(
            e.run_id == effect.run_id and e.kind is effect.kind and e.request_digest == effect.request_digest
            for e in self._state.effects.values()
        ):
            raise already_exists(
                "uq_external_effects__run_id_kind_request_digest", request_digest=effect.request_digest
            )
        self._state.effects[effect.id] = clone_value(effect)

    def get(self, effect_id: ExternalEffectId, *, for_update: bool = False) -> ExternalEffect:
        del for_update
        found = self._state.effects.get(effect_id)
        if found is None:
            raise not_found("external_effect", effect_id)
        return clone_value(found)

    def save(self, effect: ExternalEffect) -> None:
        self._backend.core.require_writable()
        cur = self._state.effects.get(effect.id)
        if cur is None:
            raise not_found("external_effect", effect.id)
        for fname in (
            "workspace_id",
            "run_id",
            "attempt_id",
            "task_id",
            "kind",
            "intent_id",
            "request_digest",
        ):
            if getattr(effect, fname) != getattr(cur, fname):
                raise field_owned("external_effect", fname)
        if thaw_json(effect.request) != thaw_json(cur.request):
            raise field_owned("external_effect", "request")
        if cur.receipt is not None and thaw_json(effect.receipt) != thaw_json(cur.receipt):
            raise field_owned("external_effect", "receipt")
        self._validate_effect(effect)
        self._state.effects[effect.id] = clone_value(effect)

    def unresolved(self, *, limit: int) -> tuple[ExternalEffect, ...]:
        rows = sorted(
            (e for e in self._state.effects.values() if e.state in _UNRESOLVED_EFFECTS),
            key=lambda e: (e.updated_at, str(e.id)),
        )
        return tuple(clone_value(e) for e in rows[: max(0, limit)])
