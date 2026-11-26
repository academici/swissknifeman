"""CLI error boundary (cli §1.1, §4): the one place that turns an exception into a message and an exit code.

``SkmError`` -> its category's exit from ``output.CLI_EXIT`` (the catalog's ``cli_exit``); Ctrl-C -> 130;
anything else -> ``INTERNAL_ERROR`` (70) with the request id, and the traceback only at ``-vv`` with secrets
masked and every character escaped like any other untrusted text.
"""

import signal
import sys
import threading
import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager
from types import FrameType

from skm.entrypoints.cli.context import CliContext, CliOptions, CliSession
from skm.entrypoints.cli.output import render_error
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, SkmError
from skm.kernel.json_types import JsonValue
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

__all__ = [
    "EXIT_INTERRUPTED",
    "EXIT_OK",
    "EXIT_TERMINATED",
    "EXIT_USAGE",
    "TRACEBACK_VERBOSITY",
    "Terminated",
    "run_guarded",
    "sigterm_unwinds",
]

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130
EXIT_TERMINATED = 143
TRACEBACK_VERBOSITY = 2


class Terminated(KeyboardInterrupt):
    """``SIGTERM`` delivered as an interrupt, so the ``except BaseException`` cleanups run as for Ctrl-C."""


def _raise_terminated(_signum: int, _frame: FrameType | None) -> None:
    raise Terminated


@contextmanager
def sigterm_unwinds() -> Generator[None]:
    """Turn ``SIGTERM`` into :class:`Terminated` while a command runs, unless something already handles it.

    The default action ends the interpreter without unwinding, which skipped the cleanup of ``backup create``
    and ``restore``. A handler installed earlier (a service, the worker) and a non-main thread are left alone.
    """
    if (
        threading.current_thread() is not threading.main_thread()
        or signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL
    ):
        yield
        return
    signal.signal(signal.SIGTERM, _raise_terminated)
    try:
        yield
    finally:
        if signal.getsignal(signal.SIGTERM) is _raise_terminated:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)


_TRACEBACK_HINT = "rerun with -vv to print the traceback"


def _internal(ctx: CliContext, cause: BaseException) -> tuple[SkmError, list[str]]:
    message = f"unexpected failure (request {ctx.request_id}); see logs"
    if ctx.verbosity < TRACEBACK_VERBOSITY:
        # The logs carry only the error type; the traceback is the one place the cause shows, and only
        # the human output prints it.
        details: dict[str, JsonValue] = {} if ctx.json else {"hint": _TRACEBACK_HINT}
        return InternalError(ErrorCode.INTERNAL_ERROR, message, details=details), []
    error = InternalError(ErrorCode.INTERNAL_ERROR, message)
    lines = "".join(traceback.format_exception(type(cause), cause, cause.__traceback__)).splitlines()
    return error, lines


def _bare() -> CliContext:
    """Context for a failure before the invocation has one: defaults, human output on the process streams."""
    ids = Uuid7Generator(SystemClock())
    return CliSession(
        options=CliOptions(),
        stdout=sys.stdout,
        stderr=sys.stderr,
        redactor=Redactor(),
        ids=ids,
        request_id="cli-" + str(ids.new_id()),
    )


def run_guarded(fn: Callable[[], int], ctx: CliContext | None, command: str) -> int:
    """Run ``fn`` and return its exit code, mapping every failure; never lets an exception escape."""
    try:
        return fn()
    except Terminated:
        return EXIT_TERMINATED
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except SkmError as error:
        return render_error(ctx or _bare(), error, command=command)
    except Exception as exc:  # noqa: BLE001 - the boundary: anything unexpected is INTERNAL_ERROR
        shown = ctx or _bare()
        error, extra = _internal(shown, exc)
        return render_error(shown, error, command=command, extra=extra)
