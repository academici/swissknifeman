"""Foreground entry point for the protected local hook daemon."""

from __future__ import annotations

import argparse
import signal
import sys
from collections.abc import Sequence

from skm.bootstrap.hookd import run_daemon

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skm-hookd", allow_abbrev=False)
    parser.add_argument("--bootstrap", help="bootstrap configuration for live policy evaluation")
    args = parser.parse_args(argv)
    stopped = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopped
        stopped = True

    previous_int = signal.signal(signal.SIGINT, stop)
    previous_term = signal.signal(signal.SIGTERM, stop)
    try:
        run_daemon(args.bootstrap, lambda: stopped)
    except (OSError, ValueError) as error:
        sys.stderr.write(f"skm-hookd: {error}\n")
        return 1
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
