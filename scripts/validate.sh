#!/usr/bin/env bash
# Validate repository structure: SKILL.md frontmatter, upstream.json,
# profiles/*.json, skills.json, snippet manifests.
# Used locally and by .github/workflows/validate.yml.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1])
errors = []
warnings = []

UPSTREAM_SOURCES = {"github", "http", "file"}
UPSTREAM_STRATEGIES = {"replace", "notify"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_frontmatter(path):
    """Return dict of frontmatter keys, or None if no frontmatter block."""
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return None  # unterminated block


def parse_inline_list(value):
    """Inline YAML list ('[a, "b", c]') -> list of strings; anything else -> []."""
    value = (value or "").strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    items = [i.strip().strip('"').strip("'") for i in value[1:-1].split(",")]
    return [i for i in items if i]


def load_upstream(skill_dir):
    f = skill_dir / "upstream.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{f.relative_to(root)}: invalid JSON: {e}")
        return {}


# --- 1. SKILL.md frontmatter ---------------------------------------------
skill_files = sorted(root.glob("skills/**/SKILL.md"))
meta_skill = root / "generate-skill/generate-skill/SKILL.md"
if meta_skill.exists():
    skill_files.append(meta_skill)

for skill_md in skill_files:
    rel = skill_md.relative_to(root)
    skill_dir = skill_md.parent
    upstream = load_upstream(skill_dir)
    fm = parse_frontmatter(skill_md)

    if fm is None:
        if upstream is not None and upstream.get("strategy") == "replace":
            errors.append(
                f"{rel}: no frontmatter and upstream strategy=replace — "
                f"frontmatter-less upstreams must use strategy=notify"
            )
        else:
            errors.append(f"{rel}: missing frontmatter block")
        continue

    required = ["name", "description"] if upstream is not None \
        else ["name", "bucket", "version", "description"]
    for field in required:
        if not fm.get(field):
            errors.append(f"{rel}: missing required frontmatter field: {field}")

