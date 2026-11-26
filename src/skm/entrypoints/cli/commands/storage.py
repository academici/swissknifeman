"""Verify storage and apply the bounded safe repair commands."""

import argparse
from typing import cast

from skm.entrypoints.cli._run_io import ask, dispatch
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import render, render_table
from skm.platform.generated.commands import RepairStorageSafe
from skm.platform.generated.queries import VerifyStorage
from skm.platform.generated.results import RepairStorageSafeResult, VerifyStorageResult
from skm.platform.storage.verify import CATALOG, LEVELS


def _verify(args: argparse.Namespace, ctx: CliContext) -> int:
    report = cast("VerifyStorageResult", ask(ctx, VerifyStorage, levels=args.level))

    def human(value: VerifyStorageResult) -> list[str]:
        counts = value.counts
        lines = [f"Errors: {counts.error}  Warnings: {counts.warning}  Info: {counts.info}"]
        if value.findings:
            lines.extend(
                render_table(
                    ctx,
                    (
                        "CODE",
                        "SEVERITY",
                        "LEVEL",
                        "TARGET",
                        "REFERENCED BY",
                        "REPAIRABILITY",
                        "DETAIL",
                    ),
                    [
                        (
                            item.code,
                            item.severity,
                            item.level,
                            f"{item.target.kind}:{item.target.id}",
                            ", ".join(f"{ref.kind}:{ref.id}" for ref in item.referenced_by),
                            item.repairability,
                            item.detail,
                        )
                        for item in value.findings
                    ],
                )
            )
        return lines

    render(ctx, report, command="platform.verify_storage", human=human)
    return 6 if report.counts.error > 0 else 0


def _repair(args: argparse.Namespace, ctx: CliContext) -> int:
    report = cast(
        "RepairStorageSafeResult",
        dispatch(
            ctx,
            RepairStorageSafe,
            codes=args.code,
            dry_run=args.dry_run,
        ),
    )

    def human(value: RepairStorageSafeResult) -> list[str]:
        rows = [
            *((item.code, f"{item.target.kind}:{item.target.id}", item.action) for item in value.repaired),
            *((item.code, f"{item.target.kind}:{item.target.id}", item.reason) for item in value.skipped),
        ]
        lines = [f"Repaired: {len(value.repaired)}  Skipped: {len(value.skipped)}"]
        return lines + (render_table(ctx, ("CODE", "TARGET", "OUTCOME"), rows) if rows else [])

    return render(ctx, report, command="platform.repair_storage_safe", human=human)


_HELP = {"verify": "check storage integrity", "repair": "expire staging and requeue dead deliveries"}
_OPERATIONS = {"verify": "platform.verify_storage", "repair": "platform.repair_storage_safe"}
_CODES = tuple(CATALOG)


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("storage", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("verify", "repair"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb == "verify":
            command.add_argument("--level", action="append", choices=LEVELS)
            command.set_defaults(run=_verify)
        if verb == "repair":
            command.add_argument("--safe", action="store_true", required=True)
            command.add_argument("--code", action="append", choices=_CODES)
            command.add_argument("--dry-run", action="store_true")
            command.set_defaults(run=_repair)
        command.set_defaults(command_name=_OPERATIONS[verb])


GROUP = CommandGroup("storage", "verify and repair storage", register, order=89)

__all__ = ["GROUP"]
