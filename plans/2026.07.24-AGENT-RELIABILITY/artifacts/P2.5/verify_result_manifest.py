#!/usr/bin/env python3
"""verify_result_manifest.py -- the P2.5 owned verifier over the frozen bank's
candidate run (plans/2026.07.24-AGENT-RELIABILITY P2.5).

Does not re-implement grading: `run_bank.py` (P0.3, immutable) is the sole
executable owner of the grading engine (D30) and is what produced
`candidate-results.json` from real P1/P2 code (`task.task_contract`,
`task.review_policy`, `task.route_evidence`) exercised per historical case.
This script's own job is narrower and downstream of that: confirm
`bank-manifest.json` integrity, confirm `candidate-results.json` covers every
frozen case and every Code Guidance scenario category, and seal a P2.5-owned
`result-manifest.json` record -- counts, floor status, category coverage and
the exact named residual failures (never a silently dropped case, D30/D59).

stdlib-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA_VERSION = "p2.5-result-manifest/v1"

# phases/P2.md P2.5 Code Guidance -- the twelve named scenario categories,
# mapped onto the case_ids that exercise them.
CATEGORY_CASES = {
    "intra-session-loss": ["missing-launch-block-intra-session"],
    "stale-cold-start": ["stale-cold-start-item"],
    "five-audit-sequence": ["five-audit-loop"],
    "public-path": ["missed-consumer-cold-start"],
    "clean-short-control": ["honest-http-clean-control"],
    "simple-brief-only-positive": ["control-simple-brief-acceptance"],
    "committed-bundle-positive": ["control-committed-bundle-highrisk"],
    "predecessor-produced-positive": ["control-predecessor-produced-path"],
    "external-path-only-negative": ["portability-external-input"],
    "privacy-rawbulk-negative": ["portability-privacy-rawbulk"],
    "missing-manifest-verifier-negative": ["portability-input-missing-highrisk"],
    "claude-codex-renderer-parity": ["claude-only-carrier", "control-provider-neutral-rendering"],
}


def fail(message: str) -> None:
    print(f"ОШИБКА: {message}", file=sys.stderr)
    raise SystemExit(1)


def canonical(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(payload) -> str:
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def file_hash(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"файл не найден: {path}")
    except json.JSONDecodeError as exc:
        fail(f"невалидный JSON {path}: {exc}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="P2.5 -- verify a candidate reliability-bank run and seal its result manifest.")
    parser.add_argument("--bank-manifest", required=True,
                        help="path to the frozen artifacts/reliability-bank-v1/bank-manifest.json")
    parser.add_argument("--results", required=True,
                        help="path to candidate-results.json (produced by run_bank.py candidate)")
    parser.add_argument("--manifest", required=True,
                        help="output path for this item's own result-manifest.json")
    args = parser.parse_args(argv)

    bank_manifest = load_json(args.bank_manifest)
    bank_payload = {k: v for k, v in bank_manifest.items() if k != "content_hash"}
    if content_hash(bank_payload) != bank_manifest["content_hash"]:
        fail("bank-manifest.json: content_hash не сходится с телом манифеста")

    results = load_json(args.results)
    expected_count = bank_manifest["counts"]["cases"]
    if len(results.get("cases", [])) != expected_count:
        fail(f"candidate-results.json: {len(results.get('cases', []))} кейсов, "
             f"банк объявляет {expected_count} -- частичный прогон не считается результатом")

    by_id = {row["case_id"]: row for row in results["cases"]}
    problems = []
    for category, case_ids in CATEGORY_CASES.items():
        for cid in case_ids:
            if cid not in by_id:
                problems.append(f"category {category}: case_id {cid!r} отсутствует в results")
    if problems:
        for p in problems:
            print(f"  ОШИБКА: {p}", file=sys.stderr)
        fail(f"{len(problems)} категорий Code Guidance не покрыты кейсами results")

    categories = {}
    for category, case_ids in CATEGORY_CASES.items():
        rows = [by_id[cid] for cid in case_ids]
        categories[category] = {"case_ids": case_ids,
                                "passed": sum(1 for r in rows if r["passed"]),
                                "total": len(rows)}

    residual = [{"case_id": r["case_id"], "kind": r["kind"], "family": r["family"],
                "failed_checks": [c["id"] for c in r["checks"] if not c["ok"]]}
               for r in results["cases"] if not r["passed"]]

    floor_summary: dict[str, list[str]] = {}
    for row in results.get("floor_status", []):
        floor_summary.setdefault(row["status"].replace("-", "_"), []).append(row["id"])

    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "owner_item": "plans/2026.07.24-AGENT-RELIABILITY P2.5",
        "bank_version": bank_manifest["bank_version"],
        "grader_version": bank_manifest["grader_version"],
        "bank_manifest_content_hash": bank_manifest["content_hash"],
        "files": {
            "bank-manifest.json": file_hash(args.bank_manifest),
            "candidate-results.json": file_hash(args.results),
            "verify_result_manifest.py": file_hash(__file__),
        },
        "counts": {
            "cases": len(results["cases"]),
            "critical": bank_manifest["counts"]["critical"],
            "control": bank_manifest["counts"]["control"],
            "passed": sum(1 for r in results["cases"] if r["passed"]),
            "failed": len(residual),
        },
        "layer": results.get("layer"),
        "metrics": results.get("metrics"),
        "floor_status": results.get("floor_status"),
        "floor_summary": {k: sorted(v) for k, v in floor_summary.items()},
        "code_guidance_categories": categories,
        "residual_failures": residual,
        "note": ("Deferred floors (F4/F5/F6/F8/F9/F10) require measurement owners "
                 "outside this item (P1.4, P0.4, P3.2/P3.3) or a live layer-2 paired "
                 "run that does not exist before P3.3 -- reported deferred, never "
                 "silently upgraded to green (D30/D59). A not-met floor or a residual "
                 "failure below is this item's honest deliverable, not a defect of "
                 "this script."),
    }
    manifest_payload["content_hash"] = content_hash(manifest_payload)
    Path(args.manifest).write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")

    not_met = floor_summary.get("not_met", [])
    print(f"verify_result_manifest: {manifest_payload['counts']['passed']}/"
          f"{manifest_payload['counts']['cases']} кейсов green, "
          f"floors not-met: {', '.join(sorted(not_met)) if not_met else '—'}, "
          f"residual: {', '.join(r['case_id'] for r in residual) if residual else '—'}")
    print(f"result-manifest: {args.manifest} content_hash={manifest_payload['content_hash'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
