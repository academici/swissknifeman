"""Who answers an executor question (execution §5.10; G27). No consilium logic lives here.

Gate categories are computed by code from paths and facts, never taken from the model. A gate category in
``human_gate`` always goes to the owner: the effective ``human_gate`` is the union of the defaults and every
configured level, so no level removes a category. ``category_audience`` only narrows (advisor → owner)
against the defaults, and ``authority_required`` is always the owner's. ``decide_audience`` applies the
§5.10 rules in their order; the work intensity is not an input.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.decision_record import QuestionCategory
from skm.modules.execution.domain.decision_request import Audience, question_digest, question_key
from skm.modules.execution.domain.risk import matching, patterns_of

if TYPE_CHECKING:
    from collections.abc import Iterable

    from skm.modules.execution.domain.contracts import ExecutionPolicy

__all__ = [
    "DEFAULT_CATEGORY_AUDIENCE",
    "DEFAULT_HUMAN_GATE",
    "DESTRUCTIVE_PATTERNS",
    "AudienceRoute",
    "AuthorityEnvelope",
    "Denied",
    "PolicyDefault",
    "ReusableDecision",
    "Reused",
    "decide_audience",
    "effective_category_audience",
    "effective_human_gate",
    "gate_categories",
]

DEFAULT_HUMAN_GATE: Final = frozenset({"security", "destructive", "public_api", "scope_expansion"})
DEFAULT_CATEGORY_AUDIENCE: Final[Mapping[QuestionCategory, Audience]] = {
    QuestionCategory.LOCAL_REVERSIBLE: Audience.ADVISOR,
    QuestionCategory.BOUNDED_AMBIGUITY: Audience.ADVISOR,
    QuestionCategory.CROSS_MODULE: Audience.ADVISOR,
    QuestionCategory.ARCHITECTURAL: Audience.OWNER,
    QuestionCategory.AUTHORITY_REQUIRED: Audience.OWNER,
    QuestionCategory.EXTERNAL_FACT: Audience.ADVISOR,
}
DESTRUCTIVE_PATTERNS: Final = ("**/migrations/**", "**/*delete*")
_RECORDABLE: Final = frozenset({"decision", "clarification"})


def decide_audience(  # noqa: PLR0911, PLR0913 -- the ordered rules of §5.10
    q: JsonObject,
    category: QuestionCategory,
    gates: frozenset[str],
    policy: ExecutionPolicy,
    reusable: ReusableDecision | None,
    advisor_rounds_used: int,
    questions_opened: int,
    *,
    task_key: str,
    answered_by_policy_before: bool = False,
    validate_answer: Callable[[JsonObject, JsonValue], bool] | None = None,
) -> AudienceRoute | PolicyDefault | Reused | Denied:
    """The first matching rule of §5.10.

    ``policy`` keys (ExecutionPolicy names): ``question_policy`` (advisor), ``max_questions_per_task`` (5),
    ``category_audience``, ``human_gate``, ``advisor_enabled`` (true), ``advisor_max_rounds`` (2) and
    ``consilium`` (``{members, trigger}`` or null). ``task_key`` identifies the question for reuse.
    A question with ``answer_schema`` requires ``validate_answer(schema, value)`` to prove the reused
    value fits that actual schema through ``platform.schema``. An absent validator fails closed.
    """
    if category is QuestionCategory.AUTHORITY_REQUIRED:
        return AudienceRoute(Audience.OWNER, "QUESTION_OWNER_ONLY")
    if gates & effective_human_gate(policy.get("human_gate")):
        return AudienceRoute(Audience.OWNER, "QUESTION_GATED")
    if questions_opened >= _int(policy.get("max_questions_per_task"), 5):
        return AudienceRoute(Audience.OWNER, "QUESTION_LIMIT")
    if reusable is not None and _reusable(task_key, q, reusable, validate_answer):
        return Reused(reusable.value, reusable.selected_option)
    question_policy = policy.get("question_policy", "advisor")
    if question_policy == "deny":
        return Denied("QUESTION_DENIED")
    if question_policy == "queue":
        return AudienceRoute(Audience.OWNER, "QUESTION_QUEUED")
    if question_policy == "defaults" and "default" in q and q.get("default") is not None:
        if answered_by_policy_before:
            return AudienceRoute(Audience.OWNER, "QUESTION_DEFAULT_USED")
        return PolicyDefault(q["default"])
    if effective_category_audience(policy.get("category_audience"))[category] is Audience.OWNER:
        return AudienceRoute(Audience.OWNER, "QUESTION_CATEGORY_OWNER")
    if (
        question_policy == "advisor"
        and policy.get("advisor_enabled", True) is not False
        and advisor_rounds_used < _int(policy.get("advisor_max_rounds"), 2)
    ):
        panel = policy.get("consilium")
        if _consilium_always(panel):
            return AudienceRoute(Audience.CONSILIUM, None)
        return AudienceRoute(Audience.ADVISOR, None)
    return AudienceRoute(Audience.OWNER, "QUESTION_NO_ADVISOR")


@dataclass(frozen=True, slots=True)
class AuthorityEnvelope:
    mode: str
    gate_categories: tuple[str, ...]
    confidence: str | None


@dataclass(frozen=True, slots=True)
class AudienceRoute:
    audience: Audience
    code: str | None


@dataclass(frozen=True, slots=True)
class PolicyDefault:
    value: JsonValue


@dataclass(frozen=True, slots=True)
class Reused:
    value: JsonValue
    selected_option: str | None


@dataclass(frozen=True, slots=True)
class Denied:
    code: str


@dataclass(frozen=True, slots=True)
class ReusableDecision:
    """An applied decision of the project found by ``question_key`` (record or revision decision spec).

    ``schema_ok`` is retained for callers of the earlier contract, but grants no authority. Schema
    questions require the live ``validate_answer`` callback of ``decide_audience`` instead.
    """

    question_key: str
    question_digest: str
    value: JsonValue
    selected_option: str | None
    schema_ok: bool = False


def gate_categories(
    facts: Mapping[str, JsonValue],
    paths: Sequence[str],
    write_scope: Sequence[str] | None,
    patterns: Mapping[str, JsonValue] | None = None,
) -> frozenset[str]:
    """Gate categories of a question from the changed or mentioned ``paths`` and its facts.

    ``patterns`` is ``execution.review.risk.patterns``; ``write_scope`` ``None`` (undeclared) makes every
    path an expansion.
    """
    table = None if patterns is None else dict(patterns)
    found: set[str] = set()
    if matching(paths, patterns_of(table, "security")):
        found.add("security")
    public_paths = matching(paths, (*patterns_of(table, "public_cli"), *patterns_of(table, "schema")))
    if public_paths or facts.get("contract_change") == "public":
        found.add("public_api")
    outside = [path for path in paths if write_scope is None or not matching([path], write_scope)]
    if outside or facts.get("scope_impact") == "plan":
        found.add("scope_expansion")
    if facts.get("reversibility") == "irreversible" and matching(paths, DESTRUCTIVE_PATTERNS):
        found.add("destructive")
    return frozenset(found)


def effective_human_gate(levels: JsonValue | None) -> frozenset[str]:
    """The defaults plus every configured category (a list, or a list of per-level lists)."""
    return DEFAULT_HUMAN_GATE | frozenset(_flatten(levels))


def effective_category_audience(value: JsonValue | None) -> dict[QuestionCategory, Audience]:
    """Defaults narrowed by the configured map: a level can move a category to the owner, never back."""
    result = dict(DEFAULT_CATEGORY_AUDIENCE)
    if isinstance(value, Mapping):
        for key, audience in cast("Mapping[str, JsonValue]", value).items():
            if key in set(QuestionCategory) and audience == "owner":
                result[QuestionCategory(key)] = Audience.OWNER
    result[QuestionCategory.AUTHORITY_REQUIRED] = Audience.OWNER
    return result


def _reusable(
    task_key: str,
    q: JsonObject,
    reusable: ReusableDecision,
    validate_answer: Callable[[JsonObject, JsonValue], bool] | None,
) -> bool:
    """Same ``question_key`` **and** digest, a ``decision``/``clarification`` kind and a fitting value."""
    if q.get("kind") not in _RECORDABLE:
        return False
    if reusable.question_key != question_key(task_key, q) or reusable.question_digest != question_digest(
        task_key, q
    ):
        return False
    return _value_fits(q, reusable, validate_answer)


def _value_fits(
    q: Mapping[str, JsonValue],
    reusable: ReusableDecision,
    validate_answer: Callable[[JsonObject, JsonValue], bool] | None,
) -> bool:
    """The reused value answers the current question: its options **and** its ``answer_schema``.

    With options the value must name one of them (option id, ``id: label`` or ``{option_id}``) and a
    recorded ``selected_option`` must be that same option; with an ``answer_schema`` the caller's
    validation must hold as well. Without either a non-empty text fits.
    """
    schema = q.get("answer_schema")
    if schema is not None:
        if not isinstance(schema, dict) or validate_answer is None:
            return False
        if validate_answer(schema, reusable.value) is not True:
            return False
    options = q.get("options")
    if isinstance(options, Sequence) and not isinstance(options, str) and options:
        labels = {
            str(option.get("id")): str(option.get("label", ""))
            for option in cast("Sequence[JsonValue]", options)
            if isinstance(option, Mapping)
        }
        named = _named_option(reusable.value, labels)
        chosen = reusable.selected_option
        return named is not None and (chosen is None or chosen == named)
    if q.get("answer_schema") is not None:
        return True
    return isinstance(reusable.value, str) and bool(reusable.value.strip())


def _named_option(value: JsonValue, labels: Mapping[str, str]) -> str | None:
    """The offered option ``value`` names, or ``None``."""
    if isinstance(value, str):
        if value in labels:
            return value
        return next((key for key, label in labels.items() if value == f"{key}: {label}"), None)
    if isinstance(value, Mapping):
        option = cast("Mapping[str, JsonValue]", value).get("option_id")
        return option if isinstance(option, str) and option in labels else None
    return None


def _consilium_always(panel: JsonValue | None) -> bool:
    if not isinstance(panel, Mapping):
        return False
    consilium = cast("Mapping[str, JsonValue]", panel)
    members = consilium.get("members")
    enough = isinstance(members, Sequence) and not isinstance(members, str) and len(members) >= 2
    return enough and consilium.get("trigger") == "always"


def _flatten(value: JsonValue | None) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Sequence):
        for item in cast("Sequence[JsonValue]", value):
            yield from _flatten(item)


def _int(value: JsonValue | None, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default
