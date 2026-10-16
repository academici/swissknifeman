"""registry — regeneration skills.json + plugin manifests + column (maintainer)."""
import hashlib
import json
import sys
from pathlib import Path

from aicore.util.io import atomic_write_text, safe_load_json
from aicore.util.repo import find_repo_root

from aicore.content import marketplace as hub_marketplace
from aicore.content.skill import (
    describe_skill, read_frontmatter as parse_frontmatter, skill_content_hash)
from aicore.util.cli import parse_flags
from aicore.util.term import die
from aicore.util.text import parse_inline_list
from .config import CORE_PLUGIN, CORE_SKILLS
from .host import host_plugin_dirs, load_host
from .module_skills import check_collisions, host_bucket_plugins
from .quality.compat import is_quarantined
from .selection import read_sidecar, registry_selection
from aicore.content.publication import manifest_bytes

from .publication import (
    PLUGIN_CATALOG_PATH, SiblingPlugin, assert_root_bootstrap_set_completeness, build_publication_catalog,
    render_claude_publication, render_codex_publication, render_repository_bootstrap_projections)


def build_registry(env):
    """Assemble structure skills.json from skills/**/SKILL.md and references.
    Returns (registry_dict, bucket_meta, bucket_dirs)."""
    root = env.root
    check_collisions(env)
    package_license = _package_license(root)
    skills = []
    references = []

    for skill_md in sorted(root.glob("skills/**/SKILL.md")):
        rel = skill_md.relative_to(root)
        parts = rel.parts
        if len(parts) < 3:
            continue
        bucket = parts[1]
        # Nested paths: devops/docker/php -> docker-php
        if len(parts) > 4:
            name = f"{parts[-2]}-{parts[-3]}" if parts[-3] != bucket else parts[-2]
        else:
            name = parts[2]
        fm = parse_frontmatter(skill_md)
        # R-4 (audit): fm-name almost always overlaps path-fallback above - but
        # build_registry() does not require running validate.sh (gate `name` in
        # frontmatter — separate step). Skill without `name` still in the middle of development
        # gets a reasonable name from the path rather than crashing/remains nameless. Left
        # intentional, not forgotten complexity.
        name = fm.get("name") or name
        sha = hashlib.sha256(skill_md.read_bytes()).hexdigest()
        entry = {
            "name": name,
            "bucket": bucket,
            "path": str(rel),
            "version": fm.get("version") or "0.1.0",
            "description": fm.get("description", ""),
            "sha256": sha,
            # Hash of the ENTIRE skill catalog (sync catches drift snippets/references, not
            # only SKILL.md). Complements sha256, see common.skill_content_hash.
            "content_sha256": skill_content_hash(skill_md.parent),
        }
        # E27: one reader of frontmatter and upstream.json (aicore describe_skill); the package
        # license is the default. A skill that cannot be described keeps the old entry shape
        # (validate reports it), so a broken fixture does not crash generation.
        try:
            described = describe_skill(skill_md.parent, skill_id=name)
        except ValueError:
            described = None
        entry["license"] = (described.license if described else None) or package_license
        if described and described.compatibility:
            entry["compatibility"] = described.compatibility
        allowed = (fm.get("allowed-tools") or fm.get("allowed_tools") or "")
        if isinstance(allowed, str) and allowed.strip():
            entry["allowed_tools"] = allowed.strip()
        # Graph/meta fields: optional, omitted when empty (same as upstream fields)
        for list_key in ("tags", "requires", "produces_for"):
            vals = parse_inline_list(fm.get(list_key, ""))
            if vals:
                entry[list_key] = vals
        # Hierarchy level (opt.): core|foundation|extension — self-documenting
        # skill layer. Scalar, omit-when-empty; complements requires/produces_for and
        # implicit CORE_BUCKETS, does NOT replace them. The value is validated in validate.sh.
        level = (fm.get("level") or "").strip()
        if level:
            entry["level"] = level
        # Selection policy (D10): selection.json beside SKILL.md → `selection` (omitted without a sidecar).
        # The schema is checked by `skiller selection check`; a broken file is a clear error here.
        try:
            sidecar = read_sidecar(skill_md.parent)
        except ValueError as exc:
            die(f"broken selection.json: {exc}")
        if sidecar:
            entry["selection"] = registry_selection(sidecar)
        # Quarantine (P8.6): compat-report.json with verdict quarantine keeps the skill out of the runtime.
        if is_quarantined(skill_md.parent):
            entry["quarantined"] = True
        # Provenance: upstream.json next to SKILL.md marks an external skill
        upstream_file = skill_md.parent / "upstream.json"
        if upstream_file.exists():
            # Broken upstream.json DO NOT drop naked traceback halfway through generation and
            # DO NOT quietly fall into source="local" (this would distort the provenance
            # external skill in marketplace) — clear error with the file path.
            up = safe_load_json(
                upstream_file,
                on_error=lambda e, f=upstream_file: die(f"broken upstream.json: {f}: {e}"),
            )
            files = up.get("files", [])
            # provenance-entry: body_path explicitly states which
            # files[]-entry - «body» upstream when SKILL.md — navigator, not
            # mirror; otherwise as before - recording SKILL.md, otherwise first (fork/merge:
            # files[].path indicates pristine-mirror in references/, e.g. in
            # strategy=fork without highlight body_path).
            body_path = up.get("body_path") or None
            main = (body_path and next(
                        (f for f in files if f.get("path") == body_path), None)) \
                or next((f for f in files if f.get("path") == "SKILL.md"), None) \
                or (files[0] if files else {})
            entry["source"] = up.get("source", "http")
            entry["upstream"] = main.get("url", "")
            if main.get("fetched_at"):
                entry["fetched_at"] = main["fetched_at"]
        else:
            entry["source"] = "local"
        skills.append(entry)

    # R-3 (audit): single source reference-materials - oss-dev/references.
    # A conscious limitation, a not forgotten special case: `parent` below ("oss-development")
    # — specific name of the owner of the skill in THIS bucket, not a generalized rule (for
    # another bucket with references/ would need his own parent — there is no such thing now,
    # see `find skills -maxdepth 2 -type d -name references`). If a second one appears
    # bucket with references/, to generalize THIS function here, and not to guess in advance.
    for ref in sorted((root / "skills/oss-dev/references").glob("*.md")):
        references.append({
            "name": ref.stem,
            "path": str(ref.relative_to(root)),
            "parent": "oss-development",
            "sha256": hashlib.sha256(ref.read_bytes()).hexdigest(),
        })

    buckets = {}
    for s in skills:
        buckets.setdefault(s["bucket"], 0)
        buckets[s["bucket"]] += 1

    # --- bucket metadata (buckets.json) --------------------------------------
    meta_file = root / "buckets.json"
    if not meta_file.exists():
        die("buckets.json not found — every bucket needs description/category/tags")
    bucket_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    bucket_dirs = sorted(d.name for d in (root / "skills").iterdir() if d.is_dir())
    # Alias-buckets:
    # metadata-record WITHOUT physical skills/<bucket> — old bucket name survives
    # merge as a list of links to the target's skills `alias_of` (see build_plugin_manifests).
    # Not «orphan» (forgotten directory), is an explicit migration record.
    alias_entries = {b: m for b, m in bucket_meta.items()
                     if isinstance(m, dict) and m.get("alias_of")}
    # Host-provided buckets: metadata only, the skills live in the host's module plugins.
    host_entries = {b for b, m in bucket_meta.items()
                    if isinstance(m, dict) and m.get("provided_by") == "host"}
    missing = [b for b in bucket_dirs if b not in bucket_meta]
    orphans = [b for b in bucket_meta
              if b not in bucket_dirs and b not in alias_entries and b not in host_entries]
    if missing:
        die(f"buckets.json: missing entries for: {', '.join(missing)}")
    if orphans:
        die(f"buckets.json: entries without skills/ dir: {', '.join(orphans)}")
    bad_targets = [b for b, m in alias_entries.items()
                  if m["alias_of"] not in bucket_dirs]
    if bad_targets:
        die("buckets.json: alias_of points to a non-existent bucket: " + ", ".join(
            f"{b}->{alias_entries[b]['alias_of']}" for b in bad_targets))

    registry = {
        "version": 5,
        "name": "swissknifeman",
        "repository": "https://github.com/academici/swissknifeman",
        "schema": "https://github.com/academici/swissknifeman/blob/main/SKILL_TEMPLATE.md",
        "buckets": {b: {"description": bucket_meta[b]["description"],
                        "count": c, "status": "active"}
                    for b, c in sorted(buckets.items())},
        "skills": skills,
        "references": references,
    }
    return registry, bucket_meta, bucket_dirs


