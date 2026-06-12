#!/usr/bin/env bash
# sync.sh — DEPRECATED: используйте `swissknifeman registry`.
#
# Тонкий wrapper на один релиз. Brain-sync удалён: brain — обычный
# потребляющий проект (cd <brain> && swissknifeman vendor, далее
# swissknifeman update).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: ./sync.sh --update-registry   (deprecated -> swissknifeman registry)

Brain-sync удалён. Подключение brain как обычного проекта:
  cd <brain> && swissknifeman vendor    # затем: swissknifeman update
EOF
}

case "${1:-}" in
  --update-registry)
    echo "DEPRECATED: sync.sh --update-registry заменён на: swissknifeman registry" >&2
    exec "$REPO_ROOT/bin/swissknifeman" registry
    ;;
  --brain|--dry-run)
    echo "ERROR: brain-sync удалён — зарегистрируйте brain как обычный проект:" >&2
    echo "  cd <brain> && swissknifeman vendor" >&2
    exit 1
    ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 1 ;;
esac
