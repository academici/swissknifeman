#!/usr/bin/env bash
set -euo pipefail
ORCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ORCH_ROOT"
PYTHONPATH=lib python3 -m unittest discover -s tests -t . "$@"
