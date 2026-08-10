#!/usr/bin/env python3
"""Forward-only P0.1--P0.4 execution-provenance ledger.

The historical commits and journal rows are evidence, not mutable state.  This
helper derives a small, deterministic ledger from literal Git object IDs,
re-evaluates each item's Task Contract against its committed tree, and emits
one bounded correction event per item only after the ledger validates.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PLAN_ID = "2026.08.02-PROVIDER-CONTRACT-LOCALE"
PLAN_RELATIVE = Path("plans") / PLAN_ID
LEDGER_RELATIVE = PLAN_RELATIVE / "artifacts/P0.8/execution-provenance-v1.json"
WRITE_SITE = "write-site: pre_mutation: allow · pre_final: allow"

ITEMS = (
    {
        "item_id": "P0.1", "commit": "0169e25678f94f601a9bb7ddc4ce80f9ede66156",
        "prescribed_route": {"model_class": "implementation", "effort": "high"},
        "historical_executor_route": {"model": "gpt-5.6-sol", "model_class": "frontier", "effort": "high"},
        "deviation": "material: baseline bundle errors; process: route overshoot",
        "result": "closed-deviations",
    },
    {
        "item_id": "P0.2", "commit": "5703feb4ee8a086538f9bc64aa36b70de3f8c61f",
        "prescribed_route": {"model_class": "frontier", "effort": "high"},
        "historical_executor_route": {"model": "gpt-5.6-sol", "model_class": "frontier", "effort": "high"},
        "deviation": "process: item and bookkeeping paths were bundled; Required Reads changed in close commit",
        "result": "closed-green",
    },
    {
        "item_id": "P0.3", "commit": "18571a14c69a57f04a8a4db58a7039f627e27c13",
        "prescribed_route": {"model_class": "frontier", "effort": "high"},
        "historical_executor_route": {"model": "gpt-5.6-sol", "model_class": "frontier", "effort": "high"},
        "deviation": "process: item and bookkeeping paths were bundled",
        "result": "closed-green",
    },
    {
        "item_id": "P0.4", "commit": "d17e4497ba751f61b131c5147ac93b87e6ad61d7",
        "prescribed_route": {"model_class": "implementation", "effort": "high"},
        "historical_executor_route": {"model": "gpt-5.6-sol", "model_class": "frontier", "effort": "high"},
        "deviation": "process: item/phase-close paths bundled; Required Reads changed in close commit; route overshoot",
        "result": "closed-green",
    },
)


class ProvenanceError(ValueError):
    pass


def canonical(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise ProvenanceError(f"git {' '.join(args)}: {completed.stderr.strip()}")
    return completed.stdout


def changed_paths(repo: Path, commit: str) -> list[str]:
    return [line for line in git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines() if line]


def classify_topology(item_id: str, paths: list[str]) -> dict[str, list[str]]:
    item_token = f"/{item_id}/"
    item_paths = [path for path in paths if item_token in path or path.endswith(f"{item_id}.md")]
    bookkeeping_paths = [path for path in paths if path not in item_paths]
    return {"item_paths": item_paths, "bookkeeping_or_phase_paths": bookkeeping_paths}


def historical_contract(repo: Path, item: dict[str, object]) -> dict[str, str]:
    """Use the real compiler against a temporary checkout of the exact commit."""
    package_root = Path(__file__).resolve().parents[3] / "packages/task/lib"
    sys.path.insert(0, str(package_root))
    from task import route_evidence, task_contract  # imported only in repository execution

    archive = subprocess.run(
        ["git", "archive", "--format=tar", str(item["commit"])], cwd=repo,
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if archive.returncode:
        raise ProvenanceError(f"git archive {item['commit']}: {archive.stderr.decode().strip()}")
    with tempfile.TemporaryDirectory(prefix="p0-provenance-") as temp:
        root = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as bundle:
            bundle.extractall(root, filter="data")
        route = item["historical_executor_route"]
        contract = task_contract.build(
            root / PLAN_RELATIVE, str(item["item_id"]),
            actual_route=route_evidence.capture_actual(
                route["model_class"], route["effort"], source="self-attested", model=route["model"],
            ),
        )
        result = task_contract.evaluate(contract)
    if result["pre_mutation"] != "allow" or result["pre_final"] != "allow":
        raise ProvenanceError(f"{item['item_id']}: historical Task Contract is {result}")
    return {"pre_mutation": result["pre_mutation"], "pre_final": result["pre_final"]}


def build_ledger(repo: Path) -> dict[str, object]:
    rows = []
    for item in ITEMS:
        resolved = git(repo, "rev-parse", f"{item['commit']}^{{commit}}").strip()
        if resolved != item["commit"]:
            raise ProvenanceError(f"{item['item_id']}: missing or ambiguous Git anchor")
        paths = changed_paths(repo, resolved)
        if not paths:
            raise ProvenanceError(f"{item['item_id']}: declared commit has no changed paths")
        codes = historical_contract(repo, item)
        rows.append({
            "item_id": item["item_id"], "item_commit": resolved,
            "changed_paths": paths, "topology": classify_topology(str(item["item_id"]), paths),
            "historical_executor_route": dict(item["historical_executor_route"]),
            "prescribed_route": dict(item["prescribed_route"]), "contract_codes": codes,
            "deviation": item["deviation"], "correction_result": item["result"],
            "validations": [{
                "command": "git diff-tree --no-commit-id --name-only -r <anchor>",
                "anchor": resolved,
            }, {
                "command": "task.task_contract.build/evaluate on git archive <anchor>",
                "anchor": resolved,
            }],
        })
    ledger = {"schema": "p0-execution-provenance/v1", "plan_id": PLAN_ID, "items": rows}
    ledger["ledger_sha256"] = hashlib.sha256(canonical(ledger)).hexdigest()
    return ledger


def validate_ledger(repo: Path, ledger: dict[str, object]) -> None:
    expected = build_ledger(repo)
    if ledger != expected:
        raise ProvenanceError("ledger differs from deterministic Git/Task Contract reconstruction")
    for row in ledger["items"]:
        if row["contract_codes"] != {"pre_mutation": "allow", "pre_final": "allow"}:
            raise ProvenanceError(f"{row['item_id']}: correction blocked by Task Contract")
        if not row["changed_paths"] or not all(entry.get("anchor") == row["item_commit"] for entry in row["validations"]):
            raise ProvenanceError(f"{row['item_id']}: changed paths or number anchors are incomplete")


def correction_note(row: dict[str, object]) -> str:
    route = row["historical_executor_route"]
    return (f"{WRITE_SITE}; item_commit={row['item_commit'][:8]}; historical_route="
            f"{route['model_class']}/{route['effort']}; deviation={row['deviation']}; "
            "ledger=artifacts/P0.8/execution-provenance-v1.json")


def correction_events(plan_dir: Path, ledger: dict[str, object], actor: str, session_id: str) -> list[dict[str, object]]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages/task/lib"))
    from task import journal
    existing = [json.loads(line) for line in (plan_dir / "journal.jsonl").read_text().splitlines() if line.strip()]
    events = []
    for row in ledger["items"]:
        evidence_id = f"p0.8-correction:{row['item_id']}:{row['ledger_sha256'] if 'ledger_sha256' in row else ledger['ledger_sha256']}"
        if any(event.get("evidence_id") == evidence_id for event in existing):
            raise ProvenanceError(f"duplicate correction evidence ID: {evidence_id}")
        previous_attempt = max((int(event.get("attempt", 0)) for event in existing if event.get("item_id") == row["item_id"]), default=0)
        note = correction_note(row)
        if not note.startswith(WRITE_SITE) or len(note) > journal.NOTE_MAX_CHARS:
            raise ProvenanceError(f"{row['item_id']}: correction note is not canonical/bounded")
        event = journal.new_entry(
            plan_id=PLAN_ID, item_id=row["item_id"], command="plan-run", actor=actor,
            session_id=session_id, attempt=previous_attempt + 1, result=row["correction_result"],
            friction=("deviation",), note=note,
        )
        event["evidence_id"] = evidence_id
        events.append(event)
    return events


def write(path: Path, ledger: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(ledger))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P0 append-only execution provenance")
    parser.add_argument("action", choices=("write", "check", "emit-events"))
    parser.add_argument("--plan-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--actor", default="gpt-5.6-sol/high")
    parser.add_argument("--session-id", default="reconciliation")
    args = parser.parse_args(argv)
    repo = Path.cwd()
    output = args.output or args.plan_dir / "artifacts/P0.8/execution-provenance-v1.json"
    try:
        if args.action == "write":
            ledger = build_ledger(repo)
            write(output, ledger)
            print(f"ledger: wrote {output}")
        else:
            source = args.input or output
            ledger = json.loads(source.read_text(encoding="utf-8"))
            validate_ledger(repo, ledger)
            if args.action == "check":
                print(f"ledger: verified {source}")
            else:
                if not args.apply:
                    raise ProvenanceError("emit-events requires --apply")
                events = correction_events(args.plan_dir, ledger, args.actor, args.session_id)
                sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages/task/lib"))
                from task import journal
                for event in events:
                    journal.append(args.plan_dir, event)
                print(f"events: appended {len(events)} corrections")
    except (OSError, json.JSONDecodeError, ProvenanceError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
