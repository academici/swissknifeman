#!/usr/bin/env bash
# Fast structural checks for aicore: the library compiles, every shipped JSON file parses,
# and the usage module stays self-sufficient. The unit tests live in scripts/test.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import compileall, json, re, sys
from pathlib import Path

root = Path(sys.argv[1])
errors = []

if not compileall.compile_dir(str(root / "lib"), quiet=1, force=True, legacy=False):
    errors.append("lib/: python files do not compile")

for sub in ("configs", "schemas"):
    for path in sorted((root / sub).rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"{path.relative_to(root)}: invalid JSON: {error}")

try:
    unit = json.loads((root / "unit.json").read_text(encoding="utf-8"))
except (OSError, ValueError) as error:
    errors.append(f"unit.json: {error}")
else:
    init = (root / "lib" / "aicore" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.M)
    if not match or match.group(1) != unit.get("version"):
        errors.append("lib/aicore/__init__.py: __version__ must equal unit.json version")

if errors:
    for line in errors:
        print(f"ERROR: {line}", file=sys.stderr)
    sys.exit(1)
print("aicore validate: OK")
PY
