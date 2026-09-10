#!/usr/bin/env python3
"""Plan and execute the owner-gated P6.1 Brain transaction.

The live planner consumes sealed P0/P5 carriers and only public worktree-local
CLIs.  It never reads provider configuration files directly.  The committed
plan is redacted and immutable; apply/resume require a separate owner approval
bound to its exact hashes.  The journal is the restart authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


PLAN_ID = "2026.08.02-PROVIDER-CONTRACT-LOCALE"
PLAN_VERSION = "p6-brain-repair-plan/v1"
EVENT_VERSION = "p6-brain-transaction-event/v1"
RESULT_VERSION = "p6-brain-repair-results/v1"
ZERO_HASH = "0" * 64
PROVIDERS = ("claude-code", "codex")
TERMINAL_EVENTS = frozenset({"accepted", "rolled-back"})
EVENTS = frozenset({
    "before-apply", "after-apply", "before-readback", "after-readback",
    "rollback-started", "accepted", "rolled-back",
})
TRANSITIONS = {
    None: {"before-apply", "rollback-started"},
    "before-apply": {"after-apply", "rollback-started"},
    "after-apply": {"before-readback", "rollback-started"},
    "before-readback": {"after-readback", "rollback-started"},
    "after-readback": {"accepted", "rollback-started"},
    "rollback-started": {"rolled-back"},
    "accepted": set(),
    "rolled-back": set(),
}
ABSOLUTE = re.compile(r"(?:^|[\s\"'])(?:/home/|/Users/|[A-Za-z]:\\)")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}$")
DECISION = re.compile(r"D[1-9][0-9]*$")
SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})"
)

SCRIPT = Path(__file__).resolve()
PLAN_DIR = SCRIPT.parent.parent
REPO = PLAN_DIR.parent.parent
P0_BRANCH = PLAN_DIR / "artifacts" / "P0.4" / "branch-verdict.json"
P5_MANIFEST = PLAN_DIR / "artifacts" / "P5" / "fleet-action-manifest.json"


class Refusal(RuntimeError):
    """Fail-closed contract refusal."""


class InjectedCrash(RuntimeError):
    """Deterministic crash point used by the committed fixture suite."""


def _carrier(name: str, default: Path) -> Path:
    """Test-only carrier override; production calls always use sealed defaults."""
    return Path(os.environ.get(name, str(default)))


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_value(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def digest_file(path: Path) -> str:
    try:
        return digest_bytes(path.read_bytes())
    except OSError as exc:
        raise Refusal(f"P6_SOURCE_UNREADABLE:{path.name}") from exc


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal(f"P6_JSON_INVALID:{path.name}") from exc


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def initialize_journal(path: Path) -> None:
    if path.exists():
        if path.read_bytes():
            validate_journal(path)
        return
    atomic_write(path, b"")


def _run_json(command: list[str], *, accepted: frozenset[int] = frozenset({0})) -> tuple[dict[str, Any], str]:
    completed = subprocess.run(command, cwd=REPO, text=True, capture_output=True, check=False)
    if completed.returncode not in accepted:
        raise Refusal(f"P6_PUBLIC_CLI_FAILED:{Path(command[0]).name}:{completed.returncode}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise Refusal(f"P6_PUBLIC_CLI_SCHEMA:{Path(command[0]).name}") from exc
    if not isinstance(value, dict):
        raise Refusal(f"P6_PUBLIC_CLI_SCHEMA:{Path(command[0]).name}")
    return value, completed.stderr


def _public_observations(project_id: str) -> tuple[dict[str, Any], Path]:
    maind, _ = _run_json([
        str(REPO / "packages/maind/bin/maind"), "health", "--project", project_id, "--json",
    ])
    root_value = maind.get("path")
    if not isinstance(root_value, str):
        raise Refusal("P6_BRAIN_LOCATOR_MISSING")
    project_root = Path(root_value)
    if not project_root.is_dir():
        raise Refusal("P6_BRAIN_UNAVAILABLE")

    skiller, skiller_stderr = _run_json([
        str(REPO / "packages/skiller/bin/skiller"), "status", "--target", str(project_root), "--json",
    ])
    harness, _ = _run_json([
        str(REPO / "packages/harness/bin/harness"), "doctor", "--settings",
        "--target", str(project_root), "--json",
    ], accepted=frozenset({0, 1, 2}))
    budgets: dict[str, dict[str, Any]] = {}
    for provider in PROVIDERS:
        report, stderr = _run_json([
            str(REPO / "packages/skiller/bin/skiller"), "budget", "--target",
            str(project_root), "--provider", provider, "--first-turn", "--json",
        ])
        budgets[provider] = {
            "status": "green" if report.get("verdict") == "OK" else "non-green",
            "total": report.get("total"),
            "unit": "estimated_tokens",
            "method": "skiller:first-turn",
            "uncertainty": "provider-reported estimate",
            "dependency_warning": "requires" in stderr,
        }

    trust_rows = []
    for row in maind.get("provider_trust", []):
        if isinstance(row, dict) and row.get("provider_id") in PROVIDERS:
            trust_rows.append({
                "provider_id": row["provider_id"],
                "status": "green" if row.get("green") is True else "non-green",
                "diagnostic_ids": sorted(item for item in row.get("diagnostics", []) if isinstance(item, str)),
            })
    trust_rows.sort(key=lambda row: row["provider_id"])
    if [row["provider_id"] for row in trust_rows] != list(PROVIDERS):
        raise Refusal("P6_PROVIDER_SET_MISMATCH")

    findings = harness.get("findings", [])
    if not isinstance(findings, list):
        raise Refusal("P6_HARNESS_SCHEMA")
    harness_rows = sorted(
        ({"id": row.get("id"), "level": row.get("level")} for row in findings if isinstance(row, dict)),
        key=lambda row: (str(row["level"]), str(row["id"])),
    )
    connect = skiller.get("connect") if isinstance(skiller.get("connect"), dict) else {}
    observations = {
        "provider_trust": trust_rows,
        "dependency_closure": {
            "status": "non-green" if "requires" in skiller_stderr else "green",
            "diagnostic_id": "SKILL_REQUIRED_EXCLUDED" if "requires" in skiller_stderr else None,
        },
        "channels": {
            "registered": sorted(item for item in skiller.get("registered_channels", []) if isinstance(item, str)),
            "extra_count": len(connect.get("extra", [])) if isinstance(connect.get("extra"), list) else None,
            "missing_count": len(connect.get("missing", [])) if isinstance(connect.get("missing"), list) else None,
        },
        "budget": budgets,
        "settings": {
            "counts": harness.get("counts"),
            "finding_rows": harness_rows,
            "status": "green" if harness.get("counts", {}).get("error") == 0 else "non-green",
        },
        "operations": {
            "memory_roundtrip": maind.get("memory_roundtrip") is True,
            "maind_mcp": maind.get("maind_mcp") is True,
            "code_mcp": maind.get("code_mcp") is True,
        },
    }
    return observations, project_root


def collect_observations(project_id: str) -> tuple[dict[str, Any], Path]:
    fixture = os.environ.get("P6_BRAIN_FIXTURE")
    if fixture:
        value = load_json(Path(fixture))
        observations = value.get("observations")
        root = value.get("fixture_root")
        if not isinstance(observations, dict) or not isinstance(root, str):
            raise Refusal("P6_FIXTURE_SCHEMA")
        return observations, Path(root)
    return _public_observations(project_id)


def _contract_identity(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    version = re.search(r"^\*\*Version:\*\*\s+(v?[0-9]+\.[0-9]+\.[0-9]+)", text, re.M)
    status = re.search(r"^\*\*Status:\*\*\s+(\S+)", text, re.M)
    if not version or not status or status.group(1) != "frozen":
        raise Refusal(f"P6_CONTRACT_NOT_FROZEN:{path.name}")
    return {"version": version.group(1), "sha256": digest_file(path)}


def _bind_sealed_project(p0_manifest: Path, project_root: Path) -> str:
    manifest = load_json(p0_manifest)
    if manifest.get("bundle_id") != "P0.1-provider-fleet-baseline":
        raise Refusal("P6_P0_MANIFEST_VERSION")
    required = {"provider-source-snapshot.json", "provider-fleet-inventory.json"}
    if not required.issubset(set(manifest.get("files", []))):
        raise Refusal("P6_P0_MANIFEST_INCOMPLETE")
    snapshot = load_json(p0_manifest.parent / "provider-source-snapshot.json")
    if snapshot.get("schema_version") != 2 or not isinstance(snapshot.get("projects"), list):
        raise Refusal("P6_P0_SNAPSHOT_VERSION")
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root, text=True, capture_output=True, check=False,
    )
    head = completed.stdout.strip() if completed.returncode == 0 else None
    matches = [
        row.get("project_id") for row in snapshot["projects"]
        if isinstance(row, dict) and isinstance(row.get("repository"), dict)
        and row["repository"].get("head") == head
    ]
    if head is None or len(matches) != 1 or not isinstance(matches[0], str):
        raise Refusal("P6_BRAIN_SEALED_IDENTITY_MISMATCH")
    return matches[0]


def _source_identities(
    p0_manifest: Path, p5_convergence: Path, p5_journal: Path,
    recovery_contract: Path, control_plane_contract: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    convergence = load_json(p5_convergence)
    if convergence.get("schema_version") != "p5-fleet-convergence/v1" or convergence.get("stable") is not True:
        raise Refusal("P6_P5_CONVERGENCE_INVALID")
    p5_manifest_path = _carrier("P6_P5_MANIFEST", P5_MANIFEST)
    p0_branch_path = _carrier("P6_P0_BRANCH", P0_BRANCH)
    manifest = load_json(p5_manifest_path)
    if convergence.get("manifest_sha256") != manifest.get("manifest_sha256"):
        raise Refusal("P6_P5_MANIFEST_DRIFT")
    if digest_file(p5_manifest_path).removeprefix("sha256:") == "":
        raise Refusal("P6_P5_MANIFEST_INVALID")
    branch = load_json(p0_branch_path)
    if branch.get("schema_version") != "p0-branch-verdict/v3":
        raise Refusal("P6_P0_BRANCH_VERSION")
    identities = {
        "p0_manifest": digest_file(p0_manifest),
        "p0_branch": digest_file(p0_branch_path),
        "p5_convergence": digest_file(p5_convergence),
        "p5_journal": digest_file(p5_journal),
        "p5_manifest": manifest.get("manifest_sha256"),
        "recovery_contract": _contract_identity(recovery_contract),
        "control_plane_contract": _contract_identity(control_plane_contract),
    }
    return identities, {"convergence": convergence, "manifest": manifest, "branch": branch}


def _unresolved_rows(
    observations: dict[str, Any], sealed_project_id: str, sealed: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    branch = sealed["branch"]
    if branch.get("branch") == "no-op":
        rows.append({
            "axis": "credential-containment", "owner": "P0.4",
            "status": "unresolved", "reason": "no mutation authority",
        })
    for trust in observations["provider_trust"]:
        if trust["status"] != "green":
            rows.append({
                "axis": "provider-trust", "owner": "harness",
                "provider_id": trust["provider_id"], "status": "unresolved",
                "reason": "explicit trusted operation required",
            })
    if observations["dependency_closure"]["status"] != "green":
        rows.append({
            "axis": "skill-dependency", "owner": "skiller", "status": "unresolved",
            "reason": "owner must choose requester removal or dependency inclusion",
        })
    if observations["settings"]["status"] != "green":
        rows.append({
            "axis": "settings-security", "owner": "harness", "status": "unresolved",
            "reason": "credential action remains P0.4 owner-gated",
        })
    if observations["channels"].get("extra_count"):
        rows.append({
            "axis": "channel-profile", "owner": "skiller", "status": "unresolved",
            "reason": "no exact public owner-qualified normalization action",
        })
    for provider, budget in sorted(observations["budget"].items()):
        if budget.get("status") != "green":
            rows.append({
                "axis": "first-turn-budget", "owner": "skiller", "provider_id": provider,
                "status": "unresolved", "reason": "policy threshold exceeded",
            })
    manifest_rows = sealed["manifest"].get("rows", [])
    p5_rows = [row for row in manifest_rows if isinstance(row, dict) and row.get("project_id") == sealed_project_id]
    unresolved_ids = sorted(
        row.get("action_id") for row in p5_rows
        if row.get("action") == "no-op-unresolved" and isinstance(row.get("action_id"), str)
    )
    if unresolved_ids:
        rows.append({
            "axis": "p5-unresolved", "owner": "P5", "status": "unresolved",
            "count": len(unresolved_ids), "action_ids_sha256": digest_value(unresolved_ids),
            "reason": "P6.1 excludes P5 unresolved repair",
        })
    return sorted(rows, key=lambda row: (row["axis"], row.get("provider_id", "")))


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    observations, project_root = collect_observations(args.project_id)
    sealed_project_id = _bind_sealed_project(Path(args.p0_manifest), project_root)
    sources, sealed = _source_identities(
        Path(args.p0_manifest), Path(args.p5_convergence), Path(args.p5_journal),
        Path(args.recovery_contract), Path(args.control_plane_contract),
    )
    actions: list[dict[str, Any]] = []
    unresolved = _unresolved_rows(observations, sealed_project_id, sealed)
    observation_sha = digest_value(observations)
    action_set_id = "action-set-" + digest_value(actions).removeprefix("sha256:")[:24]
    base = {
        "schema_version": PLAN_VERSION,
        "plan_id": PLAN_ID,
        "project_id": args.project_id,
        "sealed_project_id": sealed_project_id,
        "source_identities": sources,
        "observations": observations,
        "observation_sha256": observation_sha,
        "action_set_id": action_set_id,
        "actions": actions,
        "expected_preimage_sha256": observation_sha,
        "expected_postimage_sha256": observation_sha,
        "backup_id": "backup-not-created-empty-action-set",
        "rollback_id": "rollback-whole-brain-exact-preimage",
        "unresolved": unresolved,
        "owner_approval_required": True,
    }
    base["plan_sha256"] = digest_value(base)
    validate_plan(base)
    return base


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != PLAN_VERSION or plan.get("plan_id") != PLAN_ID:
        raise Refusal("P6_PLAN_VERSION")
    claimed = plan.get("plan_sha256")
    payload = dict(plan)
    payload.pop("plan_sha256", None)
    if claimed != digest_value(payload):
        raise Refusal("P6_PLAN_DIGEST")
    for key in ("observation_sha256", "expected_preimage_sha256", "expected_postimage_sha256"):
        if not isinstance(plan.get(key), str) or not DIGEST.fullmatch(plan[key]):
            raise Refusal("P6_PLAN_IDENTITY")
    actions = plan.get("actions")
    if not isinstance(actions, list) or len({row.get("action_id") for row in actions}) != len(actions):
        raise Refusal("P6_ACTION_SET_INVALID")
    expected_action_set = "action-set-" + digest_value(actions).removeprefix("sha256:")[:24]
    if plan.get("action_set_id") != expected_action_set:
        raise Refusal("P6_ACTION_SET_DIGEST")
    for row in actions:
        if not isinstance(row, dict) or not isinstance(row.get("action_id"), str):
            raise Refusal("P6_ACTION_SET_INVALID")
        if row.get("kind") == "full-access":
            raise Refusal("P6_IMPLICIT_FULL_ACCESS")
        if row.get("kind") == "p5-unresolved-repair":
            raise Refusal("P6_P5_UNRESOLVED_MUTATION")
        provider = row.get("provider_id")
        owner = row.get("target_owner")
        if (provider == "claude-code" and owner == "codex") or (provider == "codex" and owner == "claude-code"):
            raise Refusal("P6_CROSS_PROVIDER_ACTION")
        if not row.get("rollback_id") or not row.get("backup_id"):
            raise Refusal("P6_ACTION_ROLLBACK_MISSING")
    serialized = canonical_bytes(plan).decode("utf-8")
    if ABSOLUTE.search(serialized):
        raise Refusal("P6_PRIVACY_ROOT")
    if SECRET_VALUE.search(serialized):
        raise Refusal("P6_PRIVACY_SECRET")


def parse_approval(path: Path, plan: dict[str, Any]) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refusal("P6_APPROVAL_MISSING") from exc
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().lower()] = value.strip()
    required = {
        "status": "approved",
        "plan sha-256": plan["plan_sha256"],
        "action set id": plan["action_set_id"],
        "preimage sha-256": plan["expected_preimage_sha256"],
        "rollback id": plan["rollback_id"],
        "approver": "repository owner",
    }
    if any(fields.get(key) != value for key, value in required.items()):
        raise Refusal("P6_APPROVAL_MISMATCH")
    if not DECISION.fullmatch(fields.get("owner decision", "")):
        raise Refusal("P6_APPROVAL_DECISION")
    if SECRET_VALUE.search(text) or ABSOLUTE.search(text):
        raise Refusal("P6_APPROVAL_PRIVACY")
    return fields


def _event_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate_journal(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise Refusal("P6_JOURNAL_MISSING")
    events: list[dict[str, Any]] = []
    previous = ZERO_HASH
    prior_event: str | None = None
    for ordinal, raw in enumerate(path.read_bytes().splitlines()):
        try:
            event = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Refusal("P6_JOURNAL_TORN_OR_TRUNCATED") from exc
        if canonical_bytes(event) != raw:
            raise Refusal("P6_JOURNAL_NONCANONICAL")
        if event.get("schema_version") != EVENT_VERSION or event.get("ordinal") != ordinal:
            raise Refusal("P6_JOURNAL_ORDINAL")
        if event.get("previous_event_sha256") != previous:
            raise Refusal("P6_JOURNAL_PREVIOUS_HASH")
        if event.get("event_sha256") != _event_hash(event):
            raise Refusal("P6_JOURNAL_EVENT_HASH")
        if event.get("event") not in EVENTS:
            raise Refusal("P6_JOURNAL_EVENT_UNKNOWN")
        if event["event"] not in TRANSITIONS[prior_event]:
            raise Refusal("P6_JOURNAL_TRANSITION")
        previous = event["event_sha256"]
        prior_event = event["event"]
        events.append(event)
    terminal = [event for event in events if event["event"] in TERMINAL_EVENTS]
    if terminal and terminal[-1] is not events[-1]:
        raise Refusal("P6_JOURNAL_AFTER_TERMINAL")
    return events


def _crash(boundary: str) -> None:
    if os.environ.get("P6_CRASH_AFTER") == boundary:
        raise InjectedCrash(boundary)


def append_event(path: Path, base: dict[str, Any], event_name: str, boundary_id: str) -> dict[str, Any]:
    events = validate_journal(path)
    if events and events[-1]["event"] in TERMINAL_EVENTS:
        raise Refusal("P6_JOURNAL_TERMINAL")
    event = {
        "schema_version": EVENT_VERSION,
        "ordinal": len(events),
        "previous_event_sha256": events[-1]["event_sha256"] if events else ZERO_HASH,
        "event": event_name,
        "boundary_id": boundary_id,
        **base,
    }
    event["event_sha256"] = _event_hash(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab", buffering=0) as handle:
        handle.write(canonical_bytes(event) + b"\n")
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)
    validate_journal(path)
    _crash(f"append-{event_name}")
    return event


def _base_event(plan: dict[str, Any], approval_path: Path) -> dict[str, Any]:
    return {
        "transaction_id": "brain-" + plan["plan_sha256"].removeprefix("sha256:")[:24],
        "project_id": plan["project_id"],
        "sealed_project_id": plan["sealed_project_id"],
        "plan_sha256": plan["plan_sha256"],
        "approval_sha256": digest_file(approval_path),
        "source_sha256": digest_value(plan["source_identities"]),
        "action_set_id": plan["action_set_id"],
        "expected_preimage_sha256": plan["expected_preimage_sha256"],
        "expected_postimage_sha256": plan["expected_postimage_sha256"],
        "backup_id": plan["backup_id"],
        "state": "durable",
    }


def _current_image(plan: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    fixture_state = os.environ.get("P6_FIXTURE_STATE")
    if fixture_state:
        state = load_json(Path(fixture_state))
        identity = state.get("image_sha256")
        if not isinstance(identity, str) or not DIGEST.fullmatch(identity):
            raise Refusal("P6_FIXTURE_STATE_INVALID")
        fixture = os.environ.get("P6_BRAIN_FIXTURE")
        observations = load_json(Path(fixture)).get("observations") if fixture else None
        if not isinstance(observations, dict):
            raise Refusal("P6_FIXTURE_SCHEMA")
        return identity, observations
    observations, _ = collect_observations(plan["project_id"])
    return digest_value(observations), observations


def _fixture_set_image(identity: str) -> None:
    path = os.environ.get("P6_FIXTURE_STATE")
    if not path:
        return
    atomic_write(Path(path), pretty_bytes({"image_sha256": identity}))


def _apply_actions(plan: dict[str, Any]) -> None:
    if plan["actions"] and not os.environ.get("P6_FIXTURE_STATE"):
        raise Refusal("P6_LIVE_ACTION_UNSUPPORTED")
    _fixture_set_image(plan["expected_postimage_sha256"])
    _crash("public-apply")


def _rollback(plan: dict[str, Any]) -> None:
    _fixture_set_image(plan["expected_preimage_sha256"])
    _crash("public-rollback")


def reconcile_state(plan: dict[str, Any], journal: Path) -> dict[str, Any]:
    events = validate_journal(journal)
    if events and events[-1]["event"] in TERMINAL_EVENTS:
        return {"status": "terminal", "event": events[-1]["event"]}
    current, _ = _current_image(plan)
    if current == plan["expected_postimage_sha256"]:
        return {"status": "continue-readback", "image_sha256": current}
    if current == plan["expected_preimage_sha256"]:
        return {"status": "rollback-exact-preimage", "image_sha256": current}
    partials = {row.get("partial_postimage_sha256") for row in plan["actions"]}
    if current in partials:
        return {"status": "rollback-recognized-partial", "image_sha256": current}
    raise Refusal("P6_RECONCILE_THIRD_STATE")


def _write_results(
    path: Path, plan: dict[str, Any], approval: dict[str, str], journal: Path,
    observations: dict[str, Any], terminal: str,
) -> None:
    events = validate_journal(journal)
    if not events or events[-1]["event"] != terminal or terminal not in TERMINAL_EVENTS:
        raise Refusal("P6_RESULTS_NONTERMINAL")
    result = {
        "schema_version": RESULT_VERSION,
        "project_id": plan["project_id"],
        "sealed_project_id": plan["sealed_project_id"],
        "plan_sha256": plan["plan_sha256"],
        "approval_decision": approval["owner decision"],
        "action_set_id": plan["action_set_id"],
        "terminal_state": terminal,
        "journal_events": len(events),
        "journal_terminal_sha256": events[-1]["event_sha256"],
        "provider_readback": observations.get("provider_trust", []),
        "dependency_closure": observations.get("dependency_closure"),
        "settings": observations.get("settings"),
        "budget": observations.get("budget"),
        "security_disposition": "unresolved-p0.4-owner-gate" if any(
            row["axis"] == "credential-containment" for row in plan["unresolved"]
        ) else "verified",
        "unresolved": plan["unresolved"],
        "aggregate": "non-green" if plan["unresolved"] else "green",
    }
    result["results_sha256"] = digest_value(result)
    validate_results(result, plan, approval, events)
    atomic_write(path, pretty_bytes(result))


def validate_results(
    result: dict[str, Any], plan: dict[str, Any], approval: dict[str, str],
    events: list[dict[str, Any]],
) -> None:
    if result.get("schema_version") != RESULT_VERSION:
        raise Refusal("P6_RESULTS_VERSION")
    claimed = result.get("results_sha256")
    payload = dict(result)
    payload.pop("results_sha256", None)
    if claimed != digest_value(payload):
        raise Refusal("P6_RESULTS_DIGEST")
    if result.get("plan_sha256") != plan["plan_sha256"] or result.get("approval_decision") != approval["owner decision"]:
        raise Refusal("P6_RESULTS_IDENTITY")
    if not events or result.get("terminal_state") != events[-1].get("event"):
        raise Refusal("P6_RESULTS_TERMINAL")
    providers = [row.get("provider_id") for row in result.get("provider_readback", [])]
    if providers != list(PROVIDERS):
        raise Refusal("P6_RESULTS_PROVIDER_SET")
    serialized = canonical_bytes(result).decode("utf-8")
    if ABSOLUTE.search(serialized) or SECRET_VALUE.search(serialized):
        raise Refusal("P6_RESULTS_PRIVACY")


def execute(args: argparse.Namespace, mode: str) -> int:
    plan_path = Path(args.plan)
    plan = load_json(plan_path)
    validate_plan(plan)
    approval_path = Path(args.approval)
    approval = parse_approval(approval_path, plan)
    journal = Path(args.journal)
    results = Path(args.results)
    events = validate_journal(journal)
    base = _base_event(plan, approval_path)
    if events and events[-1]["event"] in TERMINAL_EVENTS:
        if not results.exists():
            _, observations = _current_image(plan)
            _write_results(results, plan, approval, journal, observations, events[-1]["event"])
        return 0

    if mode == "apply" and events:
        raise Refusal("P6_APPLY_REQUIRES_EMPTY_JOURNAL")
    if mode == "apply":
        current, _ = _current_image(plan)
        if current != plan["expected_preimage_sha256"]:
            raise Refusal("P6_PREIMAGE_DRIFT")
        append_event(journal, base, "before-apply", "action-set")
        _apply_actions(plan)
        append_event(journal, base, "after-apply", "action-set")
    else:
        latest = events[-1]["event"] if events else None
        current, _ = _current_image(plan)
        if latest == "rollback-started":
            _rollback(plan)
            current, observations = _current_image(plan)
            if current != plan["expected_preimage_sha256"]:
                raise Refusal("P6_ROLLBACK_READBACK_FAILED")
            append_event(journal, base, "rolled-back", "whole-brain")
            _write_results(results, plan, approval, journal, observations, "rolled-back")
            return 0
        if latest == "before-apply":
            if current == plan["expected_postimage_sha256"]:
                append_event(journal, base, "after-apply", "action-set")
                latest = "after-apply"
            elif current != plan["expected_preimage_sha256"]:
                raise Refusal("P6_RECONCILE_THIRD_STATE")
            else:
                latest = "rollback-exact-preimage"
        if latest == "before-readback":
            current, observations = _current_image(plan)
            _crash("public-readback")
            append_event(journal, base, "after-readback", "dual-provider-dependency-budget-security")
            latest = "after-readback"
        if latest == "after-readback":
            current, observations = _current_image(plan)
            if current == plan["expected_postimage_sha256"]:
                append_event(journal, base, "accepted", "whole-brain")
                _write_results(results, plan, approval, journal, observations, "accepted")
                return 0
            latest = "rollback-readback-drift"
        if latest in {None, "rollback-exact-preimage", "rollback-readback-drift"}:
            append_event(journal, base, "rollback-started", "whole-brain")
            _rollback(plan)
            current, observations = _current_image(plan)
            if current != plan["expected_preimage_sha256"]:
                raise Refusal("P6_ROLLBACK_READBACK_FAILED")
            append_event(journal, base, "rolled-back", "whole-brain")
            _write_results(results, plan, approval, journal, observations, "rolled-back")
            return 0
        if latest != "after-apply":
            raise Refusal("P6_RESUME_STATE_INVALID")

    append_event(journal, base, "before-readback", "dual-provider-dependency-budget-security")
    current, observations = _current_image(plan)
    _crash("public-readback")
    append_event(journal, base, "after-readback", "dual-provider-dependency-budget-security")
    if current != plan["expected_postimage_sha256"]:
        append_event(journal, base, "rollback-started", "whole-brain")
        _rollback(plan)
        current, observations = _current_image(plan)
        if current != plan["expected_preimage_sha256"]:
            raise Refusal("P6_ROLLBACK_READBACK_FAILED")
        append_event(journal, base, "rolled-back", "whole-brain")
        terminal = "rolled-back"
    else:
        append_event(journal, base, "accepted", "whole-brain")
        terminal = "accepted"
    _write_results(results, plan, approval, journal, observations, terminal)
    return 0


def verify_results(args: argparse.Namespace) -> int:
    plan = load_json(Path(args.plan))
    validate_plan(plan)
    approval = parse_approval(Path(args.approval), plan)
    events = validate_journal(Path(args.journal))
    result = load_json(Path(args.results))
    validate_results(result, plan, approval, events)
    current, observations = _current_image(plan)
    terminal = events[-1]["event"] if events else None
    expected = plan["expected_postimage_sha256"] if terminal == "accepted" else plan["expected_preimage_sha256"]
    if current != expected:
        raise Refusal("P6_RESULTS_CURRENT_IMAGE_DRIFT")
    if digest_value(observations.get("provider_trust", [])) != digest_value(result["provider_readback"]):
        raise Refusal("P6_RESULTS_READBACK_DRIFT")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def source_args(command: argparse.ArgumentParser) -> None:
        command.add_argument("--project-id", required=True)
        command.add_argument("--p0-manifest", required=True)
        command.add_argument("--p5-convergence", required=True)
        command.add_argument("--p5-journal", required=True)
        command.add_argument("--recovery-contract", required=True)
        command.add_argument("--control-plane-contract", required=True)

    plan = sub.add_parser("plan")
    source_args(plan)
    plan.add_argument("--output", required=True)
    plan.add_argument("--journal", required=True)
    check = sub.add_parser("check")
    source_args(check)
    check.add_argument("--plan", required=True)
    check.add_argument("--journal", required=True)

    for name in ("apply", "resume", "reconcile", "rollback", "verify-results"):
        command = sub.add_parser(name)
        command.add_argument("--plan", required=True)
        command.add_argument("--approval", required=True)
        command.add_argument("--journal", required=True)
        command.add_argument("--results", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "plan":
        value = build_plan(args)
        output = Path(args.output)
        encoded = pretty_bytes(value)
        if output.exists() and output.read_bytes() != encoded:
            raise Refusal("P6_PLAN_EXISTING_DRIFT")
        if not output.exists():
            atomic_write(output, encoded)
        initialize_journal(Path(args.journal))
        return 0
    if args.command == "check":
        existing = load_json(Path(args.plan))
        validate_plan(existing)
        if build_plan(args) != existing:
            raise Refusal("P6_CHECK_DRIFT")
        validate_journal(Path(args.journal))
        return 0
    if args.command == "apply":
        return execute(args, "apply")
    if args.command == "resume":
        return execute(args, "resume")
    if args.command == "reconcile":
        plan = load_json(Path(args.plan))
        validate_plan(plan)
        parse_approval(Path(args.approval), plan)
        print(json.dumps(reconcile_state(plan, Path(args.journal)), sort_keys=True))
        return 0
    if args.command == "rollback":
        plan = load_json(Path(args.plan))
        validate_plan(plan)
        approval_path = Path(args.approval)
        approval = parse_approval(approval_path, plan)
        journal = Path(args.journal)
        base = _base_event(plan, approval_path)
        append_event(journal, base, "rollback-started", "whole-brain")
        _rollback(plan)
        current, observations = _current_image(plan)
        if current != plan["expected_preimage_sha256"]:
            raise Refusal("P6_ROLLBACK_READBACK_FAILED")
        append_event(journal, base, "rolled-back", "whole-brain")
        _write_results(Path(args.results), plan, approval, journal, observations, "rolled-back")
        return 0
    return verify_results(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
