#!/usr/bin/env python3
"""Mutate one copied P0.5 carrier at a time and require production rejection."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / "plans" / "2026.08.02-PROVIDER-CONTRACT-LOCALE" / "artifacts" / "P0.1" / "evidence"
VERIFY = EVIDENCE / "verify.py"


def document(bundle: Path, name: str) -> dict:
    return json.loads((bundle / name).read_text(encoding="utf-8"))


def save(bundle: Path, name: str, value: dict) -> None:
    (bundle / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def mutate(name: str, callback: Callable[[Path], None], expected: str) -> tuple[str, Callable[[Path], None], str]:
    return name, callback, expected


def cases() -> list[tuple[str, Callable[[Path], None], str]]:
    return [
        mutate("missing-project", lambda bundle: (lambda value: (value["projects"].pop(), save(bundle, "project-registry-redacted.json", value)))(document(bundle, "project-registry-redacted.json")), "coverage: missing-project"),
        mutate("extra-provider-path", lambda bundle: (lambda value: (value["projects"][0]["provider_paths"].append({"artifact_id": "artifact-extra", "path": ".agents/EXTRA-NOT-IN-FLEET", "node": "file"}), save(bundle, "provider-source-snapshot.json", value)))(document(bundle, "provider-source-snapshot.json")), "coverage: provider-path-exact-set"),
        mutate("missing-provider-path", lambda bundle: (lambda value: (value["projects"][0]["provider_paths"].pop(), save(bundle, "provider-source-snapshot.json", value)))(document(bundle, "provider-source-snapshot.json")), "coverage: provider-path-exact-set"),
        mutate("duplicate-project", lambda bundle: (lambda value: (value["projects"].append(value["projects"][0]), save(bundle, "project-registry-redacted.json", value)))(document(bundle, "project-registry-redacted.json")), "registry: duplicate-or-malformed-project-id"),
        mutate("duplicate-provider", lambda bundle: (lambda value: (value["provider_rows"].append(value["provider_rows"][0]), save(bundle, "provider-fleet-inventory.json", value)))(document(bundle, "provider-fleet-inventory.json")), "provider-row: duplicate"),
        mutate("duplicate-artifact-id", lambda bundle: (lambda value: (value["projects"][0]["provider_paths"][0].update({"artifact_id": value["projects"][0]["provider_paths"][1]["artifact_id"]}), save(bundle, "provider-source-snapshot.json", value)))(document(bundle, "provider-source-snapshot.json")), "artifact: duplicate-id"),
        mutate("absolute-root", lambda bundle: (lambda value: (value["projects"][0]["provider_paths"][0].update({"path": "/home/example/leak"}), save(bundle, "provider-source-snapshot.json", value)))(document(bundle, "provider-source-snapshot.json")), "privacy: absolute-or-malformed-path"),
        mutate("secret-like-value", lambda bundle: (lambda value: (value["commands"].update({"leak": {"command": ["sk-abcdefghijklmnop"], "availability": "available"}}), save(bundle, "command-results-redacted.json", value)))(document(bundle, "command-results-redacted.json")), "privacy: absolute-or-secret-leak"),
        mutate("secret-digest", lambda bundle: (lambda value: (value["commands"]["maind_health"].update({"secret_digest": "deadbeef"}), save(bundle, "command-results-redacted.json", value)))(document(bundle, "command-results-redacted.json")), "privacy: absolute-or-secret-leak"),
        mutate("bundle-member-mismatch", lambda bundle: (lambda value: (value["files"].pop(), save(bundle, "manifest.json", value)))(document(bundle, "manifest.json")), "BUNDLE_PRIVACY_MISMATCH"),
        mutate("broken-symlink-misclassification", lambda bundle: (lambda value: (value["projects"][0]["provider_paths"].append({"artifact_id": "artifact-symlink", "path": ".agents/broken", "node": "symlink", "target_state": "healthy"}), save(bundle, "provider-source-snapshot.json", value)))(document(bundle, "provider-source-snapshot.json")), "symlink: invalid-target-state"),
        mutate("unsupported-provider", lambda bundle: (lambda value: (value["provider_rows"][0].update({"provider": "unsupported"}), save(bundle, "provider-fleet-inventory.json", value)))(document(bundle, "provider-fleet-inventory.json")), "coverage: unsupported-provider"),
        mutate("malformed-command-result", lambda bundle: (lambda value: (value["commands"].update({"bad": {"availability": "available"}}), save(bundle, "command-results-redacted.json", value)))(document(bundle, "command-results-redacted.json")), "command-result: malformed-bad"),
        mutate("measurement-less-command-result", lambda bundle: (lambda value: (value.update({"skills_baseline": {"availability": "available"}}), save(bundle, "command-results-redacted.json", value)))(document(bundle, "command-results-redacted.json")), "measurement: missing-source-count"),
    ]


def main() -> int:
    for name, callback, expected in cases():
        with tempfile.TemporaryDirectory(prefix="p0.5-") as temporary:
            bundle = Path(temporary) / "bundle"
            shutil.copytree(EVIDENCE, bundle)
            callback(bundle)
            environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run([sys.executable, str(VERIFY), "--bundle", str(bundle)], text=True, capture_output=True, env=environment)
            output = result.stdout + result.stderr
            if result.returncode == 0 or expected not in output:
                print(f"fixture failed: {name}: expected {expected!r}, got {output!r}", file=sys.stderr)
                return 1
            print(f"fixture rejected: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
