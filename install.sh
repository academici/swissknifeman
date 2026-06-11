#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-${HOME}/.ai/skills}"
BUCKET="${2:-all}"

usage() {
  cat <<'EOF'
Usage: ./install.sh [target_dir] [bucket]

Install skills from academici/swissknifeman registry.

  target_dir  Destination (default: ~/.ai/skills)
  bucket      Specific bucket or 'all' (default: all)

Examples:
  ./install.sh
  ./install.sh ~/.cursor/skills php
  ./install.sh /path/to/brain/.ai/skills devops
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

mkdir -p "$TARGET"

install_bucket() {
  local bucket="$1"
  local src="$REPO_ROOT/skills/$bucket"
  [[ -d "$src" ]] || return 0
  echo "Installing bucket: $bucket"
  cp -r "$src" "$TARGET/"
}

if [[ "$BUCKET" == "all" ]]; then
  for dir in "$REPO_ROOT"/skills/*/; do
    install_bucket "$(basename "$dir")"
  done
  if [[ -d "$REPO_ROOT/generate-skill" ]]; then
    cp -r "$REPO_ROOT/generate-skill" "$TARGET/../generate-skill" 2>/dev/null || true
  fi
else
  install_bucket "$BUCKET"
fi

echo "Installed to $TARGET"
echo "Registry: $REPO_ROOT/skills.json"