def load_bucket_aliases(env):
    """Alias-buckets from buckets.json: {old_name: target_bucket}. Easy reader
    (without build_registry) for update.py/status.py — they don't need the whole registry structure for the sake of
    one hint. Empty if there is no file (standalone/test fixture without buckets.json) or
    no aliases declared - there are none in the real registry today (D14: P7 does not drain buckets)."""
    meta_file = env.root / "buckets.json"
    if not meta_file.is_file():
        return {}
    try:
        bucket_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {b: m["alias_of"] for b, m in bucket_meta.items()
            if isinstance(m, dict) and m.get("alias_of")}


def alias_migration_hints(aliases, enabled_names):
    """One line per active alias-bucket - «bucket X now Y», without injection
. `aliases` — {old: target} from load_bucket_aliases,
    `enabled_names` — plugins actually enabled (True) in settings project."""
    return [f"bucket '{name}' now '{aliases[name]}' — update enabledPlugins, "
            f"when convenient."
            for name in sorted(enabled_names) if name in aliases]


def _repo_root(pkg_root):
    """Root monorepo (where .git and general .claude-plugin/marketplace.json) — border
    git up from the package root. Fallback: himself pkg_root (standalone-layout)."""
    return find_repo_root(pkg_root) or pkg_root


def _package_license(root):
    """The library license from package.json: the default for skills that declare none."""
    package = safe_load_json(root / "package.json", on_error=lambda e: die(f"package.json: {e}"))
    value = package.get("license")
    return value if isinstance(value, str) and value else "MIT"


