#!/usr/bin/env bash
# sync.sh — DEPRECATED: use `skiller registry`.
#
# One-release compatibility wrapper. Brain-sync was removed; brain is an
# ordinary consumer project (`cd <brain> && skiller vendor`, then `skiller update`).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: ./sync.sh --update-registry   (deprecated -> skiller registry)

Brain-sync deleted. Connection brain as a normal project:
  cd <brain> && skiller vendor    # then: skiller update
EOF
}

case "${1:-}" in
  --update-registry)
    echo "DEPRECATED: sync.sh --update-registry replaced with: skiller registry" >&2
    exec "$REPO_ROOT/bin/skiller" registry
    ;;
  --brain|--dry-run)
    echo "ERROR: brain-sync deleted - register brain as a normal project:" >&2
    echo "  cd <brain> && skiller vendor" >&2
    exit 1
    ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 1 ;;
esac
