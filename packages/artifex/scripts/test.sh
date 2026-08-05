#!/usr/bin/env bash
set -euo pipefail

artifex_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${artifex_dir}/lib${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 -m unittest discover -s "${artifex_dir}/tests" -p 'test_*.py'
