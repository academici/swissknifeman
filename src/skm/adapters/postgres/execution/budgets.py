"""PostgreSQL ``BudgetRepository`` adapter (execution §6; DDL ``0016``)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import budget_account_from_row, budget_reservation_from_row
from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import opt_aware, run
from skm.adapters.postgres.jsonb import require_aware
from skm.modules.execution.domain.stored_payloads import invalid_ref, not_found, schema_invalid

if TYPE_CHECKING:
    from skm.kernel.ids import RunId, TaskId
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, BudgetReservation
    from skm.modules.execution.domain.ids import BudgetReservationId, StepId

__all__ = ["PostgresBudgetRepository"]

_RUN_WS: Final = "SELECT workspace_id FROM skm_execution.runs WHERE id = %s"
_INSERT_ACCOUNT: Final = """
INSERT INTO skm_execution.budget_accounts (
    id, run_id, workspace_id, scope, task_id, dimension, limit_value, spent, reserved, row_version
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
# ``scope`` repeats the predicate of the partial unique indexes (ck_budget_accounts__scope ties it to
# ``task_id``), so each branch is an index lookup instead of a scan of every account of every run.
_ACCOUNTS_RUN_ONLY: Final = """
SELECT * FROM skm_execution.budget_accounts
 WHERE scope = 'run' AND run_id = %s AND dimension = %s
 ORDER BY id ASC
"""
_ACCOUNTS_RUN_AND_TASK: Final = """
SELECT * FROM skm_execution.budget_accounts
 WHERE dimension = %s
   AND ((scope = 'run' AND run_id = %s) OR (scope = 'task' AND task_id = %s AND run_id = %s))
 ORDER BY CASE WHEN scope = 'run' THEN 0 ELSE 1 END ASC, id ASC
"""
_LOCK_ACCOUNTS_WITH_RUN: Final = """
SELECT ba.*, r.unmetered_at
  FROM skm_execution.budget_accounts ba
  JOIN skm_execution.runs r ON r.id = ba.run_id
 WHERE ba.id = ANY(%s::uuid[])
 ORDER BY ba.id ASC
   FOR UPDATE OF ba
"""
_RESERVE_ACCOUNTS: Final = """
UPDATE skm_execution.budget_accounts
   SET reserved = reserved + %s, row_version = row_version + 1
 WHERE id = ANY(%s::uuid[])
   AND (limit_value IS NULL OR spent + reserved + %s <= limit_value)
"""
_ACCOUNTS_META: Final = """
SELECT id, run_id, workspace_id FROM skm_execution.budget_accounts WHERE id = ANY(%s::uuid[])
"""
_STEP_ATTEMPT: Final = "SELECT attempt_id FROM skm_execution.attempt_steps WHERE id = %s"
_INSERT_RESERVATION: Final = """
INSERT INTO skm_execution.budget_reservations (
    id, run_id, workspace_id, account_ids, dimension, attempt_id, step_id,
    amount, state, settled_amount, created_at, settled_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_GET_RESERVATION: Final = "SELECT * FROM skm_execution.budget_reservations WHERE id = %s"
_LOCK_RESERVATION: Final = "SELECT * FROM skm_execution.budget_reservations WHERE id = %s FOR UPDATE"
_LOCK_ACCOUNTS_ONLY: Final = """
SELECT id FROM skm_execution.budget_accounts WHERE id = ANY(%s::uuid[]) ORDER BY id ASC FOR UPDATE
"""
_SETTLE_ACCOUNTS: Final = """
UPDATE skm_execution.budget_accounts
   SET reserved = GREATEST(0, reserved - %s), spent = spent + %s, row_version = row_version + 1
 WHERE id = ANY(%s::uuid[])
"""
_SETTLE_RESERVATION: Final = """
UPDATE skm_execution.budget_reservations
   SET state = 'settled', settled_amount = %s, settled_at = COALESCE(%s, clock_timestamp())
 WHERE id = %s
"""
_RELEASE_ACCOUNTS: Final = """
UPDATE skm_execution.budget_accounts
   SET reserved = GREATEST(0, reserved - %s), row_version = row_version + 1
 WHERE id = ANY(%s::uuid[])
"""
_RELEASE_RESERVATION: Final = """
UPDATE skm_execution.budget_reservations
   SET state = 'released', settled_amount = NULL, settled_at = COALESCE(%s, clock_timestamp())
 WHERE id = %s
"""
_OPEN_FOR_STEPS: Final = """
SELECT * FROM skm_execution.budget_reservations
 WHERE state = 'reserved' AND step_id = ANY(%s::uuid[])
 ORDER BY created_at ASC, id ASC
"""
# One statement per scope, each restating its partial unique index's predicate so the index serves it.
_RAISE_RUN_LIMIT: Final = """
UPDATE skm_execution.budget_accounts
   SET limit_value = %s, row_version = row_version + 1
 WHERE scope = 'run' AND run_id = %s AND dimension = %s
"""
_RAISE_TASK_LIMIT: Final = """
UPDATE skm_execution.budget_accounts
   SET limit_value = %s, row_version = row_version + 1
 WHERE scope = 'task' AND task_id = %s AND dimension = %s AND run_id = %s
"""


class PostgresBudgetRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def add_accounts(self, accounts: Sequence[BudgetAccount]) -> None:
        if not accounts:
            return

        def _op() -> None:
            ws_cache: dict[UUID, UUID] = {}
            with self._conn.cursor(row_factory=dict_row) as cur:
                for acct in accounts:
                    rid = UUID(str(acct.run_id))
                    ws_id = ws_cache.get(rid)
                    if ws_id is None:
                        cur.execute(_RUN_WS, (rid,))
                        rw = cur.fetchone()
                        if rw is None:
                            raise invalid_ref("fk_budget_accounts__runs", run_id=str(acct.run_id))
                        ws_id = as_uuid(rw["workspace_id"])
                        ws_cache[rid] = ws_id
                    cur.execute(
                        _INSERT_ACCOUNT,
                        (
                            acct.id,
                            acct.run_id,
                            ws_id,
                            acct.scope,
                            acct.task_id,
                            acct.dimension.value,
                            acct.limit_value,
                            acct.spent,
                            acct.reserved,
                            max(acct.row_version, 1),
                        ),
                    )

        run(_op)

    def accounts_for(
        self, run_id: RunId, task_id: TaskId | None, dimension: BudgetDimension
    ) -> tuple[BudgetAccount, ...]:
        def _op() -> tuple[BudgetAccount, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if task_id is None:
                    cur.execute(_ACCOUNTS_RUN_ONLY, (run_id, dimension.value))
                else:
                    cur.execute(_ACCOUNTS_RUN_AND_TASK, (dimension.value, run_id, task_id, run_id))
                return tuple(budget_account_from_row(r) for r in cur.fetchall())

        return run(_op)

    def record_spend(self, account_ids: Sequence[UUID], amount: Decimal) -> None:
        if amount <= 0 or not account_ids:
            raise schema_invalid("observed spend requires positive amount and non-empty account_ids")
        ordered = sorted(set(account_ids), key=str)

        def _op() -> None:
            with self._conn.cursor() as cur:
                cur.execute(_LOCK_ACCOUNTS_ONLY, (ordered,))
                if len(cur.fetchall()) != len(ordered):
                    raise invalid_ref("observed_budget_accounts")
                cur.execute(
                    """UPDATE skm_execution.budget_accounts
                       SET spent = spent + %s, row_version = row_version + 1 WHERE id = ANY(%s)""",
                    (amount, ordered),
                )

        run(_op)

    def reserve(self, account_ids: Sequence[UUID], amount: Decimal) -> bool:
        if amount <= 0 or not account_ids:
            raise schema_invalid("reserve requires positive amount and non-empty account_ids")
        ordered = sorted(set(account_ids), key=str)

        def _op() -> bool:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_ACCOUNTS_WITH_RUN, (ordered,))
                rows = cur.fetchall()
                found_ids = {as_uuid(r["id"]) for r in rows}
                for aid in ordered:
                    if aid not in found_ids:
                        raise not_found("budget_account", aid)
                for r in rows:
                    if r["unmetered_at"] is not None:
                        return False
                    lim = None if r["limit_value"] is None else Decimal(str(r["limit_value"]))
                    if (
                        lim is not None
                        and Decimal(str(r["spent"])) + Decimal(str(r["reserved"])) + amount > lim
                    ):
                        return False
                cur.execute(_RESERVE_ACCOUNTS, (amount, ordered, amount))
                return True

        return run(_op)

    def add_reservation(self, reservation: BudgetReservation) -> None:
        if not 1 <= len(reservation.account_ids) <= 4:
            raise schema_invalid("reservation account_ids must contain 1..4 accounts", field="account_ids")

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                wanted = list(dict.fromkeys(reservation.account_ids))
                cur.execute(_ACCOUNTS_META, (wanted,))
                arows = cur.fetchall()
                if len(arows) != len(wanted):
                    raise invalid_ref("fk_budget_reservations__accounts")
                run_id = as_uuid(arows[0]["run_id"])
                ws_id = as_uuid(arows[0]["workspace_id"])
                att_id: UUID | None = None
                if reservation.step_id is not None:
                    cur.execute(_STEP_ATTEMPT, (reservation.step_id,))
                    sr = cur.fetchone()
                    if sr is None:
                        raise invalid_ref(
                            "fk_budget_reservations__attempt_steps", step_id=str(reservation.step_id)
                        )
                    att_id = as_uuid(sr["attempt_id"])
                cur.execute(
                    _INSERT_RESERVATION,
                    (
                        reservation.id,
                        run_id,
                        ws_id,
                        list(reservation.account_ids),
                        reservation.dimension.value,
                        att_id,
                        reservation.step_id,
                        reservation.amount,
                        reservation.state,
                        reservation.settled_amount,
                        require_aware(reservation.created_at),
                        opt_aware(reservation.settled_at),
                    ),
                )

        run(_op)

    def get_reservation(self, reservation_id: BudgetReservationId) -> BudgetReservation:
        def _op() -> BudgetReservation:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_RESERVATION, (reservation_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("budget_reservation", reservation_id)
                return budget_reservation_from_row(row)

        return run(_op)

    def settle(self, reservation: BudgetReservation, actual: Decimal) -> None:
        if actual < 0:
            raise schema_invalid("actual spend >= 0", field="actual")

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_RESERVATION, (reservation.id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("budget_reservation", reservation.id)
                cur_res = budget_reservation_from_row(row)
                if cur_res.state != "reserved":
                    return
                ordered = sorted(set(cur_res.account_ids), key=str)
                cur.execute(_LOCK_ACCOUNTS_ONLY, (ordered,))
                cur.execute(_SETTLE_ACCOUNTS, (cur_res.amount, actual, ordered))
                cur.execute(_SETTLE_RESERVATION, (actual, opt_aware(reservation.settled_at), cur_res.id))

        run(_op)

    def release(self, reservation: BudgetReservation) -> None:
        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_RESERVATION, (reservation.id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("budget_reservation", reservation.id)
                cur_res = budget_reservation_from_row(row)
                if cur_res.state != "reserved":
                    return
                ordered = sorted(set(cur_res.account_ids), key=str)
                cur.execute(_LOCK_ACCOUNTS_ONLY, (ordered,))
                cur.execute(_RELEASE_ACCOUNTS, (cur_res.amount, ordered))
                cur.execute(_RELEASE_RESERVATION, (opt_aware(reservation.settled_at), cur_res.id))

        run(_op)

    def open_for_steps(self, step_ids: Sequence[StepId]) -> tuple[BudgetReservation, ...]:
        if not step_ids:
            return ()

        def _op() -> tuple[BudgetReservation, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_OPEN_FOR_STEPS, ([UUID(str(s)) for s in step_ids],))
                return tuple(budget_reservation_from_row(r) for r in cur.fetchall())

        return run(_op)

    def raise_limit(
        self, run_id: RunId, task_id: TaskId | None, dimension: BudgetDimension, new_limit: Decimal | None
    ) -> None:
        if new_limit is not None and new_limit <= 0:
            raise schema_invalid("new_limit > 0", field="new_limit")

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if task_id is None:
                    cur.execute(_RAISE_RUN_LIMIT, (new_limit, run_id, dimension.value))
                else:
                    cur.execute(_RAISE_TASK_LIMIT, (new_limit, task_id, dimension.value, run_id))
                if cur.rowcount == 0:
                    raise not_found("budget_account", f"{run_id}:{task_id}:{dimension.value}")

        run(_op)
