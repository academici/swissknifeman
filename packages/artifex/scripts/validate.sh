#!/usr/bin/env bash
set -euo pipefail

artifex_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
bash "${artifex_dir}/scripts/test.sh"
"${artifex_dir}/bin/artifex" --help >/dev/null
if grep -rEn --include='*.py' --include='*.json' --include='*.md' --include=artifex \
  -e 'plans/20|artifacts/supervisor|[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[A-Z]' "${artifex_dir}"; then
  echo 'artifex validation: package references local-only plan directories or concrete plan IDs' >&2
  exit 1
fi
echo 'artifex validation: OK'
