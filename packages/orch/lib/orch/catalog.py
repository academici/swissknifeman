"""Launch catalog plus the model catalog: which command starts a role and which model a class means on a provider.

The launch catalog is orch's own file (``configs/launch-catalog.json``). Models come from the ``model-catalog/v1``
file of aicore (``--model-catalog FILE`` selects another one); orch never keeps a copy of model names (I8).
"""
from __future__ import annotations

from collections.abc import Mapping
import json
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
    """Replace ``{model}``, ``{effort}``, ``{cwd}`` and ``{orch}``; a placeholder without a value is an error."""
    def fill(match):
        if match[1] not in values:
            raise launch.LaunchError("LAUNCH_INVALID", f"no value for placeholder {{{match[1]}}}")
        return values[match[1]]
    return [launch._PLACEHOLDER_RE.sub(fill, arg) for arg in argv]


class Catalog:
    def __init__(self, model_catalog: models.ModelCatalog, launch_catalog: dict | None = None,
                 model_doc: dict | None = None):
        self.models = model_catalog
        self.launch = launch_catalog if launch_catalog is not None else launch.load_catalog()
        self._model_doc = model_doc

    @classmethod
    def load(cls, model_catalog_path: str | Path | None = None) -> "Catalog":
        """The aicore model catalog (``None`` reads the packaged one) and the launch catalog."""
        path = models.default_model_catalog_path() if model_catalog_path is None else Path(model_catalog_path)
        try:
            found = models.load_model_catalog(path)
            doc = json.loads(path.read_text(encoding="utf-8"))
        except models.ModelCatalogError as error:
            raise CatalogError("MODEL_CATALOG_UNAVAILABLE", str(error)) from error
        except (OSError, ValueError) as error:  # the file went away between validation and the second read
            raise CatalogError("MODEL_CATALOG_UNAVAILABLE", f"{path.name}: {error}") from error
        return cls(found, model_doc=doc)

    def model_document(self) -> dict:
        """The model catalog as JSON data: the file it was loaded from, else rebuilt from the parsed catalog."""
        if self._model_doc is not None:
            return self._model_doc
        return {"schema_version": "model-catalog/v1", "catalog_version": self.models.catalog_version,
                "providers": [{"provider_id": item.provider_id, "class_selectors": item.class_selectors,
                               "effort_selectors": item.effort_selectors, "model_inventory": item.inventory_dict()}
                              for item in self.models.providers]}

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
