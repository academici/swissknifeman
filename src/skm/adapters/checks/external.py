"""External checks require an installed provider; no guessed subprocess fallback."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast

from skm.modules.execution.ports import CheckRunner

from .command import CheckFacts

__all__ = ["ExternalCheckRunner", "external_check_runner"]


class ExternalCheckRunner(CheckRunner, Protocol):
    """External provider gateway; use external_check_runner()."""


class _ExternalCheckRunner:
    kind = "external"
    definition_schema_urn = "urn:skm:planning:specification:v1#/$defs/external_definition"

    def __init__(self, providers: Mapping[str, CheckRunner]) -> None:
        self.providers = dict(providers)

    def run(self, request: Any, deps: Any) -> Any:
        deps.cancel.raise_if_cancelled()
        provider = request.definition.get("provider")
        if isinstance(provider, str) and provider in self.providers:
            return self.providers[provider].run(request, deps)
        return CheckFacts(None, False, "CAPABILITY_UNAVAILABLE", False, Path(), Path(), (), 0)


def external_check_runner(providers: Mapping[str, CheckRunner] | None = None) -> CheckRunner:
    return cast("CheckRunner", _ExternalCheckRunner(providers or {}))
