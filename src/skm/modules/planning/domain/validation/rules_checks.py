"""Check rules: command units, heavy and repeated commands, manual re-runs (planning §5.7, module ``checks``).

Repository-specific heuristics of the legacy ``check_overlap`` (which scripts run which tests) are not here;
they belong to an overlay plugin (``docs/porting/planning-findings.md``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from skm.modules.planning.domain.check_spec import CheckKind, CommandDefinition, ShellDefinition
from skm.modules.planning.domain.unit import UnitKind
from skm.modules.planning.domain.validation.context import Locator, ValidationSettings
from skm.modules.planning.domain.validation.findings import FindingCode, finding

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skm.modules.planning.domain.check_spec import CheckSpec
    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding


def _command_text(check: CheckSpec) -> str | None:
    """The command line of a command check, the script of a shell check; ``None`` for other kinds."""
    definition = check.definition
    if isinstance(definition, CommandDefinition):
        return " ".join(definition.argv)
    if isinstance(definition, ShellDefinition):
        return definition.script
    return None


def _same_command(left: CheckSpec, right: CheckSpec) -> bool:
    a, b = left.definition, right.definition
    if isinstance(a, CommandDefinition) and isinstance(b, CommandDefinition):
        return a.argv == b.argv
    if isinstance(a, ShellDefinition) and isinstance(b, ShellDefinition):
        return a.script.strip() == b.script.strip()
    return False


def check_cadence(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    markers = ValidationSettings.of(ctx.settings).heavy_check_markers
    items = {item.key for item in ctx.spec.items}
    for check in ctx.spec.checks:
        text = _command_text(check)
        if text is None or check.owner not in items:
            continue
        marker = next((m for m in markers if m in text), None)
        if marker is not None:
            key = f"{check.owner}:{check.key}"
            yield finding(
                FindingCode.CHECK_CADENCE,
                f"{key} runs {marker!r}, a heavy command: put it into the check of the phase",
                key=key,
                entity_id=check.id,
                pointer=loc.pointer(key, "definition"),
                details={"marker": marker},
            )


def check_duplicate_command(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    phase_of = {item.key: item.phase for item in ctx.spec.items}
    for check in ctx.spec.checks:
        phase = phase_of.get(check.owner)
        if phase is None or _command_text(check) is None:
            continue
        same = next((c for c in ctx.spec.checks_of(phase) if _same_command(check, c)), None)
        if same is not None:
            key = f"{check.owner}:{check.key}"
            yield finding(
                FindingCode.CHECK_DUPLICATE_COMMAND,
                f"{key} repeats the command of {same.owner}:{same.key}; keep one",
                key=key,
                entity_id=check.id,
                pointer=loc.pointer(key, "definition"),
                details={"phase_check": f"{same.owner}:{same.key}"},
            )


def check_manual_rerun_after_integration(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for check in ctx.spec.checks:
        if check.kind is CheckKind.MANUAL and check.rerun_after_integration:
            key = f"{check.owner}:{check.key}"
            yield finding(
                FindingCode.CHECK_MANUAL_RERUN_AFTER_INTEGRATION,
                f"{key} is manual and re-runs after integration, which nobody can do automatically",
                key=key,
                entity_id=check.id,
                pointer=loc.pointer(key, "rerun_after_integration"),
            )


def unit_command_missing(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for unit in ctx.spec.units:
        if unit.unit_kind is UnitKind.COMMAND and unit.command is None:
            yield finding(
                FindingCode.UNIT_COMMAND_MISSING,
                f"command unit {unit.key} has no command",
                key=unit.key,
                entity_id=unit.id,
                pointer=loc.pointer(unit.key, "command"),
            )


RULES: Final = (
    check_cadence,
    check_duplicate_command,
    check_manual_rerun_after_integration,
    unit_command_missing,
)
