"""Load cross-package provider projection policies from the packaged catalog."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from .data import config_path
from .values import ProviderId


@dataclass(frozen=True)
class InstructionProjectionPolicy:
    project_common: bool


@dataclass(frozen=True)
class CommandInvocationPolicy:
    style: str


@dataclass(frozen=True)
class ProviderProjectionSpec:
    instructions: InstructionProjectionPolicy
    command_invocation: CommandInvocationPolicy


@dataclass(frozen=True)
class ProjectionCatalog:
    providers: Mapping[str, ProviderProjectionSpec]


def _parse_provider(raw: object) -> ProviderProjectionSpec:
    if not isinstance(raw, dict):
        raise ValueError("PPROJ_PROVIDER_INVALID")
    instructions_raw = raw.get("instructions")
    command_raw = raw.get("command_invocation")
    if (not isinstance(instructions_raw, dict)
            or not isinstance(instructions_raw.get("project_common"), bool)):
        raise ValueError("PPROJ_INSTRUCTIONS_INVALID")
    if (not isinstance(command_raw, dict)
            or not isinstance(command_raw.get("style"), str)):
        raise ValueError("PPROJ_COMMAND_INVALID")
    return ProviderProjectionSpec(
        InstructionProjectionPolicy(project_common=instructions_raw["project_common"]),
        CommandInvocationPolicy(style=command_raw["style"]),
    )


def load_projection_catalog(path: Path | None = None) -> ProjectionCatalog:
    """Read ``configs/provider-projection.json`` from *path* or the packaged default."""
    if path is None:
        path = config_path("provider-projection.json")
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"PPROJ_CATALOG_UNREADABLE:{path}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0.0":
        raise ValueError("PPROJ_CATALOG_SCHEMA_INVALID")
    providers_raw = payload.get("providers")
    if not isinstance(providers_raw, dict):
        raise ValueError("PPROJ_CATALOG_PROVIDERS_INVALID")
    providers = {str(key): _parse_provider(value) for key, value in providers_raw.items()}
    return ProjectionCatalog(providers=providers)


def projection_spec(catalog: ProjectionCatalog,
                    provider_id: ProviderId) -> ProviderProjectionSpec | None:
    return catalog.providers.get(provider_id.value)


def project_common_instructions(catalog: ProjectionCatalog,
                                provider_id: ProviderId) -> bool:
    spec = projection_spec(catalog, provider_id)
    return True if spec is None else spec.instructions.project_common
