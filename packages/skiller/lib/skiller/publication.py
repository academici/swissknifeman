"""Immutable semantic catalog and Claude Code publication projection.

The catalog is intentionally provider-neutral: it describes canonical skills,
publication units, package version provenance and package-owned sibling entries.
The Claude renderer is a named adapter which receives that catalog plus explicit
repository roots; it never scans the filesystem or reads another provider's
manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from aicore.artifacts.artifact import (
    ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactRenderResult, ArtifactSource,
    ArtifactTarget, plan_artifact_render)
from aicore.provider.values import CapabilityId, CapabilityRequirement, ProviderId, SupportLevel

# Publication primitives live in aicore.content.publication; the distribution plans in aicore.delivery.
from aicore.content.publication import (
    codex_plugin_manifest as _codex_plugin_manifest, manifest_bytes as _manifest_text,
    package_rel, publication_lock, render_whole_file,
    skill_runtime_files as _codex_skill_runtime_files, validate_publication_capabilities)
from aicore.delivery.distribution import (
    DistributionIdentity, ProviderDistributionPlan, connect_distribution_plan,
    distribution_artifact, vendor_distribution_plan)


# skiller's own plugin-catalog/v1 file, declared in its unit.json and read by aicore.content.marketplace.
PLUGIN_CATALOG_PATH = ".claude-plugin/catalog.json"
PLUGIN_CATALOG_SCHEMA = "urn:swissknifeman:aicore:plugin-catalog:v1"


def _generator(package_prefix: str) -> str:
    prefix = f"{package_prefix}/" if package_prefix else ""
    return f"generator: {prefix}lib/skiller/registry.py→{prefix}lib/skiller/publication.py"


_CLAUDE_ADAPTER = ArtifactAdapterIdentity(
    "skiller.claude-publication", "1.0.0", ProviderId.CLAUDE_CODE, "1.0.0",
    (CapabilityRequirement(CapabilityId("skills.repository"),
                           (SupportLevel.NATIVE, SupportLevel.ADAPTED)),),
)

_CODEX_ADAPTER = ArtifactAdapterIdentity(
    "skiller.codex-publication", "1.0.1", ProviderId.CODEX, "1.0.0",
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
    # D27: the version embedded into this unit's OWN rendered manifest ("version" field of a
    # Codex plugin.json / bundle lock) — separate from `PublicationCatalog.package_version`
    # (the skiller package API SemVer, stamped uniformly onto every artifact's provenance).
    # Defaults to "" for units built without an explicit per-unit version (kept backward
    # compatible with direct catalog construction that predates the version map).
    content_version: str = ""


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
                              generate_skill_description: str,
                              unit_versions: Mapping[str, str] | None = None,
                              default_unit_version: str | None = None) -> PublicationCatalog:
    """Build a deterministic semantic catalog from explicit canonical scan results.

    `unit_versions`/`default_unit_version` implement D27's per-unit version map
    (`configs/publication-versions.json`): a unit's `content_version` (embedded into its OWN
    rendered manifest) is `unit_versions.get(plugin_id, default_unit_version)`. Omitting both
    (direct-catalog callers predating the map) keeps every unit's `content_version` equal to
    `package_version`, the pre-D27 behavior — byte-compatible with callers that never learned
    about the map.
    """
    raw_skills = registry.get("skills")
    if not isinstance(raw_skills, list):
        raise ValueError("registry skills must be a list")
    raw_skills = [item for item in raw_skills if not (isinstance(item, dict) and item.get("quarantined"))]
    skills = tuple(sorted((_skill_from_registry(item) for item in raw_skills),
                          key=lambda item: item.semantic_id))
    by_id = {skill.semantic_id: skill for skill in skills}
    if len(by_id) != len(skills):
        raise ValueError("duplicate semantic skill ID")

    def unit_version(plugin_id: str) -> str:
        if unit_versions is None:
            return package_version
        return unit_versions.get(plugin_id, default_unit_version
                                 if default_unit_version is not None else package_version)

    metadata = tuple(sorted(
        (name, tuple((key, _freeze_value(value)) for key, value in sorted(data.items())))
        for name, data in bucket_meta.items()
        if isinstance(name, str) and isinstance(data, dict)
    ))
    metadata_by_name = {name: dict(data) for name, data in metadata}
    units = []
    for bucket in sorted(bucket_dirs):
        # a private/source-only bucket (repository-bootstrap) is indexed above for
        # ownership/hash lookup (`skills` tuple already includes its members) but never becomes
        # an ordinary publication unit — excluded here, before any Claude/Codex/marketplace
        # renderer ever sees it as a `PublicationUnit`.
        if metadata_by_name.get(bucket, {}).get("private_source_only"):
            continue
        members = tuple(skill.semantic_id for skill in skills if skill.bucket == bucket)
        if members:
            units.append(PublicationUnit(f"bucket:{bucket}", bucket, "bucket", members,
                                         content_version=unit_version(bucket)))

    for name, data in metadata:
        values = dict(data)
        if not values.get("alias_of"):
            continue
        members = tuple(f"{_bucket_for_path(path)}/{_name_for_path(path, by_id)}"
                        for path in values.get("skills", [])
                        if isinstance(path, str) and _skill_for_relative_path(path, by_id))
        if members:
            units.append(PublicationUnit(f"bucket:{name}", name, "bucket-alias", members,
                                         content_version=unit_version(name)))

    core_members = tuple(skill_id for skill_id in core_skills if skill_id in by_id)
    if core_members:
        units.append(PublicationUnit("core", core_plugin, "curated", core_members,
                                     content_version=unit_version(core_plugin)))
    units.append(PublicationUnit("generate-skill", "generate-skill", "meta", (),
                                 content_version=unit_version("generate-skill")))

    return PublicationCatalog(
        marketplace_name=_require_string(registry.get("name"), "registry name"),
        owner=(("name", "Dmitry Vostrikov"), ("email", "dv.vostrikov@gmail.com")),
        package_version=_require_semver(package_version),
        skills=skills,
        units=tuple(sorted(units, key=lambda unit: unit.unit_id)),
        bucket_metadata=metadata,
        sibling_plugins=tuple(sorted(siblings, key=lambda item: item.name)),
        generate_skill_description=generate_skill_description,
    )


def render_claude_publication(catalog: PublicationCatalog, *, repo_root: Path,
                              package_root: Path, manifest_path=None) -> tuple[ClaudePublicationArtifact, ...]:
    """Render the legacy Claude JSON bytes from a catalog and explicit roots only."""
    validate_publication_capabilities(ProviderId.CLAUDE_CODE, manifest_path=manifest_path)
    if not isinstance(catalog, PublicationCatalog):
        raise TypeError("catalog must be PublicationCatalog")
    repo_root = repo_root.resolve()
    package_root = package_root.resolve()
    by_id = {skill.semantic_id: skill for skill in catalog.skills}
    metadata = {name: dict(data) for name, data in catalog.bucket_metadata}
    artifacts = []
    plugins = []
    # The root Claude marketplace and the Codex index are assembled from the unit.json of the
    # modules (aicore.content.marketplace); skiller states its own plugins in a plugin-catalog/v1
    # file: every path is relative to the package.
    codex_policy = {"install_policy": "explicit", "auth": "none"}
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
                catalog.package_version, package_root=package_root))
            plugins.append({
                "name": unit.plugin_id,
                "source": f"skills/{unit.plugin_id}",
                "description": meta["description"],
                "category": meta.get("category", ""),
                "tags": list(meta.get("tags", [])),
                "codex": dict(codex_policy),
            })
        elif unit.kind == "bucket-alias":
            meta = metadata[unit.plugin_id]
            paths = [by_id[item].source_path.removesuffix("/SKILL.md")
                     for item in unit.member_ids]
            plugins.append({
                "name": unit.plugin_id,
                "source": "./",
                "skills": paths,
                "description": meta.get("description")
                    or f"Alias: bucket moved to '{meta['alias_of']}'",
                "category": meta.get("category", ""),
                "tags": list(meta.get("tags", [])),
                "alias_of": meta["alias_of"],
            })
        elif unit.kind == "curated":
            plugins.append({
                "name": unit.plugin_id,
                "source": "./",
                "skills": [by_id[item].source_path.removesuffix("/SKILL.md")
                           for item in unit.member_ids],
                "description": "Curated always-on core: token-economy skills (context-economy, "
                               "anti-drift, verify-claims, …) — lean replacement for the "
                               "general+oss-dev buckets in every project",
                "category": "meta",
                "tags": ["core", "token-economy", "always-on"],
                "codex": {"source": "adapters/codex/core",
                          "description": "Curated always-on core skills",
                          "category": "meta", "tags": ["core", "token-economy"], **codex_policy},
            })
        elif unit.kind == "meta":
            plugin_data = {"name": "generate-skill", "description": catalog.generate_skill_description,
                           "skills": "./"}
            artifacts.append(_render_artifact(
                package_root / "generate-skill" / ".claude-plugin" / "plugin.json", unit,
                plugin_data, (), repo_root, catalog.package_version, package_root=package_root))
            plugins.append({
                "name": "generate-skill", "source": "generate-skill",
                "description": catalog.generate_skill_description, "category": "meta",
                "tags": ["meta", "authoring"], "codex": dict(codex_policy),
            })

    catalog_data = {
        "schema": PLUGIN_CATALOG_SCHEMA,
        "marketplace": {"name": catalog.marketplace_name, "owner": dict(catalog.owner)},
        "plugins": sorted(plugins, key=lambda plugin: plugin["name"]),
    }
    artifacts.append(_render_artifact(package_root / PLUGIN_CATALOG_PATH,
                                      PublicationUnit("plugin-catalog", "plugin-catalog",
                                                      "catalog", ()), catalog_data,
                                      tuple(catalog.skills), repo_root, catalog.package_version,
                                      package_root=package_root))
    return tuple(artifacts)


def render_codex_publication(catalog: PublicationCatalog, *, repo_root: Path,
                             package_root: Path, manifest_path=None) -> tuple[CodexPublicationArtifact, ...]:
    """Render native Codex plugins independently from the semantic catalog.

    Bucket plugins remain direct canonical roots.  The discontiguous core
    unit is an explicit cache-contained bundle; only declared SKILL.md
    members are copied into that bundle.
    """
    validate_publication_capabilities(ProviderId.CODEX, manifest_path=manifest_path)
    if not isinstance(catalog, PublicationCatalog):
        raise TypeError("catalog must be PublicationCatalog")
    repo_root = repo_root.resolve()
    package_root = package_root.resolve()
    by_id = {skill.semantic_id: skill for skill in catalog.skills}
    metadata = {name: dict(data) for name, data in catalog.bucket_metadata}
    artifacts: list[CodexPublicationArtifact] = []

    for unit in catalog.units:
        if unit.kind == "bucket":
            meta = metadata[unit.plugin_id]
            root = package_root / "skills" / unit.plugin_id
            data = _codex_plugin_manifest(unit.plugin_id, unit.content_version,
                                          meta["description"], _codex_skill_dirs(unit, by_id))
            artifacts.append(_render_codex_artifact(
                root / ".codex-plugin" / "plugin.json", unit, data,
                tuple(by_id[item] for item in unit.member_ids), repo_root,
                catalog.package_version, content_version=unit.content_version,
                package_root=package_root))
        elif unit.kind == "meta":
            root = package_root / "generate-skill"
            data = _codex_plugin_manifest("generate-skill", unit.content_version,
                                          catalog.generate_skill_description,
                                          ["./generate-skill"])
            artifacts.append(_render_codex_artifact(
                root / ".codex-plugin" / "plugin.json", unit, data, (), repo_root,
                catalog.package_version, content_version=unit.content_version,
                package_root=package_root))
        elif unit.kind == "curated":
            root = package_root / "adapters" / "codex" / "core"
            artifacts.extend(_render_codex_bundle(
                root, unit, catalog, tuple(by_id[item] for item in unit.member_ids), repo_root, package_root,
                description="Curated always-on core skills", skill_root="./skills"))
    return tuple(artifacts)


def render_cursor_publication(catalog: PublicationCatalog, *, repo_root: Path,
                              manifest_path=None) -> tuple[()]:
    """Ownership assertion only: Cursor reads ``.agents/skills`` natively.

    No ``.cursor/skills`` writer ships in P0–P2; skiller must not dual-write the skill tree.
    """
    validate_publication_capabilities(ProviderId.CURSOR, manifest_path=manifest_path)
    if not isinstance(catalog, PublicationCatalog):
        raise TypeError("catalog must be PublicationCatalog")
    agents_skills = repo_root.resolve() / ".agents" / "skills"
    if not agents_skills.is_dir():
        raise ValueError("SPUB_OWNERSHIP_ASSERTION_FAILED: .agents/skills is missing")
    cursor_skills = repo_root.resolve() / ".cursor" / "skills"
    if cursor_skills.is_dir() and any(cursor_skills.iterdir()):
        raise ValueError("SPUB_OWNERSHIP_CONFLICT: .cursor/skills must not be a second writer")
    return ()


def _render_codex_bundle(root: Path, unit: PublicationUnit, catalog: PublicationCatalog,
                         members: tuple[SemanticSkill, ...], repo_root: Path, package_root: Path, *,
                         description: str, skill_root: str) -> tuple[CodexPublicationArtifact, ...]:
    artifacts = [_render_codex_artifact(
        root / ".codex-plugin" / "plugin.json", unit,
        _codex_plugin_manifest(unit.plugin_id, unit.content_version, description, [skill_root]),
        members, repo_root, catalog.package_version, content_version=unit.content_version,
                package_root=package_root)]
    for member in members:
        canonical_root = package_root / Path(member.source_path).parent
        for source in _codex_skill_runtime_files(
                canonical_root, source_root=canonical_root, plugin=unit.plugin_id):
            target = root / "skills" / member.semantic_id / source.relative_to(canonical_root)
            artifacts.append(_render_codex_artifact(
                target, unit, source.read_bytes(), (member,), repo_root,
                catalog.package_version, content_version=unit.content_version,
                package_root=package_root))
    artifacts.append(_codex_bundle_lock(root, unit, catalog.package_version, tuple(artifacts),
                                        repo_root, package_root=package_root))
    return tuple(artifacts)


def _codex_bundle_lock(root: Path, unit: PublicationUnit, package_version: str,
                       artifacts: tuple[CodexPublicationArtifact, ...],
                       repo_root: Path, package_root: Path) -> CodexPublicationArtifact:
    records = [{"path": artifact.target.relative_to(root).as_posix(),
                "source_hash": artifact.source_hash, "rendered_hash": artifact.rendered_hash}
               for artifact in artifacts]
    return _render_codex_artifact(root / "publication-lock.json", unit,
                                  publication_lock(unit.unit_id, unit.content_version, records), (),
                                  repo_root, package_version, content_version=unit.content_version,
                                  package_root=package_root)


def _render_codex_artifact(target: Path, unit: PublicationUnit, data: Mapping[str, object] | bytes,
                           sources: Sequence[SemanticSkill], repo_root: Path,
                           package_version: str, *, package_root: Path,
                           content_version: str | None = None) -> CodexPublicationArtifact:
    source_records = tuple(ArtifactSource(
        f"skiller.publication.source{index}", source.source_path,
        source.content_hash if source.content_hash.startswith("sha256:") else f"sha256:{source.content_hash}")
        for index, source in enumerate(sources))
    if not source_records:
        source_records = (ArtifactSource(
            "skiller.publication.meta",
            (Path(package_rel(repo_root, package_root)) / "package.json").as_posix(),
            "sha256:" + "0" * 64),)
    rendered = data if isinstance(data, bytes) else _manifest_text(data)
    plugin_version = content_version if content_version is not None else package_version
    result = render_whole_file(
        artifact_id=f"skiller.codex.{unit.plugin_id}.{target.relative_to(repo_root).as_posix().lstrip('.').replace('/', '-').replace('.', '-').lower()}",
        target=target.relative_to(repo_root).as_posix(), sources=source_records,
        adapter=_CODEX_ADAPTER, parameters={"publication_unit": unit.unit_id,
                                            "plugin_version": plugin_version},
        rendered=rendered)
    return CodexPublicationArtifact(target, unit.unit_id, package_version, result.managed_bytes,
                                    result.provenance.source_hash, result.provenance.rendered_hash)


def _render_artifact(target: Path, unit: PublicationUnit, data: Mapping[str, object],
                     sources: Sequence[SemanticSkill | SiblingPlugin],
                     repo_root: Path, package_version: str, *, package_root: Path) -> ClaudePublicationArtifact:
    relative_target = target.relative_to(repo_root).as_posix()
    source_records = tuple(ArtifactSource(
        f"skiller.publication.source{index}", source.source_path,
        source.content_hash if source.content_hash.startswith("sha256:") else f"sha256:{source.content_hash}")
        for index, source in enumerate(sources))
    if not source_records:
        source_records = (ArtifactSource(
            "skiller.publication.meta",
            (Path(package_rel(repo_root, package_root)) / "package.json").as_posix(),
            "sha256:" + "0" * 64),)
    result = render_whole_file(
        artifact_id=f"skiller.claude.{unit.plugin_id}", target=relative_target,
        sources=source_records, adapter=_CLAUDE_ADAPTER,
        parameters={"publication_unit": unit.unit_id, "plugin_version": package_version},
        rendered=_manifest_text(data))
    return ClaudePublicationArtifact(target, unit.unit_id, package_version, result.managed_bytes,
                                     result.provenance.source_hash, result.provenance.rendered_hash)


def _claude_skill_dirs(unit: PublicationUnit, by_id: Mapping[str, SemanticSkill]) -> list[str]:
    dirs = set()
    for item in unit.member_ids:
        skill = by_id[item]
        relative = Path(skill.source_path).parent.parent.relative_to("skills" / Path(skill.bucket))
        dirs.add("./" if str(relative) == "." else f"./{relative.as_posix()}")
    return sorted(dirs)


def _codex_skill_dirs(unit: PublicationUnit, by_id: Mapping[str, SemanticSkill]) -> list[str]:
    """Return explicit skill directories for native Codex plugin discovery."""
    bucket_root = Path("skills") / unit.plugin_id
    return sorted(
        f"./{Path(by_id[item].source_path).parent.relative_to(bucket_root).as_posix()}"
        for item in unit.member_ids
    )


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


# Distribution plans live in aicore.delivery.distribution; skiller keeps provider selection (config)
# and the identity that its distribution artifacts carry in generated provenance and the artifact
# lock. They consume package config only through the P1 adapter and do not scan a provider manifest
# or execute a native installer during planning.
_DISTRIBUTION_IDENTITY = DistributionIdentity(
    _CODEX_ADAPTER, "skiller.codex.connect", "skiller.connect.source")


def selected_distribution_providers(config, *, project_id: str) -> tuple[str, ...]:
    from aicore.util.term import die
    from .config import resolve_distribution_providers
    resolved = resolve_distribution_providers(config, project_id=project_id)
    if resolved.effective is None:
        diagnostics = ", ".join(item.code for item in resolved.diagnostics)
        die(f"provider distribution blocked: {diagnostics or 'PCFG_SCHEMA_INVALID'}")
    return tuple(item.provider_id.value for item in resolved.effective if item.enabled)


def build_vendor_distribution_plan(config, target: Path, *, project_id: str,
                                   claude_path: str, codex_path: str) -> tuple[ProviderDistributionPlan, ...]:
    return vendor_distribution_plan(
        selected_distribution_providers(config, project_id=project_id), target,
        claude_path=claude_path, codex_path=codex_path)


def build_connect_distribution_plan(config, target: Path, *, project_id: str,
                                    repo_root: Path,
                                    plugins: Sequence[str] = ()) -> tuple[ProviderDistributionPlan, ...]:
    return connect_distribution_plan(
        selected_distribution_providers(config, project_id=project_id), target,
        repo_root=repo_root, plugins=plugins, identity=_DISTRIBUTION_IDENTITY)


def _distribution_artifact(root: Path, target: Path, managed_bytes: bytes,
                           source_identity: str,
                           source_bytes: bytes) -> ArtifactRenderResult:
    return distribution_artifact(root, target, managed_bytes, source_identity, source_bytes,
                                 identity=_DISTRIBUTION_IDENTITY)


# the sole root-bootstrap producer. Class-A private/source-only identities
# never reach an ordinary bucket/core/marketplace unit (`build_publication_catalog` excludes the
# `repository-bootstrap` bucket outright); their generated surface is exactly two thin provider
# projections per configured identity (Claude + Codex root `SKILL.md` pointers, no copied body)
# plus one combined version/tree lock. `skillset.py` only implements the mirror-image consumer
# exclusion — it is never called from here and never produces a root projection.
@dataclass(frozen=True)
class RootBootstrapArtifact:
    """One generated root-bootstrap projection or its combined lock; never a canonical source."""

    target: Path
    identity: str
    provider: str
    managed_bytes: bytes
    source_hash: str
    rendered_hash: str


def _root_bootstrap_body(identity: str, description: str, canonical_path: str,
                         canonical_sha256: str, unit_version: str, package_prefix: str) -> bytes:
    """Thin provider projection body: trigger metadata + a read-canonical instruction only."""
    title = " ".join(word.capitalize() for word in identity.split("-"))
    quoted = description.replace("\\", "\\\\").replace('"', '\\"')
    lines = [
        "---",
        f"name: {identity}",
        f'description: "{quoted}"',
        "bucket: repository-bootstrap",
        f"version: {unit_version}",
        f"canonical: {canonical_path}",
        f"canonical_sha256: {canonical_sha256}",
        _generator(package_prefix),
        "---",
        "",
        f"# {title}",
        "",
        "Root-bootstrap projection — generated by `skiller registry`; DO NOT EDIT BY HAND.",
        "",
        f"Canonical content lives at `{canonical_path}` (SHA-256 `{canonical_sha256}`). Read "
        "that file for the full skill body before acting on this identity — this projection "
        "intentionally carries no copied body; it exists only so the provider discovers the "
        "trigger and points back at the canonical source.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _bootstrap_path(repo_root: Path, value: object) -> Path:
    """Resolve a host-relative carrier without allowing traversal or escaping symlinks."""
    if (not isinstance(value, str) or not value or "\\" in value
            or Path(value).is_absolute() or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise ValueError("bootstrap config: expected a repository-relative path")
    path = repo_root / value
    if not path.resolve().is_relative_to(repo_root.resolve()):
        raise ValueError(f"bootstrap config: path escapes repository: {value}")
    return path


def load_repository_bootstrap_config(repo_root: Path, host) -> dict:
    """Read host-selected schema v2: explicit canon paths and a host-owned unit version."""
    config_path = _bootstrap_path(repo_root, host.bootstrap)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"repository-bootstrap-skills.json: unreadable: {error}") from error
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int \
            or config.get("schema_version") != 2 \
            or config.get("bucket") != "repository-bootstrap":
        raise ValueError("repository-bootstrap-skills.json: unsupported schema")
    identities = config.get("identities")
    if (not isinstance(identities, list) or not identities
            or not all(isinstance(item, dict) and isinstance(item.get("identity"), str)
                       and item["identity"] and set(item) == {"identity", "canonical"}
                       for item in identities)):
        raise ValueError("bootstrap config: identities must contain identity/canonical records")
    names = [item["identity"] for item in identities]
    if sorted(names) != names or len(set(names)) != len(names):
        raise ValueError("repository-bootstrap-skills.json: identities must be a sorted, "
                         "unique, non-empty list")
    for record in identities:
        _bootstrap_path(repo_root, record["canonical"])
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", record["identity"]):
            raise ValueError("bootstrap config: invalid identity")
    _bootstrap_path(repo_root, config.get("lock_path"))
    if not isinstance(config.get("unit_version"), str) or not config["unit_version"]:
        raise ValueError("bootstrap config: unit_version is required")
    if not isinstance(config.get("class_a_content_version"), str) or not config["class_a_content_version"]:
        raise ValueError("repository-bootstrap-skills.json: class_a_content_version is required "
                         "(D38-frozen — never the umbrella publication-versions.json value)")
    class_b = config.get("class_b", [])
    if not isinstance(class_b, list):
        raise ValueError("bootstrap config: class_b must be a list")
    for record in class_b:
        _validate_class_b_record(record, names)
        if record["identity"] in names:
            raise ValueError("bootstrap config: duplicate identity")
        names.append(record["identity"])
        _bootstrap_path(repo_root, record["canonical"])
    return config


def _validate_class_b_record(record: object, class_a_identities: Sequence[str]) -> None:
    if not isinstance(record, dict):
        raise ValueError("repository-bootstrap-skills.json: class_b record must be an object")
    identity = record.get("identity")
    if not isinstance(identity, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identity):
        raise ValueError("repository-bootstrap-skills.json: class_b record needs a non-empty identity")
    if identity in class_a_identities:
        raise ValueError(f"repository-bootstrap-skills.json: class_b identity {identity!r} "
                         "collides with a class-A identity")
    if record.get("source_class") != "public-bucket":
        raise ValueError(f"repository-bootstrap-skills.json: class_b {identity!r}: "
                         "source_class must be 'public-bucket'")
    if not isinstance(record.get("canonical"), str) or not record["canonical"]:
        raise ValueError(f"repository-bootstrap-skills.json: class_b {identity!r}: "
                         "canonical path is required")
    providers = record.get("providers")
    if not isinstance(providers, list) or not providers \
            or not all(isinstance(item, str) for item in providers):
        raise ValueError(f"repository-bootstrap-skills.json: class_b {identity!r}: "
                         "providers must be a non-empty list of strings")
    if len(set(providers)) != len(providers) or not set(providers) <= {"claude", "codex"}:
        raise ValueError(f"bootstrap config: class_b {identity!r}: invalid providers")
    if not isinstance(record.get("asymmetry_reason"), str) or not record["asymmetry_reason"]:
        raise ValueError(f"repository-bootstrap-skills.json: class_b {identity!r}: "
                         "asymmetry_reason is required")
    if not isinstance(record.get("precondition"), str) or not record["precondition"]:
        raise ValueError(f"repository-bootstrap-skills.json: class_b {identity!r}: "
                         "precondition is required")


def _class_b_donor_bucket(canonical: str) -> str:
    """The publication unit that owns the class-B canonical file: the bucket for
    `skills/<bucket>/<id>/SKILL.md`, the owning module plugin for `<module>/skills/<id>/SKILL.md`."""
    parts = Path(canonical).parts
    try:
        index = parts.index("skills")
        if len(parts) > index + 2 and parts[index + 2] == "SKILL.md" and index > 0:
            return parts[index - 1]
        return parts[index + 1]
    except (ValueError, IndexError):
        raise ValueError(f"class_b canonical path {canonical!r} is not under a skills/<bucket>/ tree") from None


def _root_bootstrap_class_b_body(identity: str, description: str, canonical_path: str,
                                 canonical_sha256: str, unit_version: str,
                                 asymmetry_reason: str, package_prefix: str) -> bytes:
    """Thin class-B projection body: same no-copied-body contract as class-A, plus
    the declared provider-asymmetry note — never emitted for a provider outside `providers`."""
    title = " ".join(word.capitalize() for word in identity.split("-"))
    quoted = description.replace("\\", "\\\\").replace('"', '\\"')
    lines = [
        "---",
        f"name: {identity}",
        f'description: "{quoted}"',
        "bucket: repository-bootstrap",
        "source_class: public-bucket",
        f"version: {unit_version}",
        f"canonical: {canonical_path}",
        f"canonical_sha256: {canonical_sha256}",
        _generator(package_prefix),
        "---",
        "",
        f"# {title}",
        "",
        "Root-bootstrap class-B projection — generated by `skiller registry`; DO NOT EDIT BY HAND.",
        "",
        f"Canonical content lives at `{canonical_path}` (SHA-256 `{canonical_sha256}`). Read "
        "that file for the full skill body before acting on this identity — this projection "
        "intentionally carries no copied body; it exists only so the provider discovers the "
        "trigger and points back at the canonical source.",
        "",
        f"Provider asymmetry: {asymmetry_reason}",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def render_repository_bootstrap_projections(*, repo_root: Path, package_root: Path,
                                            manifest_path=None,
                                            host=None,
                                            donor_enabled: Mapping[str, bool] | None = None
                                            ) -> tuple[RootBootstrapArtifact, ...]:
    """Render two class-A projections per configured identity plus the class-B public-bucket projections, and their one combined lock.

    Reads ONLY the private/source-only canonical EN-only carriers named by
    `configs/repository-bootstrap-skills.json` for class-A; never scans the filesystem for
    identities and never copies canonical body text into a projection. Fails closed
    on a missing canonical carrier, a name mismatch, or a missing per-unit version. Class-A bytes
    and count are byte-for-byte unaffected by class-B (P1.5 byte-identical guard).

    `donor_enabled` is an EXPLICIT, caller-supplied inventory of which publication buckets are
    enabled (`{"general": True, ...}`) — this function never reads a live provider profile or
    cache. A class-B record whose canonical bucket is marked enabled fails closed: invariant
    (ii) forbids restoring the identity by enabling its donor bucket while this root
    projection still exists. The production caller (registry.py) passes no override, matching
    today's declared reality (`general` is not enabled) — the parameter exists so a test can
    prove the precondition fails closed without mutating any real config.
    """
    validate_publication_capabilities(ProviderId.CLAUDE_CODE, manifest_path=manifest_path)
    validate_publication_capabilities(ProviderId.CODEX, manifest_path=manifest_path)
    repo_root = repo_root.resolve()
    package_root = package_root.resolve()
    if host is None:
        from .host import load_host
        host = load_host(package_root)
    config = load_repository_bootstrap_config(repo_root, host)
    unit_version = config["unit_version"]
    # D38-frozen: class-A's OWN embedded version/publication_unit literal never tracks the
    # umbrella `unit_version` bump — that decoupling is what keeps
    # the existing class-A projection bytes byte-identical across the P1.5 owner bump.
    class_a_version = config["class_a_content_version"]

    from aicore.content.skill import read_frontmatter as parse_frontmatter

    artifacts: list[RootBootstrapArtifact] = []
    lock_records: list[dict[str, object]] = []
    for record in config["identities"]:
        identity = record["identity"]
        en_path = _bootstrap_path(repo_root, record["canonical"])
        if not en_path.is_file():
            raise ValueError(f"repository-bootstrap identity {identity!r}: canonical source "
                             f"is missing ({en_path})")
        en_hash = hashlib.sha256(en_path.read_bytes()).hexdigest()
        frontmatter = parse_frontmatter(en_path) or {}
        if frontmatter.get("name") != identity:
            raise ValueError(f"repository-bootstrap identity {identity!r}: canonical EN "
                             f"frontmatter name is {frontmatter.get('name')!r}")
        description = frontmatter.get("description", "")
        if not description:
            raise ValueError(f"repository-bootstrap identity {identity!r}: canonical EN "
                             "frontmatter has no description")
        canonical_rel = en_path.relative_to(repo_root).as_posix()
        source = ArtifactSource("skiller.repository-bootstrap.canonical", canonical_rel,
                                "sha256:" + en_hash)
        body = _root_bootstrap_body(identity, description, canonical_rel, en_hash, class_a_version, package_prefix=package_rel(repo_root, package_root))
        for provider, projections_root, adapter in (
                ("claude", repo_root / ".claude" / "skills", _CLAUDE_ADAPTER),
                ("codex", repo_root / ".agents" / "skills", _CODEX_ADAPTER)):
            target = projections_root / identity / "SKILL.md"
            result = plan_artifact_render(ArtifactRenderRequest(
                f"skiller.repository-bootstrap.{provider}.{identity}", (source,),
                ArtifactTarget(target.relative_to(repo_root).as_posix(), ("whole-file", ())),
                adapter, (),
                {"publication_unit": f"repository-bootstrap@{class_a_version}", "identity": identity},
                lambda _request, _body=body: _body,
            ))
            artifacts.append(RootBootstrapArtifact(
                target, identity, provider, result.managed_bytes,
                result.provenance.source_hash, result.provenance.rendered_hash))
            lock_records.append({
                "identity": identity, "provider": provider,
                "target": target.relative_to(repo_root).as_posix(),
                "canonical": canonical_rel,
                "canonical_sha256": en_hash,
                "rendered_sha256": result.provenance.rendered_hash.removeprefix("sha256:"),
            })

    donor_enabled = donor_enabled or {}
    for record in config.get("class_b", ()):
        identity = record["identity"]
        canonical_rel_str = record["canonical"]
        donor_bucket = _class_b_donor_bucket(canonical_rel_str)
        if donor_enabled.get(donor_bucket):
            raise ValueError(
                f"repository-bootstrap class_b {identity!r}: precondition violated — "
                f"unit {donor_bucket!r} is enabled ({record['precondition']})")
        canonical_path = _bootstrap_path(repo_root, canonical_rel_str)
        if not canonical_path.is_file():
            raise ValueError(f"repository-bootstrap class_b {identity!r}: canonical source "
                             f"is missing ({canonical_path})")
        canonical_hash = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
        frontmatter = parse_frontmatter(canonical_path) or {}
        if frontmatter.get("name") != identity:
            raise ValueError(f"repository-bootstrap class_b {identity!r}: canonical "
                             f"frontmatter name is {frontmatter.get('name')!r}")
        description = frontmatter.get("description", "")
        if not description:
            raise ValueError(f"repository-bootstrap class_b {identity!r}: canonical "
                             "frontmatter has no description")
        canonical_rel = canonical_path.relative_to(repo_root).as_posix()
        source = ArtifactSource("skiller.repository-bootstrap.class-b.canonical", canonical_rel,
                                "sha256:" + canonical_hash)
        body = _root_bootstrap_class_b_body(identity, description, canonical_rel, canonical_hash,
                                            unit_version, record["asymmetry_reason"], package_prefix=package_rel(repo_root, package_root))
        provider_roots = {"claude": (repo_root / ".claude" / "skills", _CLAUDE_ADAPTER),
                          "codex": (repo_root / ".agents" / "skills", _CODEX_ADAPTER)}
        for provider in record["providers"]:
            if provider not in provider_roots:
                raise ValueError(f"repository-bootstrap class_b {identity!r}: "
                                 f"unsupported provider {provider!r}")
            projections_root, adapter = provider_roots[provider]
            target = projections_root / identity / "SKILL.md"
            result = plan_artifact_render(ArtifactRenderRequest(
                f"skiller.repository-bootstrap.{provider}.{identity}", (source,),
                ArtifactTarget(target.relative_to(repo_root).as_posix(), ("whole-file", ())),
                adapter, (),
                {"publication_unit": f"repository-bootstrap@{unit_version}", "identity": identity,
                 "source_class": "public-bucket"},
                lambda _request, _body=body: _body,
            ))
            artifacts.append(RootBootstrapArtifact(
                target, identity, provider, result.managed_bytes,
                result.provenance.source_hash, result.provenance.rendered_hash))
            lock_records.append({
                "identity": identity, "provider": provider,
                "target": target.relative_to(repo_root).as_posix(),
                "source_class": "public-bucket",
                "canonical": canonical_rel,
                "canonical_sha256": canonical_hash,
                "rendered_sha256": result.provenance.rendered_hash.removeprefix("sha256:"),
            })

    lock_data = {
        "contract_version": "1.0.0",
        "publication_unit": f"repository-bootstrap@{unit_version}",
        "generator": _generator(package_rel(repo_root, package_root)).removeprefix("generator: "),
        "records": sorted(lock_records, key=lambda item: (item["identity"], item["provider"])),
    }
    lock_bytes = _manifest_text(lock_data)
    lock_target = _bootstrap_path(repo_root, config["lock_path"])
    artifacts.append(RootBootstrapArtifact(
        lock_target, "", "lock", lock_bytes,
        "sha256:" + hashlib.sha256(_manifest_text(
            {"records": lock_data["records"]})).hexdigest(),
        "sha256:" + hashlib.sha256(lock_bytes).hexdigest()))
    return tuple(artifacts)


_ROOT_BOOTSTRAP_PROVIDER_ROOTS = {"claude": ".claude/skills", "codex": ".agents/skills"}


def assert_root_bootstrap_set_completeness(repo_root: Path,
                                           artifacts: Sequence[RootBootstrapArtifact]) -> list[str]:
    """ (`semantic-identity-ownership-v1` invariant i): each provider's root skills
    directory equals EXACTLY the declared root-bootstrap target set — never a subset check.
    An undeclared directory is a hard failure naming the path and that it needs an owner item
    (ownership, never suppression); a declared target missing on disk is reported too so a
    partial write never passes silently. Returns [] when clean. Read-only: never deletes,
    creates or repairs a directory itself — the caller decides remediation."""
    declared: dict[str, set[str]] = {}
    for artifact in artifacts:
        if artifact.provider == "lock":
            continue
        declared.setdefault(artifact.provider, set()).add(artifact.identity)
    failures: list[str] = []
    for provider, relative_root in _ROOT_BOOTSTRAP_PROVIDER_ROOTS.items():
        root = repo_root / relative_root
        if not root.is_dir():
            continue
        actual = {entry.name for entry in root.iterdir() if entry.is_dir()}
        expected = declared.get(provider, set())
        for name in sorted(actual - expected):
            failures.append(f"{provider}: undeclared root directory {relative_root}/{name} "
                            "— needs an owner item (semantic-identity-ownership-v1 invariant i)")
        for name in sorted(expected - actual):
            failures.append(f"{provider}: declared root-bootstrap target {relative_root}/{name} "
                            "is missing on disk")
    return failures
