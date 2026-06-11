#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAIN_PATH="${BRAIN_PATH:-}"
UPDATE_REGISTRY=false
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: ./sync.sh [options]

Sync skills to academici/brain and update registry hashes.

Note: there is no separate Obsidian sync — brain is the vault target.

Options:
  --brain PATH          Path to brain repo (or set BRAIN_PATH)
  --update-registry     Recalculate sha256 in skills.json
  --dry-run             Show actions without copying
  -h, --help            Show help

Examples:
  BRAIN_PATH=~/projects/brain ./sync.sh
  ./sync.sh --update-registry
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --brain) BRAIN_PATH="$2"; shift 2 ;;
    --update-registry) UPDATE_REGISTRY=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

update_registry() {
  python3 - "$REPO_ROOT" <<'PY'
import json, hashlib, sys
from pathlib import Path

root = Path(sys.argv[1])
skills = []
references = []
MARKETPLACE_NAME = "swissknifeman"
OWNER = {"name": "Dmitry Vostrikov", "email": "dv.vostrikov@gmail.com"}


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_frontmatter(path):
    """Keys from the first ----delimited block only (body lines ignored)."""
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines()
    fm = {}
    if not lines or lines[0].strip() != "---":
        return fm
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


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
    name = fm.get("name") or name
    sha = hashlib.sha256(skill_md.read_bytes()).hexdigest()
    entry = {
        "name": name,
        "bucket": bucket,
        "path": str(rel),
        "version": fm.get("version") or "0.1.0",
        "description": fm.get("description", ""),
        "sha256": sha,
    }
    # Provenance: upstream.json next to SKILL.md marks an externally-sourced skill
    upstream_file = skill_md.parent / "upstream.json"
    if upstream_file.exists():
        up = json.loads(upstream_file.read_text(encoding="utf-8"))
        files = up.get("files", [])
        main = next((f for f in files if f.get("path") == "SKILL.md"),
                    files[0] if files else {})
        entry["source"] = up.get("source", "http")
        entry["upstream"] = main.get("url", "")
        if main.get("fetched_at"):
            entry["fetched_at"] = main["fetched_at"]
    else:
        entry["source"] = "local"
    skills.append(entry)

for ref in sorted((root / "skills/oss-dev/references").glob("*.md")):
    references.append({
        "name": ref.stem,
        "path": str(ref.relative_to(root)),
        "parent": "oss-development",
        "sha256": hashlib.sha256(ref.read_bytes()).hexdigest(),
    })

buckets = {}
for s in skills:
    b = s["bucket"]
    buckets.setdefault(b, 0)
    buckets[b] += 1

# --- bucket metadata (buckets.json) ----------------------------------------
meta_file = root / "buckets.json"
if not meta_file.exists():
    die("buckets.json not found — every bucket needs description/category/tags")
bucket_meta = json.loads(meta_file.read_text(encoding="utf-8"))
bucket_dirs = sorted(d.name for d in (root / "skills").iterdir() if d.is_dir())
missing = [b for b in bucket_dirs if b not in bucket_meta]
orphans = [b for b in bucket_meta if b not in bucket_dirs]
if missing:
    die(f"buckets.json: missing entries for: {', '.join(missing)}")
if orphans:
    die(f"buckets.json: entries without skills/ dir: {', '.join(orphans)}")

registry = {
    "version": 4,
    "name": "swissknifeman",
    "repository": "https://github.com/academici/swissknifeman",
    "schema": "https://github.com/academici/swissknifeman/blob/main/SKILL_TEMPLATE.md",
    "buckets": {b: {"description": bucket_meta[b]["description"],
                    "count": c, "status": "active"}
                for b, c in sorted(buckets.items())},
    "skills": skills,
    "references": references,
}

(root / "skills.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
print(f"Updated skills.json: {len(skills)} skills, {len(references)} references")

# --- Claude Code plugin manifests -------------------------------------------
# Each bucket is a plugin; skills are discovered via plugin.json "skills" dirs.
def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def skills_dirs(plugin_root):
    """Dirs (relative, ./-prefixed) whose subdirs contain SKILL.md files."""
    dirs = set()
    for skill_md in plugin_root.rglob("SKILL.md"):
        rel = skill_md.parent.parent.relative_to(plugin_root)
        dirs.add("./" if str(rel) == "." else f"./{rel.as_posix()}")
    return sorted(dirs)


marketplace_plugins = []
for bucket in bucket_dirs:
    bucket_dir = root / "skills" / bucket
    dirs = skills_dirs(bucket_dir)
    if not dirs:
        continue
    meta = bucket_meta[bucket]
    write_json(bucket_dir / ".claude-plugin" / "plugin.json", {
        "name": bucket,
        "description": meta["description"],
        "skills": dirs[0] if len(dirs) == 1 else dirs,
    })
    marketplace_plugins.append({
        "name": bucket,
        "source": f"./skills/{bucket}",
        "description": meta["description"],
        "category": meta.get("category", ""),
        "tags": meta.get("tags", []),
    })

meta_skill_dir = root / "generate-skill"
meta_fm = parse_frontmatter(meta_skill_dir / "generate-skill" / "SKILL.md")
write_json(meta_skill_dir / ".claude-plugin" / "plugin.json", {
    "name": "generate-skill",
    "description": meta_fm.get("description", "Meta-skill for creating new skills"),
    "skills": "./",
})
marketplace_plugins.append({
    "name": "generate-skill",
    "source": "./generate-skill",
    "description": meta_fm.get("description", "Meta-skill for creating new skills"),
    "category": "meta",
    "tags": ["meta", "authoring"],
})

write_json(root / ".claude-plugin" / "marketplace.json", {
    "name": MARKETPLACE_NAME,
    "owner": OWNER,
    "plugins": sorted(marketplace_plugins, key=lambda p: p["name"]),
})
print(f"Updated plugin manifests: {len(marketplace_plugins)} plugins "
      f"(.claude-plugin/marketplace.json)")
PY
}

sync_to_brain() {
  if [[ -z "$BRAIN_PATH" || ! -d "$BRAIN_PATH" ]]; then
    echo "BRAIN_PATH not set or directory missing. Skipping brain sync."
    return 0
  fi

  local dest="$BRAIN_PATH/.ai/skills-registry"
  echo "Syncing skills to $dest"

  if [[ "$DRY_RUN" == true ]]; then
    echo "[dry-run] Would copy $REPO_ROOT/skills -> $dest"
    echo "[dry-run] Would copy skills.json -> $BRAIN_PATH/skills-lock.json"
    return 0
  fi

  mkdir -p "$dest"
  rsync -a --delete --exclude='.claude-plugin' "$REPO_ROOT/skills/" "$dest/"
  cp "$REPO_ROOT/skills.json" "$BRAIN_PATH/skills-lock.json"
  echo "Synced to brain"
}

if [[ "$UPDATE_REGISTRY" == true ]]; then
  update_registry
fi

sync_to_brain
