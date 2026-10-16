#!/usr/bin/env python3
"""Node/pnpm preflight: prints one check-result/v1 JSON, exit 1 on fail."""
import json
import shutil
import subprocess
import sys

CHECK_ID = "node-pnpm-preflight.tools"
SCHEMA = "urn:swissknifeman:aicore:check-result:v1"


def _version(tool):
    path = shutil.which(tool)
    if not path:
        return None, None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return path, None
    return path, out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def run():
    evidence, missing = [], []
    for tool in ("node", "pnpm"):
        path, version = _version(tool)
        if version:
            evidence.append(f"{tool} {version} ({path})")
        else:
            missing.append(tool)
    if not missing:
        return {"$schema": SCHEMA, "check_id": CHECK_ID, "status": "ok", "category": "environment",
                "observed": "node and pnpm are available", "evidence": evidence}
    return {"$schema": SCHEMA, "check_id": CHECK_ID, "status": "fail", "category": "environment",
            "observed": "not available in this shell: " + ", ".join(missing), "evidence": evidence,
            "remediation": "run `nvm use 22`, then rerun; if still missing report a blocker and do not skip hooks"}


if __name__ == "__main__":
    result = run()
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(1 if result["status"] == "fail" else 0)
