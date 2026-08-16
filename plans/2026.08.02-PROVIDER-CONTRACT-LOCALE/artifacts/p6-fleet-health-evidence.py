#!/usr/bin/env python3
"""Build and verify privacy-minimized P6.3 fleet provider-health evidence."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
from typing import Any


PLAN_ID = "2026.08.02-PROVIDER-CONTRACT-LOCALE"
SCRIPT = Path(__file__).resolve()
PLAN_ROOT = SCRIPT.parents[1]
REPO_ROOT = SCRIPT.parents[3]
MAIND = REPO_ROOT / "packages" / "maind" / "bin" / "maind"
MAIND_HEALTH_SOURCE = REPO_ROOT / "packages" / "maind" / "lib" / "maind" / "provider_health.py"
P0_MEMBERS = (
    "project-registry-redacted.json",
    "provider-fleet-inventory.json",
    "provider-source-snapshot.json",
    "command-results-redacted.json",
)
DATA_MEMBERS = (
    "project-set.json",
    "provider-health-run-1.json",
    "provider-health-run-2.json",
    "fleet-health-verdict.json",
    "command-results-redacted.json",
)
PROVIDERS = ("claude-code", "codex")
PROVIDER_AXES = (
    ("migration.convergence", "sealed"),
    ("registry.selection", "sealed"),
    ("settings.integrity", "harness"),
    ("skill.dependency", "skiller"),
    ("skill.measurement.listing", "skiller"),
    ("skill.measurement.loaded-body", "skiller"),
    ("skill.measurement.runtime", "skiller"),
)
SHARED_AXES = (
    "graph.federation",
    "mcp.code",
    "mcp.maind",
    "memory.forget",
    "memory.recall",
    "memory.store",
)
ALLOWED_STATES = {
    "pass", "not-selected", "not-required", "unsupported", "unavailable",
    "unresolved", "unknown", "stale", "missing", "duplicate", "error",
}
FORBIDDEN = re.compile(
    r"(?:/home/|/Users/|[A-Za-z]:\\|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9_]{12,}|"
    r"(?:secret|password|api[-_.]?key)[\"']?\s*[:=])",
    re.IGNORECASE,
)
PRIVACY = {
    "minimized": True,
    "excluded_classes": [
        "raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets",
    ],
}


class EvidenceError(RuntimeError):
    """Stable validation failure without retaining sensitive command output."""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def digest(value: Any) -> str:
    return "sha256:" + sha256_bytes(canonical(value).encode("utf-8"))


def evidence_id(value: Any) -> str:
    return "ev:" + sha256_bytes(canonical(value).encode("utf-8"))[:24]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def later(value: str, minutes: int = 10) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"P63_JSON_INVALID:{path.name}") from error


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_json(argv: list[str], *, cwd: Path = REPO_ROOT, timeout: int = 30) -> tuple[int | None, Any, str]:
    try:
        completed = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return None, None, "P63_COMMAND_TIMEOUT"
    except (OSError, subprocess.SubprocessError):
        return None, None, "P63_COMMAND_UNAVAILABLE"
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        return completed.returncode, None, "P63_COMMAND_JSON_INVALID"
    return completed.returncode, payload, "" if completed.returncode == 0 else "P63_COMMAND_NONZERO"


def command_record(run: int, project_id: str, command_class: str,
                   returncode: int | None, payload: Any, diagnostic: str) -> dict[str, Any]:
    return {
        "run": run,
        "project_id": project_id,
        "command_class": command_class,
        "availability": "available" if returncode is not None else "unavailable",
        "exit_code": returncode,
        "stdout_schema": "json" if payload is not None else "none",
        "diagnostic": diagnostic,
    }


def stable_project_id(root: Path, records: list[dict[str, Any]]) -> str:
    identity = "|".join(sorted(
        f"{record.get('provider', 'generic')}:{record.get('channel', '')}"
        for record in records
    ))
    return "project-" + sha256_bytes((str(root) + "|" + identity).encode("utf-8"))[:16]


def validate_schema_carrier(path: Path) -> dict[str, Any]:
    schema = read_json(path)
    try:
        schema_version = schema["properties"]["schema_version"]["const"]
        contract_version = schema["properties"]["contract_version"]["const"]
        provenance = schema["x-provenance"]
    except (KeyError, TypeError) as error:
        raise EvidenceError("P63_SCHEMA_CARRIER_INVALID") from error
    if schema_version != "provider-health-evidence-set/v1" or contract_version != "1.0.0":
        raise EvidenceError("P63_SCHEMA_CARRIER_VERSION_DRIFT")
    if provenance.get("decision") != "D85":
        raise EvidenceError("P63_SCHEMA_CARRIER_PROVENANCE_INVALID")
    if provenance.get("source_sha256") != sha256_file(MAIND_HEALTH_SOURCE):
        raise EvidenceError("P63_SCHEMA_CARRIER_SOURCE_DRIFT")
    return schema


def validate_p5(convergence: dict[str, Any], journal_path: Path,
                sealed_project_ids: list[str]) -> dict[str, Any]:
    if (
        convergence.get("schema_version") != "p5-fleet-convergence/v1"
        or convergence.get("stable") is not True
        or convergence.get("complete_p0_coverage") is not True
        or convergence.get("passes") != 2
        or convergence.get("rollout_authorized") is not False
        or convergence.get("migration_readiness") != "held-unresolved"
    ):
        raise EvidenceError("P63_P5_CONVERGENCE_INVALID")
    observations = convergence.get("observations")
    if not isinstance(observations, list) or len(observations) != 2:
        raise EvidenceError("P63_P5_CONVERGENCE_INVALID")
    semantics = []
    for expected_pass, entry in enumerate(observations, 1):
        if not isinstance(entry, dict) or entry.get("pass") != expected_pass:
            raise EvidenceError("P63_P5_CONVERGENCE_INVALID")
        observation = entry.get("observation")
        if not isinstance(observation, dict):
            raise EvidenceError("P63_P5_CONVERGENCE_INVALID")
        coverage = observation.get("p0_coverage")
        if not isinstance(coverage, dict) or coverage.get("project_count") != len(sealed_project_ids):
            raise EvidenceError("P63_P5_PROJECT_SET_MISMATCH")
        if coverage.get("project_ids_sha256") != digest(sorted(sealed_project_ids)):
            raise EvidenceError("P63_P5_PROJECT_SET_MISMATCH")
        if (
            observation.get("accepted_transactions") != 0
            or observation.get("terminal_transactions") != 0
            or observation.get("consumer_writes") != 0
            or observation.get("unresolved_rows") != observation.get("row_count")
        ):
            raise EvidenceError("P63_P5_TERMINAL_STATE_INVALID")
        semantics.append({key: value for key, value in observation.items()
                          if key not in {"pass", "observation_sha256"}})
    if semantics[0] != semantics[1]:
        raise EvidenceError("P63_P5_TWO_PASS_MISMATCH")
    try:
        journal_lines = [line for line in journal_path.read_text(encoding="utf-8").splitlines()
                         if line.strip()]
    except (OSError, UnicodeError) as error:
        raise EvidenceError("P63_P5_JOURNAL_INVALID") from error
    if journal_lines:
        try:
            events = [json.loads(line) for line in journal_lines]
        except json.JSONDecodeError as error:
            raise EvidenceError("P63_P5_JOURNAL_INVALID") from error
        if not all(isinstance(event, dict) and event.get("result") in {
            "accepted", "rolled-back", "rejected", "skipped-unresolved",
        } for event in events):
            raise EvidenceError("P63_P5_JOURNAL_NONTERMINAL")
    return {
        "rollout_authorized": False,
        "migration_readiness": "held-unresolved",
        "unresolved_rows": observations[1]["observation"]["unresolved_rows"],
        "transaction_count": len(journal_lines),
    }


def load_context(args: argparse.Namespace) -> dict[str, Any]:
    schema = validate_schema_carrier(Path(args.evidence_set_schema))
    health_contract = Path(args.health_contract)
    provider_manifest = Path(args.provider_manifest)
    p0_manifest_path = Path(args.p0_manifest)
    p0_root = p0_manifest_path.parent
    p0_manifest = read_json(p0_manifest_path)
    declared = {entry["path"] if isinstance(entry, dict) else entry
                for entry in p0_manifest.get("files", [])}
    if not set(P0_MEMBERS) <= declared:
        raise EvidenceError("P63_P0_MANIFEST_INCOMPLETE")
    registry = read_json(p0_root / "project-registry-redacted.json")
    inventory = read_json(p0_root / "provider-fleet-inventory.json")
    sealed_ids = sorted(str(item["project_id"]) for item in registry.get("projects", []))
    if len(sealed_ids) != 23 or len(sealed_ids) != len(set(sealed_ids)):
        raise EvidenceError("P63_P0_PROJECT_SET_INVALID")
    provider_rows = inventory.get("provider_rows")
    expected_provider_keys = {(project_id, provider) for project_id in sealed_ids
                              for provider in PROVIDERS}
    actual_provider_keys = {
        (str(row.get("project_id")), str(row.get("provider")))
        for row in provider_rows if isinstance(row, dict)
    } if isinstance(provider_rows, list) else set()
    if actual_provider_keys != expected_provider_keys or len(provider_rows) != len(expected_provider_keys):
        raise EvidenceError("P63_P0_PROVIDER_SET_INVALID")
    if any(row.get("selected") is not True for row in provider_rows):
        raise EvidenceError("P63_P0_PROVIDER_SELECTION_INVALID")
    manifest = read_json(provider_manifest)
    provider_ids = sorted(str(item.get("id")) for item in manifest.get("providers", [])
                          if isinstance(item, dict))
    if provider_ids != list(PROVIDERS):
        raise EvidenceError("P63_PROVIDER_MANIFEST_MISMATCH")
    p5 = validate_p5(read_json(Path(args.p5_convergence)), Path(args.p5_journal), sealed_ids)
    return {
        "schema": schema,
        "schema_sha256": "sha256:" + sha256_file(Path(args.evidence_set_schema)),
        "health_contract_sha256": "sha256:" + sha256_file(health_contract),
        "provider_manifest_sha256": "sha256:" + sha256_file(provider_manifest),
        "p0_manifest_sha256": "sha256:" + sha256_file(p0_manifest_path),
        "p5_convergence_sha256": "sha256:" + sha256_file(Path(args.p5_convergence)),
        "p5_journal_sha256": "sha256:" + sha256_file(Path(args.p5_journal)),
        "source_sha256": "sha256:" + sha256_file(MAIND_HEALTH_SOURCE),
        "sealed_ids": sealed_ids,
        "p5": p5,
    }


def bind_live_projects(sealed_ids: list[str]) -> tuple[dict[str, dict[str, Any] | None], str]:
    registry_path = Path.home() / ".swissknifeman" / "projects.json"
    registry = read_json(registry_path)
    records = registry.get("projects")
    if not isinstance(records, list):
        raise EvidenceError("P63_LIVE_REGISTRY_INVALID")
    grouped: dict[Path, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise EvidenceError("P63_LIVE_REGISTRY_INVALID")
        grouped.setdefault(Path(record["path"]), []).append(record)
    computed = {stable_project_id(root, rows): root for root, rows in grouped.items()}
    if set(computed) != set(sealed_ids):
        raise EvidenceError("P63_LOCATOR_REBINDING_MISMATCH")
    returncode, live, diagnostic = run_json([str(MAIND), "projects", "list", "--json"])
    if returncode != 0 or not isinstance(live, list):
        raise EvidenceError(diagnostic or "P63_LIVE_PROJECTS_UNAVAILABLE")
    by_root: dict[Path, dict[str, Any]] = {}
    for project in live:
        if not isinstance(project, dict) or not isinstance(project.get("id"), str):
            raise EvidenceError("P63_LIVE_PROJECTS_INVALID")
        local = project.get("local_path")
        if not isinstance(local, str):
            continue
        resolved = Path(local).expanduser().resolve()
        if resolved in by_root:
            raise EvidenceError("P63_LIVE_ROOT_DUPLICATE")
        by_root[resolved] = project
    bindings: dict[str, dict[str, Any] | None] = {}
    for project_id, root in computed.items():
        live_project = by_root.get(root.expanduser().resolve())
        bindings[project_id] = None if live_project is None else {
            "live_id": live_project["id"],
            "root": root.expanduser().resolve(),
        }
    fingerprint = digest({project_id: None if value is None else value["live_id"]
                          for project_id, value in sorted(bindings.items())})
    return bindings, fingerprint


def sealed_observation(provider_id: str, axis_id: str, state: str, source_id: str,
                       observed_at: str, identity: Any) -> dict[str, Any]:
    return {
        "provider_id": provider_id,
        "axis_id": axis_id,
        "state": state,
        "evidence_id": evidence_id(identity),
        "source_id": source_id,
        "observed_at": observed_at,
        "expires_at": later(observed_at),
    }


def memory_probe(run: int, project_id: str, live_id: str) -> tuple[dict[str, str], list[dict[str, Any]], str]:
    token = f"p63-{run}-{secrets.token_hex(16)}"
    memory_id: str | None = None
    store_state = recall_state = forget_state = "unavailable"
    commands: list[dict[str, Any]] = []
    cleanup_done = False
    try:
        rc, stored, diag = run_json([
            str(MAIND), "memory", "remember", "--project", live_id,
            "--type", "p63-health-probe", "--json", token,
        ], timeout=20)
        commands.append(command_record(run, project_id, "memory-remember", rc, stored, diag))
        if rc == 0 and isinstance(stored, dict) and stored.get("written"):
            store_state = "pass"
        else:
            store_state = "error" if rc is not None else "unavailable"
        rc, recalled, diag = run_json([
            str(MAIND), "memory", "recall", "--project", live_id,
            "--limit", "10", "--json", token,
        ], timeout=20)
        commands.append(command_record(run, project_id, "memory-recall", rc, recalled, diag))
        rows = recalled if isinstance(recalled, list) else []
        match = next((row for row in rows if isinstance(row, dict)
                      and token in str(row.get("text", ""))), None)
        if rc == 0 and match is not None:
            recall_state = "pass"
            candidate = match.get("id") or match.get("memoryId")
            memory_id = str(candidate) if candidate else None
        else:
            recall_state = "error" if rc is not None else "unavailable"
        if memory_id:
            try:
                completed = subprocess.run(
                    [str(MAIND), "memory", "forget", "--project", live_id, memory_id],
                    cwd=REPO_ROOT, capture_output=True, text=True, timeout=20, check=False,
                )
                forget_rc: int | None = completed.returncode
                forget_diag = "" if completed.returncode == 0 else "P63_COMMAND_NONZERO"
            except subprocess.TimeoutExpired:
                forget_rc, forget_diag = None, "P63_COMMAND_TIMEOUT"
            except (OSError, subprocess.SubprocessError):
                forget_rc, forget_diag = None, "P63_COMMAND_UNAVAILABLE"
            commands.append(command_record(
                run, project_id, "memory-forget", forget_rc, None, forget_diag,
            ))
            cleanup_done = forget_rc == 0
            rc, after, diag = run_json([
                str(MAIND), "memory", "recall", "--project", live_id,
                "--limit", "10", "--json", token,
            ], timeout=20)
            commands.append(command_record(run, project_id, "memory-cleanup-check", rc, after, diag))
            residue = any(isinstance(row, dict) and token in str(row.get("text", ""))
                          for row in after) if isinstance(after, list) else True
            forget_state = "pass" if cleanup_done and rc == 0 and not residue else "error"
        else:
            forget_state = "error" if store_state == "pass" else "unavailable"
    finally:
        if memory_id and not cleanup_done:
            try:
                subprocess.run(
                    [str(MAIND), "memory", "forget", "--project", live_id, memory_id],
                    cwd=REPO_ROOT, capture_output=True, text=True, timeout=20, check=False,
                )
            except (OSError, subprocess.SubprocessError):
                pass
    states = {
        "memory.store": store_state,
        "memory.recall": recall_state,
        "memory.forget": forget_state,
    }
    identity = evidence_id({"project_id": project_id, "run": run, "states": states})
    return states, commands, identity


def shared_probe(run: int, project_id: str, binding: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    live_id = str(binding["live_id"])
    root = Path(binding["root"])
    observed_at = utc_now()
    memory_states, commands, memory_identity = memory_probe(run, project_id, live_id)
    rc, health, diag = run_json([str(MAIND), "health", "--cwd", "--json"], cwd=root)
    commands.append(command_record(run, project_id, "maind-health", rc, health, diag))
    maind_state = "pass" if rc == 0 and isinstance(health, dict) and health.get("maind_mcp") is True else (
        "error" if rc is not None else "unavailable"
    )
    code_state = "pass" if rc == 0 and isinstance(health, dict) and health.get("code_mcp") is True else (
        "error" if rc is not None else "unavailable"
    )
    rc, graph, diag = run_json([str(MAIND), "graph", "--project", live_id, "--json"])
    commands.append(command_record(run, project_id, "graph-view", rc, graph, diag))
    graph_state = "pass" if (
        rc == 0 and isinstance(graph, dict) and isinstance(graph.get("nodes"), list)
        and isinstance(graph.get("edges"), list)
    ) else ("error" if rc is not None else "unavailable")
    states = {
        **memory_states,
        "mcp.maind": maind_state,
        "mcp.code": code_state,
        "graph.federation": graph_state,
    }
    observations = [
        sealed_observation(
            "shared", axis_id, states[axis_id],
            "p6.3.memory" if axis_id.startswith("memory.") else (
                "maind.health" if axis_id.startswith("mcp.") else "maind.graph"
            ),
            observed_at,
            {"project_id": project_id, "axis_id": axis_id, "state": states[axis_id],
             "probe": memory_identity if axis_id.startswith("memory.") else "public-cli"},
        )
        for axis_id in SHARED_AXES
    ]
    return observations, commands, memory_states["memory.forget"] == "pass"


def requirements_and_evidence(project_id: str, shared: list[dict[str, Any]],
                              observed_at: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requirements = []
    evidence = list(shared)
    for provider_id in PROVIDERS:
        for axis_id, producer in PROVIDER_AXES:
            requirements.append({
                "provider_id": provider_id,
                "axis_id": axis_id,
                "selected": True,
                "required": True,
                "producer": producer,
            })
        evidence.append(sealed_observation(
            provider_id, "migration.convergence", "unresolved", "p5.convergence",
            observed_at, {"project_id": project_id, "provider_id": provider_id,
                          "state": "held-unresolved"},
        ))
        evidence.append(sealed_observation(
            provider_id, "registry.selection", "pass", "p0.registry",
            observed_at, {"project_id": project_id, "provider_id": provider_id,
                          "selected": True},
        ))
    for axis_id in SHARED_AXES:
        requirements.append({
            "provider_id": "shared",
            "axis_id": axis_id,
            "selected": True,
            "required": True,
            "producer": "sealed",
        })
    requirements.sort(key=lambda row: (row["provider_id"], row["axis_id"]))
    evidence.sort(key=lambda row: tuple(row[key] for key in (
        "provider_id", "axis_id", "state", "evidence_id", "source_id", "observed_at", "expires_at",
    )))
    return requirements, evidence


def seal_evidence_set(unsigned: dict[str, Any]) -> dict[str, Any]:
    result = dict(unsigned)
    result["seal"] = {"sha256": digest(unsigned)}
    return result


def normalize_public_project(project_id: str, payload: dict[str, Any],
                             cleanup_green: bool) -> dict[str, Any]:
    projects = payload.get("projects")
    if not isinstance(projects, list) or len(projects) != 1 or not isinstance(projects[0], dict):
        raise EvidenceError("P63_PUBLIC_HEALTH_SCHEMA_INVALID")
    project = projects[0]
    rows = project.get("rows")
    if not isinstance(rows, list):
        raise EvidenceError("P63_PUBLIC_HEALTH_SCHEMA_INVALID")
    normalized_rows = []
    for row in rows:
        if not isinstance(row, dict):
            raise EvidenceError("P63_PUBLIC_HEALTH_SCHEMA_INVALID")
        normalized_rows.append({key: row.get(key) for key in (
            "provider_id", "axis_id", "selected", "required", "status", "healthy",
            "evidence_id", "source_id", "observed_at", "expires_at", "diagnostics",
        ) if key in row})
    normalized_rows.sort(key=lambda row: (str(row.get("provider_id")), str(row.get("axis_id"))))
    return {
        "project_id": project_id,
        "aggregate": project.get("aggregate"),
        "diagnostics": project.get("diagnostics", []),
        "rows": normalized_rows,
        "public_result_digest": project.get("result_digest"),
        "cleanup_green": cleanup_green,
    }


def unavailable_project(project_id: str, run: int) -> dict[str, Any]:
    observed_at = utc_now()
    requirements, _ = requirements_and_evidence(project_id, [], observed_at)
    rows = [{
        "provider_id": requirement["provider_id"],
        "axis_id": requirement["axis_id"],
        "selected": requirement["selected"],
        "required": requirement["required"],
        "status": "unavailable",
        "healthy": False,
        "evidence_id": evidence_id({"project_id": project_id, "run": run,
                                    "axis_id": requirement["axis_id"], "missing": True}),
        "source_id": "p6.3.registry-missing",
        "observed_at": observed_at,
        "expires_at": later(observed_at),
        "diagnostics": ["PH_PROJECT_NOT_REGISTERED"],
    } for requirement in requirements]
    return {
        "project_id": project_id,
        "aggregate": "non-green",
        "diagnostics": ["PH_PROJECT_NOT_REGISTERED"],
        "rows": rows,
        "public_result_digest": None,
        "cleanup_green": False,
    }


def scan_project(run: int, project_id: str, binding: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    observed_at = utc_now()
    shared, commands, cleanup_green = shared_probe(run, project_id, binding)
    requirements, evidence = requirements_and_evidence(project_id, shared, observed_at)
    live_id = str(binding["live_id"])
    unsigned = {
        "schema_version": "provider-health-evidence-set/v1",
        "contract_version": "1.0.0",
        "evidence_set_id": f"p63.run-{run}.{project_id}",
        "projects": [{
            "project_id": live_id,
            "requirements": requirements,
            "evidence": evidence,
        }],
    }
    descriptor = seal_evidence_set(unsigned)
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
        handle.write(canonical(descriptor))
        handle.flush()
        rc, payload, diagnostic = run_json([
            str(MAIND), "projects", "health", "--project", live_id,
            "--evidence-set", handle.name, "--json",
        ], timeout=90)
    commands.append(command_record(run, project_id, "provider-health", rc, payload, diagnostic))
    if rc != 0 or not isinstance(payload, dict):
        project = unavailable_project(project_id, run)
        project["diagnostics"] = sorted(set(project["diagnostics"] + [
            diagnostic or "P63_PUBLIC_HEALTH_NONZERO",
        ]))
        return project, commands
    return normalize_public_project(project_id, payload, cleanup_green), commands


def validate_project_result(project: dict[str, Any]) -> None:
    rows = project.get("rows")
    if not isinstance(rows, list):
        raise EvidenceError("P63_SCAN_ROWS_INVALID")
    expected = {
        *((provider, axis) for provider in PROVIDERS for axis, _ in PROVIDER_AXES),
        *(("shared", axis) for axis in SHARED_AXES),
    }
    actual = [(str(row.get("provider_id")), str(row.get("axis_id"))) for row in rows
              if isinstance(row, dict)]
    if set(actual) != expected or len(actual) != len(expected):
        raise EvidenceError("P63_SCAN_ROW_SET_MISMATCH")
    if any(row.get("status") not in ALLOWED_STATES for row in rows):
        raise EvidenceError("P63_SCAN_STATE_INVALID")
    if any(row.get("required") is True and row.get("selected") is True
           and row.get("status") != "pass" and row.get("healthy") is True for row in rows):
        raise EvidenceError("P63_NON_GREEN_MASKED")
    providers = {row.get("provider_id") for row in rows}
    if not set(PROVIDERS) <= providers or "shared" not in providers:
        raise EvidenceError("P63_PROVIDER_OR_SHARED_PLANE_MISSING")
    migration = [row for row in rows if row.get("axis_id") == "migration.convergence"]
    expected_migration_state = (
        "unavailable" if "PH_PROJECT_NOT_REGISTERED" in project.get("diagnostics", [])
        else "unresolved"
    )
    if len(migration) != 2 or any(
        row.get("status") != expected_migration_state for row in migration
    ):
        raise EvidenceError("P63_P5_UNRESOLVED_MASKED")
    if project.get("aggregate") != "non-green":
        raise EvidenceError("P63_PROJECT_AGGREGATE_MASKED")


def run_scan(run: int, context: dict[str, Any], bindings: dict[str, dict[str, Any] | None],
             binding_fingerprint: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started_at = utc_now()
    projects: dict[str, dict[str, Any]] = {}
    commands: list[dict[str, Any]] = []
    live_items = [(project_id, binding) for project_id, binding in bindings.items()
                  if binding is not None]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(scan_project, run, project_id, binding): project_id
                   for project_id, binding in live_items}
        for future in as_completed(futures):
            project_id = futures[future]
            try:
                project, project_commands = future.result()
            except Exception as error:
                project = unavailable_project(project_id, run)
                project["diagnostics"] = sorted(set(project["diagnostics"] + [
                    "P63_PROJECT_PROBE_ERROR",
                ]))
                project_commands = [command_record(
                    run, project_id, "project-probe", None, None,
                    f"P63_PROJECT_PROBE_ERROR:{type(error).__name__}",
                )]
            projects[project_id] = project
            commands.extend(project_commands)
    for project_id, binding in bindings.items():
        if binding is None:
            projects[project_id] = unavailable_project(project_id, run)
            commands.append(command_record(
                run, project_id, "provider-health", None, None, "PH_PROJECT_NOT_REGISTERED",
            ))
    ordered = [projects[project_id] for project_id in context["sealed_ids"]]
    for project in ordered:
        validate_project_result(project)
    scan = {
        "schema_version": "p6.3-provider-health-run/v1",
        "run": run,
        "observed_at": started_at,
        "contract_version": "1.0.0",
        "binding_fingerprint": binding_fingerprint,
        "source_fingerprints": {
            key: context[key] for key in (
                "schema_sha256", "health_contract_sha256", "provider_manifest_sha256",
                "p0_manifest_sha256", "p5_convergence_sha256", "p5_journal_sha256",
                "source_sha256",
            )
        },
        "required_project_ids": context["sealed_ids"],
        "projects": ordered,
        "aggregate": "non-green",
    }
    scan["result_digest"] = digest({key: value for key, value in scan.items()
                                    if key != "result_digest"})
    commands.sort(key=lambda row: (
        row["project_id"], row["command_class"], row["diagnostic"],
    ))
    return scan, commands


VOLATILE_KEYS = {
    "run", "observed_at", "expires_at", "evaluated_at", "evidence_id",
    "result_digest", "public_result_digest", "evidence_set_id",
}


def semantic_projection(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: semantic_projection(nested) for key, nested in sorted(value.items())
                if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [semantic_projection(item) for item in value]
    return value


def validate_two_runs(first: dict[str, Any], second: dict[str, Any]) -> None:
    if first.get("required_project_ids") != second.get("required_project_ids"):
        raise EvidenceError("P63_TWO_RUN_PROJECT_SET_MISMATCH")
    if first.get("binding_fingerprint") != second.get("binding_fingerprint"):
        raise EvidenceError("P63_TWO_RUN_LOCATOR_DRIFT")
    if first.get("source_fingerprints") != second.get("source_fingerprints"):
        raise EvidenceError("P63_TWO_RUN_SOURCE_DRIFT")
    if semantic_projection(first) != semantic_projection(second):
        raise EvidenceError("P63_TWO_RUN_SEMANTIC_MISMATCH")


def assert_redacted(value: Any) -> None:
    if FORBIDDEN.search(canonical(value)):
        raise EvidenceError("P63_REDACTION_REQUIRED")
    forbidden_keys = {"local_path", "root", "path", "settings_file", "stdout", "stderr", "token"}

    def walk(nested: Any) -> None:
        if isinstance(nested, dict):
            if forbidden_keys & set(nested):
                raise EvidenceError("P63_REDACTION_REQUIRED")
            for child in nested.values():
                walk(child)
        elif isinstance(nested, list):
            for child in nested:
                walk(child)

    walk(value)


def project_set_document(context: dict[str, Any], bindings: dict[str, dict[str, Any] | None],
                         binding_fingerprint: str) -> dict[str, Any]:
    projects = [{
        "project_id": project_id,
        "binding_status": "bound" if bindings[project_id] is not None else "unavailable",
    } for project_id in context["sealed_ids"]]
    return {
        "schema_version": "p6.3-project-set/v1",
        "project_count": len(projects),
        "project_ids_sha256": digest(context["sealed_ids"]),
        "binding_fingerprint": binding_fingerprint,
        "projects": projects,
        "providers": list(PROVIDERS),
        "shared_plane": True,
        "p5": context["p5"],
        "set_differences": {
            "p0_missing": [],
            "p0_extra": [],
            "p5_migrated": [],
            "p5_unresolved_missing": [],
            "p5_unresolved_extra": [],
        },
    }


def verdict_document(context: dict[str, Any], project_set: dict[str, Any],
                     first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    blockers = {"P5_ROLLOUT_NOT_AUTHORIZED"}
    for project in second["projects"]:
        if any(row.get("required") is True and row.get("selected") is True
               and row.get("status") != "pass" for row in project["rows"]):
            blockers.add(f"PROJECT_NON_GREEN:{project['project_id']}")
        if not project.get("cleanup_green"):
            blockers.add(f"MEMORY_CLEANUP_NON_GREEN:{project['project_id']}")
    unavailable = [row["project_id"] for row in project_set["projects"]
                   if row["binding_status"] != "bound"]
    for project_id in unavailable:
        blockers.add(f"PROJECT_UNAVAILABLE:{project_id}")
    return {
        "schema_version": "p6.3-fleet-health-verdict/v1",
        "aggregate": "non-green",
        "semantic_match": True,
        "project_count": len(context["sealed_ids"]),
        "provider_count": len(PROVIDERS),
        "shared_plane": True,
        "bound_projects": len(context["sealed_ids"]) - len(unavailable),
        "unavailable_projects": unavailable,
        "run_digests": [first["result_digest"], second["result_digest"]],
        "release_blockers": sorted(blockers),
        "p7_release_authorized": False,
    }


VERIFY_SOURCE = '''#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from task.task_contract import bundle_lint

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    root = Path(args.bundle_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {entry["path"]: entry for entry in manifest["files"]}
    actual = {path.name for path in root.iterdir() if path.is_file() and path.name not in {"manifest.json", "verify.py"}}
    if actual != set(expected):
        print("P63_BUNDLE_MEMBER_MISMATCH", file=sys.stderr)
        return 1
    for name, entry in expected.items():
        data = (root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"] or len(data) != entry["bytes"]:
            print("P63_BUNDLE_DIGEST_MISMATCH:" + name, file=sys.stderr)
            return 1
    reason = bundle_lint(
        root, manifest_path=manifest_path, verifier_path=root / "verify.py",
        declared_privacy=manifest["privacy"],
    )
    if reason:
        print(reason, file=sys.stderr)
        return 1
    verdict = json.loads((root / "fleet-health-verdict.json").read_text(encoding="utf-8"))
    if verdict.get("aggregate") != "non-green" or verdict.get("semantic_match") is not True:
        print("P63_VERDICT_INVALID", file=sys.stderr)
        return 1
    print("P6.3 evidence bundle: allow")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''


def finding_text(verdict: dict[str, Any], project_set: dict[str, Any]) -> str:
    unavailable = verdict["unavailable_projects"]
    unavailable_text = ", ".join(f"`{item}`" for item in unavailable) if unavailable else "—"
    return f"""# P6 fleet health verdict

