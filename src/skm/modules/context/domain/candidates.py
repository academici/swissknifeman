"""Normalize server-owned source envelopes; payload text never determines instruction authority."""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.blocks import BLOCK_SPECS, LADDER_ORDER, BlockType, TrustLevel

if TYPE_CHECKING:
    from skm.modules.context.domain.contracts import Candidate
    from skm.modules.context.domain.policy import ContextPolicy
    from skm.modules.context.domain.request import ContextRequest


def objects(value: JsonValue | None) -> list[JsonObject]:
    """Read a JSON array of objects without accepting text as metadata."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def strings(value: JsonValue | None) -> tuple[str, ...]:
    return tuple(item for item in value if isinstance(item, str)) if isinstance(value, list) else ()


def metadata(candidate: Candidate) -> JsonObject:
    value = candidate.get("metadata", {})
    return value if isinstance(value, dict) else {}


def path_matches(trigger: str, pattern: str) -> bool:
    """Match concrete paths or scope globs, including zero directories for **/."""
    from fnmatch import fnmatchcase

    return (
        fnmatchcase(pattern, trigger)
        or fnmatchcase(trigger, pattern)
        or ("**/" in trigger and path_matches(trigger.replace("**/", "", 1), pattern))
        or ("**/" in pattern and path_matches(trigger, pattern.replace("**/", "", 1)))
    )


def discover(
    sources: Sequence[JsonObject], request: ContextRequest, policy: ContextPolicy
) -> tuple[Candidate, ...]:
    """Consume authorized, pinned resource envelopes supplied by the application facade (K19).

    No resolver or IO is called here: list_resolved(..., pins=request.pack_pins) belongs
    to assemble_draft. Source metadata is trusted control-plane data, distinct from content.
    """
    envelopes = [copy.deepcopy(source) for source in sources]
    envelopes.extend(_execution_sources(request, envelopes))
    result: dict[tuple[str, str, str], Candidate] = {}
    for source in envelopes:
        kind = BlockType(str(source["block_type"]))
        spec = BLOCK_SPECS[kind]
        meta = metadata(source)
        required = (
            (spec.mandatory in ("always", "when_present") and kind is not BlockType.MATERIALS)
            or (kind is BlockType.MATERIALS and bool(meta.get("required", source.get("mandatory", False))))
            or (kind is BlockType.CANDIDATE_DIFF and request.purpose.role in ("reviewer", "triager"))
            or (kind is BlockType.FINDINGS_UNDER_REVIEW and request.purpose.role == "triager")
            or bool(source.get("mandatory", False))
        )
        source_ref = str(source.get("source_ref", f"core:{kind.value}"))
        source_kind = str(source.get("source_kind", "core"))
        trust = TrustLevel(str(source.get("trust", spec.default_trust.value)))
        candidate: Candidate = {
            **source,
            "block_type": kind.value,
            "budget_class": spec.budget_class.value,
            "source_kind": source_kind,
            "source_ref": source_ref,
            "source_version": source.get("source_version"),
            "trust": trust.value,
            "mandatory": required,
            "atomic_group": source.get("atomic_group"),
        }
        result.setdefault((kind.value, source_ref, str(source.get("source_version", ""))), candidate)
    del policy  # Policy filters follow validation; required blocks bypass include.
    return tuple(
        sorted(
            result.values(),
            key=lambda c: (LADDER_ORDER[BlockType(str(c["block_type"]))], str(c["source_ref"])),
        )
    )


def _execution_sources(request: ContextRequest, sources: Sequence[JsonObject]) -> list[JsonObject]:
    eb = request.execution_blocks
    provided = {str(s["block_type"]) for s in sources}
    rows: list[JsonObject] = []

    def add(kind: BlockType, content: str, suffix: str = "") -> None:
        if kind.value not in provided:
            rows.append(
                {
                    "block_type": kind.value,
                    "source_kind": "execution",
                    "source_ref": f"exec:{kind.value}:{request.purpose.step_ref}{suffix}",
                    "content": content,
                }
            )

    if eb.decision_answers:
        add(
            BlockType.DECISION_ANSWERS,
            json.dumps(
                [
                    {
                        "request_id": a.request_id,
                        "question": a.question,
                        "answer": a.answer,
                        "answered_by_kind": a.answered_by_kind,
                    }
                    for a in eb.decision_answers
                ],
                sort_keys=True,
            ),
        )
    if eb.review_feedback is not None:
        add(
            BlockType.REVIEW_FEEDBACK,
            json.dumps(
                {
                    k: v
                    for k, v in eb.review_feedback.items()
                    if k not in {"raw_transcript", "transcript", "messages", "provider_log"}
                },
                sort_keys=True,
            ),
        )
    if eb.previous_attempt is not None:
        add(BlockType.PREVIOUS_ATTEMPT, eb.previous_attempt.note)
    if eb.findings_under_review:
        add(BlockType.FINDINGS_UNDER_REVIEW, json.dumps(list(eb.findings_under_review), sort_keys=True))
    if eb.context_map is not None:
        add(BlockType.CONTEXT_MAP, eb.context_map.text)
    for idx, item in enumerate(eb.research):
        add(BlockType.RESEARCH, "\n".join(c.text for c in item.claims), f":{idx}")
    for idx, item in enumerate(eb.history):
        add(BlockType.HISTORY, item.summary, f":{idx}")
    return rows
