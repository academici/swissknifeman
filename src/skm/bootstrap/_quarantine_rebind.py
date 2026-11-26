"""Verified local checkout bindings and the restored Git inspection lane."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from stat import S_ISREG
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast, override
from uuid import UUID

from skm.adapters.git.integration import GitIntegrator
from skm.adapters.git.repo_inspect import GitRepositoryInspector
from skm.adapters.git.runner import GitCommandFailed, GitRunner
from skm.adapters.postgres.uow import PostgresUnitOfWork
from skm.application_bus.bus import Bus
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID
from skm.kernel.ids import HostId, RepositoryId, RunId, ToolIntentId
from skm.kernel.json_types import JsonObject
from skm.modules.access.public import SYSTEM_ACTOR
from skm.modules.execution.application.commands import stop_autopilot
from skm.modules.execution.domain.external_effect import (
    EffectState,
    GitCommitRequest,
    effect_digest,
    request_document,
)
from skm.modules.execution.domain.ids import ExternalEffectId, StageRecordId
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.stage_record import interrupt_stage
from skm.modules.execution.module import MODULE as EXECUTION
from skm.modules.execution.ports import EffectRepository, RunRepository, StageRepository
from skm.modules.policy.public import record_outcome
from skm.modules.workspace.generated.commands import BindCheckout
from skm.modules.workspace.generated.results import BindCheckoutResult
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.fs.file_lock import FileLock, LockTimeout
from skm.platform.storage.backup import invalid
from skm.platform.system_clock import SystemClock, SystemMonotonic

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.bootstrap.composition import App
    from skm.kernel.actor import Actor
    from skm.kernel.ports_uow import RequestMeta, UnitOfWork
    from skm.modules.execution.host.stages.registry import StageRegistry
    from skm.platform.config.bootstrap import BootstrapConfig

__all__ = [
    "create_rebinds",
    "current_pins",
    "dispatch_allowed",
    "embedded_worker_stages",
    "normalize_execution",
    "rebind_checkout",
]


_REASON = "restore quarantine activation requires explicit resume"


def create_rebinds(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE public.skm_restore_rebinds (
            effect_id uuid PRIMARY KEY, binding_id uuid NOT NULL, binding_version bigint NOT NULL,
            verified_by uuid NOT NULL, verified_at timestamptz NOT NULL DEFAULT now(),
            outputs_verified boolean NOT NULL
        );
        CREATE VIEW public.skm_current_restore_rebinds AS
        SELECT e.id AS effect_id, e.run_id, b.repository_id, b.host_id, b.local_locator,
               e.request->>'target_branch' AS branch, r.outputs_verified
        FROM public.skm_restore_rebinds r
        JOIN skm_execution.external_effects e ON e.id=r.effect_id
        JOIN skm_workspace.checkout_bindings b ON b.id=r.binding_id
             AND b.workspace_id=e.workspace_id AND b.repository_id::text=e.request->>'repository_id'
        JOIN skm_workspace.hosts h ON h.id=b.host_id
        CROSS JOIN public.skm_restore_control c
        WHERE b.row_version=r.binding_version AND b.state='active' AND h.state='active'
          AND h.registered_at>=c.created_at AND b.last_verified_at>=c.created_at
    """)


@dataclass(frozen=True, slots=True)
class VerifiedPin:
    effect_id: UUID
    run_id: RunId
    repository_id: RepositoryId
    host_id: HostId
    locator: str
    branch: str


def current_pins(conn: Any) -> tuple[VerifiedPin, ...]:
    return tuple(
        VerifiedPin(effect, RunId(run), RepositoryId(repo), HostId(host), locator, branch)
        for effect, run, repo, host, locator, branch in conn.execute("""
            SELECT effect_id,run_id,repository_id,host_id,local_locator,branch
            FROM public.skm_current_restore_rebinds ORDER BY effect_id
        """)
    )


