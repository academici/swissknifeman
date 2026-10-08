"""Model catalog of the providers (the ``model-catalog/v1`` contract).

The canonical data is ``configs/model-catalog.json``. A model class (economy, implementation, frontier) and
an effort level map to a list of selectors in preference order; the first one is the default.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional

from ..util import schema
from .data import config_path

CATALOG_FILE = "model-catalog.json"
_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas" / "model-catalog" / "v1"


class ModelCatalogError(ValueError):
    """The catalog file is unreadable or does not satisfy ``model-catalog/v1``."""

    def __init__(self, path: str, code: str, message: str):
        super().__init__(f"model catalog invalid: {path or '/'}: {code}: {message}")
        self.path = path
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProviderModels:
    provider_id: str
    class_selectors: Mapping[str, tuple]
    effort_selectors: Mapping[str, tuple]
    model_inventory: Mapping[str, object]  # deeply read-only; ``inventory_dict`` returns a plain copy

    def inventory_dict(self) -> dict:
        return _thaw(self.model_inventory)


@dataclass(frozen=True)
class ModelCatalog:
    catalog_version: str
    providers: tuple

    def provider(self, provider_id: str) -> Optional[ProviderModels]:
        for item in self.providers:
            if item.provider_id == provider_id:
                return item
        return None


def default_model_catalog_path() -> Path:
    return config_path(CATALOG_FILE)


def load_model_catalog(path: Optional[Path] = None) -> ModelCatalog:
    """Read and validate a catalog; ``None`` reads the packaged one."""
    target = default_model_catalog_path() if path is None else Path(path)
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelCatalogError("", "unreadable", f"{target.name}: {exc}") from exc
    try:
        registry, kind = schema.load_contract(_SCHEMA_DIR)
    except schema.SchemaProfileError as exc:
        raise ModelCatalogError("", "schema", str(exc)) from exc
    issues = schema.validate(doc, kind, registry)
    if issues:
        first = issues[0]
        raise ModelCatalogError(first.path, first.code, first.message)
    providers = []
    for record in doc["providers"]:
        providers.append(ProviderModels(
            provider_id=record["provider_id"],
            class_selectors=_freeze(record["class_selectors"]),
            effort_selectors=_freeze(record["effort_selectors"]),
            model_inventory=_freeze(record["model_inventory"])))
    ids = [item.provider_id for item in providers]
    if len(set(ids)) != len(ids):
        raise ModelCatalogError("/providers", "unique", "provider ids must be unique")
    return ModelCatalog(doc["catalog_version"], tuple(providers))


def select_model(catalog: ModelCatalog, provider_id: str, model_class: str) -> Optional[str]:
    """The preferred model of a class, or ``None`` for an unknown provider or class."""
    return _first(catalog, provider_id, "class_selectors", model_class)


def select_effort(catalog: ModelCatalog, provider_id: str, effort: str) -> Optional[str]:
    """The provider's value for an effort level, or ``None`` for an unknown provider or level."""
    return _first(catalog, provider_id, "effort_selectors", effort)


def inventory(catalog: ModelCatalog, provider_id: str) -> Optional[dict]:
    """A plain copy of the provider's model inventory, or ``None`` for an unknown provider."""
    item = catalog.provider(provider_id)
    return None if item is None else item.inventory_dict()


def _first(catalog: ModelCatalog, provider_id: str, field: str, key: str) -> Optional[str]:
    item = catalog.provider(provider_id)
    selectors = None if item is None else getattr(item, field).get(key)
    return selectors[0] if selectors else None


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