def _package_version(root):
    """Read the frozen P3 publication-version source explicitly."""
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    version = package.get("version")
    if not isinstance(version, str):
        die("package.json: version must be a string")
    return version


def _publication_versions(root):
    """D27 per-unit version map (`configs/publication-versions.json`): separates the skiller
    package API SemVer from finite per-unit manifest versions, so an unaffected bucket manifest
    stays byte-identical across an unrelated owner's package-API bump. Absent (standalone/fixture
    root predating the map) → `(None, None)`: `build_publication_catalog` then falls back to
    stamping every unit with `package_version` uniformly — the pre-D27 behavior, unchanged."""
    path = root / "configs" / "publication-versions.json"
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path}: invalid JSON: {e}")
    if not isinstance(data, dict):
        die(f"{path}: root must be an object")
    units = data.get("units")
    if not isinstance(units, dict) or not all(isinstance(v, str) for v in units.values()):
        die(f"{path}: 'units' must be an object {{unit: version}}")
    default = data.get("default_unit_version")
    if not isinstance(default, str) or not default:
        die(f"{path}: 'default_unit_version' is required and must be a string")
    return units, default


def _sibling_plugins(repo_root, package_root, host):
    """Scan the bounded sibling-package manifest input before catalog construction."""
    siblings = []
    candidates = host_plugin_dirs(repo_root, package_root, host)
    for package in sorted(candidates, key=lambda path: path.relative_to(repo_root).as_posix()):
        manifest = package / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            continue
        codex_manifest = package / ".codex-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        siblings.append(SiblingPlugin(
            name=data.get("name", package.name), package=package.name,
            description=data.get("description", ""),
            category=data.get("category", "ecosystem"),
            tags=tuple(data.get("keywords", [])),
            source_path=package.relative_to(repo_root).as_posix(),
            content_hash=hashlib.sha256(manifest.read_bytes()).hexdigest(),
            codex_supported=codex_manifest.is_file(),
        ))
    return tuple(siblings)


def build_catalog(env, bucket_meta, bucket_dirs, registry=None):
    """Shared semantic-catalog construction — the immutable P1 input every provider renderer
    consumes AND the read-only D42 core/donor-bucket diagnostic (doctor.py), so the
    identity→carrier mapping is read from exactly one seam, never re-derived."""
    root = env.root
    repo_root = _repo_root(root)
    if registry is None:
        registry, _meta, _dirs = build_registry(env)
    meta_skill = parse_frontmatter(root / "generate-skill" / "generate-skill" / "SKILL.md")
    unit_versions, default_unit_version = _publication_versions(root)
    return build_publication_catalog(
        registry=registry, bucket_meta=bucket_meta, bucket_dirs=bucket_dirs,
        core_skills=CORE_SKILLS, core_plugin=CORE_PLUGIN,
        package_version=_package_version(root), siblings=_sibling_plugins(repo_root, root, load_host(root)),
        generate_skill_description=meta_skill.get("description", "Meta-skill for creating new skills"),
        unit_versions=unit_versions, default_unit_version=default_unit_version,
    )


