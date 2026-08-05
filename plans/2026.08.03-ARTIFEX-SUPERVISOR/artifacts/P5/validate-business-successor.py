#!/usr/bin/env python3
"""Independent D108 G2→G2B successor validator and manifest writer."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
G2_COMMIT = "124df816"
G2_DIGEST = "ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path}")
    return value


def package_rows(root: Path, package: Path) -> list[dict]:
    files = [path for path in package.rglob("*") if path.is_file() and path.suffix in {"", ".py", ".sh", ".md"}]
    return [{"path": path.relative_to(root).as_posix(), "sha256": digest(path)} for path in sorted(files)]


def check_d105(root: Path, index: Path) -> list[dict]:
    document = load(index)
    rows = document.get("admissions")
    if (set(document) != {"schema_version", "index_version", "catalog_hash", "request_hash", "g2_package_digest", "admissions"}
            or document.get("schema_version") != "artifex-business-dispatch-admission-index-v1"
            or document.get("g2_package_digest") != G2_DIGEST or not isinstance(rows, list) or len(rows) != 14):
        raise ValueError("D105 index closure")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("trial_id") in seen or row.get("provider") not in {"codex", "claude-code"}:
            raise ValueError("D105 row identity")
        seen.add(row["trial_id"])
        admission = load(index.parent.parent.parent / row["path"])
        replay = admission.get("replay", {})
        if (digest(index.parent.parent.parent / row["path"]) != row.get("sha256")
                or admission.get("admission_hash") != hashlib.sha256(json.dumps(
                    {k: v for k, v in admission.items() if k != "admission_hash"}, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
                or admission.get("usage") != {"used_slices": 0, "max_slices": 1, "reusable": False}
                or replay.get("events") != [] or replay.get("used_slices") != 0
                or admission.get("task", {}).get("g2_package_digest") != G2_DIGEST):
            raise ValueError(f"D105 usage/hash: {row.get('trial_id')}")
    return rows


def g2_unchanged(root: Path, manifest: Path) -> None:
    value = load(manifest)
    for row in value.get("g2", {}).get("package_files", []):
        shown = subprocess.run(["git", "show", f"{G2_COMMIT}:{row['path']}"], cwd=root,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False).stdout
        if not shown or hashlib.sha256(shown).hexdigest() != row.get("sha256"):
            raise ValueError(f"immutable G2 evidence drift: {row.get('path')}")


def expected(root: Path, args: argparse.Namespace) -> dict:
    contract = args.contract.read_text(encoding="utf-8")
    if "business-dispatch-admission-v1@1.0.0" not in contract or "fourteen" not in contract:
        raise ValueError("business contract version")
    cases, provider, provider_cases = load(args.cases), load(args.provider_manifest), load(args.provider_cases)
    if (cases.get("positive", {}).get("indexed_admissions") != 14
            or len(cases.get("negative_mutations", [])) != 14
            or set(provider.get("providers", {})) != {"codex", "claude-code"}
            or set(provider_cases.get("positive", [])) != {"codex-d108-canary", "claude-d108-canary"}):
        raise ValueError("contract/provider cases")
    rows = check_d105(root, args.admission_index)
    g2_unchanged(root, args.g2)
    package = args.package.resolve()
    files = package_rows(root, package)
    generation = {"schema_version": "artifex-business-successor-generation-v1", "generation_version": "1.0.0",
                  "predecessor": {"generation": "G2", "commit": G2_COMMIT, "digest": G2_DIGEST},
                  "successor": {"generation": "G2B", "package_files": files}, "generation_hash": ""}
    generation["generation_hash"] = hashlib.sha256(json.dumps({k: v for k, v in generation.items() if k != "generation_hash"},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = load(args.assurance) if args.assurance.exists() else None
    probes = _probes(args, existing)
    assurance = {"schema_version": "artifex-business-successor-assurance-v1", "assurance_version": "1.0.0",
                 "g2_predecessor": G2_DIGEST, "g2b_generation_hash": generation["generation_hash"],
                 "d105_rows": len(rows), "d105_used_rows": 0,
                 "provider_versions": {key: value["version"] for key, value in provider["providers"].items()},
                 "d108_pre_provider_observations": [
                     {"provider": "codex", "root": "mktemp:p5-g2b-codex", "exit_code": 1, "process_count": 0, "business_intent": False},
                     {"provider": "claude-code", "root": "mktemp:p5-g2b-claude-code", "exit_code": 1, "process_count": 0, "business_intent": False},
                 ], "r2_capability_probes": probes,
                 "assurance_hash": ""}
    assurance["assurance_hash"] = hashlib.sha256(json.dumps({k: v for k, v in assurance.items() if k != "assurance_hash"},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"generation": generation, "assurance": assurance}


def _observation(raw: str | None, *, provider: str, root: str) -> dict:
    if raw is None:
        raise ValueError("R2 observation required for write")
    value = json.loads(raw)
    required = {"provider", "root", "exit_code", "process_count", "duration_ms", "event_count", "kind", "reason_code", "usage_measured", "wrapper"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("R2 observation schema")
    if (value["provider"] != provider or value["root"] != root or value["exit_code"] != 0
            or value["process_count"] != 1 or value["kind"] != "success" or value["reason_code"] != "OK"
            or value["usage_measured"] is not True or not isinstance(value["duration_ms"], int)
            or value["duration_ms"] < 0 or not isinstance(value["event_count"], int)
            or not 0 <= value["event_count"] <= 16):
        raise ValueError("R2 observation controls")
    wrapper = value["wrapper"]
    if provider == "codex":
        expected = {"single_fresh_exec": True, "hard_timeout_ms": 120000, "max_output_bytes": 8192,
                    "max_event_count": 16, "strict_config": True, "rollout_budget_limit_tokens": 2000,
                    "automatic_retry": False, "max_turns_claimed": False, "money_cap_claimed": False}
    else:
        expected = {"hard_timeout_ms": 120000, "max_output_bytes": 8192, "max_event_count": 16,
                    "max_turns": 2, "cost_limit_microunits": 1000000, "automatic_retry": False,
                    "dont_ask": True, "strict_empty_mcp": True}
    if wrapper != expected:
        raise ValueError("R2 wrapper contract")
    return value


def _probes(args: argparse.Namespace, existing: dict | None) -> list[dict]:
    if args.write:
        return [_observation(args.codex_r2, provider="codex", root="mktemp:p5-g2b-codex-r2"),
                _observation(args.claude_r2, provider="claude-code", root="mktemp:p5-g2b-claude-code-r2")]
    if not isinstance(existing, dict):
        raise ValueError("R2 assurance missing")
    rows = existing.get("r2_capability_probes")
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("R2 probe cardinality")
    # Revalidate saved, minimized records instead of trusting the manifest hash.
    return [_observation(json.dumps(row, sort_keys=True), provider="codex", root="mktemp:p5-g2b-codex-r2"),
            _observation(json.dumps(rows[1], sort_keys=True), provider="claude-code", root="mktemp:p5-g2b-claude-code-r2")]


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("contract", "cases", "provider-manifest", "provider-cases", "generation", "assurance", "g2", "admission-index", "package"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--codex-r2")
    parser.add_argument("--claude-r2")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[4]
        value = expected(root, args)
        if args.write:
            args.generation.write_text(json.dumps(value["generation"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            args.assurance.write_text(json.dumps(value["assurance"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        elif load(args.generation) != value["generation"] or load(args.assurance) != value["assurance"]:
            raise ValueError("G2B generation/assurance drift")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"P5 business successor validator: FAIL: {exc}", file=sys.stderr)
        return 1
    print("P5 business successor validator: OK (G2→G2B; 14/14 D105 rows unused; 2 non-business probes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
