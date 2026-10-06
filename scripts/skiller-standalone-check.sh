#!/usr/bin/env bash
# Prove Skiller works with only its tracked files and the shared core dependency.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
standalone_tmp="$(mktemp -d /tmp/skiller-standalone.XXXXXXXX)"
trap 'rm -rf "$standalone_tmp"' EXIT

python3 - "$REPO_ROOT" "$standalone_tmp" <<'PY'
import shutil
import subprocess
import sys
from pathlib import Path

root, destination = map(Path, sys.argv[1:])
tracked = subprocess.check_output(
    ["git", "ls-files", "-z", "--", "packages/skiller", "core",
     "configs/provider-capabilities.json", "configs/provider-distribution.json",
     "configs/provider-projection.json"], cwd=root)
for entry in tracked.decode("utf-8").split("\0"):
    if not entry:
        continue
    relative = Path(entry)
    if "node_modules" in relative.parts:
        continue
    if relative.parts[:2] == ("packages", "skiller"):
        target = destination / "vendor" / "skiller" / relative.relative_to("packages/skiller")
    else:
        target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / relative, target, follow_symlinks=False)
PY

cd "$standalone_tmp/vendor/skiller"
echo "Standalone Skiller: tracked package + core (including shared provider data), no repository or host config"
env -u PYTHONPATH -u SKILLER_HOST_CONFIG bash scripts/test.sh
# Marketplaces live outside the package in the host checkout. Render them for
# this standalone layout so validation retains its publication drift checks.
env -u PYTHONPATH -u SKILLER_HOST_CONFIG bash bin/skiller registry
env -u PYTHONPATH -u SKILLER_HOST_CONFIG bash scripts/validate.sh