def build_claude_publication(env, bucket_meta, bucket_dirs, registry=None):
    """Render legacy Claude artifacts through the immutable P3 semantic catalog."""
    root = env.root
    repo_root = _repo_root(root)
    catalog = build_catalog(env, bucket_meta, bucket_dirs, registry)
    return render_claude_publication(catalog, repo_root=repo_root, package_root=root)


def build_codex_publication(env, bucket_meta, bucket_dirs, registry=None):
    """Render native Codex outputs from the same immutable semantic catalog."""
    root = env.root
    repo_root = _repo_root(root)
    catalog = build_catalog(env, bucket_meta, bucket_dirs, registry)
    return render_codex_publication(catalog, repo_root=repo_root, package_root=root)


def build_repository_bootstrap_publication(env):
    """Render configured thin root-bootstrap projections + their combined lock."""
    root = env.root
    repo_root = _repo_root(root)
    return render_repository_bootstrap_projections(repo_root=repo_root, package_root=root)


def build_plugin_manifests(env, bucket_meta, bucket_dirs, registry=None):
    """Compatibility view of Claude artifacts for the legacy registry writer/checker."""
    return [(artifact.target, json.loads(artifact.managed_bytes.decode("utf-8")))
            for artifact in build_claude_publication(env, bucket_meta, bucket_dirs, registry)]


def _has_repository_bootstrap_config(root):
    """Standalone/fixture roots predating carry no root-bootstrap config — skip the
    renderer entirely rather than fail closed on a file that was never meant to exist there."""
    host = load_host(root)
    return host.bootstrap is not None and (host.root / host.bootstrap).is_file()


def _prune_publication_artifacts(artifacts):
    """Remove only unchanged artifacts retired from a prior publication lock."""
    expected = {item.target for item in artifacts}
    pending = []
    for artifact in artifacts:
        if artifact.target.name != "publication-lock.json" or not artifact.target.is_file():
            continue
        root = artifact.target.parent
        previous = json.loads(artifact.target.read_text())
        for record in previous.get("artifacts", []):
            relative = Path(record["path"])
            path = root / relative
            if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("PUBLICATION_RETIRE_UNSAFE_PATH: " + str(path))
            if path in expected or not path.exists():
                continue
            if path.is_symlink() or not path.is_file() or "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != record["rendered_hash"]:
                raise ValueError("PUBLICATION_RETIRE_MODIFIED: " + str(path))
            pending.append(path)
    for path in pending:
        path.unlink()


def hub_units(env):
    """Modules whose `provides.plugins` make the hub marketplace: the `packages/` of the host root
    plus this package, which is always present (a layout without its unit.json gets the default)."""
    root = env.root
    repo_root = _repo_root(root)
    units = {}
    if (repo_root / "packages").is_dir():
        units = hub_marketplace.discover({"SKM_UNITS_PATH": str(repo_root / "packages")})
    own = units.get("skiller")
    if own is None or own.root.resolve() != root.resolve():
        units["skiller"] = hub_marketplace.Unit("skiller", root, {"provides": {"plugins": [
            {"name": "skiller", "catalog": PLUGIN_CATALOG_PATH}]}})
    return units


def assemble_marketplace(env, catalogs=None):
    """{repo-relative path: bytes} of the root Claude marketplace and the Codex index. `catalogs`
    ({path: bytes}) replaces catalog files that are not (yet) on disk."""
    return hub_marketplace.assemble(hub_units(env), _repo_root(env.root), catalogs=catalogs)


