"""Pure, version-gated mapper for the terminal P0 Codex CLI surface."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .common import AdapterRefusal, failed, load_json, require_request


PROBE_VERSION = "codex-cli 0.146.0"
BUSINESS_VERSION = "codex-cli 0.146.0"
ALLOWED_EVENTS = frozenset({"thread.started", "turn.started", "item.completed", "turn.completed", "turn.failed", "error"})


def resolve_binary(env: dict[str, str] | None = None) -> str:
    value = (env or os.environ).get("SKM_CODEX_BIN") or shutil.which("codex")
    if not value:
        raise AdapterRefusal("PROVIDER_UNAVAILABLE")
    return value


def _routing(request: dict, routing_path: str | Path) -> tuple[str, str]:
    routing = load_json(routing_path)
    mapping = routing.get("mappings", {}).get("codex", {})
    selector = mapping.get("class_selectors", {}).get(request["route"]["model_class"], [])
    effort = mapping.get("effort_selectors", {}).get(request["route"]["effort"], [])
    if len(selector) != 1 or len(effort) != 1:
        raise AdapterRefusal("MAPPING_UNKNOWN")
    return selector[0], effort[0]


def build_argv(request: dict, *, routing_path: str | Path, schema_path: str | Path,
               cwd: str | Path, native_tools: tuple[str, ...], binary: str | None = None) -> list[str]:
    require_request(request)
    if not isinstance(native_tools, tuple):
        raise AdapterRefusal("CAPABILITY_UNSUPPORTED")
    # The pinned Codex surface has no demonstrated global no-tool carrier.  Refuse
    # before binary resolution so a sandbox/prompt cannot accidentally widen scope.
    if not native_tools:
        raise AdapterRefusal("CAPABILITY_UNSUPPORTED")
    raise AdapterRefusal("CAPABILITY_UNSUPPORTED")
    # A future owner-bound native mapping belongs below this point; P3.4 never guesses it.
    if request["provider"].get("cli_version") != PROBE_VERSION:
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if request["permissions"].get("sandbox_mode") not in ("read_only", "workspace_write", "danger_full_access"):
        raise AdapterRefusal("PERMISSION_REFUSED")
    if not Path(schema_path).is_file() or not Path(cwd).is_dir():
        raise AdapterRefusal("MAPPING_UNKNOWN")
    model, effort = _routing(request, routing_path)
    effort_key = "model_" + "reason" + "ing_effort"
    config = ["-c", "approval_policy=never", "-c", "features.multi_agent=false",
              "-c", f"{effort_key}={effort}"]
    return [binary or resolve_binary(), "exec", "--json", "--ephemeral", "--strict-config",
            "--ignore-user-config", "-C", str(Path(cwd)), "-m", model, "-s",
            request["permissions"]["sandbox_mode"].replace("_", "-"), *config,
            "--output-schema", str(Path(schema_path)), "-"]


def build_business_argv(request: dict, *, schema_path: str | Path, cwd: str | Path, binary: str | None = None) -> list[str]:
    """D112 R2 mapping, distinct from the intentionally refusing smoke mapper.

    The native CLI has no enforceable turn or money cap.  The caller therefore
    owns the hard process limits; this list deliberately contains neither.
    """
    require_request(request)
    if (request["provider"].get("cli_version") != BUSINESS_VERSION
            or request["permissions"].get("sandbox_mode") != "workspace_write"
            or request["permissions"].get("network_mode") != "disabled"):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if request.get("child_policy", {}).get("mode") != "forbidden" or not Path(schema_path).is_file() or not Path(cwd).is_dir():
        raise AdapterRefusal("CAPABILITY_UNSUPPORTED")
    return [binary or resolve_binary(), "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--strict-config", "--skip-git-repo-check", "-C", str(Path(cwd)), "-s", "workspace-write", "--disable", "multi_agent", "-c", "sandbox_workspace_write.network_access=false", "-c", "approval_policy=never", "--output-schema", str(Path(schema_path)), "-"]


def prepare(request: dict, *, plan_dir: Path, native_tools: tuple[str, ...],
            content_resolver: object) -> dict:
    """Preflight Codex before resolving content the mapper cannot lawfully run."""
    schema = plan_dir / "artifacts/P3/unresolved-schema.json"
    argv = build_argv(request, routing_path=plan_dir.parents[2] / "packages/task/configs/command-routing.json",
                     schema_path=schema, cwd=plan_dir, native_tools=native_tools)
    raise AdapterRefusal("MAPPING_UNKNOWN")


def normalize_record(line: str, request: dict) -> dict:
    if request.get("provider", {}).get("cli_version") != PROBE_VERSION:
        return failed("MAPPING_UNKNOWN", "provider_failure")
    try:
        record = json.loads(line)
    except (TypeError, json.JSONDecodeError):
        return failed("PROVIDER_PROTOCOL_UNKNOWN", "provider_failure")
    if not isinstance(record, dict) or set(record) - {"type", "thread_id", "usage", "item", "error"}:
        return failed("PROVIDER_PROTOCOL_UNKNOWN", "provider_failure")
    event_type = record.get("type")
    if event_type not in ALLOWED_EVENTS:
        return failed("PROVIDER_PROTOCOL_UNKNOWN", "provider_failure")
    if event_type == "error":
        return failed("PROVIDER_NONZERO", "provider_failure")
    if event_type == "turn.failed":
        return failed("OUTPUT_SCHEMA_INVALID", "schema_failure")
    return {"event_type": event_type, "usage_observed": isinstance(record.get("usage"), dict),
            "session_observed": isinstance(record.get("thread_id"), str)}


def fold_records(records: list[str], request: dict, *, exit_code: int) -> dict:
    if not isinstance(records, list) or len(records) > request["budgets"].get("max_event_count", 0):
        return failed("BUDGET_EVENT_COUNT", "budget_exhausted")
    normalized = [normalize_record(line, request) for line in records]
    refusal = next((row for row in normalized if row.get("worker_succeeded") is False), None)
    if refusal:
        return refusal
    terminal = any(row.get("event_type") == "turn.completed" for row in normalized)
    if exit_code != 0:
        return failed("PROVIDER_NONZERO", "provider_failure")
    if not terminal:
        return failed("PROVIDER_PROTOCOL_UNKNOWN", "provider_failure")
    return {"worker_succeeded": True, "acceptance_state": "not_evaluated", "exit_class": "success",
            "reason_code": "OK", "event_count": len(normalized),
            "usage_observed": any(row.get("usage_observed") for row in normalized)}
