#!/usr/bin/env python3
"""Independently validate the minimized P4.6 effective-hook evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path


EXPECTED_ACTIONS = [
    {"id": "harness.codex.lifecycle.hooks", "observation": "stale-source",
     "action": "update", "reason": "source-changed"},
    {"id": "harness.codex.lifecycle.handler", "observation": "stale-source",
     "action": "update", "reason": "source-changed"},
]
EXPECTED_KEYS = {
    "schema_version", "command", "pre_repair", "repair", "post_repair",
    "generated_sha256", "packages_core_diff_sha256",
}


def fail(message: str) -> None:
    raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def root_for(script: Path) -> Path:
    return script.resolve().parents[4]


def package_core_digest(root: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "--binary", "--", "packages", "core"], cwd=root,
        capture_output=True, check=False,
    )
    if result.returncode:
        fail("git diff packages/core failed")
    return hashlib.sha256(result.stdout).hexdigest()


def validate(value: object, *, root: Path, expected_target: str, expected_provider: str) -> None:
    if not isinstance(value, dict) or set(value) != EXPECTED_KEYS:
        fail("evidence shape")
    if value["schema_version"] != "p4-hook-integrity-v1":
        fail("schema version")

    command = value["command"]
    if command != {
        "argv": ["packages/harness/bin/harness", "hooks"],
        "provider": expected_provider,
        "target": expected_target,
        "flags": ["observer", "trusted"],
    }:
        fail("command/target/provider/flags")
    target = Path(expected_target)
    if not target.is_absolute() or target.resolve() != root:
        fail("absolute repository target")

    pre = value["pre_repair"]
    if not isinstance(pre, dict) or set(pre) != {"exit_code", "plan_sha256", "status", "actions"}:
        fail("pre-repair shape")
    if pre["exit_code"] != 0 or pre["status"] != "warning" or pre["actions"] != EXPECTED_ACTIONS:
        fail("pre-repair exact stale-source actions")
    if not isinstance(pre["plan_sha256"], str) or not pre["plan_sha256"].startswith("sha256:"):
        fail("pre-repair plan hash")

    repair = value["repair"]
    if repair != {"invocations": 1, "exit_code": 0,
                  "planned_actions": [row["id"] for row in EXPECTED_ACTIONS]}:
        fail("one successful repair")

    post = value["post_repair"]
    if not isinstance(post, dict) or set(post) != {"exit_code", "plan_sha256", "status", "actions"}:
        fail("post-repair shape")
    if post["exit_code"] != 0 or post["status"] != "green" or post["actions"] != []:
        fail("literal green with zero residual actions")
    if not isinstance(post["plan_sha256"], str) or not post["plan_sha256"].startswith("sha256:"):
        fail("post-repair plan hash")

    rendered = value["generated_sha256"]
    if not isinstance(rendered, dict) or set(rendered) != {".codex/hooks.json", ".codex/hooks/lifecycle.py"}:
        fail("generated hash set")
    for relative, expected in rendered.items():
        if not isinstance(expected, str) or len(expected) != 64 or digest(root / relative) != expected:
            fail(f"generated hash mismatch: {relative}")
    if value["packages_core_diff_sha256"] != package_core_digest(root):
        fail("packages/core diff digest")


def self_test(root: Path) -> None:
    baseline = json.loads((root / "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/hook-integrity-results-v1.json").read_text())
    target = str(root)
    validate(baseline, root=root, expected_target=target, expected_provider="codex")
    fixtures = {
        "exit-0-warning": lambda x: x["post_repair"].update(status="warning"),
        "wrong-root": lambda x: x["command"].update(target="/tmp"),
        "wrong-provider": lambda x: x["command"].update(provider="claude-code"),
        "wrong-flags": lambda x: x["command"].update(flags=[]),
        "residual-stale": lambda x: x["post_repair"].update(actions=[EXPECTED_ACTIONS[0]]),
        "unexpected-action": lambda x: x["pre_repair"].update(actions=EXPECTED_ACTIONS + [EXPECTED_ACTIONS[0]]),
        "missing-plan-hash": lambda x: x["post_repair"].pop("plan_sha256"),
        "repair-refusal": lambda x: x["repair"].update(exit_code=1),
    }
    for name, mutate in fixtures.items():
        candidate = deepcopy(baseline)
        mutate(candidate)
        try:
            validate(candidate, root=root, expected_target=target, expected_provider="codex")
        except ValueError:
            continue
        fail(f"fixture accepted: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path)
    parser.add_argument("--expected-target")
    parser.add_argument("--expected-provider")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    root = root_for(Path(__file__))
    if args.self_test:
        self_test(root)
        print("hook integrity validator self-test: OK")
        return 0
    if not args.results or not args.expected_target or not args.expected_provider:
        parser.error("--results, --expected-target, and --expected-provider are required")
    validate(json.loads(args.results.read_text(encoding="utf-8")), root=root,
             expected_target=args.expected_target, expected_provider=args.expected_provider)
    print("hook integrity validator: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"hook integrity validator: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
