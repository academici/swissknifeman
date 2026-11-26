"""Immutable review targets and receipts (execution §§4.20, 5.19)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Literal

    from skm.kernel.ids import (
        FileVersionId,
        PlanId,
        PrincipalId,
        ProjectId,
        RepositoryId,
        RevisionId,
        WorkspaceId,
    )
    from skm.modules.execution.domain.ids import ReviewRequestId


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    id: ReviewRequestId
    workspace_id: WorkspaceId
    project_id: ProjectId
    mount: str
    repository_id: RepositoryId
    target: ReviewTarget
    profile_key: str
    reason: str
    requested_by: PrincipalId
    plan_id: PlanId
    revision_id: RevisionId
    created_at: datetime

    @property
    def target_digest(self) -> str:
        return target_digest(self.target)


@dataclass(frozen=True, slots=True)
class CommitReviewTarget:
    kind: Literal["commits"]
    base_commit: str
    head_commit: str


@dataclass(frozen=True, slots=True)
class WorkingTreeReviewTarget:
    kind: Literal["working_tree"]
    base_commit: str
    patch_file_version_id: FileVersionId


type ReviewTarget = CommitReviewTarget | WorkingTreeReviewTarget


def target_document(target: ReviewTarget) -> JsonObject:
    result: JsonObject = {"kind": target.kind, "base_commit": target.base_commit}
    if isinstance(target, CommitReviewTarget):
        result["head_commit"] = target.head_commit
    else:
        result["patch_file_version_id"] = str(target.patch_file_version_id)
    return result


def target_digest(target: ReviewTarget) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                target_document(target), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
    )


def validate_target(target: ReviewTarget) -> None:
    commits = [target.base_commit]
    if isinstance(target, CommitReviewTarget):
        commits.append(target.head_commit)
    if any(re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit) is None for commit in commits):
        raise error_for(ErrorCode.SCHEMA_INVALID, "review targets require resolved commit object IDs")


@dataclass(frozen=True, slots=True)
class ReviewReceipt:
    request_id: UUID
    run_id: UUID
    status: str
    verdict: str | None
    findings: tuple[JsonObject, ...]
    output_id: UUID
    tree_digest: str
    base_commit: str
    head_commit: str
    SCHEMA_URN: ClassVar[str] = "urn:skm:execution:view:get-review-receipt:v1"

    def fresh_for(self, head_tree_digest: str) -> bool:
        return self.tree_digest == head_tree_digest

    @classmethod
    def from_json(cls, data: Any) -> Self:
        return cls(
            UUID(data["request_id"]),
            UUID(data["run_id"]),
            data["status"],
            data["verdict"],
            tuple(data["findings"]),
            UUID(data["output_id"]),
            data["tree_digest"],
            data["base_commit"],
            data["head_commit"],
        )

    def to_json(self) -> JsonObject:
        return {
            "request_id": str(self.request_id),
            "run_id": str(self.run_id),
            "status": self.status,
            "verdict": self.verdict,
            "findings": list(self.findings),
            "output_id": str(self.output_id),
            "tree_digest": self.tree_digest,
            "base_commit": self.base_commit,
            "head_commit": self.head_commit,
        }


class RequestReview(dict[str, Any]):
    """Bus identity for the generated JSON-mode request contract."""

    SCHEMA_URN = "urn:skm:execution:command:request-review:v1"

    @classmethod
    def from_json(cls, data: Any) -> Self:
        return cls(data)

    def to_json(self) -> JsonObject:
        return dict(self)
