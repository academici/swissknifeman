"""Named provider renderers for the P5 common profile plan.

The module receives a resolved semantic profile and emits one P2 artifact plan per
provider. It never reads project/user/fleet carriers and never translates one rendered
provider output into another.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, ProviderId, plan_artifact_render, sha256_digest)

from .profiles import ProfileResolution


def render_locale_context(locale_result) -> dict[str, object]:
    """Return provider-owned output metadata from an already resolved locale context.

    The locale resolver remains the sole owner of precedence and catalog choice; this
    adapter merely names its output boundary and never persists locale intent.
    """
    if getattr(locale_result, "surfaces", None) is None:
        raise ValueError("HARNESS_LOCALE_CONTEXT_REFUSED")
    return {"provider_boundary": "harness", "surfaces": [row.as_dict() for row in locale_result.surfaces]}


_ADAPTER_VERSION = "1.0.0"


@dataclass(frozen=True)
class ProviderAdapter:
    target_path: str
    renderer: object
    needs_binding_source: bool


def render_profile(resolution: ProfileResolution, *, codex_bindings_path: Path) -> bytes:
    """Render provider-native bytes independently after all security gates pass."""
    if not isinstance(resolution, ProfileResolution):
        raise TypeError("resolution must be ProfileResolution")
    if not resolution.green:
        raise ValueError("cannot render a refused profile")
    try:
        adapter = _ADAPTERS[resolution.provider_id]
    except KeyError as error:
        raise ValueError("HARNESS_MAPPING_MISSING") from error
    return adapter.renderer(resolution, codex_bindings_path)


def plan_profile_artifact(resolution: ProfileResolution, *, catalog_path: Path,
                          codex_bindings_path: Path):
    """Create the P2 deterministic render result used by dry-run/write/check/repair."""
    if not resolution.green:
        raise ValueError("cannot plan a refused profile")
    catalog_path, codex_bindings_path = Path(catalog_path), Path(codex_bindings_path)
    source = ArtifactSource("harness.profile.catalog", "packages/harness/configs/common/profile-catalog.json",
                            sha256_digest(catalog_path.read_bytes()))
    binding_source = ArtifactSource("harness.codex.profile-bindings",
                                    "packages/harness/configs/codex/config/profile-bindings.json",
                                    sha256_digest(codex_bindings_path.read_bytes()))
    try:
        adapter = _ADAPTERS[resolution.provider_id]
    except KeyError as error:
        raise ValueError("HARNESS_MAPPING_MISSING") from error
    sources = (source, binding_source) if adapter.needs_binding_source else (source,)
    identity = ArtifactAdapterIdentity(
        f"harness.{resolution.provider_id.value}.profile", _ADAPTER_VERSION,
        resolution.provider_id, "1.0.0", ())
    target = ArtifactTarget(adapter.target_path, ("whole-file", ()))
    parameters = {"profile_id": resolution.profile.id, "target_scope": resolution.target_scope,
                  "operation_id": resolution.operation_id or "", "target_identity": resolution.target_identity or ""}
    return plan_artifact_render(ArtifactRenderRequest(
        f"harness.{resolution.provider_id.value}.{resolution.profile.id}", sources, target,
        identity, (), parameters,
        lambda _request: render_profile(resolution, codex_bindings_path=codex_bindings_path)))


def _render_claude(resolution: ProfileResolution, _bindings_path: Path) -> bytes:
    profile_id = resolution.profile.id
    if profile_id == "observe":
        value = {"permissions": {"defaultMode": "default"}}
    elif profile_id == "workspace-contained":
        value = {"permissions": {"defaultMode": "acceptEdits"}}
    else:
        value = {"permissions": {"defaultMode": "bypassPermissions"}}
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


def _render_codex(resolution: ProfileResolution, path: Path) -> bytes:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        binding = value["codex"][resolution.profile.id]
        approval, sandbox = binding["approval_policy"], binding["sandbox_mode"]
    except (KeyError, TypeError) as error:
        raise ValueError("HARNESS_MAPPING_MISSING") from error
    if not isinstance(approval, str) or not isinstance(sandbox, str):
        raise ValueError("HARNESS_MAPPING_MISSING")
    return f'approval_policy = "{approval}"\nsandbox_mode = "{sandbox}"\n'.encode("utf-8")


_ADAPTERS = {
    ProviderId.CLAUDE_CODE: ProviderAdapter(".claude/settings.local.json", _render_claude, False),
    ProviderId.CODEX: ProviderAdapter(".codex/config.toml", _render_codex, True),
}
