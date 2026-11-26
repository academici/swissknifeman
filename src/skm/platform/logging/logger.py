"""Operational logging only: no audit records, domain events or exception text."""

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.platform.logging.envelope import valid_name
from skm.platform.logging.setup import emit

__all__ = ["StructLogger", "get_logger"]

_ERROR_TYPES = (ValueError, TypeError, RuntimeError, OSError, TimeoutError, KeyError, AssertionError)


class StructLogger:
    def __init__(self, component: str) -> None:
        if not valid_name(component):
            raise ValueError("logging component must be a bounded dotted identifier")
        self._component = component

    def debug(self, event: str, /, **fields: object) -> None:
        emit(self._component, "debug", event, fields)

    def info(self, event: str, /, **fields: object) -> None:
        emit(self._component, "info", event, fields)

    def warning(self, event: str, /, **fields: object) -> None:
        emit(self._component, "warning", event, fields)

    def error(self, event: str, /, *, exc: BaseException | None = None, **fields: object) -> None:
        if exc is not None:
            # Messages, args, notes, traceback, locals and cause chains remain in memory.
            fields["error.type"] = "Exception"
            if type(exc) in _ERROR_TYPES:
                fields["error.type"] = type(exc).__name__
            if isinstance(exc, SkmError):
                fields["error.type"] = "SkmError"
                if type(exc.code) is ErrorCode:
                    fields["code"] = exc.code
        emit(self._component, "error", event, fields)


def get_logger(component: str) -> StructLogger:
    return StructLogger(component)
