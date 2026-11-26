"""``IdempotencyStore`` over the memory state (receipts keyed by workspace/principal/operation/key)."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime

from skm.adapters.memory.core.state import NIL_UUID, MemoryBackendState
from skm.application_bus.ports import IdempotencyReceipt
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import PrincipalId, WorkspaceId

__all__ = ["MemoryIdempotencyStore"]


class MemoryIdempotencyStore:
    def __init__(self, state: MemoryBackendState) -> None:
        self._core = state.core

    def get(
        self,
        workspace_id: WorkspaceId | None,
        principal_id: PrincipalId,
        operation: str,
        key: str,
    ) -> IdempotencyReceipt | None:
        row = self._core.idempotency.get((workspace_id or NIL_UUID, principal_id, operation, key))
        if row is None or row.expires_at <= self._core.clock.now():
            return None
        return replace(row, result=deepcopy(row.result))

    def put(self, receipt: IdempotencyReceipt) -> None:
        self._core.require_writable()
        row_key = (receipt.workspace_id or NIL_UUID, receipt.principal_id, receipt.operation, receipt.key)
        existing = self._core.idempotency.get(row_key)
        if existing is not None and existing.expires_at > self._core.clock.now():
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "idempotency receipt already exists",
                details={"kind": "idempotency_receipt"},
            )
        self._core.idempotency[row_key] = replace(receipt, result=deepcopy(receipt.result))

    def purge_expired(self, now: datetime, *, limit: int) -> int:
        self._core.require_writable()
        expired = [row_key for row_key, row in self._core.idempotency.items() if row.expires_at <= now]
        for row_key in expired[: max(limit, 0)]:
            del self._core.idempotency[row_key]
        return min(len(expired), max(limit, 0))
