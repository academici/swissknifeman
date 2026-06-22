#!/usr/bin/env bash
# SCAN → ANALYZE → EXTRACT pipeline for skills discovery
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${REPO_ROOT}/.skills-scanner.json"
THRESHOLD=60
EXTRACT=false
OUTPUT_DIR="${REPO_ROOT}/.scanner-output"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --extract) EXTRACT=true; shift ;;
    --threshold) THRESHOLD="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: scan-skills.sh [--extract] [--threshold N]"
      exit 0
      ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

if [[ ! -f "$CONFIG" ]]; then
  echo "Missing $CONFIG"
  exit 1
fi

scan_paths=$(python3 -c "import json; print('\n'.join(json.load(open('$CONFIG'))['scan_paths']))")
exclude_patterns=("vendor/" "node_modules/" ".git/" "storage/")

should_exclude() {
  local path="$1"
  for pat in "${exclude_patterns[@]}"; do
    [[ "$path" == *"$pat"* ]] && return 0
  done
  return 1
}

quality_score() {
  local file="$1"
  local score=0
  grep -qE '/\*\*|#\s|declare\(strict' "$file" 2>/dev/null && score=$((score + 20)) || true
  grep -qE ':\s*(string|int|bool|array|void|float|\?)' "$file" 2>/dev/null && score=$((score + 20)) || true
  local lines
  lines=$(wc -l < "$file")
  [[ "$lines" -le 100 ]] && score=$((score + 20)) || score=$((score + 10))
  ! grep -qE '\b[0-9]{3,}\b' "$file" 2>/dev/null && score=$((score + 20)) || score=$((score + 10))
  score=$((score + 20))
  echo "$score"
}

anonymize_snippet() {
  local src="$1"
  local dest="$2"
  local project
  project=$(echo "$src" | sed -E 's|.*/projects/([^/]+).*|\1|')
  {
    echo "<?php"
    echo ""
    echo "// Source: ${project}/$(basename "$src") (anonymized)"
    echo ""
    sed -E \
      -e 's/namespace [A-Za-z0-9\\]+;/namespace App\\Snippets;/' \
      -e 's/use [A-Za-z0-9\\]+\\[A-Za-z0-9\\]+;//g' \
      "$src" | tail -n +2
  } > "$dest" 2>/dev/null || cp "$src" "$dest"
}

guess_bucket() {
  local path="$1"
  case "$path" in
    *azguard*|*permission*|*auth*) echo "php/laravel-permissions" ;;
    *botkit*|*bot*) echo "php/botkit" ;;
    *filament*) echo "php/filament" ;;
    *docker*|*compose*) echo "devops/docker" ;;
    *) echo "php/laravel" ;;
  esac
}

echo "=== SCAN ==="
candidates=()
while IFS= read -r scan_path; do
  expanded="${scan_path/#\~/$HOME}"
  for path in $expanded; do
    [[ -e "$path" ]] || continue
    while IFS= read -r -d '' file; do
      should_exclude "$file" && continue
      case "$file" in
        *.php|*.yml|*.yaml|*.sh|*.env.example) ;;
        *) continue ;;
      esac
      score=$(quality_score "$file")
      if [[ "$score" -ge "$THRESHOLD" ]]; then
        candidates+=("$file:$score")
        echo "  [$score] $file"
      fi
    done < <(find "$path" -type f \( -name "*.php" -o -name "*.yml" -o -name "*.yaml" -o -name "*.sh" -o -name ".env.example" \) -print0 2>/dev/null)
  done
done <<< "$scan_paths"

echo ""
echo "=== ANALYZE: ${#candidates[@]} candidates (threshold >= $THRESHOLD) ==="

if [[ "$EXTRACT" == true && ${#candidates[@]} -gt 0 ]]; then
  echo "=== EXTRACT ==="
  rm -rf "$OUTPUT_DIR"
  mkdir -p "$OUTPUT_DIR"
  manifest="${OUTPUT_DIR}/candidates.json"
  echo "[" > "$manifest"
  first=true
  for entry in "${candidates[@]}"; do
    file="${entry%%:*}"
    score="${entry##*:}"
    bucket=$(guess_bucket "$file")
    basename=$(basename "$file")
    dest_dir="${OUTPUT_DIR}/${bucket}/snippets"
    mkdir -p "$dest_dir"
    dest_file="${dest_dir}/${basename}"
    if [[ "$file" == *.php ]]; then
      anonymize_snippet "$file" "$dest_file"
    else
      cp "$file" "$dest_file"
    fi
    $first || echo "," >> "$manifest"
    first=false
    python3 -c "
import json
print(json.dumps({'source': '$file', 'score': $score, 'bucket': '$bucket', 'snippet': '$basename'}), end='')
" >> "$manifest"
    echo "  -> ${bucket}/snippets/${basename}"
  done
  echo "" >> "$manifest"
  echo "]" >> "$manifest"
  echo "Extracted to ${OUTPUT_DIR}/"
fi
