"""Immutable semantic catalog and Claude Code publication projection.

The catalog is intentionally provider-neutral: it describes canonical skills,
publication units, package version provenance and package-owned sibling entries.
The Claude renderer is a named adapter which receives that catalog plus explicit
repository roots; it never scans the filesystem or reads another provider's
manifest.
"""
from dataclasses import dataclass
import json
import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, CapabilityId, CapabilityRequirement, ProviderId,
                  SupportLevel, plan_artifact_render)


_CLAUDE_ADAPTER = ArtifactAdapterIdentity(
    "skiller.claude-publication", "1.0.0", ProviderId.CLAUDE_CODE, "1.0.0",
    (CapabilityRequirement(CapabilityId("skills.repository"),
                           (SupportLevel.NATIVE, SupportLevel.ADAPTED)),),
)

_CODEX_ADAPTER = ArtifactAdapterIdentity(
    "skiller.codex-publication", "1.0.0", ProviderId.CODEX, "1.0.0",
    (CapabilityRequirement(CapabilityId("skills.repository"),
                           (SupportLevel.NATIVE, SupportLevel.ADAPTED)),),
)


@dataclass(frozen=True)
class SemanticSkill:
    """Canonical skill identity and content provenance, never a provider path."""

    semantic_id: str
    bucket: str
    name: str
    source_path: str
    content_hash: str


@dataclass(frozen=True)
class PublicationUnit:
    """One ordered semantic publication unit from the frozen P3 contract."""

    unit_id: str
    plugin_id: str
    kind: str
    member_ids: tuple[str, ...]


@dataclass(frozen=True)
class SiblingPlugin:
    """A package-owned marketplace entry preserved outside skiller units."""

    name: str
    package: str
    description: str
    category: str
    tags: tuple[str, ...]
    source_path: str
    content_hash: str
    codex_supported: bool = False


@dataclass(frozen=True)
class PublicationCatalog:
    """Immutable package-owned input shared by independent provider renderers."""

    marketplace_name: str
    owner: tuple[tuple[str, str], ...]
    package_version: str
    skills: tuple[SemanticSkill, ...]
    units: tuple[PublicationUnit, ...]
    bucket_metadata: tuple[tuple[str, tuple[tuple[str, object], ...]], ...]
    sibling_plugins: tuple[SiblingPlugin, ...]
    generate_skill_description: str
    skm_present: bool


@dataclass(frozen=True)
class ClaudePublicationArtifact:
    """P2-backed rendered bytes and provenance for one Claude generated artifact."""

    target: Path
    publication_unit_id: str
    package_version: str
    managed_bytes: bytes
    source_hash: str
    rendered_hash: str


@dataclass(frozen=True)
class CodexPublicationArtifact:
    """P2-backed generated Codex artifact; never a canonical skill source."""

    target: Path
    publication_unit_id: str
    package_version: str
    managed_bytes: bytes
    source_hash: str
    rendered_hash: str


