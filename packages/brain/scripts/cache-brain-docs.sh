#!/usr/bin/env bash
# Cache project BRAIN documents in maind memory for `maind memory recall`.
# maind is taken from $MAIND_BIN or PATH.
#
# `maind memory store` and --key/--file do not exist. The write command is
# `maind memory remember`; it accepts --project|--scope, --share, --type, and --json.
# Pass the document topic (for example docs:brd) through --type.
#
# Usage:
#   cache-brain-docs.sh --scope project:<ns> <topic>=<path/to/file.md> [<topic>=<path> ...]
#
# Example:
#   cache-brain-docs.sh --scope project:loqum \
#     docs:brd=docs-private/dev/BRD.md \
#     docs:architecture=docs-private/dev/Architecture_Loqum.md
#
# Recall later:
#   maind memory recall --scope project:loqum "docs:brd"
set -euo pipefail

MAIND_BIN="${MAIND_BIN:-maind}"
if ! command -v "$MAIND_BIN" >/dev/null 2>&1; then
  echo "ERROR: maind not found; set MAIND_BIN" >&2
  exit 1
fi

usage() {
  echo "Usage: $0 --scope <scope> <topic>=<path> [<topic>=<path> ...]" >&2
  echo "  (or --project <id> instead of --scope)" >&2
  exit 1
}

[ $# -ge 2 ] || usage

SCOPE_ARGS=()
case "$1" in
  --scope)   SCOPE_ARGS=(--scope "$2");   shift 2 ;;
  --project) SCOPE_ARGS=(--project "$2"); shift 2 ;;
  *) usage ;;
esac

[ $# -ge 1 ] || usage

for pair in "$@"; do
  topic="${pair%%=*}"
  path="${pair#*=}"
  if [ "$topic" = "$pair" ] || [ -z "$path" ]; then
    echo "ERROR: format expected <topic>=<path>, received: $pair" >&2
    exit 1
  fi
  if [ ! -f "$path" ]; then
    echo "WARN: file not found, skip: $path" >&2
    continue
  fi
  content="$(cat -- "$path")"
  echo "→ remember ${SCOPE_ARGS[*]} --type $topic ← $path"
  "$MAIND_BIN" memory remember "${SCOPE_ARGS[@]}" --type "$topic" "$content"
done