def write_plugin_manifests(env, bucket_meta, bucket_dirs):
    """Write all plugin-manifests + marketplace.json (atomically). Returns the number of plugins."""
    manifests = build_plugin_manifests(env, bucket_meta, bucket_dirs)
    for path, data in manifests:
        atomic_write_text(path, manifest_bytes(data).decode("utf-8"))
    codex_artifacts = build_codex_publication(env, bucket_meta, bucket_dirs)
    _prune_publication_artifacts(codex_artifacts)
    for artifact in codex_artifacts:
        atomic_write_text(artifact.target, artifact.managed_bytes.decode("utf-8"))
    # The root Claude marketplace and the Codex index come from the unit.json of the modules; the
    # skiller catalog written above is one of their inputs.
    indexes = assemble_marketplace(env)
    for relative, data in indexes.items():
        atomic_write_text(_repo_root(env.root) / relative, data.decode("utf-8"))
    if _has_repository_bootstrap_config(env.root):
        bootstrap_artifacts = build_repository_bootstrap_publication(env)
        for artifact in bootstrap_artifacts:
            atomic_write_text(artifact.target, artifact.managed_bytes.decode("utf-8"))
        # (D40 invariant i): fail closed on write too — an undeclared root directory
        # (e.g. a stray hand-written adapter reappearing) is never a silent "unique carrier".
        completeness_failures = assert_root_bootstrap_set_completeness(
            _repo_root(env.root), bootstrap_artifacts)
        if completeness_failures:
            die("root-bootstrap root-set completeness:\n" +
                "\n".join(f"  - {item}" for item in completeness_failures))
    # number of plugins = size of the Claude marketplace.plugins
    return len(json.loads(indexes[hub_marketplace.CLAUDE_INDEX])["plugins"])