def build_publication_catalog(*, registry: Mapping[str, object], bucket_meta: Mapping[str, object],
                              bucket_dirs: Sequence[str], core_skills: Sequence[str],
                              core_plugin: str, package_version: str,
                              siblings: Sequence[SiblingPlugin],
                              generate_skill_description: str, skm_present: bool) -> PublicationCatalog:
    """Build a deterministic semantic catalog from explicit canonical scan results."""
    raw_skills = registry.get("skills")
    if not isinstance(raw_skills, list):
        raise ValueError("registry skills must be a list")
    skills = tuple(sorted((_skill_from_registry(item) for item in raw_skills),
                          key=lambda item: item.semantic_id))
    by_id = {skill.semantic_id: skill for skill in skills}
    if len(by_id) != len(skills):
        raise ValueError("duplicate semantic skill ID")

    metadata = tuple(sorted(
        (name, tuple((key, _freeze_value(value)) for key, value in sorted(data.items())))
        for name, data in bucket_meta.items()
        if isinstance(name, str) and isinstance(data, dict)
    ))
    units = []
    for bucket in sorted(bucket_dirs):
        members = tuple(skill.semantic_id for skill in skills if skill.bucket == bucket)
        if members:
            units.append(PublicationUnit(f"bucket:{bucket}", bucket, "bucket", members))

    for name, data in metadata:
        values = dict(data)
        if not values.get("alias_of"):
            continue
        members = tuple(f"{_bucket_for_path(path)}/{_name_for_path(path, by_id)}"
                        for path in values.get("skills", [])
                        if isinstance(path, str) and _skill_for_relative_path(path, by_id))
        if members:
            units.append(PublicationUnit(f"bucket:{name}", name, "bucket-alias", members))

    core_members = tuple(skill_id for skill_id in core_skills if skill_id in by_id)
    if core_members:
        units.append(PublicationUnit("core", core_plugin, "curated", core_members))
    units.append(PublicationUnit("generate-skill", "generate-skill", "meta", ()))
    if skm_present:
        units.append(PublicationUnit("skm", "skm", "management", ()))

    return PublicationCatalog(
        marketplace_name=_require_string(registry.get("name"), "registry name"),
        owner=(("name", "Dmitry Vostrikov"), ("email", "dv.vostrikov@gmail.com")),
        package_version=_require_semver(package_version),
        skills=skills,
        units=tuple(sorted(units, key=lambda unit: unit.unit_id)),
        bucket_metadata=metadata,
        sibling_plugins=tuple(sorted(siblings, key=lambda item: item.name)),
        generate_skill_description=generate_skill_description,
        skm_present=skm_present,
    )


def render_claude_publication(catalog: PublicationCatalog, *, repo_root: Path,
                              package_root: Path) -> tuple[ClaudePublicationArtifact, ...]:
    """Render the legacy Claude JSON bytes from a catalog and explicit roots only."""
    if not isinstance(catalog, PublicationCatalog):
        raise TypeError("catalog must be PublicationCatalog")
    repo_root = repo_root.resolve()
    package_root = package_root.resolve()
    rel_package = package_root.relative_to(repo_root).as_posix() if package_root != repo_root else ""

    def source_path(relative: str) -> str:
        return f"./{rel_package}/{relative}" if rel_package else f"./{relative}"

    by_id = {skill.semantic_id: skill for skill in catalog.skills}
    metadata = {name: dict(data) for name, data in catalog.bucket_metadata}
    artifacts = []
    marketplace_plugins = []
    for unit in catalog.units:
        if unit.kind == "bucket":
            meta = metadata[unit.plugin_id]
            skill_dirs = _claude_skill_dirs(unit, by_id)
            if not skill_dirs:
                continue
            plugin_data = {
                "name": unit.plugin_id,
                "description": meta["description"],
                "skills": skill_dirs[0] if len(skill_dirs) == 1 else skill_dirs,
            }
            artifacts.append(_render_artifact(
                package_root / "skills" / unit.plugin_id / ".claude-plugin" / "plugin.json",
                unit, plugin_data, tuple(by_id[item] for item in unit.member_ids), repo_root,
                catalog.package_version))
            marketplace_plugins.append({
                "name": unit.plugin_id,
                "source": source_path(f"skills/{unit.plugin_id}"),
                "description": meta["description"],
                "category": meta.get("category", ""),
                "tags": meta.get("tags", []),
                "package": "skiller",
            })
        elif unit.kind == "bucket-alias":
            meta = metadata[unit.plugin_id]
            paths = [source_path(by_id[item].source_path.removesuffix("/SKILL.md"))
                     for item in unit.member_ids]
            marketplace_plugins.append({
                "name": unit.plugin_id,
                "source": "./",
                "skills": paths,
                "description": meta.get("description")
                    or f"Alias: бакет перенесён в '{meta['alias_of']}'",
                "category": meta.get("category", ""),
                "tags": meta.get("tags", []),
                "package": "skiller",
                "alias_of": meta["alias_of"],
            })
        elif unit.kind == "curated":
            marketplace_plugins.append({
                "name": unit.plugin_id,
                "source": "./",
                "skills": [source_path(by_id[item].source_path.removesuffix("/SKILL.md"))
                           for item in unit.member_ids],
                "description": "Curated always-on core: token-economy skills (context-economy, "
                               "anti-drift, verify-claims, …) — lean replacement for the "
                               "general+oss-dev buckets in every project",
                "category": "meta",
                "tags": ["core", "token-economy", "always-on"],
                "package": "skiller",
            })
        elif unit.kind == "meta":
            plugin_data = {"name": "generate-skill", "description": catalog.generate_skill_description,
                           "skills": "./"}
            artifacts.append(_render_artifact(
                package_root / "generate-skill" / ".claude-plugin" / "plugin.json", unit,
                plugin_data, (), repo_root, catalog.package_version))
            marketplace_plugins.append({
                "name": "generate-skill", "source": source_path("generate-skill"),
                "description": catalog.generate_skill_description, "category": "meta",
                "tags": ["meta", "authoring"], "package": "skiller",
            })
        elif unit.kind == "management":
            marketplace_plugins.append({
                "name": "skm", "source": source_path("skm"),
                "description": "skiller CLI — управление скиллами проекта: бакеты "
                               "(connect/vendor), integrate, статус",
                "category": "meta", "tags": ["cli", "skills", "management"],
                "package": "skiller",
            })

    marketplace_plugins.extend({
        "name": sibling.name, "source": f"./{sibling.source_path}",
        "description": sibling.description, "category": sibling.category,
        "tags": list(sibling.tags), "package": sibling.package,
    } for sibling in catalog.sibling_plugins)
    marketplace_data = {
        "name": catalog.marketplace_name,
        "owner": dict(catalog.owner),
        "plugins": sorted(marketplace_plugins, key=lambda plugin: plugin["name"]),
    }
    all_sources = tuple(catalog.skills) + tuple(catalog.sibling_plugins)
    artifacts.append(_render_artifact(repo_root / ".claude-plugin" / "marketplace.json",
                                      PublicationUnit("claude-marketplace", "claude-marketplace",
                                                      "marketplace", ()), marketplace_data,
                                      all_sources, repo_root, catalog.package_version))
    return tuple(artifacts)


