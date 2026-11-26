#!/usr/bin/env python3
"""Optional check of the Docker environment: is the daemon reachable, how far does its authority go, do the credential
helper and compose work. Docker is not required by orch; without it every row is `skip`.

    docker-env-check.py [--json]

Exit 1 only for a `fail` row (a broken credential helper); a `warn` is advice (docs/docker-environment.md).

A probe of the environment doctor, apart from orchestration: no run calls it and `orch.py doctor` does not."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from orch import docker_env  # noqa: E402


def main(argv=None) -> int:
    rows = docker_env.check()
    if "--json" in (sys.argv[1:] if argv is None else argv):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{row['status'].upper():5} {row['check_id']}: {row['observed']}")
            for line in row.get("evidence", []):
                print(f"        {line}")
            if row.get("remediation"):
                print(f"        fix: {row['remediation']}")
    return 1 if any(row["status"] == "fail" for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
