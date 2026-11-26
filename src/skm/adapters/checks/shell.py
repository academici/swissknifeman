"""Explicitly acknowledged shell checks use the same capture/isolation/lifecycle path."""

from typing import Any, Protocol, cast, override

from skm.modules.execution.ports import CheckRunner

from .command import CheckExecutor

__all__ = ["ShellCheckRunner", "shell_check_runner"]


class ShellCheckRunner(CheckRunner, Protocol):
    """Host check gateway; use shell_check_runner()."""


class _ShellCheckRunner(CheckExecutor):
    kind = "shell"
    definition_schema_urn = "urn:skm:planning:specification:v1#/$defs/shell_definition"

    def __init__(self, *, shell_allowed: bool, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.allowed = shell_allowed

    @override
    def argv(self, request: Any) -> tuple[str, ...]:
        script = request.definition.get("script")
        if (
            not self.allowed
            or request.definition.get("risk_ack") is not True
            or not isinstance(script, str)
            or not script
        ):
            raise ValueError("shell_not_allowed: shell checks require risk_ack and checks.shell.allowed")
        return "/bin/sh", "-c", script


def shell_check_runner(*, shell_allowed: bool, **kwargs: Any) -> CheckRunner:
    return cast("CheckRunner", _ShellCheckRunner(shell_allowed=shell_allowed, **kwargs))
