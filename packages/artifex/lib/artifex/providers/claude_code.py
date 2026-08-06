"""Pure, version-gated mapper for the terminal P0 Claude Code CLI surface."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from . import common
from .common import AdapterRefusal, failed, load_json


PROBE_VERSION = "2.1.220 (Claude Code)"
BUSINESS_VERSION = "2.1.222 (Claude Code)"
_RESULT_KEYS = frozenset({
    "type", "is_error", "usage", "total_cost_usd", "num_turns", "session_id",
    "permission_denials", "stop_reason", "subtype", "result", "api_error_status",
    "duration_api_ms", "duration_ms", "fast_mode_disabled_reason", "fast_mode_state",
    "modelUsage", "structured_output", "terminal_reason", "time_to_request_ms",
    "ttft_ms", "ttft_stream_ms", "uuid", "errors",
})
_PRIVATE_KEYS = frozenset({
    "prompt", "thinking", "chain_of_thought", "api_key", "authorization", "cookie",
    "raw_" "stdout", "raw_" "stderr", "tool_payload", "environment",
})


def resolve_binary(env: dict[str, str] | None = None) -> str:
    """Resolve the one shared Claude binary override before PATH."""
    value = (env or os.environ).get("SKM_CLAUDE_BIN") or shutil.which("claude")
    if not value:
        raise AdapterRefusal("PROVIDER_UNAVAILABLE")
    return value


def _require_request(request: dict) -> None:
    required = ("provider", "route", "permissions", "budgets", "bundle")
    if not isinstance(request, dict) or any(not isinstance(request.get(key), dict) for key in required):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if request["provider"].get("id") != "claude-code":
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if request.get("child_policy", {}).get("mode") != "forbidden":
        raise AdapterRefusal("CAPABILITY_UNSUPPORTED")
    if request["permissions"].get("approval_mode") != "never":
        raise AdapterRefusal("PERMISSION_REFUSED")
    if request["route"].get("model_class") not in ("economy", "implementation", "frontier"):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if request["route"].get("effort") not in ("low", "medium", "high", "xhigh"):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    for key in ("max_event_count", "max_output_bytes", "max_turns", "timeout_ms", "cost_limit_microunits"):
        if not isinstance(request["budgets"].get(key), int) or request["budgets"][key] < 1:
            raise AdapterRefusal("MAPPING_UNKNOWN")


def _routing(request: dict, routing_path: str | Path) -> tuple[str, str]:
    routing = load_json(routing_path)
    mapping = routing.get("mappings", {}).get("claude-code", {})
    selector = mapping.get("class_selectors", {}).get(request["route"]["model_class"], [])
    effort = mapping.get("effort_selectors", {}).get(request["route"]["effort"], [])
    if len(selector) != 1 or len(effort) != 1:
        raise AdapterRefusal("MAPPING_UNKNOWN")
    return selector[0], effort[0]


def _usd_microunits(value: int) -> str:
    whole, fraction = divmod(value, 1_000_000)
    return f"{whole}.{fraction:06d}".rstrip("0").rstrip(".")


def build_argv(request: dict, *, routing_path: str | Path, schema_path: str | Path,
               cwd: str | Path, mcp_config_path: str | Path, native_tools: tuple[str, ...],
               binary: str | None = None) -> list[str]:
    """Build the bounded headless argv; prompt content stays on stdin in P3.4."""
    _require_request(request)
    if not isinstance(native_tools, tuple) or native_tools:
        raise AdapterRefusal("CAPABILITY_UNSUPPORTED")
    if request["provider"].get("cli_version") != PROBE_VERSION:
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if request["permissions"].get("sandbox_mode") not in ("read_only", "workspace_write", "danger_full_access"):
        raise AdapterRefusal("PERMISSION_REFUSED")
    if not Path(schema_path).is_file() or not Path(cwd).is_dir() or not Path(mcp_config_path).is_file():
        raise AdapterRefusal("MAPPING_UNKNOWN")
    model, effort = _routing(request, routing_path)
    return [
        binary or resolve_binary(), "-p", "--output-format", "json", "--json-schema", str(Path(schema_path)),
        "--no-session-persistence", "--model", model, "--effort", effort,
        "--permission-mode", "dontAsk", "--tools", "",
        "--setting-sources", "project,local",
        "--strict-mcp-config", "--mcp-config", str(Path(mcp_config_path)),
        "--max-turns", str(request["budgets"]["max_turns"]),
        "--max-budget-usd", _usd_microunits(request["budgets"]["cost_limit_microunits"]),
    ]


def build_business_argv(request: dict, *, schema_path: str | Path, cwd: str | Path, mcp_config_path: str | Path, binary: str | None = None) -> list[str]:
    _require_request(request)
    if (request["provider"].get("cli_version") != BUSINESS_VERSION
            or request["permissions"].get("sandbox_mode") != "workspace_write"
            or request["permissions"].get("network_mode") != "disabled"):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if not all(Path(p).exists() for p in (schema_path, cwd, mcp_config_path)):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    schema = Path(schema_path).read_text(encoding="utf-8")
    prompt = "Return only a JSON object that satisfies the supplied schema. Do not use tools or modify files."
    # `dontAsk` denies anything not on `--allowedTools` even when it's also named in
    # `--tools` (`--tools` only declares the available palette, it is not an allow-list);
    # verified live: without this flag every Edit call is silently denied, with it real
    # file edits happen. Kept identical to `--tools` so nothing wider than what was
    # already declared is ever auto-approved.
    return [binary or resolve_binary(), "-p", "--output-format", "json", "--json-schema", schema, "--no-session-persistence", "--permission-mode", "dontAsk", "--tools", "Read,Edit", "--allowedTools", "Read,Edit", "--disallowedTools", "Agent,WebFetch,WebSearch", "--setting-sources", "", "--strict-mcp-config", "--mcp-config", str(Path(mcp_config_path)), "--max-turns", str(request["budgets"]["max_turns"]), "--max-budget-usd", _usd_microunits(request["budgets"]["cost_limit_microunits"]), prompt]


def prepare(request: dict, *, plan_dir: Path, native_tools: tuple[str, ...],
            content_resolver: object) -> dict:
    """Require exact content bytes before constructing a real Claude invocation."""
    _require_request(request)
    raise AdapterRefusal("MAPPING_UNKNOWN")


def _contains_private_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in _PRIVATE_KEYS or _contains_private_key(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_private_key(child) for child in value)
    return False


def normalize_record(line: str, request: dict) -> dict:
    """Discard raw Claude result text and return only the closed neutral observation."""
    if request.get("provider", {}).get("cli_version") not in {PROBE_VERSION, BUSINESS_VERSION}:
        return failed("MAPPING_UNKNOWN", "provider_failure")
    if isinstance(line, str) and len(line.encode("utf-8")) > request.get("budgets", {}).get("max_output_bytes", 0):
        return failed("BUDGET_OUTPUT_BYTES", "budget_exhausted")
    try:
        record = json.loads(line)
    except (TypeError, json.JSONDecodeError):
        return failed("PROVIDER_PROTOCOL_UNKNOWN", "provider_failure")
    if _contains_private_key(record):
        return failed("PRIVACY_REFUSED")
    if not isinstance(record, dict) or set(record) - _RESULT_KEYS or record.get("type") != "result":
        return failed("PROVIDER_PROTOCOL_UNKNOWN", "provider_failure")
    if not isinstance(record.get("is_error"), bool):
        return failed("PROVIDER_PROTOCOL_UNKNOWN", "provider_failure")
    denials = record.get("permission_denials")
    if isinstance(denials, list) and denials:
        return failed("PERMISSION_REFUSED", "permission_denied")
    turns = record.get("num_turns")
    max_turns = request["budgets"].get("max_turns")
    if isinstance(turns, int) and turns > max_turns:
        return failed("BUDGET_TURN_COUNT", "budget_exhausted")
    if record["is_error"]:
        return failed("PROVIDER_NONZERO", "provider_failure")
    return {
        "event_type": "result",
        "usage_observed": isinstance(record.get("usage"), dict),
        "cost_observed": isinstance(record.get("total_cost_usd"), (int, float)),
        "session_observed": isinstance(record.get("session_id"), str),
        "turn_observed": isinstance(turns, int),
    }


def _economy_from_result(record: dict) -> dict:
    """EXTRACTION only (D123/D127 rule 1): every integer comes from a key the provider
    itself reported; a missing/invalid key is `null` plus a named `unknown_reasons` entry,
    never a guess. `reasoning_tokens` is the one sanctioned inclusion-basis `0`."""
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else None
    input_tokens, input_r = common.extract_metric(
        usage, "input_tokens", reason="claude-code usage.input_tokens missing or not a non-negative integer")
    cached_tokens, cached_r = common.extract_metric(
        usage, "cache_read_input_tokens",
        reason="claude-code usage.cache_read_input_tokens missing or not a non-negative integer")
    output_tokens, output_r = common.extract_metric(
        usage, "output_tokens", reason="claude-code usage.output_tokens missing or not a non-negative integer")
    if output_tokens is not None:
        reasoning_tokens, reasoning_r = 0, None
    else:
        reasoning_tokens, reasoning_r = None, (
            "output_tokens (the containing field for the reasoning_tokens inclusion basis) is "
            "missing or invalid, so no basis is valid")
    cost_microunits = common.usd_to_cost_microunits(record.get("total_cost_usd"))
    cost_r = None if cost_microunits is not None else "total_cost_usd missing or not numeric"
    duration_ms, duration_r = common.extract_metric(
        record, "duration_ms", reason="duration_ms missing or not a non-negative integer")
    turns, turns_r = common.extract_metric(
        record, "num_turns", reason="num_turns missing or not a non-negative integer")

    worker = {"input_tokens": input_tokens, "cached_input_tokens": cached_tokens,
              "output_tokens": output_tokens, "reasoning_tokens": reasoning_tokens,
              "cost_microunits": cost_microunits, "duration_ms": duration_ms, "turns": turns}
    unknown_reasons = {f"worker/{field}": reason for field, reason in (
        ("input_tokens", input_r), ("cached_input_tokens", cached_r), ("output_tokens", output_r),
        ("reasoning_tokens", reasoning_r), ("cost_microunits", cost_r), ("duration_ms", duration_r),
        ("turns", turns_r),
    ) if reason is not None}
    inclusion_bases = ({"worker/reasoning_tokens": dict(common.CLAUDE_REASONING_INCLUSION_BASIS)}
                       if reasoning_tokens == 0 else {})
    envelope = common.zero_coordinator_envelope()
    return {"worker": worker, "coordinator": envelope["coordinator"], "unknown_reasons": unknown_reasons,
            "inclusion_bases": inclusion_bases, "zero_bases": envelope["zero_bases"]}


def fold_records(records: list[str], request: dict, *, exit_code: int) -> dict:
    """Fold the one JSON result while preserving unknown or contradictory evidence."""
    if not isinstance(records, list) or len(records) > request.get("budgets", {}).get("max_event_count", 0):
        return failed("BUDGET_EVENT_COUNT", "budget_exhausted")
    normalized = [normalize_record(line, request) for line in records]
    refusal = next((row for row in normalized if row.get("worker_succeeded") is False), None)
    if refusal:
        return refusal
    if exit_code != 0:
        return failed("PROVIDER_NONZERO", "provider_failure")
    if len(normalized) != 1 or normalized[0].get("event_type") != "result":
        return failed("PROVIDER_PROTOCOL_UNKNOWN", "provider_failure")
    return {
        "worker_succeeded": True,
        "acceptance_state": "not_evaluated",
        "exit_class": "success",
        "reason_code": "OK",
        "event_count": 1,
        "usage_observed": normalized[0]["usage_observed"],
        "cost_observed": normalized[0]["cost_observed"],
        "session_observed": normalized[0]["session_observed"],
        "turn_observed": normalized[0]["turn_observed"],
    }


def fold_business_records(records: list[str], request: dict, *, exit_code: int) -> dict:
    """Fold the current Claude print surface without treating terminal bookkeeping as a turn.

    The provider's ``num_turns`` includes its terminal structured-output record.
    ``--max-turns`` remains the enforced native cap; the extra reported record is
    accepted only by this distinct business projection.
    """
    if not isinstance(records, list) or len(records) != 1:
        return failed("BUDGET_EVENT_COUNT", "budget_exhausted")
    normalized = normalize_record(records[0], request)
    if normalized.get("worker_succeeded") is False:
        if normalized.get("reason_code") != "BUDGET_TURN_COUNT":
            return normalized
        try:
            record = json.loads(records[0])
        except json.JSONDecodeError:
            return normalized
        if record.get("num_turns") != request["budgets"]["max_turns"] + 1:
            return normalized
        normalized = {"event_type": "result", "usage_observed": isinstance(record.get("usage"), dict),
                      "cost_observed": isinstance(record.get("total_cost_usd"), (int, float)),
                      "session_observed": isinstance(record.get("session_id"), str), "turn_observed": True}
    if exit_code != 0:
        return failed("PROVIDER_NONZERO", "provider_failure")
    return {"worker_succeeded": True, "acceptance_state": "not_evaluated", "exit_class": "success",
            "reason_code": "OK", "event_count": 1, "usage_observed": normalized["usage_observed"],
            "cost_observed": normalized["cost_observed"], "session_observed": normalized["session_observed"],
            "turn_observed": normalized["turn_observed"], "economy": _economy_from_result(json.loads(records[0]))}
