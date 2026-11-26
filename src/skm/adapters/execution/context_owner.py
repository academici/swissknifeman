"""Context ownership fencing through execution's facade in the caller's transaction."""

from datetime import datetime
from typing import Any, cast, override
from uuid import UUID

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.ids import HostId, ProjectId, RunId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.context.ports import ContextOwnerClaim, ContextOwnerGuard
from skm.modules.execution import public as execution
from skm.platform.config import ConfigLoader
from skm.platform.config.effective import FrozenConfig
from skm.platform.config.keys import Chain
from skm.platform.config.store import ConfigStore, ScopeTree

__all__ = ["ExecutionContextOwnerGuard"]


class ExecutionContextOwnerGuard(ContextOwnerGuard):
    def __init__(self, config: ConfigLoader | None = None) -> None:
        self._config = config

    @override
    def require_current(
        self, uow: UnitOfWork, actor: Actor, owner_ref: str, claim: ContextOwnerClaim, now: datetime
    ) -> None:
        execution.require_current_context_owner(
            uow,
            actor,
            owner_ref,
            assignment_id=claim.assignment_id,
            attempt_id=claim.attempt_id,
            worker_id=claim.worker_id,
            fencing_token=claim.fencing_token,
            now=now,
        )

    @override
    def research_policy(
        self,
        uow: UnitOfWork,
        actor: Actor,
        project_id: ProjectId,
        *,
        step_ref: str | None,
        for_update: bool,
        now: datetime,
        permission: str = "context.read",
    ) -> JsonObject:
        if self._config is None:
            raise InternalError(ErrorCode.CONFIG_INVALID, "research requires the configuration loader")
        store, scopes = uow.repo(ConfigStore), uow.repo(ScopeTree)
        if actor.kind is not PrincipalKind.WORKER:
            if step_ref is not None:
                execution.require_research_step_scope(uow, project_id, step_ref)
            # Human requests have no authenticated worker host; use the server's instance registry.
            host_config = self._config.effective(store, scopes, None, Chain.HOST)
            return {"context.research.sources": host_config.get("context.research.sources")}
        bound = execution.require_research_assignment(
            uow,
            actor,
            project_id,
            step_ref=step_ref,
            for_update=for_update,
            now=now,
            permission=permission,
        )
        frozen = FrozenConfig.from_document(cast("dict[str, Any]", bound["config_snapshot"]))
        config = self._config.effective(
            store,
            scopes,
            ScopeRef(ScopeKind.RUN, ScopeId(RunId(UUID(str(bound["run_id"]))))),
            frozen=frozen,
        )
        keys = (
            "context.max_classification_for_runtime",
            *(
                key
                for key in config.resolved_keys()
                if key.startswith("context.research.") and config.registry.spec(key).chain.value == "work"
            ),
        )
        host_config = self._config.effective_host(
            store, scopes, ScopeRef(ScopeKind.HOST, ScopeId(HostId(UUID(str(bound["host_id"])))))
        )
        return {
            **{key: config.get(key) for key in keys},
            "context.research.sources": host_config.get("context.research.sources"),
        }
