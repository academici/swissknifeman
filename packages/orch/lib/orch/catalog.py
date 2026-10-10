"""Launch catalog plus the model catalog: which command starts a role and which model a class means on a provider.

The launch catalog is orch's own file (``configs/launch-catalog.json``). Models come from the ``model-catalog/v1``
file of aicore (``--model-catalog FILE`` selects another one); orch never keeps a copy of model names (I8).
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from aicore.provider import models

from orch import launch

CLASS_RANK = {"economy": 0, "implementation": 1, "frontier": 2}


class CatalogError(ValueError):
    """``MODEL_CATALOG_UNAVAILABLE`` for an unreadable or invalid model catalog, ``CATALOG_UNKNOWN`` for a missing entry."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def substitute(argv: list[str], values: Mapping[str, str]) -> list[str]:
    """Replace ``{model}``, ``{effort}`` and ``{cwd}``; a placeholder without a value is an error."""
    def fill(match):
        if match[1] not in values:
            raise launch.LaunchError("LAUNCH_INVALID", f"no value for placeholder {{{match[1]}}}")
        return values[match[1]]
    return [launch._PLACEHOLDER_RE.sub(fill, arg) for arg in argv]


class Catalog:
    def __init__(self, model_catalog: models.ModelCatalog, launch_catalog: dict | None = None):
        self.models = model_catalog
        self.launch = launch_catalog if launch_catalog is not None else launch.load_catalog()

    @classmethod
    def load(cls, model_catalog_path: str | Path | None = None) -> "Catalog":
        """The aicore model catalog (``None`` reads the packaged one) and the launch catalog."""
        try:
            return cls(models.load_model_catalog(None if model_catalog_path is None else Path(model_catalog_path)))
        except models.ModelCatalogError as error:
            raise CatalogError("MODEL_CATALOG_UNAVAILABLE", str(error)) from error

    def launch_entry(self, role: str, provider: str) -> dict:
        return launch.entry(self.launch, role, provider)

    def _selected(self, provider: str, table: str, key: str, select) -> str:
        found = select(self.models, provider, key)
        if found is None:
            raise CatalogError("CATALOG_UNKNOWN", f"model catalog has no {table} entry for {key!r} of provider {provider!r}")
        return found

    def resolve_model(self, provider: str, model_class: str) -> str:
        """First model of the class on the provider (I8: no model names live in orch)."""
        return self._selected(provider, "class_selectors", model_class, models.select_model)

    def resolve_effort(self, provider: str, effort: str) -> str:
        return self._selected(provider, "effort_selectors", effort, models.select_effort)
