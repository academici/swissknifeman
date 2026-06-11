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
meta_skill = root / "generate-skill/SKILL.md"
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
        sorted((root / "generate-skill").glob("upstream.json")):
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
