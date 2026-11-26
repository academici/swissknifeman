"""Manual checks return facts without a sandbox or child process."""

from pathlib import Path
from typing import Any, Protocol, cast

from skm.modules.execution.ports import CheckRunner

from .command import CheckFacts

__all__ = ["ManualCheckRunner", "manual_check_runner"]


class ManualCheckRunner(CheckRunner, Protocol):
    """Host check gateway; use manual_check_runner()."""


class _ManualCheckRunner:
    kind = "manual"
    definition_schema_urn = "urn:skm:planning:specification:v1#/$defs/manual_definition"

    def run(self, request: Any, deps: Any) -> CheckFacts:
        deps.cancel.raise_if_cancelled()
        if not isinstance(request.definition.get("instructions_md", ""), str):
            raise ValueError("manual instructions must be text")
        return CheckFacts(None, False, None, False, Path(), Path(), (), 0)


def manual_check_runner() -> CheckRunner:
    return cast("CheckRunner", _ManualCheckRunner())
