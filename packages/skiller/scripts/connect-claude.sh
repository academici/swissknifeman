#!/usr/bin/env bash
# connect-claude.sh — DEPRECATED: use `skiller connect`.
#
# Thin wrapper per release: translates old flags to CLI.
#   ./scripts/connect-claude.sh --target DIR [--profile P | --plugins a,b]
#                               [--file F] [--cleanup-vendored] [--list]
#                               [--dry-run] [--hub]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "DEPRECATED: connect-claude.sh replaced CLI — cd <project> && skiller connect" >&2
exec "$REPO_ROOT/bin/skiller" connect "$@"