def dispatch_allowed(conn: Any, operation: str, identity: str) -> bool:
    if operation == "execution.reconcile_external_effect":
        return (
            conn.execute(
                "SELECT 1 FROM public.skm_current_restore_rebinds WHERE effect_id::text=%s", (identity,)
            ).fetchone()
            is not None
        )
    # Only nonterminal runs with recorded dependencies take part in project-wide admission.
    row = conn.execute(
        """
        SELECT NOT EXISTS (
          SELECT 1 FROM skm_execution.runs r CROSS JOIN public.skm_restore_control c
          WHERE (CASE WHEN %s THEN r.id ELSE r.project_id END)::text=%s
            AND r.status IN ('created','ready','running','waiting','paused')
            AND c.blocked_runs ? r.id::text
            AND (
              NOT EXISTS (SELECT 1 FROM public.skm_current_restore_rebinds b WHERE b.run_id=r.id)
              OR c.fixed_blocks ? r.id::text
              OR EXISTS (
                SELECT 1 FROM skm_execution.attempts a JOIN skm_execution.attempt_steps s ON s.attempt_id=a.id
                WHERE a.run_id=r.id
                AND (s.session_ref IS NOT NULL OR s.process_identity IS NOT NULL)
              )
              OR EXISTS (
                SELECT 1 FROM skm_execution.external_effects e WHERE e.run_id=r.id
                AND e.state IN ('intended','executing','outcome_unknown')
              )
              OR EXISTS (
                SELECT 1 FROM skm_execution.run_integration_hosts h WHERE h.run_id=r.id
                AND NOT EXISTS (
                  SELECT 1 FROM public.skm_current_restore_rebinds b
                  WHERE (b.run_id,b.repository_id)=(h.run_id,h.repository_id)
                )
              )
              OR EXISTS (
                SELECT 1 FROM skm_execution.attempt_outputs o
                CROSS JOIN LATERAL jsonb_array_elements(o.manifest->'mounts') AS m
                WHERE o.run_id=r.id AND NOT EXISTS (
                  SELECT 1 FROM public.skm_current_restore_rebinds b
                  WHERE b.run_id=r.id AND b.repository_id::text=m->>'repository_id' AND b.outputs_verified
                )
              )
            )
        )
    """,
        (operation == "execution.resume_run", identity),
    ).fetchone()
    return bool(row and row[0])


class _OfflineGit(GitRunner):
    @override
    def build_environment(
        self, base_env: Mapping[str, str] | None = None, *, allow_ssh_agent: bool = False
    ) -> dict[str, str]:
        return {
            **super().build_environment(base_env, allow_ssh_agent=allow_ssh_agent),
            "GIT_ALLOW_PROTOCOL": "",
            "GIT_NO_LAZY_FETCH": "1",
        }


def _observed_outputs(conn: Any, run: RunId, repo: RepositoryId, root: str, git: _OfflineGit) -> bool:
    for base, head, tree in conn.execute(
        """
        SELECT DISTINCT m->>'base_commit',m->>'head_commit',m->>'tree_sha'
        FROM skm_execution.attempt_outputs o
        CROSS JOIN LATERAL jsonb_array_elements(o.manifest->'mounts') AS m
        WHERE o.run_id=%s AND m->>'repository_id'=%s
    """,
        (run, str(repo)),
    ):
        result = git.run(root, ("rev-parse", "--verify", "--end-of-options", f"{head}^{{tree}}"), check=False)
        if (
            result.exit_code
            or result.stdout.strip() != tree
            or git.run(root, ("cat-file", "-e", f"{base}^{{commit}}"), check=False).exit_code
        ):
            return False
    return True


