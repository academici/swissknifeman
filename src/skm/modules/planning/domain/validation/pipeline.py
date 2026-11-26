"""The validation pipeline: built-in rules, then plugin rules, collected without ever mutating the plan.

A rule is a pure function of the context. What it returns are findings about the user's plan; what it raises
is a defect of the validator (or of a plugin), recorded as a ``RuleFailure`` and never turned into a finding.
The failure of a built-in rule always blocks (fail closed); a plugin failure blocks by setting.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.planning.domain.compile_graph import compile_execution_graph
from skm.modules.planning.domain.validation import (
    rules_acceptance,
    rules_checks,
    rules_context,
    rules_decisions,
    rules_dependencies,
    rules_readiness,
    rules_references,
    rules_review,
    rules_routing,
    rules_scope,
    rules_structure,
)
from skm.modules.planning.domain.validation.context import ValidationSettings
from skm.modules.planning.domain.validation.findings import (
    PLUGIN_CODE,
    Finding,
    RuleFailure,
    Severity,
    ValidationReport,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from skm.modules.planning.domain.compile_graph import ExecutionGraph
    from skm.modules.planning.domain.validation.context import ValidationContext

type Rule = Callable[[ValidationContext], Iterable[Finding]]

_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


@dataclass(frozen=True, slots=True)
class PluginRule:
    """A ``planning_rule`` component of a trusted plugin; ``component_id`` names it in a ``RuleFailure``."""

    component_id: str
    rule: Rule


_MODULES = (
    rules_structure,
    rules_references,
    rules_dependencies,
    rules_scope,
    rules_readiness,
    rules_acceptance,
    rules_review,
    rules_checks,
    rules_decisions,
    rules_context,
    rules_routing,
)

# Module order of planning §5.7; inside a module the rules are in the alphabetical order of their codes.
DEFAULT_RULES: tuple[Rule, ...] = tuple(rule for module in _MODULES for rule in module.RULES)


def validate(
    ctx: ValidationContext,
    rules: tuple[Rule, ...] = DEFAULT_RULES,
    plugin_rules: tuple[PluginRule, ...] = (),
) -> ValidationReport:
    """Run ``rules``, then ``plugin_rules`` if ``planning.validation.external_checks`` is on, over ``ctx``."""
    findings: list[Finding] = []
    failures: list[RuleFailure] = []
    for rule in rules:
        produced = _run(rule, ctx, failures, plugin=None)
        findings.extend(produced)
    if _external_checks(ctx, failures):
        for plugin in plugin_rules:
            produced = _run(plugin.rule, ctx, failures, plugin=plugin.component_id)
            findings.extend(produced)
    findings.sort(key=_sort_key)
    graph = _graph(ctx, failures, reported=any(found.severity is Severity.ERROR for found in findings))
    return ValidationReport(tuple(findings), tuple(failures), graph)


def _external_checks(ctx: ValidationContext, failures: list[RuleFailure]) -> bool:
    """``planning.validation.external_checks``; settings the pipeline cannot read are a failure of its own."""
    try:
        return ValidationSettings.of(ctx.settings).external_checks
    except Exception as error:  # noqa: BLE001 - unreadable settings are a defect of the caller
        failures.append(RuleFailure("settings", type(error).__name__, str(error), None))
        return False


def _sort_key(found: Finding) -> tuple[int, str, str]:
    return _SEVERITY_ORDER[found.severity], found.pointer or "", found.code


def _name(rule: Rule) -> str:
    return getattr(rule, "__name__", None) or type(rule).__name__


def _run(
    rule: Rule, ctx: ValidationContext, failures: list[RuleFailure], *, plugin: str | None
) -> list[Finding]:
    """The findings of one rule, all or none: a rule that fails half way adds only its failure."""
    try:
        produced = list(rule(ctx))
        for found in produced:
            _require_finding(found, plugin)
    except Exception as error:  # noqa: BLE001 - any exception of a rule is a validator defect, not a finding
        failures.append(RuleFailure(_name(rule), type(error).__name__, str(error), plugin))
        return []
    return produced


def _require_finding(found: object, plugin: str | None) -> None:
    """A result that is not a well-formed finding is a defect of its rule; a plugin has narrower limits.

    The checks of the fields are no-ops for the type checker and real for a rule that is not what it claims.
    Everything the report later sorts or serialises is checked here, inside the boundary of the rule.
    """
    if not isinstance(found, Finding):
        raise TypeError(f"a rule returned {type(found).__name__}, not a Finding")
    if not isinstance(found.severity, Severity):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("finding severity is not a Severity")
    if not isinstance(found.code, str) or not isinstance(found.message, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("finding code and message must be text")
    if found.entity_key is not None and not isinstance(found.entity_key, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("finding entity_key must be text or None")
    if found.pointer is not None and not isinstance(found.pointer, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("finding pointer must be text or None")
    if found.entity_id is not None and not isinstance(found.entity_id, UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("finding entity_id must be an entity id or None")
    if not isinstance(found.details, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("finding details must be a mapping")
    _require_json(found.details, "details")
    if plugin is not None:
        if PLUGIN_CODE.fullmatch(found.code) is None:
            raise ValueError(f"plugin finding code {found.code!r} is not x_<publisher>_<name>")
        if found.severity is Severity.ERROR:
            raise ValueError("a plugin finding is a warning at most")


def _require_json(value: object, where: str) -> None:
    """``value`` is JSON-compatible all the way down: text-keyed mappings, lists, scalars, finite numbers."""
    if value is None or isinstance(value, bool | int | str):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"finding {where} holds a number that is not finite")
        return
    if isinstance(value, Mapping):
        for name, member in cast("Mapping[object, object]", value).items():
            if not isinstance(name, str):
                raise TypeError(f"finding {where} has a key that is not text")
            _require_json(member, f"{where}.{name}")
        return
    if isinstance(value, list | tuple):
        for n, member in enumerate(cast("Sequence[object]", value)):
            _require_json(member, f"{where}[{n}]")
        return
    raise TypeError(f"finding {where} holds a {type(value).__name__}, which is not JSON")


def _graph(ctx: ValidationContext, failures: list[RuleFailure], *, reported: bool) -> ExecutionGraph | None:
    """The execution graph of the plan; ``None`` for a cycle or if it cannot be built.

    A rule reports a cycle as a finding; one that no error finding accounts for is a defect of the validator,
    so that a plan the compiler rejects never passes as valid.
    """
    try:
        return compile_execution_graph(ctx.spec)
    except ValidationFailed as error:
        if error.code is ErrorCode.DEPENDENCY_CYCLE:
            if not reported:
                failures.append(
                    RuleFailure("compile_execution_graph", type(error).__name__, str(error), None)
                )
            return None
        failures.append(RuleFailure("compile_execution_graph", type(error).__name__, str(error), None))
    except Exception as error:  # noqa: BLE001 - the compiler failing is a validator defect
        failures.append(RuleFailure("compile_execution_graph", type(error).__name__, str(error), None))
    return None