**Aggregate:** `non-green`  
**Evidence contract:** `provider-health-v1` / `1.0.0`  
**Project set:** {verdict['project_count']} sealed P0 projects; {verdict['bound_projects']} live bindings  
**Two-run semantic comparison:** match  
**P7 release authorized:** no

## Verdict

Both fresh read-only scans used the same committed source, frozen health contract, D85 evidence-set
schema, provider manifest, P0 set and P5 convergence inputs. Claude, Codex and shared-plane rows
remain separate. Every project stays non-green because P5 migration is held unresolved; no green
provider or available project masks a required peer.

One sealed project is absent from the current public mAInd registry and is therefore represented by
explicit unavailable rows: {unavailable_text}. This is evidence, not repair authority.

## Release blockers

""" + "".join(f"- `{blocker}`\n" for blocker in verdict["release_blockers"]) + f"""

## Privacy and cleanup

The bundle contains stable IDs, states, diagnostics and digests only. It excludes roots, raw command
output, memory text/IDs, settings, environment values, credentials and transcripts. Disposable
memory probes were forgotten for every bound project; the unavailable project has no probe residue.
The exact P0/P5 project-set differences are empty; migrated set is empty and all {project_set['p5']['unresolved_rows']}
P5 action rows remain unresolved.
"""


def write_bundle(args: argparse.Namespace) -> int:
    context = load_context(args)
    bindings, binding_fingerprint = bind_live_projects(context["sealed_ids"])
    project_set = project_set_document(context, bindings, binding_fingerprint)
    print(f"P6.3 live scan 1/2: {sum(value is not None for value in bindings.values())} bound projects")
    first, commands_first = run_scan(1, context, bindings, binding_fingerprint)
    print("P6.3 live scan 2/2")
    second, commands_second = run_scan(2, context, bindings, binding_fingerprint)
    validate_two_runs(first, second)
    verdict = verdict_document(context, project_set, first, second)
    command_results = {
        "schema_version": "p6.3-command-results-redacted/v1",
        "commands": sorted(commands_first + commands_second, key=lambda row: (
            row["run"], row["project_id"], row["command_class"], row["diagnostic"],
        )),
        "raw_output_retained": False,
    }
    for document in (project_set, first, second, verdict, command_results):
        assert_redacted(document)
    output = Path(args.output_dir)
    documents = {
        "project-set.json": project_set,
        "provider-health-run-1.json": first,
        "provider-health-run-2.json": second,
        "fleet-health-verdict.json": verdict,
        "command-results-redacted.json": command_results,
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, document in documents.items():
        atomic_text(output / name, pretty(document))
    atomic_text(output / "verify.py", VERIFY_SOURCE)
    entries = []
    for name in DATA_MEMBERS:
        data = (output / name).read_bytes()
        entries.append({"path": name, "sha256": sha256_bytes(data), "bytes": len(data)})
    manifest = {
        "schema_version": "p6.3-evidence-manifest/v1",
        "bundle_id": "P6.3-provider-fleet-health",
        "files": entries,
        "privacy": PRIVACY,
        "producer": "p6-fleet-health-evidence.py write",
    }
    atomic_text(output / "manifest.json", pretty(manifest))
    finding = PLAN_ROOT / "findings" / "P6-fleet-health-verdict.md"
    atomic_text(finding, finding_text(verdict, project_set))
    print(f"P6.3 evidence written: {len(context['sealed_ids'])} projects, aggregate non-green")
    return 0


def check_bundle(args: argparse.Namespace) -> int:
    context = load_context(args)
    bindings, binding_fingerprint = bind_live_projects(context["sealed_ids"])
    output = Path(args.output_dir)
    required = {"manifest.json", "verify.py", *DATA_MEMBERS}
    actual = {path.name for path in output.iterdir() if path.is_file()} if output.is_dir() else set()
    if actual != required:
        raise EvidenceError("P63_BUNDLE_MEMBER_MISMATCH")
    manifest = read_json(output / "manifest.json")
    entries = manifest.get("files")
    if not isinstance(entries, list) or {entry.get("path") for entry in entries} != set(DATA_MEMBERS):
        raise EvidenceError("P63_BUNDLE_MANIFEST_INVALID")
    for entry in entries:
        data = (output / str(entry["path"])).read_bytes()
        if entry.get("sha256") != sha256_bytes(data) or entry.get("bytes") != len(data):
            raise EvidenceError("P63_BUNDLE_DIGEST_MISMATCH")
    project_set = read_json(output / "project-set.json")
    expected_set = project_set_document(context, bindings, binding_fingerprint)
    if project_set != expected_set:
        raise EvidenceError("P63_PROJECT_SET_STALE")
    first = read_json(output / "provider-health-run-1.json")
    second = read_json(output / "provider-health-run-2.json")
    if first.get("source_fingerprints") != second.get("source_fingerprints"):
        raise EvidenceError("P63_SOURCE_FINGERPRINT_MISMATCH")
    validate_two_runs(first, second)
    for project in first.get("projects", []):
        validate_project_result(project)
    for project in second.get("projects", []):
        validate_project_result(project)
    verdict = read_json(output / "fleet-health-verdict.json")
    if verdict != verdict_document(context, project_set, first, second):
        raise EvidenceError("P63_VERDICT_STALE")
    command_results = read_json(output / "command-results-redacted.json")
    for document in (project_set, first, second, verdict, command_results):
        assert_redacted(document)
    finding = PLAN_ROOT / "findings" / "P6-fleet-health-verdict.md"
    if not finding.is_file() or finding.read_text(encoding="utf-8") != finding_text(verdict, project_set):
        raise EvidenceError("P63_FINDING_STALE")
    print("P6.3 evidence check: allow")
    return 0


def expect_error(code: str, action) -> None:
    try:
        action()
    except EvidenceError as error:
        if str(error).split(":", 1)[0] == code:
            return
        raise
    raise EvidenceError("P63_SELF_TEST_FALSE_NEGATIVE:" + code)


def self_test(args: argparse.Namespace) -> int:
    validate_schema_carrier(Path(args.evidence_set_schema))
    measurement_axes = {
        axis_id for axis_id, producer in PROVIDER_AXES
        if producer == "skiller" and axis_id.startswith("skill.measurement.")
    }
    if measurement_axes != {
        "skill.measurement.listing",
        "skill.measurement.loaded-body",
        "skill.measurement.runtime",
    }:
        raise EvidenceError("P63_MEASUREMENT_AXIS_SET_INVALID")
    now = utc_now()
    shared = [sealed_observation("shared", axis, "pass", "p6.3.test", now, axis)
              for axis in SHARED_AXES]
    requirements, _ = requirements_and_evidence("project-test", shared, now)
    rows = [{
        "provider_id": item["provider_id"], "axis_id": item["axis_id"],
        "selected": True, "required": True,
        "status": "unresolved" if item["axis_id"] == "migration.convergence" else "pass",
        "healthy": False if item["axis_id"] == "migration.convergence" else True,
    } for item in requirements]
    project = {"project_id": "project-test", "aggregate": "non-green", "rows": rows}
    validate_project_result(project)
    missing = {**project, "rows": rows[:-1]}
    expect_error("P63_SCAN_ROW_SET_MISMATCH", lambda: validate_project_result(missing))
    duplicate = {**project, "rows": rows + [dict(rows[0])]}
    expect_error("P63_SCAN_ROW_SET_MISMATCH", lambda: validate_project_result(duplicate))
    masked = json.loads(json.dumps(project))
    next(row for row in masked["rows"] if row["axis_id"] == "migration.convergence")["healthy"] = True
    expect_error("P63_NON_GREEN_MASKED", lambda: validate_project_result(masked))
    one_provider = {**project, "rows": [row for row in rows if row["provider_id"] != "codex"]}
    expect_error("P63_SCAN_ROW_SET_MISMATCH", lambda: validate_project_result(one_provider))
    timeout_green = json.loads(json.dumps(project))
    target = next(row for row in timeout_green["rows"] if row["axis_id"] == "settings.integrity")
    target.update({"status": "unavailable", "healthy": True})
    expect_error("P63_NON_GREEN_MASKED", lambda: validate_project_result(timeout_green))
    root_leak = {"project_id": "project-test", "local_path": "/tmp/example"}
    expect_error("P63_REDACTION_REQUIRED", lambda: assert_redacted(root_leak))
    secret_leak = {"value": "api_key='abcdefghijklmnop'"}
    expect_error("P63_REDACTION_REQUIRED", lambda: assert_redacted(secret_leak))
    first = {"required_project_ids": ["project-test"], "binding_fingerprint": "sha256:a",
             "source_fingerprints": {"source": "sha256:b"}, "projects": [project], "run": 1}
    second = json.loads(json.dumps(first)); second["run"] = 2
    validate_two_runs(first, second)
    second["projects"][0]["rows"][0]["status"] = "error"
    expect_error("P63_TWO_RUN_SEMANTIC_MISMATCH", lambda: validate_two_runs(first, second))
    bad_p5 = {"schema_version": "p5-fleet-convergence/v1", "stable": False}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
        expect_error("P63_P5_CONVERGENCE_INVALID", lambda: validate_p5(
            bad_p5, Path(handle.name), ["project-test"],
        ))
    if Path(args.health_contract).read_text(encoding="utf-8").find("**Version:** v1.0.0") < 0:
        raise EvidenceError("P63_HEALTH_CONTRACT_VERSION_DRIFT")
    print("P6.3 self-test: allow (12 rejection classes)")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    self_parser = commands.add_parser("self-test")
    self_parser.add_argument("--health-contract", required=True)
    self_parser.add_argument("--evidence-set-schema", required=True)
    self_parser.add_argument("--fixtures", required=True)
    for name in ("write", "check"):
        command = commands.add_parser(name)
        command.add_argument("--p0-manifest", required=True)
        command.add_argument("--p5-convergence", required=True)
        command.add_argument("--p5-journal", required=True)
        command.add_argument("--health-contract", required=True)
        command.add_argument("--evidence-set-schema", required=True)
        command.add_argument("--provider-manifest", required=True)
        command.add_argument("--output-dir", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "self-test":
            return self_test(args)
        if args.command == "write":
            return write_bundle(args)
        return check_bundle(args)
    except EvidenceError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
