"""Publish accepted per-target deltas; partial completion is durable and never rolled back."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import RepositoryId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.ids import ExternalEffectId
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.host.stages.base import StageOutcome

if TYPE_CHECKING:
    from skm.modules.execution.host.stages.base import StageRequest
    from skm.modules.execution.ports import StageDeps


class ExternalGit(Protocol):
    """Optional Git gateway; inspection must return an explicit reaped cleanup status."""

    def inspect_effect(self, repo: Any, effect: Any, binding: Any, client: Any) -> JsonObject: ...
    def push_external(
        self, repo: Any, effect: str, request: Any, digest: str, client: Any, ownership: Any
    ) -> JsonObject: ...


class EffectProvider(Protocol):
    """Trusted provider adapter: execute journals before consuming admission; lookup never writes.

    Provider lookup returns an exact receipt or an explicit absence proof only after quiescence.
    Missing, ambiguous or incomplete evidence is outcome_unknown.
    Lookup completion confirms cleanup independently of the effect state; return reaped=False
    when helper cleanup is unconfirmed, or raise CleanupUnconfirmed.
    """

    def execute_effect(self, effect: JsonObject, *, client: Any, ownership: JsonObject) -> JsonObject: ...
    def lookup_effect(self, effect: JsonObject) -> JsonObject: ...


class IntegrateStage:
    stage_type: Literal["integrate"] = "integrate"
    side: Literal["host"] = "host"
    params_schema_urn = "urn:skm:execution:workflow:v1#/$defs/params"

    def __init__(
        self,
        *,
        ownership: Callable[[ExternalEffectId, StageRequest, StageDeps], JsonObject] | None = None,
        provider: EffectProvider | None = None,
    ) -> None:
        self.ownership, self.provider = ownership, provider

    def run(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        if request.instruction.mode is StageMode.RECONCILE:
            return self._reconcile(request, deps)
        integration = cast("JsonObject", request.begin.get("integrate", request.begin))
        if integration.get("external_effect") is not None:
            return self._external(request, deps, integration)
        return self._publish(request, deps)

    def _publish(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        environment = deps.environment
        if environment is None:
            raise ValueError("integration requires a prepared environment")
        integration = cast("JsonObject", request.begin.get("integrate", request.begin))
        # These are trusted Begin inputs, not runtime output or moving checkout HEADs.
        if not integration.get("accepted_output_id"):
            raise ValueError("integration requires an acceptance decision")
        targets = cast("list[JsonObject]", integration.get("integration_targets", []))
        if not targets:
            raise ValueError("integration requires pinned targets")
        ordered = sorted(
            targets, key=lambda t: (str(t["repository_id"]).encode(), str(t["target_branch"]).encode())
        )
        identities = [(str(t["repository_id"]), str(t["target_branch"])) for t in targets]
        if targets != ordered or len(set(identities)) != len(targets):
            raise ValueError("integration targets must be unique and in byte order")
        receipts: list[JsonValue] = []
        commits: list[JsonValue] = []
        effects: list[JsonValue] = []
        for target in targets:
            if deps.cancel.cancelled:
                return StageOutcome(
                    StageOutcomeKind.RUNTIME_ERROR,
                    {"error_code": "LEASE_LOST", "integration_receipts": receipts},
                )
            mount = str(target["mount"])
            repository_id = target["repository_id"]
            if mount not in environment.mounts or not any(
                str(b.repository_id) == repository_id and b.mount == mount for b in environment.baseline
            ):
                raise ValueError("integration target is not a bound mount")
            outputs = cast("list[JsonObject]", target.get("outputs", []))
            if not outputs or outputs[-1]["output_id"] != integration["accepted_output_id"]:
                raise ValueError("target must publish the accepted output")
            slot: JsonObject | None = None
            try:
                slot = self._acquire(target, deps, cast("JsonObject", integration.get("slot_limits", {})))
                if "slot_id" not in slot:
                    return StageOutcome(
                        StageOutcomeKind.RUNTIME_ERROR,
                        {
                            "error_code": "SLOT_BUSY",
                            "error_class": "timeout",
                            "integration_receipts": receipts,
                        },
                    )
                effect_id = ExternalEffectId(UUID(str(target["effect_id"])))
                inputs = {**target, "artifact_digests": integration.get("artifact_digests", [])}
                inputs["process_ownership"] = (
                    self.ownership(effect_id, request, deps)
                    if self.ownership is not None
                    else target.get("process_ownership")
                )
                inputs["source_repo"] = str(environment.mounts[mount])
                locator = target.get("repository_locator")
                if locator is not None and not isinstance(locator, str):
                    raise ValueError("repository locator must be a trusted string")
                repo = environment.mounts[mount] if locator is None else locator
                prepared = deps.vcs.prepare_integration(repo, effect_id, inputs, slot=slot)
                receipt = deps.vcs.publish_integration(
                    repo, effect_id, prepared, slot=slot, client=deps.worker
                )
                wire = {**asdict(receipt), "at": receipt.at.isoformat()}
                receipts.append(json.loads(json.dumps(wire, default=str)))
                effects.append(
                    {
                        "effect_id": str(effect_id),
                        "repository_id": str(repository_id),
                        "request_digest": receipt.request_digest,
                        "receipt_ref": receipt.receipt_ref,
                    }
                )
                commits.extend(receipt.commit_shas)
            except SkmError as error:
                kind = (
                    StageOutcomeKind.CONFLICT
                    if error.code is ErrorCode.INTEGRATION_CONFLICT
                    else StageOutcomeKind.OUTCOME_UNKNOWN
                    if error.code is ErrorCode.OUTCOME_UNKNOWN
                    else StageOutcomeKind.RUNTIME_ERROR
                )
                return StageOutcome(
                    kind,
                    {
                        "error_code": error.code.value,
                        "integration_receipts": receipts,
                        "effects": [
                            *effects,
                            {"effect_id": str(target["effect_id"]), "state": error.code.value},
                        ],
                        "commit_shas": commits,
                    },
                    reaped=kind is not StageOutcomeKind.OUTCOME_UNKNOWN,
                )
            except OSError:
                return StageOutcome(
                    StageOutcomeKind.OUTCOME_UNKNOWN,
                    {
                        "error_code": "OUTCOME_UNKNOWN",
                        "integration_receipts": receipts,
                        "effects": [
                            *effects,
                            {"effect_id": str(target["effect_id"]), "state": "outcome_unknown"},
                        ],
                        "commit_shas": commits,
                    },
                    reaped=False,
                )
            finally:
                if slot is not None and "slot_id" in slot:
                    deps.worker.release_integration_slot(slot)
        return self._proposal(request, receipts, commits) or StageOutcome(
            StageOutcomeKind.SUCCESS,
            {
                "integration_receipts": receipts,
                "effects": effects,
                "commit_shas": commits,
                "output_ids": [str(integration["accepted_output_id"])],
            },
        )

    @staticmethod
    def _proposal(request: StageRequest, receipts: Any, commits: Any) -> StageOutcome | None:
        params = request.instruction.params or {}
        proposal: Any = params.get("effect_request")
        if proposal is None and params.get("push") == "intent":
            args = params.get("push_request")
            if not isinstance(args, dict):
                raise ValueError("push:intent requires exact push_request arguments")
            proposal = {"kind": "git_push", "args": args}
        if proposal is not None:
            return StageOutcome(
                StageOutcomeKind.APPROVAL_REQUIRED,
                {"effect_request": proposal, "integration_receipts": receipts, "commit_shas": commits},
            )
        return None

    @staticmethod
    def _repo(deps: StageDeps, effect: Any) -> Any:
        repository = str(effect["request"]["repository_id"])
        bound = getattr(deps.vcs, "repositories", {})
        if repository in bound:
            return bound[repository]
        if deps.environment is not None:
            mount = next(b.mount for b in deps.environment.baseline if str(b.repository_id) == repository)
            return deps.environment.mounts[mount]
        raise ValueError("inspector requires the pinned host repository map")

    def _reconcile(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        effect = cast("Any", request.begin.get("integrate", {}))
        params = request.instruction.params or {}
        if (
            not effect.get("effect_id")
            or params.get("effect_id") != effect["effect_id"]
            or params.get("request_digest") != effect.get("request_digest")
        ):
            return StageOutcome(StageOutcomeKind.OUTCOME_UNKNOWN, {"error_code": "OUTCOME_UNKNOWN"})
        deps.cancel.raise_if_cancelled()
        unknown: Any = {"state": "outcome_unknown", "reason_code": "LOOKUP_UNAVAILABLE"}
        git_lookup_started = False
        found: Any
        try:
            if effect["kind"] in {"git_commit", "git_push"}:
                found = unknown
                if (
                    self.ownership is not None
                    and effect.get("inspection_claim")
                    and hasattr(deps.vcs, "inspect_effect")
                ):
                    own = self.ownership(ExternalEffectId(UUID(effect["effect_id"])), request, deps)
                    repo = self._repo(deps, effect)
                    git_lookup_started = True
                    found = cast("ExternalGit", deps.vcs).inspect_effect(
                        repo,
                        effect,
                        {"claim": effect["inspection_claim"], "ownership": own},
                        deps.worker,
                    )
            elif self.provider is not None:
                found = self.provider.lookup_effect(effect)
            else:
                found = unknown
        except (OSError, SkmError, ValueError):
            found = unknown
        result: JsonObject = {
            "effect_id": effect["effect_id"],
            "request_digest": effect["request_digest"],
            "state": found.get("state", "outcome_unknown"),
        }
        for key in ("receipt", "reason_code"):
            if found.get(key) is not None:
                result[key] = found[key]
        kind = (
            StageOutcomeKind.OUTCOME_UNKNOWN
            if result["state"] == "outcome_unknown"
            else StageOutcomeKind.SUCCESS
        )
        return StageOutcome(
            kind, {"reconciled_effect": result}, reaped=found.get("reaped", not git_lookup_started) is True
        )

    def _external(self, request: StageRequest, deps: StageDeps, integration: Any) -> StageOutcome:
        effect = integration["external_effect"]
        identity = ExternalEffectId(UUID(effect["effect_id"]))
        if effect.get("state") == "succeeded":
            return self._next_effect(integration, str(identity), effect["kind"])
        if effect.get("state", "intended") != "intended":
            return StageOutcome(StageOutcomeKind.OUTCOME_UNKNOWN, {"error_code": "OUTCOME_UNKNOWN"})
        if self.ownership is None:
            return StageOutcome(StageOutcomeKind.RUNTIME_ERROR, {"error_code": "CAPABILITY_UNAVAILABLE"})
        ownership = self.ownership(identity, request, deps)
        deps.cancel.raise_if_cancelled()
        try:
            if effect["kind"] == "git_push" and hasattr(deps.vcs, "push_external"):
                cast("ExternalGit", deps.vcs).push_external(
                    self._repo(deps, effect),
                    str(identity),
                    effect["request"],
                    effect["request_digest"],
                    deps.worker,
                    ownership,
                )
            elif self.provider is not None:
                receipt = self.provider.execute_effect(effect, client=deps.worker, ownership=ownership)
                deps.worker.record_effect(
                    {
                        "effect_id": str(identity),
                        "kind": effect["kind"],
                        "request_digest": effect["request_digest"],
                        "phase": "result",
                        "result": {
                            "succeeded": True,
                            "ref": receipt["ref"],
                            "response_digest": receipt["response_digest"],
                        },
                    }
                )
            else:
                return StageOutcome(StageOutcomeKind.RUNTIME_ERROR, {"error_code": "CAPABILITY_UNAVAILABLE"})
        except (OSError, SkmError):
            return StageOutcome(
                StageOutcomeKind.OUTCOME_UNKNOWN,
                {
                    "error_code": "OUTCOME_UNKNOWN",
                    "effects": [{"effect_id": str(identity), "state": "outcome_unknown"}],
                },
                reaped=False,
            )
        return self._next_effect(integration, str(identity), effect["kind"])

    @staticmethod
    def _next_effect(integration: Any, identity: str, kind: str) -> StageOutcome:
        pending = [
            e
            for e in integration.get("external_effects", ())
            if e["effect_id"] != identity and e["state"] != "succeeded"
        ]
        if pending:
            first = pending[0]
            if first["state"] != "intended":
                return StageOutcome(StageOutcomeKind.OUTCOME_UNKNOWN, {"error_code": "OUTCOME_UNKNOWN"})
            return StageOutcome(
                StageOutcomeKind.APPROVAL_REQUIRED,
                {"effect_request": {"kind": first["kind"], "args": first["request"]}},
            )
        return StageOutcome(StageOutcomeKind.SUCCESS, {"pushed": kind == "git_push"})

    @staticmethod
    def _acquire(target: JsonObject, deps: StageDeps, limits: JsonObject) -> JsonObject:
        deadline = deps.monotonic.monotonic() + float(
            cast("int | float", limits.get("wait_max_seconds", 1800))
        )
        poll = max(0.01, float(cast("int | float", limits.get("poll_seconds", 5))))
        while True:
            deps.cancel.raise_if_cancelled()
            try:
                slot = deps.worker.acquire_integration_slot(
                    RepositoryId(UUID(str(target["repository_id"]))), str(target["target_branch"])
                )
                if "slot_id" in slot:
                    return slot
            except SkmError as error:
                if error.code is not ErrorCode.SLOT_BUSY:
                    raise
            remaining = deadline - deps.monotonic.monotonic()
            if remaining <= 0:
                return {"code": "SLOT_BUSY"}
            deps.cancel.wait(min(poll, remaining))

    def __call__(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        return self.run(request, deps)
