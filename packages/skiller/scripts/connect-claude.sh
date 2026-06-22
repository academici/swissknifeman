#!/usr/bin/env bash
# connect-claude.sh — DEPRECATED: используйте `skiller connect`.
#
# Тонкий wrapper на один релиз: транслирует старые флаги в CLI.
#   ./scripts/connect-claude.sh --target DIR [--profile P | --plugins a,b]
#                               [--file F] [--cleanup-vendored] [--list]
#                               [--dry-run] [--hub]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "DEPRECATED: connect-claude.sh заменён CLI — cd <project> && skiller connect" >&2
exec "$REPO_ROOT/bin/skiller" connect "$@"
