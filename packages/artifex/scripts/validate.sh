#!/usr/bin/env bash
set -euo pipefail

artifex_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
bash "${artifex_dir}/scripts/test.sh"
"${artifex_dir}/bin/artifex" --help >/dev/null
if rg -n 'plans/2026\.08\.03-ARTIFEX-SUPERVISOR|artifacts/supervisor' "${artifex_dir}" --glob '*.py' --glob artifex; then
  echo 'artifex validation: package runtime references plan-local evidence' >&2
  exit 1
fi
echo 'artifex validation: OK'