def render_codex_publication(catalog: PublicationCatalog, *, repo_root: Path,
                             package_root: Path) -> tuple[CodexPublicationArtifact, ...]:
    """Render native Codex plugins independently from the semantic catalog.

    Bucket plugins remain direct canonical roots.  The discontiguous core and
    management unit are explicit cache-contained bundles; only declared SKILL.md
    members are copied into those bundles.
    """
    if not isinstance(catalog, PublicationCatalog):
        raise TypeError("catalog must be PublicationCatalog")
    repo_root = repo_root.resolve()
    package_root = package_root.resolve()
    by_id = {skill.semantic_id: skill for skill in catalog.skills}
    metadata = {name: dict(data) for name, data in catalog.bucket_metadata}
    artifacts: list[CodexPublicationArtifact] = []
    plugins: list[dict[str, object]] = []

    def source_path(path: Path) -> str:
        return "./" + path.relative_to(repo_root).as_posix()

    for unit in catalog.units:
        if unit.kind == "bucket":
            meta = metadata[unit.plugin_id]
            root = package_root / "skills" / unit.plugin_id
            data = _codex_plugin_manifest(unit.plugin_id, catalog.package_version,
                                          meta["description"], ["./"])
            artifacts.append(_render_codex_artifact(
                root / ".codex-plugin" / "plugin.json", unit, data,
                tuple(by_id[item] for item in unit.member_ids), repo_root,
                catalog.package_version))
            plugins.append(_codex_marketplace_entry(unit.plugin_id, source_path(root),
                                                    meta["description"], meta))
        elif unit.kind == "meta":
            root = package_root / "generate-skill"
            data = _codex_plugin_manifest("generate-skill", catalog.package_version,
                                          catalog.generate_skill_description,
                                          ["./generate-skill"])
            artifacts.append(_render_codex_artifact(
                root / ".codex-plugin" / "plugin.json", unit, data, (), repo_root,
                catalog.package_version))
            plugins.append(_codex_marketplace_entry("generate-skill", source_path(root),
                                                    catalog.generate_skill_description,
                                                    {"category": "meta", "tags": ["meta", "authoring"]}))
        elif unit.kind == "curated":
            root = package_root / "adapters" / "codex" / "core"
            artifacts.extend(_render_codex_bundle(
                root, unit, catalog, tuple(by_id[item] for item in unit.member_ids), repo_root, package_root,
                description="Curated always-on core skills", skill_root="./skills"))
            plugins.append(_codex_marketplace_entry("core", source_path(root),
                                                    "Curated always-on core skills",
                                                    {"category": "meta", "tags": ["core", "token-economy"]}))
        elif unit.kind == "management":
            root = package_root / "adapters" / "codex" / "skm"
            artifacts.extend(_render_codex_skm_bundle(root, unit, catalog, repo_root))
            plugins.append(_codex_marketplace_entry("skm", source_path(root),
                                                    "skiller management skill adapter",
                                                    {"category": "meta", "tags": ["cli", "skills", "management"]}))

    codex_siblings = tuple(
        sibling for sibling in catalog.sibling_plugins if sibling.codex_supported)
    plugins.extend(_codex_marketplace_entry(
        sibling.name, f"./{sibling.source_path}", sibling.description,
        {"category": sibling.category, "tags": sibling.tags})
        for sibling in codex_siblings)

    marketplace = {
        "name": catalog.marketplace_name,
        "plugins": sorted(plugins, key=lambda plugin: str(plugin["name"])),
    }
    artifacts.append(_render_codex_artifact(
        repo_root / ".agents" / "plugins" / "marketplace.json",
        PublicationUnit("codex-marketplace", "codex-marketplace", "marketplace", ()),
        marketplace, tuple(catalog.skills) + codex_siblings,
        repo_root, catalog.package_version))
    return tuple(artifacts)


