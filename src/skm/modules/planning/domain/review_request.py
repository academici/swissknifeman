"""Service-plan review-request DTOs and canonical specification builder (planning §7.11).

``ReviewRequestSpec`` and its target union live in ``planning`` so ``execution`` imports them via
``skm.modules.planning.public`` without creating a reverse dependency from ``planning`` to ``execution``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import EntityId, FileVersionId, parse_uuid
from skm.modules.planning.domain.canonical import normalize_document
from skm.modules.planning.domain.specification import SPECIFICATION_URN

if TYPE_CHECKING:
    from skm.kernel.id_generator import IdGenerator
    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "REVIEW_REQUESTS_ALIAS",
    "REVIEW_REQUESTS_GOAL",
    "REVIEW_REQUESTS_TITLE",
    "REVIEW_REQUEST_EXTENSION_NS",
    "CommitReviewTarget",
    "ReviewRequestSpec",
    "ReviewRequestTarget",
    "WorkingTreeReviewTarget",
    "build_review_request_document",
    "coerce_review_request_spec",
]

REVIEW_REQUESTS_ALIAS: Final = "review-requests"
REVIEW_REQUESTS_TITLE: Final = "Review requests"
REVIEW_REQUESTS_GOAL: Final = "Independent review of changes requested outside plans."
REVIEW_REQUEST_EXTENSION_NS: Final = "skm/review-request"

_MOUNT_RE: Final = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$", re.ASCII)
_SKILL_KEY_RE: Final = re.compile(r"^[a-z][a-z0-9-]*(?:(?::|/)[a-z][a-z0-9-]*)?$", re.ASCII)
_REASON_MAX_CHARS: Final = 20_000
_SHORT_TEXT_MAX_CHARS: Final = 300


@dataclass(frozen=True, slots=True)
class CommitReviewTarget:
    """Commit-range target ``<base_commit>..<head_commit>`` for an out-of-plan review request."""

    kind: Literal["commits"]
    base_commit: str
    head_commit: str


@dataclass(frozen=True, slots=True)
class WorkingTreeReviewTarget:
    """Working-tree patch target ``<base_commit>..working tree`` pinned to an uploaded patch version."""

    kind: Literal["working_tree"]
    base_commit: str
    patch_file_version_id: FileVersionId


type ReviewRequestTarget = CommitReviewTarget | WorkingTreeReviewTarget


@dataclass(frozen=True, slots=True)
class ReviewRequestSpec:
    """Input DTO for ``planning.public.publish_review_request_revision`` (planning §7.11)."""

    request_id: UUID
    mount: str
    target: ReviewRequestTarget
    profile: str
    reason: str


def _invalid_field(pointer: str, message: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        message,
        details={"issues": [{"pointer": pointer, "message": message, "schema_pointer": ""}]},
    )


def _as_uuid(value: object, pointer: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return parse_uuid(value)
        except ValueError as exc:
            raise _invalid_field(pointer, "must be a valid UUID") from exc
    raise _invalid_field(pointer, "must be a UUID")


def _require_commit_ref(value: object, pointer: str) -> str:
    if not isinstance(value, str) or not value or any(ch.isspace() or ch == "\x00" for ch in value):
        raise _invalid_field(pointer, "commit reference must be a non-empty string without whitespace")
    return value


def _coerce_target(raw: object) -> ReviewRequestTarget:
    if isinstance(raw, CommitReviewTarget):
        if raw.kind != "commits":
            raise _invalid_field("/target/kind", "target.kind must be 'commits'")
        return CommitReviewTarget(
            kind="commits",
            base_commit=_require_commit_ref(raw.base_commit, "/target/base_commit"),
            head_commit=_require_commit_ref(raw.head_commit, "/target/head_commit"),
        )
    if isinstance(raw, WorkingTreeReviewTarget):
        if raw.kind != "working_tree":
            raise _invalid_field("/target/kind", "target.kind must be 'working_tree'")
        return WorkingTreeReviewTarget(
            kind="working_tree",
            base_commit=_require_commit_ref(raw.base_commit, "/target/base_commit"),
            patch_file_version_id=FileVersionId(
                _as_uuid(raw.patch_file_version_id, "/target/patch_file_version_id")
            ),
        )
    if isinstance(raw, Mapping):
        mapping = cast("Mapping[str, object]", raw)
        kind = mapping.get("kind")
        if kind == "commits":
            return CommitReviewTarget(
                kind="commits",
                base_commit=_require_commit_ref(mapping.get("base_commit"), "/target/base_commit"),
                head_commit=_require_commit_ref(mapping.get("head_commit"), "/target/head_commit"),
            )
        if kind == "working_tree":
            return WorkingTreeReviewTarget(
                kind="working_tree",
                base_commit=_require_commit_ref(mapping.get("base_commit"), "/target/base_commit"),
                patch_file_version_id=FileVersionId(
                    _as_uuid(mapping.get("patch_file_version_id"), "/target/patch_file_version_id")
                ),
            )
        raise _invalid_field("/target/kind", "target.kind must be 'commits' or 'working_tree'")
    raise _invalid_field("/target", "target must be a CommitReviewTarget or WorkingTreeReviewTarget")


def coerce_review_request_spec(spec: object) -> ReviewRequestSpec:
    """Validate and normalize ``spec`` (dataclass or mapping) into a ``ReviewRequestSpec``."""
    if isinstance(spec, ReviewRequestSpec):
        raw_request_id: object = spec.request_id
        raw_mount: object = spec.mount
        raw_target: object = spec.target
        raw_profile: object = spec.profile
        raw_reason: object = spec.reason
    elif isinstance(spec, Mapping):
        mapping = cast("Mapping[str, object]", spec)
        raw_request_id = mapping.get("request_id")
        raw_mount = mapping.get("mount")
        raw_target = mapping.get("target")
        raw_profile = mapping.get("profile")
        raw_reason = mapping.get("reason")
    else:
        raise _invalid_field("", "review request spec must be a ReviewRequestSpec or mapping")

    request_id = _as_uuid(raw_request_id, "/request_id")
    if not isinstance(raw_mount, str) or _MOUNT_RE.fullmatch(raw_mount) is None:
        raise _invalid_field("/mount", "mount must match ^[a-z0-9][a-z0-9-]{0,62}$")
    target = _coerce_target(raw_target)
    if not isinstance(raw_profile, str) or _SKILL_KEY_RE.fullmatch(raw_profile) is None:
        raise _invalid_field("/profile", "profile must be a valid skill key")
    if not isinstance(raw_reason, str) or not raw_reason.strip() or len(raw_reason) > _REASON_MAX_CHARS:
        raise _invalid_field("/reason", f"reason must be 1..{_REASON_MAX_CHARS} non-blank characters")

    return ReviewRequestSpec(
        request_id=request_id,
        mount=raw_mount,
        target=target,
        profile=raw_profile,
        reason=raw_reason,
    )


def _existing_phase_id(current_document: Mapping[str, JsonValue] | None) -> EntityId | None:
    if current_document is None:
        return None
    phases = current_document.get("phases")
    if not isinstance(phases, list):
        return None
    for entry in phases:
        if isinstance(entry, Mapping) and entry.get("key") == "P1":
            raw_id = entry.get("id")
            if isinstance(raw_id, str):
                try:
                    return EntityId(parse_uuid(raw_id))
                except ValueError:
                    return None
    return None


def build_review_request_document(
    spec: ReviewRequestSpec,
    *,
    ids: IdGenerator,
    current_document: Mapping[str, JsonValue] | None = None,
) -> JsonObject:
    """Build the canonical ``SpecificationDoc`` for ``spec`` (planning §7.11 step 2)."""
    validated = coerce_review_request_spec(spec)
    phase_id = _existing_phase_id(current_document)
    if phase_id is None:
        phase_id = EntityId(ids.new_id())
    item_id = EntityId(ids.new_id())
    criterion_id = EntityId(ids.new_id())

    if isinstance(validated.target, CommitReviewTarget):
        range_label = f"{validated.target.base_commit}..{validated.target.head_commit}"
    else:
        range_label = f"{validated.target.base_commit}..working tree"

    item_title = f"Review {range_label} of {validated.mount}"
    if len(item_title) > _SHORT_TEXT_MAX_CHARS:
        raise _invalid_field("/target", f"formatted item title exceeds {_SHORT_TEXT_MAX_CHARS} characters")

    raw_doc: JsonObject = {
        "schema": SPECIFICATION_URN,
        "title": REVIEW_REQUESTS_TITLE,
        "goal": REVIEW_REQUESTS_GOAL,
        "phases": [
            {
                "id": str(phase_id),
                "key": "P1",
                "title": REVIEW_REQUESTS_TITLE,
                "goal": "Review the requested change range.",
                "design_state": "detailed",
                "depends_on": [],
            }
        ],
        "items": [
            {
                "id": str(item_id),
                "key": "P1.1",
                "phase": "P1",
                "title": item_title,
                "summary": validated.reason,
                "why": "Owner-requested review.",
                "work_kind": "review",
                "scope": {"include": [f"{validated.mount}:{range_label}"], "exclude": []},
                "deliverables": ["Review report"],
                "guidance_md": validated.reason,
                "review": {
                    "mode": "required",
                    "profile": validated.profile,
                    "independence": "separate_session",
                },
            }
        ],
        "criteria": [
            {
                "id": str(criterion_id),
                "key": "AC1",
                "owner": "P1.1",
                "statement": "The review report covers the requested range.",
                "verification_mode": "review",
            }
        ],
        "extensions": {
            REVIEW_REQUEST_EXTENSION_NS: {
                "schema_version": 1,
                "value": {"request_id": str(validated.request_id)},
            }
        },
    }
    return normalize_document(raw_doc)
