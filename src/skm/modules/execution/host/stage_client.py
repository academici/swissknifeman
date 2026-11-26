"""Assignment-bound worker operations; stage handlers cannot dispatch arbitrary commands."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from itertools import islice
from typing import TYPE_CHECKING, cast

from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from skm.application_bus.client import SkmClient
    from skm.kernel.cancel import CancelToken
    from skm.kernel.ids import RepositoryId
    from skm.modules.artifacts.public import StagedBlobRef
    from skm.modules.execution.domain.lease import WorkerClaim
    from skm.modules.execution.host.heartbeat import HostConcurrency


def claim_json(claim: WorkerClaim) -> JsonObject:
    return {
        "assignment_id": str(claim.assignment_id),
        "attempt_id": str(claim.attempt_id),
        "worker_id": str(claim.worker_id),
        "fencing_token": claim.fencing_token,
    }


class BoundStageClient:
    """Stage operations always use the worker credential and resume the same assignment."""

    __slots__ = (
        "__cancel",
        "__claim",
        "__client",
        "__commands",
        "__failures",
        "__progress",
        "__renewals_closed",
        "__stop",
        "__tool_calls",
        "guard",
    )

    def __init__(
        self,
        client: SkmClient,
        claim: WorkerClaim,
        commands: Mapping[str, Callable[[JsonObject], object]],
        cancel: CancelToken,
        on_stop: Callable[[str], None] = lambda _reason: None,
        *,
        concurrency: HostConcurrency,
    ) -> None:
        self.__client, self.__claim, self.__commands, self.__cancel = client, claim, commands, cancel
        self.__stop, self.__failures = on_stop, 0
        self.guard = concurrency.lock()
        self.__progress: JsonObject = {}
        self.__tool_calls: dict[str, JsonObject] = {}
        self.__renewals_closed = False

    def _send(self, name: str, payload: JsonObject) -> JsonObject:
        self.__cancel.raise_if_cancelled()
        command = self.__commands[name]({**payload, "claim": claim_json(self.__claim)})
        from skm.kernel.errors import BackendUnavailable

        key = self.__client.new_idempotency_key()
        try:
            return cast("JsonObject", self.__client.dispatch(command, idempotency_key=key))
        except BackendUnavailable:
            progress = payload.get("progress")
            if (
                name != "renew_lease"
                or not isinstance(progress, dict)
                or progress.get("phase") != "runtime_started"
            ):
                raise
            self.__cancel.raise_if_cancelled()
            return cast("JsonObject", self.__client.dispatch(command, idempotency_key=key))

    def _renew(self) -> JsonObject:
        from skm.kernel.error_codes import ErrorCode
        from skm.kernel.errors import SkmError

        try:
            while True:
                progress = dict(self.__progress)
                batch = dict(islice(self.__tool_calls.items(), 100))
                if batch:
                    progress["tool_calls"] = {"coverage": "partial", "calls": list(batch.values())}
                signal = self._send("renew_lease", {"progress": progress})
                # The runtime handoff is acknowledged once. Tool reports are ordinary renewals.
                self.__progress.pop("phase", None)
                self.__failures = 0
                for call_id in batch:
                    del self.__tool_calls[call_id]
                if signal.get("cancel_requested"):
                    self.__stop("user_cancel")
                    return signal
                if not self.__tool_calls:
                    return signal
        except Exception as error:
            self.__failures += 1
            if (isinstance(error, SkmError) and error.code is ErrorCode.LEASE_LOST) or self.__failures >= 2:
                self.__stop("lease_lost")
            raise

    def report_progress(self, progress: JsonObject) -> JsonObject:
        with self.guard:
            data = dict(progress)
            batch = cast("JsonObject | None", data.pop("tool_calls", None))
            if batch is not None:
                for call in cast("list[JsonObject]", batch["calls"]):
                    identity = str(call["call_id"])
                    prior = self.__tool_calls.get(identity)
                    self.__tool_calls[identity] = (
                        call
                        if prior is None
                        else {
                            **prior,
                            **{key: value for key, value in call.items() if value is not None},
                        }
                    )
            self.__progress.update(data)
            return self._renew()

    def flush_tool_calls(self) -> None:
        with self.guard:
            if self.__tool_calls:
                self._renew()

    def heartbeat(self) -> JsonObject:
        with self.guard:
            if self.__renewals_closed:
                # The committed next instruction ended this assignment while this tick queued.
                return {}
            return self._renew()

    def set_stage(self, stage_record_id: str, step_id: str | None = None) -> None:
        with self.guard:
            self.__progress = {"stage_record_id": stage_record_id}
            self.__tool_calls.clear()
            if step_id is not None:
                self.__progress["step_id"] = step_id

    def clear_progress(self, *, assignment_finished: bool = False) -> None:
        with self.guard:
            self.__progress.clear()
            self.__tool_calls.clear()
            self.__renewals_closed |= assignment_finished

    def progress(self) -> JsonObject:
        with self.guard:
            return dict(self.__progress)

    def seal_output(self, manifest: JsonObject, patch: StagedBlobRef | None) -> JsonObject:
        with self.guard:
            return self._send(
                "seal_output",
                {
                    "stage_record_id": self.__progress["stage_record_id"],
                    "source": "executor" if self.__progress.get("step_id") else "range",
                    **({"step_id": self.__progress["step_id"]} if self.__progress.get("step_id") else {}),
                    "manifest": manifest,
                    "patch": patch,
                },
            )

    def record_effect(self, report: JsonObject) -> JsonObject:
        if "claim" in report:
            raise ValueError("a stage cannot replace its assignment binding")
        with self.guard:
            return self._send("record_external_effect", report)

    def acquire_integration_slot(self, repository_id: RepositoryId, target_branch: str) -> JsonObject:
        with self.guard:
            return self._send(
                "acquire_integration_slot",
                {"repository_id": str(repository_id), "target_branch": target_branch},
            )

    def release_integration_slot(self, slot: JsonObject) -> None:
        with self.guard:
            self._send(
                "release_integration_slot",
                {"slot_id": slot["slot_id"], "fencing_token": slot["fencing_token"]},
            )
