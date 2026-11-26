"""Context rules: bindings, heavy texts and materials (planning §5.7, module ``context``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from skm.modules.planning.domain.decision import Decision, DecisionState
from skm.modules.planning.domain.material import FreshnessPolicy, MaterialKind, must_refresh_expired
from skm.modules.planning.domain.reads import MaterialRead, PlanEntityRead
from skm.modules.planning.domain.validation.context import FileVersionStatus, Locator, ValidationSettings
from skm.modules.planning.domain.validation.findings import FindingCode, finding, pointer_of

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from skm.modules.planning.domain.reads import Read
    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding


def _bytes(text: str | None) -> int:
    return 0 if text is None else len(text.encode("utf-8"))


def brief_duplicate(ctx: ValidationContext) -> Iterator[Finding]:
    brief = ctx.spec.brief
    first: dict[str, int] = {}
    for n, message in enumerate(() if brief is None else brief.messages):
        text = message.text.strip()
        if text not in first:
            first[text] = n
            continue
        yield finding(
            FindingCode.BRIEF_DUPLICATE,
            f"brief message {message.key} repeats the text of an earlier message",
            key=message.key,
            pointer=pointer_of("brief", "messages", n, "text"),
            details={"first_pointer": pointer_of("brief", "messages", first[text], "text")},
        )


def context_heavy(ctx: ValidationContext) -> Iterator[Finding]:
    spec, loc, limit = ctx.spec, Locator(ctx.document), ValidationSettings.of(ctx.settings).heavy_text_bytes

    def texts() -> Iterator[tuple[str | None, str | None, str | None]]:
        """``(entity key, pointer of the text, text)`` of every text that enters many contexts."""
        yield None, "/context_md", spec.context_md
        for n, message in enumerate(() if spec.brief is None else spec.brief.messages):
            yield message.key, pointer_of("brief", "messages", n, "text"), message.text
        for n, section in enumerate(spec.sections):
            yield None, pointer_of("sections", n, "text"), section.text
        for entity in (*spec.phases, *spec.decisions):
            yield entity.key, loc.pointer(entity.key, "context_md"), entity.context_md
        for entity in (*spec.phases, *spec.items, *spec.units, *spec.decisions):
            for n, section in enumerate(entity.sections):
                yield entity.key, loc.pointer(entity.key, "sections", n, "text"), section.text

    for key, pointer, text in texts():
        size = _bytes(text)
        if size > limit:
            yield finding(
                FindingCode.CONTEXT_HEAVY,
                f"a text of {size} bytes enters many contexts (limit {limit})",
                key=key,
                pointer=pointer,
                details={"bytes": size, "limit": limit},
            )


def _read_refs(reads: Iterable[Read]) -> Iterator[str]:
    for read in reads:
        if isinstance(read, MaterialRead | PlanEntityRead):
            yield read.ref


def context_unbound(ctx: ValidationContext) -> Iterator[Finding]:
    spec, loc = ctx.spec, Locator(ctx.document)
    refs: set[str] = set()
    for entity in (*spec.items, *spec.units):
        refs.update(_read_refs(entity.reads))
    for item in spec.items:
        refs.update(_read_refs(item.examples))
        refs.update(item.decisions)
    for phase in spec.phases:
        refs.update(_read_refs(phase.supporting))
    heads = {ref.partition("#")[0] for ref in refs}
    for decision in spec.decisions:
        if decision.state is DecisionState.ACCEPTED and not (
            decision.is_global or decision.applies_to or decision.key in heads
        ):
            yield finding(
                FindingCode.CONTEXT_UNBOUND,
                f"decision {decision.key} reaches no context: bind it, make it global or read it",
                key=decision.key,
                entity_id=decision.id,
                pointer=loc.pointer(decision.key, "applies_to"),
            )
    for material in spec.materials:
        key = f"material/{material.key}"
        if not (material.is_global or material.applies_to or key in heads):
            yield finding(
                FindingCode.CONTEXT_UNBOUND,
                f"{key} reaches no context: bind it, make it global or read it from an item",
                key=key,
                entity_id=material.id,
                pointer=loc.pointer(key, "applies_to"),
            )


def execution_prompt_heavy(ctx: ValidationContext) -> Iterator[Finding]:
    spec, loc, limit = ctx.spec, Locator(ctx.document), ValidationSettings.of(ctx.settings).heavy_text_bytes
    pitfalls = {phase.key: phase.pitfalls for phase in spec.phases}
    for item in spec.items:
        parts = (*spec.rules, *pitfalls.get(item.phase, ()), *item.rules, item.guidance_md or "")
        size = sum(_bytes(part) for part in parts)
        if size > limit:
            yield finding(
                FindingCode.EXECUTION_PROMPT_HEAVY,
                f"rules, pitfalls and guidance of {item.key} weigh {size} bytes (limit {limit})",
                key=item.key,
                entity_id=item.id,
                pointer=loc.pointer(item.key),
                details={"bytes": size, "limit": limit},
            )


def material_stale(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for material in ctx.spec.materials:
        if material.freshness.policy is not FreshnessPolicy.MUST_REFRESH:
            continue
        if material.kind is MaterialKind.FILE_VERSION:
            observation = (
                None if material.file_version_id is None else ctx.file_versions.get(material.file_version_id)
            )
            if observation is None or observation.status is not FileVersionStatus.READY:
                continue  # missing or not ready is material_unavailable, not stale
            observed_at = observation.created_at
        elif material.kind is MaterialKind.EXTERNAL_SOURCE:
            observed_at = material.retrieved_at
        else:
            continue  # a repository path is always pinned
        if must_refresh_expired(material.freshness.max_age_seconds, observed_at, ctx.now):
            key = f"material/{material.key}"
            yield finding(
                FindingCode.MATERIAL_STALE,
                f"{key} must be refreshed: it is older than {material.freshness.max_age_seconds} seconds "
                "or its age is unknown",
                key=key,
                entity_id=material.id,
                pointer=loc.pointer(key, "freshness"),
                details={"max_age_seconds": material.freshness.max_age_seconds},
            )


def material_unavailable(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for material in ctx.spec.materials:
        if material.kind is not MaterialKind.FILE_VERSION or material.file_version_id is None:
            continue
        observation = ctx.file_versions.get(material.file_version_id)
        status = FileVersionStatus.MISSING if observation is None else observation.status
        if status is not FileVersionStatus.READY:
            key = f"material/{material.key}"
            yield finding(
                FindingCode.MATERIAL_UNAVAILABLE,
                f"{key} points to a file version that is {status.value}",
                key=key,
                entity_id=material.id,
                pointer=loc.pointer(key, "file_version_id"),
                details={"status": status.value},
            )


def scope_ambiguous(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for entity in (*ctx.spec.decisions, *ctx.spec.materials):
        if entity.is_global and entity.applies_to:
            key = entity.key if isinstance(entity, Decision) else f"material/{entity.key}"
            yield finding(
                FindingCode.SCOPE_AMBIGUOUS,
                f"{key} is global and also applies to {', '.join(entity.applies_to)}; keep one",
                key=key,
                entity_id=entity.id,
                pointer=loc.pointer(key, "global"),
                details={"applies_to": list(entity.applies_to)},
            )


RULES: Final = (
    brief_duplicate,
    context_heavy,
    context_unbound,
    execution_prompt_heavy,
    material_stale,
    material_unavailable,
    scope_ambiguous,
)