def rebind_checkout(
    app: App, actor: Actor, meta: RequestMeta, host: HostId, effect: UUID, checkout: Path
) -> JsonObject:
    git = _OfflineGit()
    inspector = GitRepositoryInspector(git)
    # Lock across the local observation and pin transaction so activation sees one version.
    with app.uow_factory(meta, readonly=False) as uow:
        conn = cast("PostgresUnitOfWork", uow).connection
        conn.execute("SELECT id FROM public.skm_restore_control FOR UPDATE")
        row = conn.execute(
            """
            SELECT e.run_id,p.repository_id,e.request->>'target_branch',
                   d.canonical_remote,e.workspace_id
            FROM skm_execution.external_effects e
            JOIN skm_execution.run_integration_hosts p ON p.run_id=e.run_id
                 AND p.repository_id::text=e.request->>'repository_id'
            JOIN skm_workspace.repositories d ON d.id=p.repository_id
            JOIN skm_execution.integration_slots s ON s.repository_id=p.repository_id
                 AND s.target_branch=e.request->>'target_branch' AND s.writer_host_id=p.host_id
            JOIN skm_workspace.hosts h ON h.id=%s
            CROSS JOIN public.skm_restore_control c
            WHERE e.id=%s AND e.kind='git_commit'
              AND e.state IN ('executing','outcome_unknown','failed','succeeded')
              AND h.state='active' AND h.registered_at>=c.created_at
        """,
            (host, effect),
        ).fetchone()
        if row is None:
            raise invalid("restore_rebind_unverified")
        run, repo, branch, remote, workspace = row
        competing = conn.execute(
            """
            SELECT 1 FROM public.skm_current_restore_rebinds
            WHERE effect_id<>%s AND repository_id=%s AND host_id<>%s AND (run_id=%s OR branch=%s)
        """,
            (effect, repo, host, run, branch),
        ).fetchone()
        if competing is not None:
            raise invalid("restore_rebind_pin_conflict")
        try:
            observed = inspector.observe(checkout.absolute())
            root = observed.toplevel
            marker = observed.marker
            identity_matches = (
                remote in {entry.value for entry in observed.remotes}
                if remote is not None
                else marker is not None
                and (marker.instance_id, marker.workspace_id, marker.repository_id)
                == (app.instance_id, workspace, repo)
            )
            if (
                root is None
                or observed.head is None
                or not identity_matches
                or (marker is not None and marker.repository_id != repo)
            ):
                raise invalid("restore_rebind_repository_mismatch")
            if not inspector.branch_exists(root, branch):
                raise invalid("restore_rebind_branch_missing")
            outputs = _observed_outputs(conn, RunId(run), RepositoryId(repo), root, git)
        except (OSError, ValueError, GitCommandFailed):
            raise invalid("restore_rebind_unverified") from None

        binding = BindCheckout(
            repository_id=repo,
            host_id=host,
            local_locator=root,
            observed_toplevel=root,
            observed_remotes=tuple(entry.value for entry in observed.remotes),
            observed_head=observed.head,
            observed_dirty=observed.dirty,
            observed_at=observed.observed_at,
        )
        existing = conn.execute(
            """
            SELECT id,row_version FROM skm_workspace.checkout_bindings
            WHERE host_id=%s AND repository_id=%s AND state='active' AND local_locator=%s
        """,
            (host, repo, root),
        ).fetchone()
        if existing is None:
            result = cast("BindCheckoutResult", Bus.dispatch(app.bus, binding, actor=actor, meta=meta))
            if result.state != "active":
                raise invalid("restore_rebind_unverified")
            existing = result.binding_id, result.row_version
        binding_id, version = existing
        conn.execute(
            """
            INSERT INTO public.skm_restore_rebinds
                (effect_id,binding_id,binding_version,verified_by,outputs_verified)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (effect_id) DO UPDATE SET binding_id=excluded.binding_id,
                binding_version=excluded.binding_version,verified_by=excluded.verified_by,
                verified_at=now(),outputs_verified=excluded.outputs_verified
        """,
            (effect, binding_id, version, actor.principal_id, outputs),
        )
        uow.commit()
    return {"effect_id": str(effect), "binding_id": str(binding_id), "state": "verified"}


