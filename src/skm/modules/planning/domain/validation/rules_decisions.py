"""Decision rules: required fields and supersession (planning §5.7, module ``decisions``)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from skm.modules.planning.domain.decision import DecisionState
from skm.modules.planning.domain.validation.context import Locator
from skm.modules.planning.domain.validation.findings import FindingCode, finding

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding

_OPTION_LETTER: Final = re.compile(r"[A-Z]")


def _blank(text: str | None) -> bool:
    return text is None or not text.strip()


def decision_fields(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for decision in ctx.spec.decisions:
        missing: list[str] = []
        if decision.state is DecisionState.OPEN and _blank(decision.question):
            missing.append("question")
        if decision.state in (DecisionState.PROPOSED, DecisionState.ACCEPTED):
            missing.extend(
                name
                for name, text in (("decision", decision.decision), ("rationale", decision.rationale))
                if _blank(text)
            )
        for name in missing:
            yield finding(
                FindingCode.DECISION_FIELDS,
                f"{decision.state.value} decision {decision.key} needs {name}",
                key=decision.key,
                entity_id=decision.id,
                pointer=loc.pointer(decision.key, name),
                details={"state": decision.state.value, "missing": name},
            )
        text = (decision.decision or "").strip()
        if _OPTION_LETTER.fullmatch(text) and text not in {option.key for option in decision.options}:
            yield finding(
                FindingCode.DECISION_FIELDS,
                f"decision {decision.key} chooses option {text}, which it does not have",
                key=decision.key,
                entity_id=decision.id,
                pointer=loc.pointer(decision.key, "decision"),
                details={"option": text},
            )


def decision_superseded_orphan(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    by_key = {decision.key: decision for decision in ctx.spec.decisions}
    replaced_by: dict[str, list[str]] = {}
    for decision in ctx.spec.decisions:
        for target in decision.supersedes:
            replaced_by.setdefault(target, []).append(decision.key)

    def report(subject: str, reason: str, message: str, *tail: str | int) -> Finding:
        decision = by_key[subject]
        return finding(
            FindingCode.DECISION_SUPERSEDED_ORPHAN,
            message,
            key=subject,
            entity_id=decision.id,
            pointer=loc.pointer(subject, *tail),
            details={"reason": reason},
        )

    for decision in ctx.spec.decisions:
        if decision.state is DecisionState.SUPERSEDED:
            replacers = replaced_by.get(decision.key, [])
            if not replacers:
                yield report(
                    decision.key, "no_superseder", f"{decision.key} is superseded by no decision", "state"
                )
            elif len(replacers) > 1:
                yield report(
                    decision.key,
                    "multiple_superseders",
                    f"{decision.key} is superseded by {len(replacers)} decisions: {', '.join(replacers)}",
                    "state",
                )
        for n, target in enumerate(decision.supersedes):
            replaced = by_key.get(target)
            if replaced is not None and replaced.state is not DecisionState.SUPERSEDED:
                yield report(
                    decision.key,
                    "target_not_superseded",
                    f"{decision.key} supersedes {target}, which is not marked superseded",
                    "supersedes",
                    n,
                )
        if decision.supersedes and decision.state is not DecisionState.ACCEPTED:
            yield report(
                decision.key,
                "superseder_not_accepted",
                f"{decision.key} supersedes {', '.join(decision.supersedes)} but is not accepted",
                "state",
            )


RULES: Final = (decision_fields, decision_superseded_orphan)
