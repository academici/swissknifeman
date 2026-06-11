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
    # Prefer frontmatter name when present
    content = skill_md.read_text(encoding="utf-8")
    for line in content.splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            break
    sha = hashlib.sha256(skill_md.read_bytes()).hexdigest()
    desc = ""
    for line in content.splitlines():
        if line.startswith("description:"):
            desc = line.split(":", 1)[1].strip().strip('"').strip("'")
            break
    skills.append({
        "name": name,
        "bucket": bucket,
        "path": str(rel),
        "version": "0.1.0",
        "description": desc,
        "sha256": sha,
    })

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

registry = {
    "version": 3,
    "name": "swissknifeman",
    "repository": "https://github.com/academici/swissknifeman",
    "schema": "https://github.com/academici/swissknifeman/blob/main/SKILL_TEMPLATE.md",
    "buckets": {b: {"count": c, "status": "active"} for b, c in sorted(buckets.items())},
    "skills": skills,
    "references": references,
}

(root / "skills.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
print(f"Updated skills.json: {len(skills)} skills, {len(references)} references")
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
  rsync -a --delete "$REPO_ROOT/skills/" "$dest/"
  cp "$REPO_ROOT/skills.json" "$BRAIN_PATH/skills-lock.json"
  echo "Synced to brain"
}

if [[ "$UPDATE_REGISTRY" == true ]]; then
  update_registry
fi

sync_to_brain
