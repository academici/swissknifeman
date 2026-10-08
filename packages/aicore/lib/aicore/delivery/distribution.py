"""Provider distribution plans: where each provider's skills and plugins land in a project.

A plan names the managed vendor path or the marketplace channel of one provider; the Codex
marketplace channel also renders a self-contained bundle of the selected plugins and checks its
ownership against the artifact lock. The caller selects the providers and owns the identities
that appear in generated provenance (:class:`DistributionIdentity`), so the bytes and ids of
the artifacts do not depend on this module. Nothing here runs a native installer except the
explicit :func:`run_codex_native_install`.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from ..artifacts.artifact import ArtifactAdapterIdentity, ArtifactRenderResult, ArtifactSource
from ..artifacts.lock import (LOCK_RELATIVE_PATH, ArtifactActionKind, ArtifactPlan,
                              plan_artifact_lock)
from ..content.publication import (contained, distribution_catalog, manifest_bytes,
                                   render_whole_file, skill_runtime_files,
                                   validate_publication_capabilities)
from ..provider.distribution import connect_channel, vendor_channel
from ..provider.values import ProviderId
from ..util.term import die
from . import MARKETPLACE


@dataclass(frozen=True)
class DistributionIdentity:
    """The names a caller stamps on its distribution artifacts.

    ``adapter`` is the adapter identity recorded in provenance, ``namespace`` both prefixes the
    artifact ids and owns the artifact-lock records, ``source_id`` names the source of each artifact.
    """

    adapter: ArtifactAdapterIdentity
    namespace: str
    source_id: str


@dataclass(frozen=True)
class ProviderDistributionPlan:
    provider_id: str
    channel: str
    target: Path
    target_identity: str
    source_hash: str
    rendered_hash: str
    artifacts: tuple[ArtifactRenderResult, ...] = ()
    artifact_plan: ArtifactPlan | None = None


def vendor_distribution_plan(providers: Sequence[str], target: Path, *, claude_path: str,
                             codex_path: str) -> tuple[ProviderDistributionPlan, ...]:
    """Plan the managed vendor path of every provider in ``providers`` (already selected)."""
    catalog = distribution_catalog()
    path_params = {"claude_path": claude_path, "codex_path": codex_path}
    plans = []
    for provider in providers:
        vendor = vendor_channel(catalog, ProviderId(provider))
        if vendor is None:
            continue
        rel = path_params.get(vendor.path_param)
        if rel is None:
            die(f"SPUB_CAPABILITY_UNSUPPORTED: provider {provider}, channel vendor: "
                f"unknown path_param {vendor.path_param!r}")
        plans.append(ProviderDistributionPlan(provider, "vendor", target / rel,
                                              (target / rel).as_posix(), "", ""))
    seen = set()
    for plan in plans:
        resolved = plan.target.resolve(strict=False)
        if resolved in seen:
            die("SPUB_OWNERSHIP_CONFLICT: selected providers share one managed vendor path")
        seen.add(resolved)
    return tuple(plans)


def connect_distribution_plan(providers: Sequence[str], target: Path, *, repo_root: Path,
                              identity: DistributionIdentity,
                              plugins: Sequence[str] = ()) -> tuple[ProviderDistributionPlan, ...]:
    """Plan the marketplace channel of every provider in ``providers`` (already selected)."""
    catalog = distribution_catalog()
    plans = []
    for provider in providers:
        connect = connect_channel(catalog, ProviderId(provider))
        if connect is None:
            continue
        provider_id = ProviderId(provider)
        try:
            validate_publication_capabilities(provider_id)
        except (OSError, TypeError, ValueError) as exc:
            die(f"SPUB_CAPABILITY_UNSUPPORTED: provider {provider}, "
                f"channel marketplace: {exc}")
        if connect.mode == "claude-marketplace":
            plans.append(ProviderDistributionPlan(provider, "marketplace", target / connect.target,
                                                   connect.target, "", ""))
        elif connect.mode == "codex-marketplace":
            repo_root = repo_root.resolve()
            target = target.resolve()
            marketplace = repo_root / connect.marketplace
            if not marketplace.is_file():
                die("SPUB_BUNDLE_INCOMPLETE: provider codex, unit marketplace, "
                    f"target {marketplace}: generated marketplace is missing; run skiller registry")
            if target == repo_root:
                plans.append(ProviderDistributionPlan(
                    provider, "marketplace", marketplace, marketplace.as_posix(), "", ""))
            else:
                if not plugins:
                    die("SPUB_BUNDLE_INCOMPLETE: provider codex, channel marketplace-bundle, "
                        f"target {target}: selected plugin set is required")
                artifacts, artifact_plan = codex_connect_artifacts(
                    repo_root=repo_root, target=target, plugins=plugins,
                    marketplace_path=marketplace, identity=identity)
                marketplace_artifact = next(
                    item for item in artifacts
                    if item.target.path == ".agents/plugins/marketplace.json")
                plans.append(ProviderDistributionPlan(
                    provider, "marketplace-bundle",
                    target / marketplace_artifact.target.path,
                    marketplace_artifact.target.path,
                    marketplace_artifact.provenance.source_hash,
                    marketplace_artifact.provenance.rendered_hash,
                    artifacts, artifact_plan))
        else:
            die(f"SPUB_CAPABILITY_UNSUPPORTED: provider {provider}, connect mode {connect.mode}")
    return tuple(plans)


def codex_connect_artifacts(*, repo_root: Path, target: Path,
                            plugins: Sequence[str], marketplace_path: Path,
                            identity: DistributionIdentity) -> tuple[
                                tuple[ArtifactRenderResult, ...], ArtifactPlan]:
    """Build and ownership-preflight a self-contained repo Codex marketplace.

    The source repository marketplace is only an index.  Every selected plugin
    is materialized as a deterministic bundle under the consumer repository;
    no consumer entry points back at the source checkout.
    """
    try:
        source_marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die("SPUB_BUNDLE_INCOMPLETE: provider codex, unit marketplace, "
            f"target {marketplace_path}: invalid generated marketplace: {exc}")
    entries = source_marketplace.get("plugins")
    if not isinstance(entries, list):
        die("SPUB_BUNDLE_INCOMPLETE: provider codex, unit marketplace, "
            f"target {marketplace_path}: plugins must be a list")
    by_name = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            die("SPUB_BUNDLE_INCOMPLETE: provider codex, unit marketplace: invalid plugin entry")
        name = entry["name"]
        if name in by_name:
            die(f"SPUB_OWNERSHIP_CONFLICT: provider codex, unit {name}: duplicate marketplace entry")
        by_name[name] = entry

    selected = tuple(sorted(set(plugins)))
    if len(selected) != len(tuple(plugins)):
        die("SPUB_OWNERSHIP_CONFLICT: provider codex, channel marketplace-bundle: "
            "duplicate selected plugin")

    artifacts: list[ArtifactRenderResult] = []
    consumer_entries = []
    bundles_root = target / ".agents" / "plugins" / "bundles"
    for name in selected:
        if not name or Path(name).name != name or name in {".", ".."}:
            die(f"SPUB_PATH_UNCONTAINED: provider codex, unit {name!r}: invalid plugin ID")
        entry = by_name.get(name)
        if entry is None:
            die(f"SPUB_BUNDLE_INCOMPLETE: provider codex, unit {name}, "
                f"target {marketplace_path}: selected plugin is not declared")
        source_rel = codex_local_source(entry, plugin=name)
        source_root = contained(repo_root, repo_root / source_rel, plugin=name,
                                 label="source")
        if not source_root.is_dir():
            die(f"SPUB_BUNDLE_INCOMPLETE: provider codex, unit {name}, "
                f"target {source_root}: plugin source is missing")
        bundle_root = bundles_root / name
        bundle_artifacts = codex_bundle_artifacts(
            source_root=source_root, bundle_root=bundle_root, plugin=name,
            repo_root=repo_root, target=target, identity=identity)
        if bundle_root.exists():
            expected_paths = {
                target / artifact.target.path for artifact in bundle_artifacts
            }
            unexpected = next((
                path for path in bundle_root.rglob("*")
                if path.is_file() and path not in expected_paths
            ), None)
            if unexpected is not None:
                die(f"SPUB_OWNERSHIP_CONFLICT: provider codex, unit {name}, "
                    f"target {unexpected}: unowned file in managed bundle")
        artifacts.extend(bundle_artifacts)
        consumer_entries.append({
            "name": name,
            "source": {
                "source": "local",
                "path": "./" + bundle_root.relative_to(target).as_posix(),
            },
            "policy": {
                "installation": "AVAILABLE",
                "authentication": "ON_INSTALL",
            },
            "category": entry.get("category", ""),
        })

    marketplace_data = {
        "name": source_marketplace.get("name", MARKETPLACE),
        "interface": {"displayName": source_marketplace.get("name", MARKETPLACE)},
        "plugins": consumer_entries,
    }
    marketplace_bytes = manifest_bytes(marketplace_data)
    marketplace_target = target / ".agents" / "plugins" / "marketplace.json"
    artifacts.append(distribution_artifact(
        target, marketplace_target, marketplace_bytes,
        marketplace_path.relative_to(repo_root).as_posix(),
        marketplace_path.read_bytes(), identity=identity))

    result = tuple(sorted(artifacts, key=lambda item: item.target.path))
    lock_path = target / LOCK_RELATIVE_PATH
    lock_bytes = lock_path.read_bytes() if lock_path.is_file() else None
    artifact_plan = plan_artifact_lock(
        target, result, lock_bytes=lock_bytes, owner_namespace=identity.namespace)
    refused = tuple(action for action in artifact_plan.actions
                    if action.action is ArtifactActionKind.REFUSE)
    if refused:
        details = "; ".join(
            f"{action.target_path}: {action.diagnostic}" for action in refused)
        die("SPUB_OWNERSHIP_CONFLICT: provider codex, channel marketplace-bundle, "
            f"target {target}: {details}")
    return result, artifact_plan


def codex_bundle_artifacts(*, source_root: Path, bundle_root: Path, plugin: str,
                           repo_root: Path, target: Path,
                           identity: DistributionIdentity) -> tuple[ArtifactRenderResult, ...]:
    manifest = source_root / ".codex-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"SPUB_BUNDLE_INCOMPLETE: provider codex, unit {plugin}, "
            f"target {manifest}: invalid plugin manifest: {exc}")
    if not isinstance(data, dict) or data.get("name") != plugin:
        die(f"SPUB_BUNDLE_INCOMPLETE: provider codex, unit {plugin}, "
            f"target {manifest}: manifest identity mismatch")
    raw_roots = data.get("skills")
    roots = [raw_roots] if isinstance(raw_roots, str) else raw_roots
    if not isinstance(roots, list) or not roots or not all(isinstance(item, str) for item in roots):
        die(f"SPUB_BUNDLE_INCOMPLETE: provider codex, unit {plugin}, "
            f"target {manifest}: declared skills are missing")

    files = [manifest]
    for raw_root in roots:
        root = contained(source_root, source_root / raw_root, plugin=plugin,
                          label="declared skill root")
        if root.is_file():
            members = [root] if root.name == "SKILL.md" else []
        elif root.is_dir():
            members = sorted(root.rglob("SKILL.md"))
        else:
            members = []
        if not members:
            die(f"SPUB_BUNDLE_INCOMPLETE: provider codex, unit {plugin}, "
                f"target {root}: declared skill root has no SKILL.md")
        for member in members:
            contained(source_root, member, plugin=plugin,
                       label="declared skill member")
            files.extend(skill_runtime_files(
                member.parent, source_root=source_root, plugin=plugin))

    unique = tuple(sorted(set(files), key=lambda item: item.relative_to(source_root).as_posix()))
    artifacts = []
    for source in unique:
        source_bytes = source.read_bytes()
        relative = source.relative_to(source_root)
        artifacts.append(distribution_artifact(
            target, bundle_root / relative, source_bytes,
            source.relative_to(repo_root).as_posix(), source_bytes, identity=identity))
    return tuple(artifacts)


def codex_local_source(entry: Mapping[str, object], *, plugin: str) -> str:
    source = entry.get("source")
    if isinstance(source, str):
        path = source
    elif isinstance(source, Mapping) and source.get("source") == "local":
        path = source.get("path")
    else:
        path = None
    if not isinstance(path, str) or not path.startswith("./"):
        die(f"SPUB_PATH_UNCONTAINED: provider codex, unit {plugin}: "
            "marketplace source must be a contained local ./ path")
    return path


def distribution_artifact(root: Path, target: Path, managed_bytes: bytes,
                          source_identity: str, source_bytes: bytes, *,
                          identity: DistributionIdentity) -> ArtifactRenderResult:
    relative_target = target.relative_to(root).as_posix()
    digest = hashlib.sha256(relative_target.encode("utf-8")).hexdigest()[:16]
    return render_whole_file(
        artifact_id=f"{identity.namespace}.a{digest}",
        target=relative_target,
        sources=(ArtifactSource(
            identity.source_id, source_identity,
            "sha256:" + hashlib.sha256(source_bytes).hexdigest()),),
        adapter=identity.adapter,
        parameters={"channel": "marketplace-bundle"},
        rendered=managed_bytes)


def run_codex_native_install(*, repo_root: Path, plugin: str, dry_run: bool,
                             runner=subprocess.run, executable: str = "codex") -> tuple[bool, str]:
    """The explicit native global transaction; dry-run never probes or runs it."""
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
            if command[2:4] == ["marketplace", "add"] and "already added from a different source" in detail:
                try:
                    listed = runner([executable, "plugin", "marketplace", "list", "--json"],
                                    check=False, capture_output=True, text=True)
                    origin = runner(["git", "-C", str(repo_root), "remote", "get-url", "origin"],
                                    check=False, capture_output=True, text=True)
                    sources = [m.get("marketplaceSource", {}) for m in json.loads(listed.stdout).get("marketplaces", [])
                               if m.get("name") == MARKETPLACE]
                    expected_origin = origin.stdout.strip()
                    source = sources[0] if len(sources) == 1 else {}
                    matches_git_origin = (source.get("sourceType") == "git"
                                          and source.get("source") == expected_origin)
                    matches_local_checkout = False
                    if source.get("sourceType") == "local" and isinstance(source.get("source"), str):
                        local_root = source["source"]
                        local_origin = runner(["git", "-C", local_root, "remote", "get-url", "origin"],
                                              check=False, capture_output=True, text=True)
                        local_head = runner(["git", "-C", local_root, "rev-parse", "HEAD"],
                                            check=False, capture_output=True, text=True)
                        release_head = runner(["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                                              check=False, capture_output=True, text=True)
                        matches_local_checkout = (local_origin.returncode == 0 and local_head.returncode == 0
                                                  and release_head.returncode == 0
                                                  and local_origin.stdout.strip() == expected_origin
                                                  and local_head.stdout.strip() == release_head.stdout.strip())
                    if listed.returncode or origin.returncode or not (matches_git_origin or matches_local_checkout):
                        return False, "SPUB_INSTALL_UNAVAILABLE: existing marketplace source does not match repository origin and release commit"
                    if matches_local_checkout:
                        # Local marketplaces have no Codex upgrade transaction. The exact
                        # checked-out release is already their source; proceed to plugin add.
                        continue
                    upgraded = runner([executable, "plugin", "marketplace", "upgrade", MARKETPLACE],
                                      check=False, capture_output=True, text=True)
                    if upgraded.returncode == 0:
                        continue
                    detail = (upgraded.stderr or upgraded.stdout).strip()
                except (OSError, ValueError, AttributeError) as exc:
                    detail = str(exc)
            return False, f"SPUB_INSTALL_UNAVAILABLE: {' '.join(command[:3])} failed: {detail}"
    return True, f"codex/native-install: marketplace={repo_root}, plugin={plugin}@{MARKETPLACE}"
