#!/usr/bin/env bash
# sync.sh — DEPRECATED: используйте `skiller registry`.
#
# Тонкий wrapper на один релиз. Brain-sync удалён: brain — обычный
# потребляющий проект (cd <brain> && skiller vendor, далее
# skiller update).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: ./sync.sh --update-registry   (deprecated -> skiller registry)

Brain-sync удалён. Подключение brain как обычного проекта:
  cd <brain> && skiller vendor    # затем: skiller update
EOF
}

case "${1:-}" in
  --update-registry)
    echo "DEPRECATED: sync.sh --update-registry заменён на: skiller registry" >&2
    exec "$REPO_ROOT/bin/skiller" registry
    ;;
  --brain|--dry-run)
    echo "ERROR: brain-sync удалён — зарегистрируйте brain как обычный проект:" >&2
    echo "  cd <brain> && skiller vendor" >&2
    exit 1
    ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 1 ;;
esac
