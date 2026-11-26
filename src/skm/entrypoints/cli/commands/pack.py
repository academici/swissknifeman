"""Compile and verify local extension pack assets."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from skm.bootstrap.pack_compiler import compile_pack_tree
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.output import render

if TYPE_CHECKING:
    import argparse

    from skm.entrypoints.cli.context import CliContext

__all__ = ["GROUP", "register"]

_HELP = {"compile": "deduplicate pack assets and write or verify the SHA-256 lock"}


def _compile(args: argparse.Namespace, ctx: CliContext) -> int:
    result = compile_pack_tree(args.path, check=args.check)
    action = "Verified" if args.check else "Compiled"
    return render(
        ctx,
        result,
        command=args.command_name,
        human=lambda _: (
            f"{action} {result['packs']} pack(s), {result['duplicate_copies']} duplicate copies saved"
        ),
    )


def register(sub: SubParsers) -> None:
    group = sub.add_parser("pack", help="compile local extension packs")
    verbs = group.add_subparsers(dest="verb", required=True)
    for verb in ("compile",):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_compile, command_name="cli.pack.compile")
        command.add_argument(
            "--path", type=Path, default=Path("resources/packs"), help="pack or collection directory"
        )
        command.add_argument("--check", action="store_true", help="verify compilation without writing files")


GROUP = CommandGroup("pack", "compile local extension packs", register, requires_backend=False, order=79)
