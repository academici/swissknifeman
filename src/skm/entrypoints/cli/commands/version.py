"""``skm version`` (cli §6.1): package, known database schema and Python versions; needs no backend."""

import argparse
import platform
from dataclasses import dataclass

from skm import __version__
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import render

__all__ = ["GROUP", "register"]

COMMAND = "version"


@dataclass(frozen=True, slots=True)
class VersionInfo:
    package_version: str
    schema_version: int
    python_version: str


def _info() -> VersionInfo:
    # Imported here so the global ``--version`` and parser construction never load the composition root.
    from skm.bootstrap.composition import KNOWN_SCHEMA_VERSION

    return VersionInfo(__version__, KNOWN_SCHEMA_VERSION, platform.python_version())


def _summary(info: VersionInfo) -> str:
    return f"skm {info.package_version} (schema {info.schema_version:04d}, python {info.python_version})"


def _version(args: argparse.Namespace, ctx: CliContext) -> int:  # noqa: ARG001 - the group contract
    return render(ctx, _info(), human=_summary, command=COMMAND)


def register(sub: SubParsers) -> None:
    parser = sub.add_parser(COMMAND, help="print the skm, database schema and Python versions")
    parser.set_defaults(run=_version, command_name=COMMAND)
    # Like every other command, --json also works after the group; a suppressed default keeps a global one.
    parser.add_argument(
        "--json",
        default=argparse.SUPPRESS,
        action="store_true",
        help="machine-readable output (as global --json)",
    )


GROUP = CommandGroup(
    name=COMMAND,
    help="print the skm, database schema and Python versions",
    register=register,
    requires_backend=False,
    order=20,
)
