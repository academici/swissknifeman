"""Doctor checks evaluated from explicit host observations."""

from collections import Counter
from collections.abc import Callable, Iterable

from skm.modules.integrations.domain.reports import CheckResult, DoctorReport
from skm.modules.integrations.domain.target import TargetId

from . import claude, clients, hygiene, projections
from .context import DoctorContext

__all__ = ["DoctorContext", "run_checks", "summarize"]


def run_checks(ctx: DoctorContext) -> DoctorReport:
    checks: list[Callable[[DoctorContext], Iterable[CheckResult]]] = list(projections.CHECKS)
    checks.extend(hygiene.CHECKS)
    if ctx.target is TargetId.CLAUDE_CODE:
        checks.extend((*claude.CHECKS, projections.local_settings_gitignored))
    elif ctx.target is TargetId.CURSOR:
        checks.extend(clients.CURSOR_CHECKS)
    elif ctx.target is TargetId.CODEX:
        checks.extend(clients.CODEX_CHECKS)
    return summarize(tuple(result for check in checks for result in check(ctx)))


def summarize(checks: tuple[CheckResult, ...]) -> DoctorReport:
    """A single severity ordering for unit, host, JSON and human reports."""
    counts = Counter(check.level for check in checks)
    levels = ("error", "warning", "info", "ok")
    return DoctorReport(
        tuple(checks),
        {level: counts[level] for level in levels},
        next((level for level in levels if counts[level]), "ok"),
    )
