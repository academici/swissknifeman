"""Host adapters for user schemas and operator-specified acceptance commands."""

from collections.abc import Mapping
from pathlib import Path

from skm.modules.execution.ports import GateCommandResult
from skm.platform.process.environment import build_env
from skm.platform.process.runner import run
from skm.platform.schema.user_schema import validate_user_json

__all__ = ["LocalUserSchemaValidator", "SubprocessGateRunner"]


class LocalUserSchemaValidator:
    def validate(self, payload: object, schema_path: Path) -> tuple[bool, str | None]:
        return validate_user_json(payload, schema_path)


class SubprocessGateRunner:
    def __init__(self, environ: Mapping[str, str]) -> None:
        self._env = build_env(environ)

    def run_gate(
        self, argv: tuple[str, ...], *, cwd: Path, timeout_seconds: float, max_output_bytes: int
    ) -> GateCommandResult:
        if type(argv) is not tuple:
            raise TypeError("gate command requires an argv tuple")
        try:
            result = run(
                argv,
                cwd=cwd,
                env=self._env,
                timeout_seconds=timeout_seconds,
                max_stdout_bytes=max_output_bytes,
                capture_combined_tail=True,
            )
        except (OSError, ValueError):
            return GateCommandResult(127, "could not start gate command")
        return GateCommandResult(
            result.exit_code,
            result.stdout.decode("utf-8", errors="replace"),
            result.timed_out,
            result.stdout_truncated,
        )