def check_drift(env):
    """[relpath] generated artifacts that lag behind the sources ([] if pure).
    Rebuilds the registry+manifests+_index.md+graph.md+budget.md in memory and checks against
    disk - gate against silent drift (validate.sh just checked the validity JSON).
    graph.md/budget.md added in audit R-2: `cmd_registry` generates them, but earlier
    drift-the gate didn't know about them - CLAUDE.md promises «generezhka - do not edit with your hands»
    for both, but the gate did not check this."""
    root = env.root
    repo_root = _repo_root(root)
    registry, bucket_meta, bucket_dirs = build_registry(env)
    drift = []

    def _cmp(path, expected):
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError:
            actual = None
        if actual != expected:
            try:
                rel = path.relative_to(repo_root).as_posix()
            except ValueError:
                rel = str(path)
            drift.append(rel)

    _cmp(root / "skills.json", json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    _cmp(root / "skills" / "_index.md",
         render_index(registry, bucket_meta, host_bucket_plugins(env)))
    claude_artifacts = build_claude_publication(env, bucket_meta, bucket_dirs, registry)
    for artifact in claude_artifacts:
        _cmp(artifact.target, artifact.managed_bytes.decode("utf-8"))
    for artifact in build_codex_publication(env, bucket_meta, bucket_dirs, registry):
        _cmp(artifact.target, artifact.managed_bytes.decode("utf-8"))
    indexes = assemble_marketplace(env, {a.target: a.managed_bytes for a in claude_artifacts
                                         if a.target.name == "catalog.json"})
    for relative, data in indexes.items():
        _cmp(repo_root / relative, data.decode("utf-8"))
    if _has_repository_bootstrap_config(root):
        bootstrap_artifacts = build_repository_bootstrap_publication(env)
        for artifact in bootstrap_artifacts:
            _cmp(artifact.target, artifact.managed_bytes.decode("utf-8"))
        # (D40 invariant i): registry --check must catch an undeclared root directory,
        # not only stale bytes of a declared one — ownership, never suppression.
        drift.extend(assert_root_bootstrap_set_completeness(repo_root, bootstrap_artifacts))

    graph_text, _n_nodes, _n_edges = render_graph(registry)
    _cmp(_docs_root(root) / "docs" / "guide" / "graph.md", graph_text)

    # budget.md — only if skills.json is already on disk (write_budget_map die'etc
    # without it); at first `registry` (file not yet available) has nothing to compare with - not a gate.
    from .budget import render_budget_map
    if (root / "skills.json").is_file():
        budget_text, *_rest = render_budget_map(root, registry)
        _cmp(_docs_root(root) / "docs" / "guide" / "budget.md", budget_text)
    return drift


def render_index(registry, bucket_meta, host_buckets=None):
    """Markdown-registry for discovery (skills/_index.md): skills on buckets + tag matrix.
    Entirely generated from skills.json — human-readable face of the machine registry.
    `host_buckets` ({bucket: plugins}) adds one line per bucket the host provides."""
    skills = registry["skills"]
    host_buckets = dict(host_buckets or {})
    for name, meta in bucket_meta.items():
        if isinstance(meta, dict) and meta.get("provided_by") == "host":
            host_buckets.setdefault(name, ())
    by_bucket = {}
    for s in skills:
        by_bucket.setdefault(s["bucket"], []).append(s)
    tag_map = {}
    for s in skills:
        for t in s.get("tags", []):
            tag_map.setdefault(t, []).append(s["name"])

    lines = [
        "# Skill Registry swissknifeman",
        "",
        "<!-- GENERATED `skiller registry` — do not edit manually -->",
        "",
        "Source of truth for ported skills (machine registry - `skills.json`). "
        "Distribution to projects: `skiller connect` (plugin buckets) / `vendor` "
        "(physical. transfer). CORE-set of token skills (`general`/`oss-dev`) is heard "
        "by default - see `connect`/`vendor`.",
        "",
        f"Total: {len(skills)} skills in {len(by_bucket)} buckets.",
        "",
        "## Skills for buckets",
    ]
    for bucket in sorted(set(by_bucket) | set(host_buckets)):
        if bucket not in by_bucket:
            plugins = host_buckets[bucket]
            lines += ["", f"### {bucket} — provided by host modules: {', '.join(plugins)}"
                      if plugins else f"### {bucket} — provided by the host"]
            continue
        desc = bucket_meta.get(bucket, {}).get("description", "")
        items = sorted(by_bucket[bucket], key=lambda s: s["name"])
        lines += ["", f"### {bucket} — {desc} ({len(items)})", "",
                  "| Skill | Description | Tags |", "|:--|:--|:--|"]
        for s in items:
            d = s.get("description", "").replace("|", "\\|")
            if len(d) > 90:
                d = d[:89] + "…"
            tags = ", ".join(f"`{t}`" for t in s.get("tags", []))
            lines.append(f"| `{s['name']}` | {d} | {tags} |")

    lines += ["", "## Tag matrix", "",
              "Search for skills by tag (load pointwise, not the whole bucket).", "",
              "| Tag | Skills |", "|:--|:--|"]
    for tag in sorted(tag_map):
        names = ", ".join(f"`{n}`" for n in sorted(set(tag_map[tag])))
        lines.append(f"| `{tag}` | {names} |")
    return "\n".join(lines) + "\n"


def _docs_root(p):
    """Nearest up directory with docs/guide (package itself; fallback — p). Parity with
    budget._docs_root (both docs live in the package's docs directory)."""
    for cand in (p, *p.parents):
        if (cand / "docs" / "guide").is_dir():
            return cand
    return p


def render_graph(registry):
    """Mermaid-skill dependency graph (requires/produces_for) from registry-dict.
    Ported from scripts/generate-graph.sh (was bash+heredoc — the only one
    generated artifact WITHOUT python-functions, from here drift-the gate did not see him,
    audit R-2). Previously a separate process; now the same source of mathematics that
    y skills.json/_index.md — check_drift compares WITH THIS function, does not guess."""
    skills = registry["skills"]
    by_name = {s["name"]: s for s in skills}

    requires_edges = set()
    produces_edges = set()
    for s in skills:
        for dep in s.get("requires", []):
            if dep in by_name:
                requires_edges.add((s["name"], dep))
    for s in skills:
        for dst in s.get("produces_for", []):
            if dst in by_name and (dst, s["name"]) not in requires_edges:
                produces_edges.add((s["name"], dst))

    connected = {n for e in requires_edges | produces_edges for n in e}

    buckets = {}
    for name in sorted(connected):
        buckets.setdefault(by_name[name]["bucket"], []).append(name)

    isolated = {}
    for s in skills:
        if s["name"] not in connected:
            isolated.setdefault(s["bucket"], []).append(s["name"])

    def node_id(name):
        return name.replace("-", "_")

    lines = [
        "# Skill dependency graph",
        "",
        "> Generated `skiller registry` (registry.render_graph) from `skills.json` — "
        "cannot be edited manually.",
        "> Reassembly: `skiller registry`.",
        "",
        "Solid arrow `A --> B` — `A` requires `B` (`requires`): `skiller vendor` will last `B`",
        "during installation `A`. Dotted `A -.-> B` — result `A` serves as an input for `B`",
        "(`produces_for`). Only skills participating in the graph are shown; isolated -",
        "in the table below.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for bucket in sorted(buckets):
        lines.append(f"  subgraph {node_id(bucket)}[\"{bucket}\"]")
        for name in buckets[bucket]:
            lines.append(f"    {node_id(name)}[\"{name}\"]")
        lines.append("  end")
    for src, dst in sorted(requires_edges):
        lines.append(f"  {node_id(src)} -->|requires| {node_id(dst)}")
    for src, dst in sorted(produces_edges):
        lines.append(f"  {node_id(src)} -.->|feeds| {node_id(dst)}")
    lines += [
        "```",
        "",
        f"**In the column:** {len(connected)} skills, {len(requires_edges)} ribs requires, "
        f"{len(produces_edges)} ribs produces_for.",
        "",
        f"## Isolated skills ({sum(len(v) for v in isolated.values())})",
        "",
        "Skills without connections `requires`/`produces_for` — are self-sufficient.",
        "",
        "| Bucket | Skills |",
        "|---|---|",
    ]
    for bucket in sorted(isolated):
        names = ", ".join(f"`{n}`" for n in sorted(isolated[bucket]))
        lines.append(f"| {bucket} | {names} |")
    lines.append("")
    return "\n".join(lines), len(connected), len(requires_edges) + len(produces_edges)


def write_graph(env, registry):
    """Write docs/guide/graph.md (atomically). Returns (n_nodes, n_edges)."""
    text, n_nodes, n_edges = render_graph(registry)
    out = _docs_root(env.root) / "docs" / "guide" / "graph.md"
    atomic_write_text(out, text)
    return n_nodes, n_edges


def cmd_registry(env, argv):
    opts = parse_flags(argv, {"--check": "bool"})
    if opts["help"]:
        print("skiller registry [--check]\n"
              "  without flag - regenerate skills.json/_index.md/manifests/graph/budget;\n"
              "  --check   — DO NOT write, but check artifacts with sources (drift-gate, rc=1 when drifting).")
        return
    if opts["check"]:
        drift = check_drift(env)
        if drift:
            print("DRIFT: generated artifacts are behind the sources - run `skiller registry`:",
                  file=sys.stderr)
            for d in drift:
                print(f"  - {d}", file=sys.stderr)
            sys.exit(1)
        print("registry --check: artifacts are relevant "
              "(skills.json/_index.md/manifests/graph.md/budget.md)")
        return
    root = env.root
    registry, bucket_meta, bucket_dirs = build_registry(env)

    atomic_write_text(root / "skills.json",
                      json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated skills.json: {len(registry['skills'])} skills, "
          f"{len(registry['references'])} references")

    # Field consumer level: distribution by hierarchy levels. Silent until now
    # one skill is not marked (level — opt-in), lights up as it is entered.
    levels = {}
    for s in registry["skills"]:
        lv = s.get("level")
        if lv:
            levels[lv] = levels.get(lv, 0) + 1
    if levels:
        order = ["core", "foundation", "extension"]
        parts = [f"{lv} {levels[lv]}" for lv in order if lv in levels]
        parts += [f"{lv} {n}" for lv, n in sorted(levels.items())
                  if lv not in order]
        untagged = len(registry["skills"]) - sum(levels.values())
        print(f"  levels (level): {', '.join(parts)}; without level: {untagged}")

    atomic_write_text(root / "skills" / "_index.md",
                      render_index(registry, bucket_meta, host_bucket_plugins(env)))
    print("Updated skills/_index.md (tag matrix)")

    n_plugins = write_plugin_manifests(env, bucket_meta, bucket_dirs)
    print(f"Updated plugin manifests: {n_plugins} plugins "
          f"(.claude-plugin/marketplace.json)")

    if _has_repository_bootstrap_config(root):
        n_bootstrap = len(build_repository_bootstrap_publication(env))
        print(f"Updated root-bootstrap projections: {n_bootstrap} artifacts "
              f"(.claude/skills + .agents/skills + publication-lock.json, P1.2/D31)")

    n_nodes, n_edges = write_graph(env, registry)
    print(f"Updated docs/guide/graph.md: {n_nodes} nodes, {n_edges} edges")

    # Token Budget Map (three-tier) — in-process, token-math
    # lived in one module budget.py, and not duplicated.
    from .budget import write_budget_map
    write_budget_map(env)
