"""Immutable effects and exact, identity-bound observations; no external IO."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from skm.kernel.ids import AttemptId, RepositoryId, RunId, TaskId, WorkspaceId
    from skm.modules.execution.domain.ids import ExternalEffectId, OutputId


class EffectKind(StrEnum):
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    PR_CREATE = "pr_create"
    MESSAGE = "message"
    PUBLISH = "publish"
    FS_WRITE_EXTERNAL = "fs_write_external"


class EffectState(StrEnum):
    INTENDED = "intended"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True, slots=True)
class ExternalEffect:
    id: ExternalEffectId
    workspace_id: WorkspaceId
    run_id: RunId
    attempt_id: AttemptId
    task_id: TaskId
    kind: EffectKind
    intent_id: UUID | None
    request_digest: str
    request: JsonObject
    state: EffectState
    receipt: JsonObject | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class GitCommitRequest:
    repository_id: RepositoryId
    target_branch: str
    before_sha: str
    after_sha: str
    tree_sha: str
    baseline_sha: str
    output_ids: tuple[OutputId, ...]
    output_digests: tuple[str, ...]
    commit_shas: tuple[str, ...]
    assignment_fencing_token: int
    slot_fencing_token: int
    writer_epoch_sha: str


@dataclass(frozen=True, slots=True)
class GitCommitReceipt:
    ref: str
    before_sha: str
    after_sha: str
    tree_sha: str
    commit_shas: tuple[str, ...]
    target_branch: str
    output_ids: tuple[OutputId, ...]
    request_digest: str
    writer_epoch_sha: str
    receipt_ref: str
    receipt_commit_sha: str
    at: datetime


def observation_digest(
    effect_id: str, request_digest: str, state: str, ref: str, reason_code: str | None = None
) -> str:
    body = {
        "effect_id": effect_id,
        "request_digest": request_digest,
        "state": state,
        "ref": ref,
        "reason_code": reason_code,
    }
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
    )


def validate_observation(effect: ExternalEffect, state: EffectState, receipt: Any, reason: Any) -> None:
    """Only a positive receipt or an explicit absence observation can resolve uncertainty.

    Facts come from the trusted pinned inspector, never from a missing lookup or a transport error.
    Its response digest binds the observed ref, outcome and proof classification to this exact request.
    """
    if state is EffectState.OUTCOME_UNKNOWN:
        return
    if state not in {EffectState.SUCCEEDED, EffectState.FAILED} or not isinstance(receipt, dict):
        raise error_for(ErrorCode.INVALID_REFERENCE, "effect resolution requires an observation receipt")
    receipt = cast("dict[str, Any]", receipt)
    request = effect.request
    if effect.kind is EffectKind.GIT_COMMIT and state is EffectState.SUCCEEDED:
        fields = (
            "before_sha",
            "after_sha",
            "tree_sha",
            "target_branch",
            "output_ids",
            "commit_shas",
            "writer_epoch_sha",
        )
        if (
            any(receipt.get(k) != request[k] for k in fields)
            or receipt.get("request_digest") != effect.request_digest
            or receipt.get("ref") != request["after_sha"]
            or receipt.get("receipt_ref") != "refs/skm/effects/" + str(effect.id)
            or not receipt.get("receipt_commit_sha")
            or not receipt.get("at")
        ):
            raise error_for(ErrorCode.INVALID_REFERENCE, "Git receipt differs from its immutable request")
        return
    ref = receipt.get("ref")
    if not isinstance(ref, str) or not ref or not receipt.get("at"):
        raise error_for(ErrorCode.INVALID_REFERENCE, "observation has no ref or timestamp")
    if state is EffectState.FAILED:
        expected = request.get("before_sha", "absent:" + str(effect.id))
        if reason != "EFFECT_ABSENT" or ref != expected:
            raise error_for(ErrorCode.INVALID_REFERENCE, "failed requires proven absence after quiescence")
    elif effect.kind is EffectKind.GIT_PUSH and (
        ref != request["after_sha"] and reason != "REMOTE_DESCENDANT"
    ):
        raise error_for(ErrorCode.INVALID_REFERENCE, "remote observation does not prove the approved SHA")
    if receipt.get("response_digest") != observation_digest(
        str(effect.id), effect.request_digest, state.value, ref, reason
    ):
        raise error_for(ErrorCode.INVALID_REFERENCE, "observation is not bound to this effect request")


def exact_trailers(message: str, expected: dict[str, str]) -> bool:
    """Identity must be unique keys in the final trailer paragraph, not text in the body."""
    paragraphs = message.strip().split("\n\n")
    if len(paragraphs) < 2:
        return False
    rows = [line.partition(": ") for line in paragraphs[-1].splitlines()]
    return all(
        sum(key == k and sep == ": " for key, sep, _ in rows) == 1
        and any(key == k and value == v for key, _, value in rows)
        for k, v in expected.items()
    )


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=lambda v: v.isoformat() if hasattr(v, "isoformat") else str(v),
    ).encode()


def request_document(request: GitCommitRequest) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(canonical(asdict(request))))


def effect_digest(effect_id: ExternalEffectId, request: GitCommitRequest) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            canonical(
                {"effect_id": str(effect_id), "kind": "git_commit", "request": request_document(request)}
            )
        ).hexdigest()
    )


def commit_request(raw: Any) -> GitCommitRequest:
    from uuid import UUID

    from skm.kernel.ids import RepositoryId
    from skm.modules.execution.domain.ids import OutputId

    return GitCommitRequest(
        RepositoryId(UUID(raw["repository_id"])),
        raw["target_branch"],
        raw["before_sha"],
        raw["after_sha"],
        raw["tree_sha"],
        raw["baseline_sha"],
        tuple(OutputId(UUID(v)) for v in raw["output_ids"]),
        tuple(raw["output_digests"]),
        tuple(raw["commit_shas"]),
        raw["assignment_fencing_token"],
        raw["slot_fencing_token"],
        raw["writer_epoch_sha"],
    )


def receipt_from_document(request: GitCommitRequest, journal: Any, data: Any) -> GitCommitReceipt:
    from datetime import datetime

    return GitCommitReceipt(
        request.after_sha,
        request.before_sha,
        request.after_sha,
        request.tree_sha,
        request.commit_shas,
        request.target_branch,
        request.output_ids,
        str(journal["request_digest"]),
        request.writer_epoch_sha,
        str(journal["receipt_ref"]),
        str(journal["receipt_commit"]),
        datetime.fromisoformat(data["at"]),
    )


def require_admission(
    admission: Any,
    effect_id: str,
    digest: str,
    started: float,
    now: float,
    *,
    slot_token: int | None = None,
    cached: bool = False,
) -> None:
    from datetime import datetime

    try:
        duration = (
            datetime.fromisoformat(admission["admit_until"]) - datetime.fromisoformat(admission["server_now"])
        ).total_seconds()
        valid = (
            not cached
            and 0 < duration <= 5
            and now < started + duration
            and admission.get("effect_id") == effect_id
            and admission.get("request_digest") == digest
            and admission.get("admission_id")
            and (slot_token is None or admission.get("slot_fencing_token") == slot_token)
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise error_for(ErrorCode.LEASE_LOST, "expired, cached or mismatched effect admission")


def projected_request(
    inputs: Any, before: str, commits: Any, tree: str, epoch: str, slot_token: int
) -> GitCommitRequest:
    return commit_request(
        {
            "repository_id": inputs["repository_id"],
            "target_branch": inputs["target_branch"],
            "before_sha": before,
            "after_sha": commits[-1] if commits else before,
            "tree_sha": tree,
            "baseline_sha": inputs["baseline_sha"],
            "output_ids": [
                o["output_id"]
                for o in (
                    inputs["outputs"][-1:]
                    if inputs.get("commit_mode", "final_only") == "final_only"
                    else inputs["outputs"]
                )
            ],
            "output_digests": [
                o["output_digest"]
                for o in (
                    inputs["outputs"][-1:]
                    if inputs.get("commit_mode", "final_only") == "final_only"
                    else inputs["outputs"]
                )
            ],
            "commit_shas": list(commits),
            "assignment_fencing_token": inputs["assignment_fencing_token"],
            "slot_fencing_token": slot_token,
            "writer_epoch_sha": epoch,
        }
    )


def local_identities_match(journal: Any, messages: list[str]) -> bool:
    expected = {"SKM-Effect": journal["effect_id"], "SKM-Attempt": journal["inputs"]["attempt_id"]}
    return all(
        any(
            exact_trailers(message, {**expected, "SKM-Output": output})
            for output in journal["request"]["output_ids"]
        )
        for message in messages
    )


def result_report(report: Any, receipt: Any) -> Any:
    return {
        **report,
        "phase": "result",
        "result": {"succeeded": True, "ref": receipt["ref"], "response_digest": receipt["response_digest"]},
    }


def local_receipt_matches(journal: Any, doc: Any, tree: str, chain: list[str]) -> bool:
    request = journal["request"]
    return (
        doc["request"] == request
        and doc["effect_id"] == journal["effect_id"]
        and doc["request_digest"] == journal["request_digest"]
        and tree == request["tree_sha"]
        and chain == request["commit_shas"]
    )


def push_arguments(request: Any, url: str, config: list[str]) -> list[str]:
    import re

    before, after, ref = request["before_sha"], request["after_sha"], request["target_ref"]
    if (
        any(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) is None for sha in (before, after))
        or set(after) == {"0"}
        or request.get("force") is not False
        or len(request.get("refspecs", [])) != 1
        or request["refspecs"][0].partition(":")[2] != ref
    ):
        raise error_for(ErrorCode.APPROVAL_MISMATCH, "push requires exact SHAs and a single approved ref")
    return [
        *config,
        "push",
        "--porcelain",
        "--no-follow-tags",
        "--force-with-lease=" + ref + ":" + before,
        "--",
        url,
        after + ":" + ref,
    ]


def reconciliation_observation(journal: Any, state: str, at: str, receipt: Any = None) -> Any:
    result = {
        "state": state,
        "effect_id": journal["effect_id"],
        "request": journal["request"],
        "receipt_ref": "refs/skm/effects/" + journal["effect_id"],
    }
    if state == "succeeded":
        result["receipt"] = receipt
    elif state == "failed":
        ref = journal["request"]["before_sha"]
        result.update(
            reason_code="EFFECT_ABSENT",
            receipt={
                "ref": ref,
                "at": at,
                "response_digest": observation_digest(
                    journal["effect_id"], journal["request_digest"], state, ref, "EFFECT_ABSENT"
                ),
            },
        )
    return result


def observation_receipt(effect: str, digest: str, state: str, ref: str, reason: Any, at: str) -> Any:
    return {"ref": ref, "at": at, "response_digest": observation_digest(effect, digest, state, ref, reason)}


def push_rejected(code: int | None, output: bytes, truncated: bool, target: str) -> bool:
    rows = [line.split("\t") for line in output.decode("utf-8", "replace").splitlines()]
    return bool(
        code
        and not truncated
        and any(
            len(row) == 3
            and row[0] == "!"
            and row[1].partition(":")[2] == target
            and row[2].startswith(("[rejected]", "[remote rejected]"))
            for row in rows
        )
    )