class _ReadOnlyIntegrator(GitIntegrator):
    """Reuse the fenced Git reader, opening the existing writer lock read-only."""

    @override
    def reconcile_integration(
        self, repo: Path | str, effect_id: ExternalEffectId, request: GitCommitRequest
    ) -> Any:
        folder, _, _ = self._target(Path(repo), request.target_branch, create=False)
        lock = folder / "writer.lock"
        if not S_ISREG(lock.lstat().st_mode):
            raise ValueError("invalid writer lock")
        try:
            with FileLock(lock, create=False, readonly=True).hold(timeout_seconds=1):
                path = folder / (str(effect_id) + ".json")
                journal = self._load(path)
                if (
                    journal["effect_id"] != str(effect_id)
                    or journal["request"] != request_document(request)
                    or journal["request_digest"] != effect_digest(effect_id, request)
                ):
                    raise ValueError("Git journal does not match the restored effect")
                return self._reconcile(Path(repo), path, journal, persist=False)
        except LockTimeout:
            raise invalid("restore_inspection_busy") from None


class _RestoreInspector:
    def __init__(self, state: Path, pins: Any) -> None:
        self._pins = pins
        self._reader = _ReadOnlyIntegrator(
            _OfflineGit(),
            worktrees_root=state / "integration-inspection",
            now=SystemClock().now,
            monotonic=SystemMonotonic().monotonic,
        )

    @property
    def repositories(self) -> dict[str, Path]:
        return {str(pin.repository_id): Path(pin.locator) for pin in self._pins()}

    def inspect_effect(self, repo: Path, effect: Any, binding: Any, client: Any) -> JsonObject:
        if effect["kind"] == "git_commit" and any(
            str(pin.effect_id) == effect["effect_id"] and Path(pin.locator) == repo for pin in self._pins()
        ):
            return cast("JsonObject", self._reader.inspect_effect(repo, effect, binding, client))
        return {"state": "outcome_unknown", "reason_code": "RESTORE_BINDING_REQUIRED", "reaped": True}


def embedded_worker_stages(
    app: App, bootstrap: BootstrapConfig, host_id: HostId, *, recovery: bool
) -> tuple[StageRegistry, dict[type[object], object]]:
    from dataclasses import asdict
    from secrets import token_hex

    from skm.adapters.postgres.connection import PgSettings, connect_single
    from skm.bootstrap.composition_resources import database_dsn
    from skm.kernel.ids import AttemptId
    from skm.modules.execution.host.stages.integrate import IntegrateStage
    from skm.modules.execution.host.stages.registry import HostStage, StageRegistry
    from skm.modules.execution.ports import CheckRunnerRegistry, IsolationRegistry, Vcs
    from skm.modules.runtimes.public import ProcessOwner, RuntimeRegistry
    from skm.plugin_api.manifest import ComponentKind

    if not recovery:
        return StageRegistry(
            cast("HostStage", stage)
            for plugin in app.plugins
            for (kind, _), stage in plugin.instances.items()
            if kind is ComponentKind.STAGE_HANDLER and getattr(stage, "side", None) == "host"
        ), {}

    def pins() -> tuple[VerifiedPin, ...]:
        with connect_single(PgSettings(database_dsn(bootstrap, {}), "skm-restore-inspection")) as conn:
            return tuple(pin for pin in current_pins(conn) if pin.host_id == host_id)

    def ownership(effect: ExternalEffectId, request: Any, _deps: Any) -> JsonObject:
        claim = request.begin["integrate"]["inspection_claim"]
        owner = ProcessOwner(
            host_id,
            UUID(claim["worker_id"]),
            AttemptId(UUID(claim["attempt_id"])),
            UUID(claim["stage_record_id"]),
            "git_effect",
            effect,
            token_hex(24),
            str(bootstrap.state_dir / "identities"),
        )
        return {
            "kind": "pgroup_best_effort",
            "ref": f"pgroup:{effect}",
            "owner": {key: str(value) for key, value in asdict(owner).items()},
        }

    class Unavailable:
        def get(self, _key: str) -> Any:
            raise invalid("restore_worker_inspection_only")

    empty = Unavailable()
    return StageRegistry((cast("HostStage", IntegrateStage(ownership=ownership)),)), {
        RuntimeRegistry: empty,
        CheckRunnerRegistry: empty,
        IsolationRegistry: empty,
        Vcs: _RestoreInspector(bootstrap.state_dir, pins),
    }