# --- 2. upstream.json -----------------------------------------------------
for up_file in sorted(root.glob("skills/**/upstream.json")) + \
        sorted((root / "generate-skill").glob("**/upstream.json")):
    rel = up_file.relative_to(root)
    skill_dir = up_file.parent
    if not (skill_dir / "SKILL.md").exists():
        errors.append(f"{rel}: upstream.json without sibling SKILL.md")
    try:
        data = json.loads(up_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue

    if data.get("schema_version") != 1:
        errors.append(f"{rel}: schema_version must be 1")
    if data.get("source") not in UPSTREAM_SOURCES:
        errors.append(f"{rel}: source must be one of {sorted(UPSTREAM_SOURCES)}")
    if data.get("strategy") not in UPSTREAM_STRATEGIES:
        errors.append(f"{rel}: strategy must be one of {sorted(UPSTREAM_STRATEGIES)}")
    if data.get("source") == "file":
        warnings.append(f"{rel}: source=file is for local fixtures/tests only")

    files = data.get("files")
    if not isinstance(files, list) or not files:
        errors.append(f"{rel}: files must be a non-empty array")
        continue
    for i, entry in enumerate(files):
        for key in ("path", "url", "sha256", "fetched_at"):
            if key not in entry:
                errors.append(f"{rel}: files[{i}] missing key: {key}")
        path = entry.get("path", "")
        if path:
            target = (skill_dir / path).resolve()
            if not str(target).startswith(str(skill_dir.resolve())):
                errors.append(f"{rel}: files[{i}].path escapes skill dir: {path}")
            elif not target.exists():
                errors.append(f"{rel}: files[{i}].path does not exist: {path}")
        fetched = entry.get("fetched_at", "")
        if fetched and not DATE_RE.match(fetched):
            errors.append(f"{rel}: files[{i}].fetched_at must be YYYY-MM-DD or empty")

# --- 3. profiles/*.json ---------------------------------------------------
profiles_dir = root / "profiles"
if profiles_dir.is_dir():
    for prof in sorted(profiles_dir.glob("*.json")):
        rel = prof.relative_to(root)
        try:
            data = json.loads(prof.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        if data.get("name") != prof.stem:
            errors.append(f"{rel}: name must match filename ({prof.stem})")
        buckets = data.get("buckets")
        if not isinstance(buckets, list) or not buckets:
            errors.append(f"{rel}: buckets must be a non-empty array")
        elif buckets != ["*"]:
            for b in buckets:
                if not (root / "skills" / b).is_dir():
                    errors.append(f"{rel}: unknown bucket: {b}")

# --- 4. skills.json -------------------------------------------------------
reg = root / "skills.json"
if reg.exists():
    try:
        json.loads(reg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"skills.json: invalid JSON: {e}")
else:
    errors.append("skills.json not found")

# --- 5. snippet manifests -------------------------------------------------
for manifest in sorted(root.glob("skills/**/snippets/index.json")):
    rel = manifest.relative_to(root)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue
    for s in data.get("snippets", []):
        f = manifest.parent / s.get("file", "")
        if not f.exists():
            errors.append(f"{rel}: missing snippet: {s.get('file')}")

# --- 6. buckets.json --------------------------------------------------------
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
bucket_dirs = sorted(d.name for d in (root / "skills").iterdir() if d.is_dir())
bucket_meta = {}
meta_file = root / "buckets.json"
if not meta_file.exists():
    errors.append("buckets.json not found")
else:
    try:
        bucket_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"buckets.json: invalid JSON: {e}")
        bucket_meta = {}
    for b in bucket_dirs:
        if b not in bucket_meta:
            errors.append(f"buckets.json: missing entry for bucket: {b}")
    for b, meta in bucket_meta.items():
        if b not in bucket_dirs:
            errors.append(f"buckets.json: entry without skills/ dir: {b}")
        if not (isinstance(meta, dict) and meta.get("description")):
            errors.append(f"buckets.json: {b}: description must be non-empty")


# --- 7. plugin manifests (.claude-plugin/) ----------------------------------
def expected_skills_dirs(plugin_root):
    """Same algorithm as sync.sh: parents of skill dirs, ./-prefixed."""
    dirs = set()
    for skill_md in plugin_root.rglob("SKILL.md"):
        rel = skill_md.parent.parent.relative_to(plugin_root)
        dirs.add("./" if str(rel) == "." else f"./{rel.as_posix()}")
    return sorted(dirs)


STALE_HINT = "run 'swissknifeman registry' (or ./sync.sh --update-registry)"
plugin_roots = {b: root / "skills" / b for b in bucket_dirs}
plugin_roots["generate-skill"] = root / "generate-skill"

for plugin_name, plugin_root in sorted(plugin_roots.items()):
    pj = plugin_root / ".claude-plugin" / "plugin.json"
    rel = pj.relative_to(root)
    if not pj.exists():
        errors.append(f"{rel}: missing ({STALE_HINT})")
        continue
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{rel}: invalid JSON: {e}")
        continue
    if data.get("name") != plugin_name:
        errors.append(f"{rel}: name must be '{plugin_name}'")
    if not KEBAB_RE.match(data.get("name", "")):
        errors.append(f"{rel}: name must be kebab-case")
    if not data.get("description"):
        errors.append(f"{rel}: description must be non-empty")
    declared = data.get("skills", [])
    declared = [declared] if isinstance(declared, str) else declared
    if sorted(declared) != expected_skills_dirs(plugin_root):
        errors.append(f"{rel}: stale skills dirs ({STALE_HINT})")

mp_file = root / ".claude-plugin" / "marketplace.json"
if not mp_file.exists():
    errors.append(f".claude-plugin/marketplace.json: missing ({STALE_HINT})")
else:
    try:
        mp = json.loads(mp_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f".claude-plugin/marketplace.json: invalid JSON: {e}")
        mp = {}
    if mp:
        if mp.get("name") != "swissknifeman":
            errors.append(".claude-plugin/marketplace.json: name must be 'swissknifeman'")
        if not mp.get("owner", {}).get("name"):
            errors.append(".claude-plugin/marketplace.json: owner.name must be set")
        entries = mp.get("plugins", [])
        names = [p.get("name", "") for p in entries]
        if len(names) != len(set(names)):
            errors.append(".claude-plugin/marketplace.json: duplicate plugin names")
        if sorted(names) != sorted(plugin_roots):
            errors.append(
                f".claude-plugin/marketplace.json: plugins must match dirs on disk "
                f"({STALE_HINT})")
        for p in entries:
            src = p.get("source", "")
            if not (root / src).is_dir():
                errors.append(
                    f".claude-plugin/marketplace.json: {p.get('name')}: "
                    f"source dir not found: {src}")
            if not p.get("description"):
                errors.append(
                    f".claude-plugin/marketplace.json: {p.get('name')}: "
                    f"description must be non-empty")

# --- 7b. no skills nested inside a skill dir ---------------------------------
# Claude Code discovers a dir with SKILL.md as a leaf skill; SKILL.md deeper
# inside it is silently invisible to plugin discovery.
for skill_md in skill_files:
    d = skill_md.parent
    nested = [p for p in d.rglob("SKILL.md") if p != skill_md]
    for p in nested:
        errors.append(
            f"{p.relative_to(root)}: nested inside skill "
            f"'{d.relative_to(root)}' — invisible to plugin discovery; "
            f"flatten it (e.g. '{d.name}-{p.parent.name}' next to '{d.name}')")

# --- 8. skill-name uniqueness ------------------------------------------------
# Plugin namespace flattens per plugin: dup inside a bucket = error.
# Across buckets namespacing keeps it legal, but vendoring modes collide: warn.
by_bucket = {}
for skill_md in skill_files:
    fm = parse_frontmatter(skill_md) or {}
    name = fm.get("name", "")
    if not name:
        continue
    bucket = skill_md.relative_to(root).parts[1] \
        if skill_md.relative_to(root).parts[0] == "skills" else "generate-skill"
    by_bucket.setdefault(bucket, {}).setdefault(name, []).append(
        str(skill_md.relative_to(root)))
seen_names = {}
for bucket, names in sorted(by_bucket.items()):
    for name, paths in sorted(names.items()):
        if len(paths) > 1:
            errors.append(
                f"duplicate skill name '{name}' in bucket '{bucket}': "
                f"{', '.join(paths)}")
        seen_names.setdefault(name, []).append(bucket)
for name, in_buckets in sorted(seen_names.items()):
    if len(in_buckets) > 1:
        warnings.append(
            f"skill name '{name}' appears in buckets {', '.join(in_buckets)} — "
            f"legal with plugin namespaces, collides in vendoring modes")

# --- 9. dependency graph (requires / produces_for) ---------------------------
# Edge names are frontmatter `name` values. Cycles are checked over `requires`
# only: an `A requires B` + `B produces_for A` pair is a normal complementary
# link, not a cycle.
graph_requires = {}
graph_produces = {}
name_to_rel = {}
for skill_md in skill_files:
    rel = skill_md.relative_to(root)
    fm = parse_frontmatter(skill_md) or {}
    name = fm.get("name", "").strip().strip('"').strip("'")
    if not name:
        continue
    name_to_rel.setdefault(name, str(rel))
    for key, store in (("requires", graph_requires), ("produces_for", graph_produces)):
        raw = fm.get(key, "").strip()
        deps = parse_inline_list(raw)
        if raw and raw != "[]" and not deps:
            warnings.append(
                f"{rel}: {key} is set but not an inline list ('{raw}') — "
                f"use '[a, b]' syntax; multiline YAML lists are not parsed")
        store[name] = deps

all_names = set(graph_requires) | set(graph_produces)
for name in sorted(all_names):
    src = name_to_rel[name]
    for key, store in (("requires", graph_requires), ("produces_for", graph_produces)):
        for dep in store.get(name, []):
            if dep == name:
                errors.append(f"{src}: {key} references itself")
            elif dep not in all_names:
                errors.append(f"{src}: {key} unknown skill '{dep}'")

# Cycle detection over `requires` (iterative DFS, white/grey/black colouring)
WHITE, GREY, BLACK = 0, 1, 2
colour = {n: WHITE for n in all_names}
for start in sorted(all_names):
    if colour[start] != WHITE:
        continue
    stack = [(start, iter(graph_requires.get(start, [])))]
    colour[start] = GREY
    path = [start]
    while stack:
        node, it = stack[-1]
        advanced = False
        for dep in it:
            if dep not in all_names:
                continue
            if colour[dep] == GREY:
                cycle = path[path.index(dep):] + [dep]
                errors.append(f"requires cycle: {' -> '.join(cycle)}")
            elif colour[dep] == WHITE:
                colour[dep] = GREY
                path.append(dep)
                stack.append((dep, iter(graph_requires.get(dep, []))))
                advanced = True
                break
        if not advanced:
            colour[node] = BLACK
            path.pop()
            stack.pop()

# --- 10. internal project skills (.claude/skills/) ---------------------------
# Внутренние скиллы разработки реестра: НЕ экспортируются и НЕ попадают в
# skills.json — линтуются мягко (только name+description, без полей реестра).
registry_names = set(seen_names)
for skill_md in sorted(root.glob(".claude/skills/*/SKILL.md")):
    rel = skill_md.relative_to(root)
    fm = parse_frontmatter(skill_md)
    if fm is None:
        errors.append(f"{rel}: missing frontmatter block")
        continue
    name = fm.get("name", "").strip().strip('"').strip("'")
    if not name or not fm.get("description"):
        errors.append(f"{rel}: internal skill needs name + description")
        continue
    if not KEBAB_RE.match(name):
        errors.append(f"{rel}: name must be kebab-case")
    if name != skill_md.parent.name:
        errors.append(f"{rel}: name '{name}' must match dir '{skill_md.parent.name}'")
    if name in registry_names:
        warnings.append(
            f"{rel}: internal skill name '{name}' collides with a registry skill")

# --- report ----------------------------------------------------------------
for w in warnings:
    print(f"WARN: {w}")
for e in errors:
    print(f"ERROR: {e}")

checked = len(skill_files)
if errors:
    print(f"\n{checked} skills checked — {len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1)
print(f"{checked} skills checked — all valid ({len(warnings)} warning(s))")
PY

# --- 11. CLI + shell scripts ---------------------------------------------------
[[ -x "$REPO_ROOT/bin/swissknifeman" ]] || {
  echo "ERROR: bin/swissknifeman missing or not executable" >&2; exit 1; }
for sh in "$REPO_ROOT/bin/swissknifeman" "$REPO_ROOT/install.sh" \
          "$REPO_ROOT/sync.sh" "$REPO_ROOT"/scripts/*.sh; do
  bash -n "$sh" || { echo "ERROR: bash -n failed: $sh" >&2; exit 1; }
done
echo "CLI + shell scripts: syntax OK"

# --- 12. lib/swissknifeman package + unit/integration tests --------------------
[[ -d "$REPO_ROOT/lib/swissknifeman" ]] || {
  echo "ERROR: lib/swissknifeman package missing" >&2; exit 1; }
PYTHONPATH="$REPO_ROOT/lib" python3 -c "import swissknifeman.cli" || {
  echo "ERROR: lib/swissknifeman fails to import" >&2; exit 1; }
"$REPO_ROOT/scripts/test.sh" || { echo "ERROR: tests failed" >&2; exit 1; }
