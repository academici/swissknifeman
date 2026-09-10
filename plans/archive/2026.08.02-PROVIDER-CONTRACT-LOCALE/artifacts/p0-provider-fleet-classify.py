#!/usr/bin/env python3
"""Build and validate P0.2's conservative, no-write provider fleet matrix."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
PLAN = HERE.parent
EVIDENCE = HERE / "P0.1" / "evidence"
SNAPSHOT = EVIDENCE / "provider-source-snapshot.json"
INVENTORY = EVIDENCE / "provider-fleet-inventory.json"
OUTPUT = HERE / "P0-provider-fleet-classification.json"
REPORT = PLAN / "research" / "09-fleet-migration-classification.md"
CLASSES = {"canonical-equivalent", "local-override", "stale-managed-copy", "broken-link", "ambiguous"}
OWNERS = {"skm-managed", "project-owned", "unknown"}
ACTIONS = {"no-op", "report", "manual-review"}
DESTINATIONS = {"P5.1", "P5.2", "P5.3", "no-op"}
KNOWN_CASES = ("FlexCRM", "Vintera", "Insiders", "Azguard", "Dterema")
SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.I)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_id(project_id: str, path: str) -> str:
    return f"{project_id}:{path}"


def provider_index(fleet: dict) -> dict[tuple[str, str], list[str]]:
    result: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in fleet["provider_rows"]:
        project_id, provider = row["project_id"], row["provider"]
        for path in row["carrier_paths"]:
            result[(project_id, path)].add(provider)
    return {key: sorted(value) for key, value in result.items()}


def classify(row: dict) -> tuple[str, str, str, str]:
    """Return class, owner, action and destination using only recorded proof."""
    if row["node"] == "symlink" and row.get("target_state") == "broken":
        return "broken-link", "unknown", "no-op", "P5.1"
    # No snapshot row names a canonical source, an older source identity, or a semantic
    # delta. The frozen contract therefore requires a no-op ambiguous disposition.
    return "ambiguous", "unknown", "no-op", "no-op"


def build() -> dict:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    fleet = json.loads(INVENTORY.read_text(encoding="utf-8"))
    providers = provider_index(fleet)
    source_digest = digest(SNAPSHOT)
    inventory_digest = digest(INVENTORY)
    records = []
    for project in snapshot["projects"]:
        project_id = project["project_id"]
        for row in project["provider_paths"]:
            classification, owner, action, destination = classify(row)
            path = row["path"]
            records.append({
                "artifact_id": artifact_id(project_id, path),
                "project_id": project_id,
                "path": path,
                "providers": providers.get((project_id, path), ["shared"]),
                "node": row["node"],
                "managed": row["managed"],
                "tracked": row["tracked"],
                "target_state": row.get("target_state"),
                "classification": classification,
                "owner": owner,
                "action": action,
                "rollback": "not-applicable: no write is proposed",
                "destination": destination,
                "evidence": [source_digest, inventory_digest, f"snapshot-path:{project_id}:{path}"],
            })
    records.sort(key=lambda row: row["artifact_id"])
    known_cases = []
    for name in KNOWN_CASES:
        matches = [row for row in records if name.lower() in row["path"].lower()]
        known_cases.append({
            "case": name,
            "artifact_count": len(matches),
            "classifications": dict(sorted(Counter(row["classification"] for row in matches).items())),
            "disposition": "no-op pending P5 proof" if matches else "not observed in redacted path catalog",
            "sample_artifact_ids": [row["artifact_id"] for row in matches[:5]],
        })
    return {
        "schema_version": 1,
        "source": {"snapshot": source_digest, "inventory": inventory_digest, "row_count": len(records)},
        "policy": {
            "broken_link": "recorded symlink target_state=broken -> broken-link/report/P5.1",
            "otherwise": "missing named canonical source, stale-source identity, or semantic delta -> ambiguous/no-op",
            "writes": "forbidden",
        },
        "classifications": records,
        "known_cases": known_cases,
        "summary": dict(sorted(Counter(row["classification"] for row in records).items())),
    }


def source_ids() -> set[str]:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return {artifact_id(project["project_id"], row["path"])
            for project in snapshot["projects"] for row in project["provider_paths"]}


def contains_leak(value: object) -> bool:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "/home/" in text or "\\\\" in text or bool(SECRET_RE.search(text))


def validate(document: dict) -> list[str]:
    errors: list[str] = []
    records = document.get("classifications")
    if not isinstance(records, list):
        return ["classifications must be a list"]
    ids = [row.get("artifact_id") for row in records if isinstance(row, dict)]
    if len(ids) != len(records) or len(set(ids)) != len(ids):
        errors.append("duplicate-or-invalid-artifact-id")
    if set(ids) != source_ids():
        errors.append("artifact-id-set-mismatch")
    for row in records:
        if not isinstance(row, dict):
            errors.append("non-object-record")
            continue
        if row.get("classification") not in CLASSES:
            errors.append("invalid-classification")
        if row.get("owner") not in OWNERS:
            errors.append("invalid-owner")
        if row.get("action") not in ACTIONS:
            errors.append("invalid-action")
        if row.get("destination") not in DESTINATIONS:
            errors.append("invalid-destination")
        if not row.get("project_id") or not row.get("path") or not row.get("providers") or not row.get("evidence"):
            errors.append("missing-required-evidence-or-identity")
        if not isinstance(row.get("rollback"), str) or not row["rollback"]:
            errors.append("missing-rollback")
        if row.get("classification") in {"local-override", "ambiguous"} and row.get("action") != "no-op":
            errors.append("unsafe-ambiguous-or-local-action")
        if row.get("action") != "no-op" and row.get("owner") != "skm-managed":
            errors.append("automatic-action-without-ownership")
        if row.get("classification") == "broken-link" and row.get("target_state") != "broken":
            errors.append("broken-link-without-proof")
    cases = {row.get("case") for row in document.get("known_cases", []) if isinstance(row, dict)}
    if cases != set(KNOWN_CASES):
        errors.append("missing-known-case-trace")
    if contains_leak(document):
        errors.append("privacy-leak")
    return sorted(set(errors))


def render_report(document: dict) -> str:
    lines = [
        "# P0.2 — fleet migration classification",
        "",
        "This is a deterministic, no-write reduction of the sealed P0.1 evidence. A row is only",
        "given a non-ambiguous class where the snapshot itself proves it; all other rows remain",
        "no-op until a later P5 item supplies the missing ownership or semantic proof.",
        "",
        "## Summary",
        "",
        "| Classification | Rows | Disposition |",
        "|:--|--:|:--|",
    ]
    for name, count in document["summary"].items():
        disposition = "report to P5.1" if name == "broken-link" else "no-op"
        lines.append(f"| `{name}` | {count} | {disposition} |")
    lines += ["", "## Brief-known cases", "", "| Case | Traced rows | Classes | Disposition |", "|:--|--:|:--|:--|"]
    for case in document["known_cases"]:
        classes = ", ".join(f"{key}: {value}" for key, value in case["classifications"].items()) or "none"
        lines.append(f"| {case['case']} | {case['artifact_count']} | {classes} | {case['disposition']} |")
    lines += [
        "",
        "## Safety boundary",
        "",
        "No provider or fleet path was modified. `canonical-equivalent`, `local-override`, and",
        "`stale-managed-copy` require evidence excluded from this privacy-minimized snapshot; they",
        "are deliberately not inferred from a filename, a managed flag, or content similarity.",
        "",
        "Machine source: `artifacts/P0-provider-fleet-classification.json`.",
        "",
    ]
    return "\n".join(lines)


def write() -> int:
    document = build()
    errors = validate(document)
    if errors:
        print("build rejected: " + ", ".join(errors), file=sys.stderr)
        return 1
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render_report(document), encoding="utf-8")
    print(f"wrote {len(document['classifications'])} classifications")
    return 0


def check() -> int:
    if not OUTPUT.exists() or not REPORT.exists():
        print("missing generated output", file=sys.stderr)
        return 1
    document = json.loads(OUTPUT.read_text(encoding="utf-8"))
    errors = validate(document)
    if document != build():
        errors.append("generated-output-stale")
    if REPORT.read_text(encoding="utf-8") != render_report(document):
        errors.append("report-stale")
    if errors:
        print("rejected: " + ", ".join(sorted(set(errors))), file=sys.stderr)
        return 1
    print("allow")
    return 0


def self_test() -> int:
    document = build()
    fixtures = []
    bad = copy.deepcopy(document); bad["classifications"][0]["classification"] = "invalid"; fixtures.append(bad)
    bad = copy.deepcopy(document); bad["classifications"][0]["action"] = "report"; fixtures.append(bad)
    bad = copy.deepcopy(document); bad["classifications"][0]["evidence"] = []; fixtures.append(bad)
    bad = copy.deepcopy(document); bad["classifications"][0]["owner"] = "invalid"; fixtures.append(bad)
    bad = copy.deepcopy(document); bad["classifications"][0]["rollback"] = ""; fixtures.append(bad)
    bad = copy.deepcopy(document); bad["known_cases"] = []; fixtures.append(bad)
    bad = copy.deepcopy(document); bad["classifications"][0]["path"] = "/home/leak"; fixtures.append(bad)
    if any(not validate(fixture) for fixture in fixtures):
        print("negative fixture accepted", file=sys.stderr)
        return 1
    print("negative fixtures rejected")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--negative", choices=["enum", "action", "evidence", "owner", "rollback", "known-case", "privacy"])
    args = parser.parse_args()
    if args.write:
        return write()
    if args.check:
        return check()
    if args.self_test:
        return self_test()
    print("fixture correctly rejected: " + args.negative, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
