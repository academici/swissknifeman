"""Checked resolution of a historical RED review through its owning repairs.

The additive receipt never changes item history or review verdict. Evidence is
anchored to committed repair results, and every review finding must be resolved.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

from task import journal, plan_bundle, plan_decisions, plan_item_state, plan_layout, plan_repeat, plan_weight, terminal_policy

SCHEMA = "phase-findings-resolution/v1"


class FindingsError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def receipt_path(plan_dir, phase_id):
    return plan_layout.carrier_path(plan_dir, "phase-findings-resolution", phase_id=phase_id)


def _require(condition, message):
    if not condition:
        raise FindingsError(message)


def _closed(value, fields):
    _require(isinstance(value, dict) and set(value) == set(fields), "invalid closed resolution schema")


def _path(root, value):
    _require(isinstance(value, str) and bool(value), "missing evidence path")
    p = PurePosixPath(value)
    _require(not p.is_absolute() and ".." not in p.parts and "\\" not in value,
             "evidence path outside root")
    target = root / p
    _require(target.resolve().is_relative_to(root.resolve()) and target.is_file()
             and not target.is_symlink(), "missing or unsafe evidence file")
    return target


def _file(root, ref):
    _closed(ref, ("path", "sha256"))
    target = _path(root, ref["path"])
    _require(hashlib.sha256(target.read_bytes()).hexdigest() == ref["sha256"], "evidence digest mismatch")
    return target


def _git(repo, *args):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
    _require(result.returncode == 0, "repair commit/evidence is unavailable")
    return result.stdout


def _commit(repo, ref):
    _require(isinstance(ref, str) and re.fullmatch(r"[0-9a-f]{40}", ref), "invalid repair commit")
    _git(repo, "merge-base", "--is-ancestor", ref, "HEAD")


def _at_commit(repo, commit, target):
    relative = target.resolve().relative_to(repo.resolve()).as_posix()
    _require(_git(repo, "show", f"{commit}:{relative}") == target.read_bytes(),
             "evidence differs from committed repair")


def _head(events, item):
    rows = [e for e in events if e.get("item_id") == item]
    event = plan_item_state.latest_execution_event(rows)
    _require(event is not None, "execution result missing")
    return event


def _committed_events(repo, root, commit):
    path = (root / "journal.jsonl").relative_to(repo).as_posix()
    return [json.loads(line) for line in _git(repo, "show", f"{commit}:{path}").decode().splitlines() if line.strip()]


def _review_origin(repo, root, event, report):
    """The first committed review result owns the historical report bytes."""
    path = (root / "journal.jsonl").relative_to(repo).as_posix()
    for commit in _git(repo, "log", "--reverse", "--format=%H", "--", path).decode().splitlines():
        if event in _committed_events(repo, root, commit):
            _at_commit(repo, commit, report)
            return
    raise FindingsError("historical review result was never committed")


def _inventory(text):
    """Require an exhaustive ID/severity/owner table and matching finding headings."""
    tables = {}
    in_table = False
    table_count = 0
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == "ID" and "Severity" in cells and cells[-1] == "Owning item":
            table_count += 1
            in_table = True
            continue
        if not line.startswith("|"):
            in_table = False
        if in_table and cells and re.fullmatch(r"[A-Z]+[0-9]+", cells[0]):
            _require(len(cells) >= 3 and cells[1] in {"blocker", "major", "minor"}
                     and cells[0] not in tables, "invalid or duplicate finding row")
            owners = re.findall(r"P[0-9]+\.[0-9]+", cells[-1])
            _require(bool(owners), "finding has no owning item")
            tables[cells[0]] = set(owners)
    headings = re.findall(r"^### ([A-Z]+[0-9]+) — .+$", text, re.M)
    _require(table_count == 1 and tables and len(headings) == len(set(headings)) and set(headings) == set(tables),
             "finding inventory incomplete or ambiguous")
    return tables


def validate(plan_dir, phase_id, candidate):
    """Return resolved review IDs only after checking the entire evidence chain."""
    root = Path(plan_dir).resolve()
    path = receipt_path(root, phase_id)
    record = json.loads(path.read_text(encoding="utf-8"))
    _closed(record, ("schema_version", "phase_id", "validation_anchor", "repairs", "reviews"))
    _require(record["schema_version"] == SCHEMA and record["phase_id"] == phase_id, "wrong resolution phase/schema")
    repo = plan_weight.repo_root_for(root)
    events = journal.read_authoritative_entries(root)
    anchor = record["validation_anchor"]
    _commit(repo, anchor)
    # The final validated repair commit must still describe every declared
    # phase product byte, including tracked glob members and the RED report.
    from task import plan_gates
    rebuilt = plan_gates.phase_candidate_fingerprint(root, phase_id)["snapshot"]
    _require(plan_gates._candidate_snapshot_fingerprint(candidate) ==
             plan_gates._candidate_snapshot_fingerprint(rebuilt), "candidate no longer current")
    products = []
    for row in rebuilt["product_files"]:
        products.extend(row.get("members", [row]))
    _require(products and all(row.get("state") == "file" for row in products), "product coverage incomplete")
    for row in products:
        _at_commit(repo, anchor, _path(repo, row["path"]))
    _require(isinstance(record["repairs"], dict) and record["repairs"], "repair evidence missing")
    repairs = {}
    for item, proof in record["repairs"].items():
        _require(re.fullmatch(rf"{re.escape(phase_id)}\.\d+", item), "foreign repair item")
        _closed(proof, ("event_sha256", "commit", "validation"))
        event = _head(events, item)
        _require(event["result"] == "closed-green" and digest(event) == proof["event_sha256"], "repair not current GREEN")
        terminal_policy.validate_entry(event, plan_dir=root)
        if event.get("attempt", 1) > 1:
            _require(plan_repeat.for_run(root, item, event.get("run_id")) is not None, "repair repeat not admitted")
        _commit(repo, proof["commit"])
        committed = _committed_events(repo, root, proof["commit"])
        _require(event in committed, "repair commit does not contain terminal evidence")
        declared = event["decision"]["terminal_evidence"]["validation"]
        rows = proof["validation"]
        _require(isinstance(rows, list) and len(rows) == len(declared), "incomplete repair validation")
        for expected, row in zip(declared, rows):
            _closed(row, ("carrier", "log", "exit"))
            _require(row["carrier"] == expected["carrier"] and row["log"]["path"] in expected["evidence_ids"],
                     "validation not linked to terminal carrier")
            _require(row["log"]["path"].endswith(".log") and
                     row["exit"]["path"] == row["log"]["path"][:-4] + ".exit", "exit witness not paired with log")
            log = _file(root, row["log"])
            exit_file = _file(root, row["exit"])
            _require(exit_file.read_text().strip() == "0", "repair validation failed or skipped")
            _at_commit(repo, proof["commit"], log)
            _at_commit(repo, proof["commit"], exit_file)
        repairs[item] = event
    _require(anchor in {proof["commit"] for proof in record["repairs"].values()}, "anchor is not a validated repair")
    _require(isinstance(record["reviews"], list) and record["reviews"], "review resolution missing")
    resolved = set()
    used_repairs = set()
    decisions = {d.identifier: d for d in plan_decisions.load_decisions(root)}
    for review in record["reviews"]:
        _closed(review, ("item_id", "event_sha256", "report", "findings"))
        item = review["item_id"]
        _require(re.fullmatch(rf"{re.escape(phase_id)}\.\d+", item) and item not in resolved,
                 "foreign or duplicate review")
        event = _head(events, item)
        _require(event["result"] == "closed-deviations" and digest(event) == review["event_sha256"], "review history mismatch")
        terminal_policy.validate_entry(event, plan_dir=root)
        fields = plan_bundle._fields(root, item)
        _require("read-only" in fields.get("Implementation Rules", "").lower(), "item is not a read-only review")
        report = _file(root, review["report"])
        _review_origin(repo, root, event, report)
        report_path = review["report"]["path"]
        _require(report_path in re.findall(r"`([^`]+)`", fields.get("Deliverables", "")), "report not review deliverable")
        text = report.read_text()
        _require(re.search(r"\*\*Verdict:\s*RED\.?\*\*", text), "historical RED report required")
        gap = event["decision"]["terminal_evidence"]["repair_exhausted"]
        _require(gap["verdict"] == "outside-scope" and report_path in gap["failed_carrier"], "deviation is not a review finding")
        inventory = _inventory(text)
        rows = review["findings"]
        _require(isinstance(rows, list) and len(rows) == len(inventory) and
                 {r.get("id") for r in rows if isinstance(r, dict)} == set(inventory), "unresolved findings")
        for row in rows:
            _require(row.get("status") == "resolved" and row.get("owner_item") in inventory[row["id"]]
                     and re.fullmatch(rf"{re.escape(phase_id)}\.\d+", str(row.get("owner_item"))), "finding owner/status mismatch")
            owner = row["owner_item"]
            if row.get("kind") == "owning-repair":
                _closed(row, ("id", "status", "kind", "owner_item"))
                _require(owner in repairs and events.index(repairs[owner]) > events.index(event), "repair did not follow RED review")
                used_repairs.add(owner)
            elif row.get("kind") == "contract-sync":
                _closed(row, ("id", "status", "kind", "owner_item", "decision_id", "commit", "files"))
                decision = decisions.get(row["decision_id"])
                _require(decision is not None and decision.status == "accepted" and
                         decision.superseded_by is None and owner in decision.items, "contract sync decision invalid")
                _commit(repo, row["commit"])
                _at_commit(repo, row["commit"], report)
                _at_commit(repo, row["commit"], decision.path)
                changed = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-z", "-r", row["commit"]).decode().split("\0")
                _require(isinstance(row["files"], list) and row["files"], "contract sync evidence missing")
                for ref in row["files"]:
                    target = _file(root, ref)
                    _require(target.relative_to(repo).as_posix() in changed and
                             ref["path"] in text, "contract sync unrelated to finding")
                    _at_commit(repo, row["commit"], target)
                _at_commit(repo, anchor, decision.path)
            else:
                raise FindingsError("unsupported finding resolution")
        resolved.add(item)
    _require(used_repairs == set(repairs), "unlinked repair evidence")
    non_green = {r["item_id"] for r in candidate["terminal_item_heads"] if r["status"] != "🟢 Done"}
    _require(resolved == non_green, "non-review deviations remain unresolved")
    return {"review_items": sorted(resolved), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def acceptance(plan_dir, phase_id, candidate):
    try:
        return {"allow": True, **validate(plan_dir, phase_id, candidate)}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {"allow": False, "code": "PHASE_FINDINGS_UNRESOLVED", "reason": str(exc)}


def closed_green(plan_dir, phase_id):
    """A phase GREEN projection needs a persisted, still-valid close admission."""
    events = journal.read_authoritative_entries(plan_dir)
    closes = [e for e in events if e.get("item_id") == phase_id and e.get("command") == "plan-close"]
    if not closes or closes[-1].get("result") != "closed-green":
        return False
    event = closes[-1]
    if "findings_resolution_sha256" not in (event.get("decision") or {}):
        return False
    from task import plan_gates
    try:
        candidate = plan_gates.phase_candidate_fingerprint(plan_dir, phase_id)
    except (ValueError, OSError):
        return False
    proof = acceptance(plan_dir, phase_id, candidate["snapshot"])
    return proof["allow"] and proof["sha256"] == event["decision"]["findings_resolution_sha256"]
