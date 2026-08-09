#!/usr/bin/env python3
"""CLI for the durable P5 decision queue."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "lib"))

from task import plan_requests  # noqa: E402


def _json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Append-only очередь решений планов (P5.4)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("request", "resolve"):
        item = sub.add_parser(name)
        item.add_argument("--plan-dir", required=True)
        item.add_argument("--json", required=True, dest="json_path")
        item.add_argument("--actor", default="owner")
    request = sub.choices["request"]
    resolve = sub.choices["resolve"]
    resolve.add_argument("--decision-id", required=True)
    resolve.add_argument("--resolver-id", required=True)
    resolve.add_argument("--continuation")
    resolve.add_argument("--cold-start-reason")
    claim = sub.add_parser("claim")
    claim.add_argument("--plan-dir", required=True)
    claim.add_argument("--decision-id", required=True)
    claim.add_argument("--resolver-id", required=True)
    claim.add_argument("--lease-expires-at", required=True)
    claim.add_argument("--actor", default="owner")
    listing = sub.add_parser("list")
    listing.add_argument("--plan-dir", required=True)
    rendering = sub.add_parser("render")
    rendering.add_argument("--plan-dir", required=True)
    rendering.add_argument("--out")
    rendering.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "request":
            result = plan_requests.request(args.plan_dir, _json(args.json_path), actor=args.actor)
        elif args.command == "claim":
            result = plan_requests.claim(args.plan_dir, args.decision_id, resolver_id=args.resolver_id,
                                         lease_expires_at=args.lease_expires_at, actor=args.actor)
        elif args.command == "resolve":
            continuation = _json(args.continuation) if args.continuation else None
            result = plan_requests.resolve(args.plan_dir, args.decision_id, _json(args.json_path),
                                           resolver_id=args.resolver_id, current_continuation=continuation,
                                           resume_available=args.cold_start_reason is None,
                                           fallback_reason=args.cold_start_reason, actor=args.actor)
        elif args.command == "list":
            result = {key: {"resolved": value["response"] is not None,
                            "subject": value["request"]["subject"]}
                      for key, value in plan_requests.states(args.plan_dir).items()}
        else:
            print(plan_requests.render(args.plan_dir, out=args.out, check=args.check))
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