def _record(uow: UnitOfWork, run: Any, name: str, fields: JsonObject) -> None:
    event = next(e for e in EXECUTION.events if e.event_type == f"urn:skm:execution:event:{name}:v1")
    data: JsonObject = {
        "run_id": str(run.id),
        "workspace_id": str(run.workspace_id),
        "project_id": str(run.project_id),
        "cause": {"trigger_kind": "lease_recovery", "advance_rule": None, "reason_codes": [], "refs": []},
        **fields,
    }
    uow.record(cast("Any", event)(run.id, run.workspace_id, data))


def normalize_execution(uow: UnitOfWork, app: App) -> None:
    conn = cast("PostgresUnitOfWork", uow).connection
    clock = SystemClock()
    ctx, now = SimpleNamespace(actor=SYSTEM_ACTOR, clock=clock), clock.now()
    repo = uow.repo(RunRepository)
    for (run_id,) in conn.execute(
        "SELECT id FROM skm_execution.runs "
        "WHERE status IN ('created','ready','running','waiting','paused') ORDER BY id"
    ):
        run = repo.get(RunId(run_id), for_update=True)
        paused = replace(
            run,
            status=RunStatus.PAUSED,
            pause_source="owner",
            pause_reason=_REASON,
            stop_code=None,
            started_at=run.started_at or now,
            queued=False,
            row_version=run.row_version + 1,
        )
        repo.save(paused, expected_version=run.row_version)
        _record(
            uow,
            run,
            "run-paused",
            {
                "reason": _REASON,
                "by": str(SYSTEM_PRINCIPAL_ID),
                "pause_source": "owner",
                "stop_code": None,
            },
        )
    for (project,) in conn.execute(
        "SELECT project_id FROM skm_execution.autopilot_states WHERE state<>'stopped' ORDER BY 1"
    ):
        cmd = stop_autopilot.StopAutopilot(
            {"project_id": str(project), "reason": _REASON, "emergency": False}
        )
        ctx.config = app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
        stop_autopilot.handle(cmd, ctx, uow)
    _close_execution(uow, ctx, now)


def _close_execution(uow: UnitOfWork, ctx: Any, now: datetime) -> None:
    conn = cast("PostgresUnitOfWork", uow).connection
    for (identity,) in conn.execute(
        "SELECT id FROM skm_execution.external_effects WHERE state='executing' ORDER BY 1"
    ):
        effects = uow.repo(EffectRepository)
        effect = effects.get(ExternalEffectId(identity), for_update=True)
        effects.save(replace(effect, state=EffectState.OUTCOME_UNKNOWN, updated_at=now))
        if effect.intent_id is not None:
            record_outcome(
                uow,
                ctx,
                intent_id=ToolIntentId(effect.intent_id),
                outcome="outcome_unknown",
                receipt=effect.receipt or {"reason_code": "RESTORE_BINDING_REQUIRED"},
            )
        run = uow.repo(RunRepository).get(effect.run_id)
        _record(
            uow,
            run,
            "external-effect-outcome-unknown",
            {
                "effect_id": str(effect.id),
                "attempt_id": str(effect.attempt_id),
                "kind": effect.kind.value,
            },
        )
    for (identity,) in conn.execute(
        "SELECT id FROM skm_execution.attempt_stages "
        "WHERE state IN ('started','context_draft','running') ORDER BY 1"
    ):
        stages = uow.repo(StageRepository)
        stages.save(interrupt_stage(stages.get(StageRecordId(identity), for_update=True), now=now))
    conn.execute("""
        UPDATE skm_execution.assignments SET state='cancelled', row_version=row_version+1
        WHERE state IN ('available','leased');
        DELETE FROM skm_execution.assignment_leases;
        UPDATE skm_execution.integration_slots SET holder_attempt_id=NULL,expires_at=NULL,
            row_version=row_version+1 WHERE holder_attempt_id IS NOT NULL;
        UPDATE skm_workspace.workers SET state='retired',row_version=row_version+1 WHERE state<>'retired';
        UPDATE skm_workspace.hosts SET state='retired',row_version=row_version+1
        WHERE registered_at < (SELECT created_at FROM public.skm_restore_control) AND state='active';
    """)
