"""Publication primitives: whole-file artifacts, manifests, Codex plugin files, locks.

The mechanics every publisher shares (the skill library, the command projection, later the hub):
serialising a manifest, building one whole-file artifact request, the Codex ``plugin.json`` and
marketplace entry, the publication lock record and the runtime-file walk of one skill tree. What
stays with the caller is policy: artifact ids, adapter identities, provenance parameters, the key
order of the serialisation and the kinds of publication units.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Mapping, Sequence

from ..artifacts.artifact import (ArtifactAdapterIdentity, ArtifactRenderRequest,
                                  ArtifactRenderResult, ArtifactSource, ArtifactTarget,
                                  plan_artifact_render)
from ..provider.distribution import load_distribution_catalog
from ..provider.manifest import (default_manifest_path, load_provider_manifest,
                                 provider_config_catalog)
from ..provider.registry import AdapterCatalog, AdapterDescriptor
from ..provider.values import (CapabilityId, CapabilityRequirement, EffectiveProvider,
                               ProviderId, SupportLevel)
from ..util.term import die
from .skill import SKILL_IGNORE


def package_rel(repo_root: Path, package_root: Path) -> str:
    """Package prefix relative to its host root, empty for standalone layouts."""
    relative = package_root.relative_to(repo_root).as_posix()
    return "" if relative == "." else relative


def manifest_bytes(data: Mapping[str, object], *, sort_keys: bool = False) -> bytes:
    """Serialise a JSON manifest: two-space indent, UTF-8 kept, trailing newline.

    Keys keep their insertion order unless the caller asks for ``sort_keys``.
    """
    return (json.dumps(data, indent=2, ensure_ascii=False, sort_keys=sort_keys)
            + "\n").encode("utf-8")


_DISTRIBUTION_CATALOG = None


def distribution_catalog():
    """The provider distribution catalog, loaded once per process."""
    global _DISTRIBUTION_CATALOG
    if _DISTRIBUTION_CATALOG is None:
        _DISTRIBUTION_CATALOG = load_distribution_catalog()
    return _DISTRIBUTION_CATALOG


# The publication gate asks one question of the manifest: does this provider support the
# repository-skills capability at an accepted level. The identity below carries only that question;
# the identities that appear in generated provenance stay with the publishers.
_GATE_REQUIREMENTS = (CapabilityRequirement(CapabilityId("skills.repository"),
                                            (SupportLevel.NATIVE, SupportLevel.ADAPTED)),)


def validate_publication_capabilities(provider_id: ProviderId, *, manifest_path=None):
    """Fail closed against the root manifest before publication bytes are rendered."""
    manifest_path = Path(manifest_path) if manifest_path is not None else (
        default_manifest_path())
    manifest = load_provider_manifest(manifest_path)
    identity = ArtifactAdapterIdentity(
        "aicore.publication-gate", "1.0.0", provider_id, "1.0.0", _GATE_REQUIREMENTS)
    gate = AdapterCatalog((AdapterDescriptor(
        "skills.publication", identity, lambda _request: b""),)).select(
            provider_id=provider_id, artifact_kind="skills.publication",
            capability_catalog=provider_config_catalog(manifest),
            effective_provider=EffectiveProvider(provider_id, True))
    if gate.selection is None:
        raise ValueError(",".join(item.code for item in gate.diagnostics))
    return manifest


def render_whole_file(*, artifact_id: str, target: str, sources: tuple[ArtifactSource, ...],
                      adapter: ArtifactAdapterIdentity, parameters: Mapping[str, object],
                      rendered: bytes) -> ArtifactRenderResult:
    """Plan one whole-file artifact: ``target`` is a relative POSIX path, no override layers."""
    return plan_artifact_render(ArtifactRenderRequest(
        artifact_id, sources, ArtifactTarget(target, ("whole-file", ())), adapter, (),
        dict(parameters), lambda _request: rendered))


def capability_requirements(capabilities: Sequence[str]) -> tuple[CapabilityRequirement, ...]:
    """One requirement per distinct capability id, sorted, accepting adapted and native support."""
    return tuple(CapabilityRequirement(CapabilityId(item),
                                       (SupportLevel.ADAPTED, SupportLevel.NATIVE))
                 for item in sorted(set(capabilities)))


def codex_plugin_manifest(name: str, version: str, description: str,
                          skills: list[str]) -> dict[str, object]:
    return {"name": name, "version": version, "description": description, "skills": skills}


def codex_marketplace_entry(name: str, path: str, description: str,
                            metadata: Mapping[str, object]) -> dict[str, object]:
    if not path.startswith("./") or ".." in Path(path).parts:
        raise ValueError("Codex marketplace source path must be contained and ./-prefixed")
    return {
        "name": name,
        "source": path,
        "description": description,
        "category": metadata.get("category", ""),
        "tags": list(metadata.get("tags", [])),
        "install_policy": "explicit",
        "auth": "none",
    }


def publication_lock(unit_id: str, version: str,
                     records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """The lock document of one publication unit; the records are kept as the caller built them."""
    return {"contract_version": "1.0.0", "publication_unit": unit_id,
            "version": version, "artifacts": list(records)}


def skill_runtime_files(skill_root: Path, *, source_root: Path,
                        plugin: str) -> tuple[Path, ...]:
    """Enumerate one consumer skill tree with the canonical vendor exclusions."""
    ignore = shutil.ignore_patterns(*SKILL_IGNORE)
    pending = [skill_root]
    seen_dirs = set()
    files = []
    while pending:
        directory = pending.pop()
        resolved_dir = contained(
            source_root, directory, plugin=plugin, label="runtime support directory")
        if resolved_dir in seen_dirs:
            continue
        seen_dirs.add(resolved_dir)
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            die(f"SPUB_BUNDLE_INCOMPLETE: provider codex, unit {plugin}, "
                f"target {directory}: cannot read runtime support files: {exc}")
        excluded = ignore(str(directory), [entry.name for entry in entries])
        for entry in entries:
            if entry.name in excluded:
                continue
            resolved = contained(
                source_root, entry, plugin=plugin, label="runtime support file")
            if resolved.is_dir():
                pending.append(entry)
            elif resolved.is_file():
                files.append(entry)
    return tuple(files)


def contained(root: Path, candidate: Path, *, plugin: str, label: str) -> Path:
    root = root.resolve()
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        die(f"SPUB_PATH_UNCONTAINED: provider codex, unit {plugin}, "
            f"{label} {candidate} escapes {root}")
    return resolved
