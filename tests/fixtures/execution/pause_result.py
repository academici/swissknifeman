"""An operator pauses through the real command immediately before a selected result commits."""

from uuid import UUID

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import Surface
from skm.modules.execution.generated.commands import PauseRun


def with_result_pause(client, app, data, state):
    if not data.get("pause_before_result"):
        return client
    owner = app.client(
        actor=Actor(PrincipalId(UUID(data["owner_id"])), PrincipalKind.HUMAN, "recovery owner"),
        surface=Surface.CLI,
    )
    return PauseBeforeResult(
        client, owner, data["pause_run_id"], data["pause_before_result"], state / "paused-result"
    )


class PauseBeforeResult:
    def __init__(self, inner, owner, run_id, kind, marker):
        self.inner, self.owner, self.run_id, self.kind, self.marker = inner, owner, run_id, kind, marker

    def dispatch(self, command, *, idempotency_key=None):
        if (
            type(command).__name__ == "RecordStageResult"
            and command.get("outcome_kind") == self.kind
            and not self.marker.exists()
        ):
            self.owner.dispatch(PauseRun(UUID(self.run_id), "pause at terminal result boundary"))
            self.marker.write_text("paused")
        return self.inner.dispatch(command, idempotency_key=idempotency_key)

    def __getattr__(self, name):
        return getattr(self.inner, name)