def _codex_plugin_manifest(name: str, version: str, description: str,
                           skills: list[str]) -> dict[str, object]:
    return {"name": name, "version": version, "description": description, "skills": skills}


def _codex_marketplace_entry(name: str, path: str, description: str,
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


def _render_codex_bundle(root: Path, unit: PublicationUnit, catalog: PublicationCatalog,
                         members: tuple[SemanticSkill, ...], repo_root: Path, package_root: Path, *,
                         description: str, skill_root: str) -> tuple[CodexPublicationArtifact, ...]:
    artifacts = [_render_codex_artifact(
        root / ".codex-plugin" / "plugin.json", unit,
        _codex_plugin_manifest(unit.plugin_id, catalog.package_version, description, [skill_root]),
        members, repo_root, catalog.package_version)]
    for member in members:
        target = root / "skills" / member.semantic_id / "SKILL.md"
        source = (package_root / member.source_path).read_bytes()
        artifacts.append(_render_codex_artifact(target, unit, source, (member,), repo_root,
                                                catalog.package_version))
    artifacts.append(_codex_bundle_lock(root, unit, catalog.package_version, tuple(artifacts), repo_root))
    return tuple(artifacts)


def _render_codex_skm_bundle(root: Path, unit: PublicationUnit, catalog: PublicationCatalog,
                             repo_root: Path) -> tuple[CodexPublicationArtifact, ...]:
    skill = ("---\nname: skm\ndescription: skiller CLI management adapter.\n---\n\n"
             "Use the repository-local skiller CLI for status, doctor, skills, and integration.\n")
    artifacts = [
        _render_codex_artifact(root / ".codex-plugin" / "plugin.json", unit,
                               _codex_plugin_manifest("skm", catalog.package_version,
                                                      "skiller management skill adapter", ["./skills"]),
                               (), repo_root, catalog.package_version),
        _render_codex_artifact(root / "skills" / "skm" / "SKILL.md", unit,
                               skill.encode("utf-8"), (), repo_root, catalog.package_version),
    ]
    artifacts.append(_codex_bundle_lock(root, unit, catalog.package_version, tuple(artifacts), repo_root))
    return tuple(artifacts)


def _codex_bundle_lock(root: Path, unit: PublicationUnit, version: str,
                       artifacts: tuple[CodexPublicationArtifact, ...],
                       repo_root: Path) -> CodexPublicationArtifact:
    records = [{"path": artifact.target.relative_to(root).as_posix(),
                "source_hash": artifact.source_hash, "rendered_hash": artifact.rendered_hash}
               for artifact in artifacts]
    return _render_codex_artifact(root / "publication-lock.json", unit,
                                  {"contract_version": "1.0.0", "publication_unit": unit.unit_id,
                                   "version": version, "artifacts": records}, (), repo_root, version)


def _render_codex_artifact(target: Path, unit: PublicationUnit, data: Mapping[str, object] | bytes,
                           sources: Sequence[SemanticSkill], repo_root: Path,
                           package_version: str) -> CodexPublicationArtifact:
    source_records = tuple(ArtifactSource(
        f"skiller.publication.source{index}", source.source_path,
        source.content_hash if source.content_hash.startswith("sha256:") else f"sha256:{source.content_hash}")
        for index, source in enumerate(sources))
    if not source_records:
        source_records = (ArtifactSource("skiller.publication.meta", "packages/skiller/package.json",
                                         "sha256:" + "0" * 64),)
    rendered = data if isinstance(data, bytes) else _manifest_text(data)
    result = plan_artifact_render(ArtifactRenderRequest(
        f"skiller.codex.{unit.plugin_id}.{target.relative_to(repo_root).as_posix().lstrip('.').replace('/', '-').replace('.', '-').lower()}", source_records,
        ArtifactTarget(target.relative_to(repo_root).as_posix(), ("whole-file", ())),
        _CODEX_ADAPTER, (), {"publication_unit": unit.unit_id,
                              "plugin_version": package_version},
        lambda _request: rendered,
    ))
    return CodexPublicationArtifact(target, unit.unit_id, package_version, result.managed_bytes,
                                    result.provenance.source_hash, result.provenance.rendered_hash)


def _render_artifact(target: Path, unit: PublicationUnit, data: Mapping[str, object],
                     sources: Sequence[SemanticSkill | SiblingPlugin],
                     repo_root: Path, package_version: str) -> ClaudePublicationArtifact:
    relative_target = target.relative_to(repo_root).as_posix()
    source_records = tuple(ArtifactSource(
        f"skiller.publication.source{index}", source.source_path,
        source.content_hash if source.content_hash.startswith("sha256:") else f"sha256:{source.content_hash}")
        for index, source in enumerate(sources))
    if not source_records:
        source_records = (ArtifactSource("skiller.publication.meta", "packages/skiller/package.json",
                                         "sha256:" + "0" * 64),)
    result = plan_artifact_render(ArtifactRenderRequest(
        f"skiller.claude.{unit.plugin_id}", source_records,
        ArtifactTarget(relative_target, ("whole-file", ())), _CLAUDE_ADAPTER, (),
        {"publication_unit": unit.unit_id, "plugin_version": package_version},
        lambda _request: _manifest_text(data),
    ))
    return ClaudePublicationArtifact(target, unit.unit_id, package_version, result.managed_bytes,
                                     result.provenance.source_hash, result.provenance.rendered_hash)


def _manifest_text(data: Mapping[str, object]) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _claude_skill_dirs(unit: PublicationUnit, by_id: Mapping[str, SemanticSkill]) -> list[str]:
    dirs = set()
    for item in unit.member_ids:
        skill = by_id[item]
        relative = Path(skill.source_path).parent.parent.relative_to("skills" / Path(skill.bucket))
        dirs.add("./" if str(relative) == "." else f"./{relative.as_posix()}")
    return sorted(dirs)


def _skill_from_registry(value: object) -> SemanticSkill:
    if not isinstance(value, Mapping):
        raise ValueError("registry skill must be an object")
    bucket = _require_string(value.get("bucket"), "skill bucket")
    name = _require_string(value.get("name"), "skill name")
    path = _require_string(value.get("path"), "skill path")
    content_hash = _require_string(value.get("content_sha256") or value.get("sha256"), "skill hash")
    return SemanticSkill(f"{bucket}/{name}", bucket, name, path, content_hash)


def _skill_for_relative_path(path: str, by_id: Mapping[str, SemanticSkill]) -> SemanticSkill | None:
    return next((skill for skill in by_id.values()
                 if skill.source_path == f"skills/{path}/SKILL.md"), None)


def _bucket_for_path(path: str) -> str:
    return path.partition("/")[0]


def _name_for_path(path: str, by_id: Mapping[str, SemanticSkill]) -> str:
    skill = _skill_for_relative_path(path, by_id)
    return skill.name if skill else ""


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_semver(value: str) -> str:
    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("package version must be SemVer")
    return value


def _freeze_value(value: object) -> object:
    """Capture JSON-like catalog metadata without retaining mutable caller values."""
    if isinstance(value, dict):
        return tuple((key, _freeze_value(item)) for key, item in sorted(value.items()))
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value


# P3.4 distribution plans live beside the P3-owned semantic publication seam.
# They intentionally consume package config only through the P1 adapter and do
# not scan a provider manifest or execute a native installer during planning.
@dataclass(frozen=True)
class ProviderDistributionPlan:
    provider_id: str
    channel: str
    target: Path
    target_identity: str
    source_hash: str
    rendered_hash: str


def selected_distribution_providers(config, *, project_id: str) -> tuple[str, ...]:
    from .common import die
    from .config import resolve_distribution_providers
    resolved = resolve_distribution_providers(config, project_id=project_id)
    if resolved.effective is None:
        diagnostics = ", ".join(item.code for item in resolved.diagnostics)
        die(f"provider distribution blocked: {diagnostics or 'PCFG_SCHEMA_INVALID'}")
    return tuple(item.provider_id.value for item in resolved.effective if item.enabled)


def build_vendor_distribution_plan(config, target: Path, *, project_id: str,
                                   claude_path: str, codex_path: str) -> tuple[ProviderDistributionPlan, ...]:
    from .common import die
    paths = {"claude-code": claude_path, "codex": codex_path}
    plans = tuple(ProviderDistributionPlan(provider, "vendor", target / paths[provider],
                                           (target / paths[provider]).as_posix(), "", "")
                  for provider in selected_distribution_providers(config, project_id=project_id))
    seen = set()
    for plan in plans:
        resolved = plan.target.resolve(strict=False)
        if resolved in seen:
            die("SPUB_OWNERSHIP_CONFLICT: selected providers share one managed vendor path")
        seen.add(resolved)
    return plans


def build_connect_distribution_plan(config, target: Path, *, project_id: str,
                                    repo_root: Path) -> tuple[ProviderDistributionPlan, ...]:
    from .common import die
    plans = []
    for provider in selected_distribution_providers(config, project_id=project_id):
        if provider == "claude-code":
            plans.append(ProviderDistributionPlan(provider, "marketplace", target / ".claude",
                                                   ".claude", "", ""))
        elif provider == "codex":
            if target.resolve() != repo_root.resolve():
                die("SPUB_PATH_UNCONTAINED: Codex marketplace thin adapter is self-host only; use skiller sync for a vendor consumer")
            marketplace = repo_root / ".agents" / "plugins" / "marketplace.json"
            if not marketplace.is_file():
                die("SPUB_BUNDLE_INCOMPLETE: generated Codex marketplace is missing; run skiller registry")
            plans.append(ProviderDistributionPlan(provider, "marketplace", marketplace,
                                                   marketplace.as_posix(), "", ""))
        else:
            die(f"SPUB_CAPABILITY_UNSUPPORTED: provider {provider}")
    return tuple(plans)


def run_codex_native_install(*, repo_root: Path, plugin: str, dry_run: bool,
                             runner=subprocess.run, executable: str = "codex") -> tuple[bool, str]:
    """The explicit native global transaction; dry-run never probes or runs it."""
    from .common import MARKETPLACE
    if dry_run:
        return True, "SPUB_INSTALL_EXPLICIT_REQUIRED: dry-run; native installer was not invoked"
    if shutil.which(executable) is None:
        return False, "SPUB_INSTALL_UNAVAILABLE: codex executable not found"
    commands = (
        [executable, "plugin", "marketplace", "add", str(repo_root)],
        [executable, "plugin", "add", f"{plugin}@{MARKETPLACE}"],
    )
    for command in commands:
        try:
            result = runner(command, check=False, capture_output=True, text=True)
        except OSError as exc:
            return False, f"SPUB_INSTALL_UNAVAILABLE: {exc}"
        if getattr(result, "returncode", 1) != 0:
            detail = (getattr(result, "stderr", "") or getattr(result, "stdout", "")).strip()
            return False, f"SPUB_INSTALL_UNAVAILABLE: {' '.join(command[:3])} failed: {detail}"
    return True, f"codex/native-install: marketplace={repo_root}, plugin={plugin}@{MARKETPLACE}"
