"""Native hook client with protected enforcement; diagnostics go only to stderr."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import argparse

__all__ = ["main", "register_arguments"]

_KNOWN_FLAGS = frozenset({"--target", "--surface", "--project", "--bootstrap", "--class"})


def register_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("event_name", metavar="EVENT")
    parser.add_argument("--target", required=True)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--class", dest="hook_class", choices=("enforcement", "workflow", "observation"))


def _fast_parse(tokens: Sequence[str]) -> argparse.Namespace | None:
    event_name: str | None = None
    values: dict[str, str] = {}
    idx = 0
    total = len(tokens)
    while idx < total:
        token = tokens[idx]
        if token.startswith("-"):
            flag, eq, inline = token.partition("=")
            if flag not in _KNOWN_FLAGS or flag in values:
                return None
            if eq:
                values[flag] = inline
                idx += 1
            else:
                if idx + 1 >= total or tokens[idx + 1].startswith("-"):
                    return None
                values[flag] = tokens[idx + 1]
                idx += 2
        else:
            if event_name is not None:
                return None
            event_name = token
            idx += 1
    if (
        event_name is None
        or "--target" not in values
        or "--surface" not in values
        or "--project" not in values
    ):
        return None
    if "--class" in values and values["--class"] not in {"enforcement", "workflow", "observation"}:
        return None
    return cast(
        "argparse.Namespace",
        SimpleNamespace(
            event_name=event_name,
            target=values["--target"],
            surface=values["--surface"],
            project=values["--project"],
            bootstrap=values.get("--bootstrap"),
            hook_class=values.get("--class"),
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    tokens = sys.argv[1:] if argv is None else argv
    args = _fast_parse(tokens)
    if args is None:
        import argparse

        parser = argparse.ArgumentParser(prog="skm-hook", allow_abbrev=False)
        register_arguments(parser)
        parser.add_argument("--bootstrap")
        args = parser.parse_args(argv)
    from skm.bootstrap.hook import invoke

    return invoke(args, sys.stdin, sys.stdout, sys.stderr, os.environ, args.bootstrap)


if __name__ == "__main__":
    raise SystemExit(main())
