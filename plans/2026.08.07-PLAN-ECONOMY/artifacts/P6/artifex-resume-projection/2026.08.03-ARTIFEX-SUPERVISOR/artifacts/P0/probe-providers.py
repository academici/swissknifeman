#!/usr/bin/env python3
"""Run bounded, no-write provider observations and retain only safe summaries."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


CAP_SECONDS = 45
CAP_BYTES = 65536
PROVIDERS = ("codex", "claude-code")
DECLARED = frozenset({
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/findings/P0-provider-capability-matrix-2026-08-03.md",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P0/provider-matrix-v1.json",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P0/probe-providers.py",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P0/validate-provider-matrix.py",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P0/provider-probes/codex.json",
    "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P0/provider-probes/claude-code.json",
})
FORBIDDEN = ("prompt", "thinking", "api_key", "api-key", "authorization", "cookie")
SCHEMA = {"type": "object", "properties": {"result": {"type": "string"}},
          "required": ["result"], "additionalProperties": False}


def status(root: Path) -> set[str]:
    result = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=all"],
                            cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError("git status failed")
    return {line[3:] for line in result.stdout.splitlines() if line}


def allowed_delta(before: set[str], after: set[str]) -> list[str]:
    return sorted(path for path in before ^ after if path not in DECLARED)


def clipped(data: bytes) -> bytes:
    return data[:CAP_BYTES]


def version(binary: str) -> str | None:
    try:
        run = subprocess.run([binary, "--version"], text=True, capture_output=True,
                             timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return run.stdout.strip() if run.returncode == 0 and run.stdout.strip() else None


def help_text(provider: str, binary: str) -> str:
    try:
        argv = [binary, "exec", "--help"] if provider == "codex" else [binary, "--help"]
        run = subprocess.run(argv, text=True, capture_output=True,
                             timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    merged = (run.stdout or "") + (run.stderr or "")
    return clipped(merged.encode("utf-8", "replace")).decode("utf-8", "replace").lower()


def features(provider: str, help_output: str) -> dict[str, str]:
    if provider == "codex":
        return {
            "structured_output": "supported" if "--output-schema" in help_output else "unknown",
            "machine_events": "supported" if "--json" in help_output else "unknown",
            "permission_boundary": "supported" if "--sandbox" in help_output else "unknown",
            "ephemeral_session": "supported" if "--ephemeral" in help_output else "unsupported",
            "child_agent_control": "unknown",
        }
    return {
        "structured_output": "supported" if "--json-schema" in help_output else "unknown",
        "machine_events": "supported" if "--output-format" in help_output else "unknown",
        "permission_boundary": "supported" if "--permission-mode" in help_output else "unknown",
        "ephemeral_session": "unsupported",
        "child_agent_control": "supported" if "--agents" in help_output else "unknown",
    }


def safe_argv(argv: list[str]) -> list[str]:
    """The final element is an instruction and is intentionally never retained."""
    return argv[:-1] + ["<input-not-retained>"]


def parse_events(provider: str, stdout: bytes) -> tuple[list[str], dict[str, bool]]:
    types: list[str] = []
    values = {"usage": False, "cache": False, "cost": False, "session": False}
    if provider == "codex":
        rows = stdout.decode("utf-8", "replace").splitlines()
    else:
        rows = [stdout.decode("utf-8", "replace")]
    for row in rows:
        try:
            value = json.loads(row)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        kind = value.get("type")
        if isinstance(kind, str) and kind not in types:
            types.append(kind)
        keys = set(value)
        values["usage"] |= bool(keys & {"usage", "num_turns", "input_tokens", "output_tokens"})
        values["cache"] |= bool(keys & {"cache_read_input_tokens", "cache_creation_input_tokens"})
        values["cost"] |= bool(keys & {"total_cost_usd", "cost_usd"})
        values["session"] |= bool(keys & {"session_id", "thread_id"})
    return sorted(types), values


def reason_class(stdout: bytes, stderr: bytes) -> str:
    text = (clipped(stdout) + b"\n" + clipped(stderr)).decode("utf-8", "replace").lower()
    if "quota" in text or "limit" in text:
        return "quota_or_limit"
    if "auth" in text or "login" in text or "credential" in text:
        return "authentication_or_access"
    if "schema" in text:
        return "schema_rejected"
    if "permission" in text:
        return "permission_denied"
    return "nonzero_without_safe_classification"


def execute(provider: str, argv: list[str], root: Path, temp: Path) -> dict[str, object]:
    before = status(root)
    try:
        run = subprocess.run(argv, cwd=temp, capture_output=True, timeout=CAP_SECONDS,
                             check=False)
        outcome = "exited" if run.returncode == 0 else "nonzero"
        output = clipped(run.stdout)
        event_types, fields = parse_events(provider, output)
        result: dict[str, object] = {"argv": safe_argv(argv), "exit_code": run.returncode,
                                     "outcome": outcome, "event_types": event_types,
                                     "observed_fields": fields,
                                     "stdout_bytes_captured": min(len(run.stdout), CAP_BYTES),
                                     "stderr_bytes_captured": min(len(run.stderr), CAP_BYTES)}
        if run.returncode:
            result["reason_class"] = reason_class(run.stdout, run.stderr)
    except subprocess.TimeoutExpired:
        result = {"argv": safe_argv(argv), "exit_code": None, "outcome": "timeout",
                  "event_types": [], "observed_fields": {"usage": False, "cache": False,
                  "cost": False, "session": False}, "stdout_bytes_captured": 0,
                  "stderr_bytes_captured": 0}
    except OSError as error:
        result = {"argv": safe_argv(argv), "exit_code": None, "outcome": "unavailable",
                  "event_types": [], "observed_fields": {"usage": False, "cache": False,
                  "cost": False, "session": False}, "stdout_bytes_captured": 0,
                  "stderr_bytes_captured": 0, "reason_class": type(error).__name__}
    delta = allowed_delta(before, status(root))
    if delta:
        raise RuntimeError(f"unexpected project delta: {delta}")
    return result


def provider_argv(provider: str, binary: str, temp: Path, schema: Path, invalid: Path) -> list[tuple[str, list[str]]]:
    instruction = "Return one JSON object that matches the requested shape. Do not use tools."
    if provider == "codex":
        common = [binary, "exec", "--json", "--ephemeral", "-C", str(temp), "-s", "read-only"]
        return [
            ("bounded_success", common + ["--output-schema", str(schema), instruction]),
            ("schema_boundary", common + ["--output-schema", str(invalid), instruction]),
        ]
    common = [binary, "-p", "--bare", "--output-format", "json", "--json-schema",
              json.dumps(SCHEMA, separators=(",", ":")), "--max-turns", "1",
              "--max-budget-usd", "0.05", "--permission-mode", "plan"]
    return [
        ("bounded_success", common + [instruction]),
        ("schema_boundary", [binary, "-p", "--bare", "--output-format", "json", "--json-schema",
                             '{"type":"object","required":"invalid"}', "--max-turns", "1",
                             "--max-budget-usd", "0.05", "--permission-mode", "plan", instruction]),
    ]


def observe(provider: str, root: Path, output: Path, temp: Path) -> dict[str, object]:
    binary = shutil.which("codex" if provider == "codex" else "claude")
    record: dict[str, object] = {"schema_version": "provider-probe-v1", "provider": provider,
                                 "observed_at": dt.date.today().isoformat(), "binary": {
                                     "name": "codex" if provider == "codex" else "claude",
                                     "path": binary, "version": version(binary) if binary else None},
                                 "provenance": "local binary --version and --help; bounded temporary-git observation",
                                 "execution": {"temporary_git_repository": True,
                                               "timeout_seconds": CAP_SECONDS,
                                               "byte_cap": CAP_BYTES,
                                               "session_mode": "ephemeral" if provider == "codex" else "print-mode; no resume"},
                                 "runs": [], "capabilities": {}, "project_delta": []}
    if not binary:
        record["availability"] = "unavailable"
        record["capabilities"] = {name: "unknown" for name in features(provider, "")}
        return record
    local_help = help_text(provider, binary)
    record["availability"] = "available"
    record["capabilities"] = features(provider, local_help)
    schema = temp / "schema.json"
    invalid = temp / "invalid-schema.json"
    schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
    invalid.write_text('{"type":"object","required":"invalid"}', encoding="utf-8")
    for name, argv in provider_argv(provider, binary, temp, schema, invalid):
        run = execute(provider, argv, root, temp)
        run["name"] = name
        record["runs"].append(run)
    success = next(row for row in record["runs"] if row["name"] == "bounded_success")
    if success["outcome"] == "exited":
        record["capabilities"]["structured_output"] = "supported"
    elif record["capabilities"]["structured_output"] == "supported":
        record["capabilities"]["structured_output"] = "degraded"
    if success["event_types"]:
        record["capabilities"]["machine_events"] = "supported"
    fields = success["observed_fields"]
    record["accounting"] = {key: "observed" if fields[key] else "unknown"
                            for key in ("usage", "cache", "cost")}
    record["session_identity"] = "observed" if fields["session"] else "unknown"
    return record


def assert_safe(value: object) -> None:
    lowered = json.dumps(value, ensure_ascii=False).lower()
    if any(token in lowered for token in FORBIDDEN):
        raise RuntimeError("unsafe retained value")


def matrix(records: list[dict[str, object]]) -> dict[str, object]:
    rows = []
    for record in records:
        rows.append({"provider": record["provider"], "availability": record["availability"],
                     "version": record["binary"]["version"], "record": f"provider-probes/{record['provider']}.json",
                     "capabilities": record["capabilities"], "accounting": record["accounting"],
                     "session_identity": record["session_identity"]})
    return {"schema_version": "provider-matrix-v1", "observed_at": dt.date.today().isoformat(),
            "scope": "local installed CLI surface; bounded no-write temporary-git observations",
            "providers": rows,
            "harness_crosswalk": {"provider_audit": "read-only provider-qualified render audit",
                                  "exec_wave": "Claude Code only; sequential process worker; no Codex driver"},
            "verdict": "Capability states are local observations; unknown is not zero or parity."}


def finding(data: dict[str, object]) -> str:
    lines = ["# Provider capability matrix — 2026-08-03", "", "## Method", "",
             "Both installed clients were invoked from a freshly initialized temporary Git repository. "
             "The driver used a 45-second cap, 65,536-byte capture cap, read-only or plan permission, "
             "and retained no raw client output. The temporary directory is removed after the normalized "
             "records pass validation.", "", "## Verdict", "",
             "The matrix distinguishes supported, degraded, unsupported, and unknown local states; it does not assert provider parity. "
             "Harness remains a Claude Code-only exec-wave baseline, while provider audit is a read-only configuration audit.",
             "", "## Provider observations", "", "| Provider | Availability | Version | Structured output | Session identity | Usage / cache / cost |", "|:--|:--|:--|:--|:--|:--|"]
    for row in data["providers"]:
        accounting = row["accounting"]
        lines.append(f"| {row['provider']} | {row['availability']} | {row['version'] or 'unknown'} | "
                     f"{row['capabilities']['structured_output']} | {row['session_identity']} | "
                     f"{accounting['usage']} / {accounting['cache']} / {accounting['cost']} |")
    lines.extend(["", "The exact non-secret invocation shapes, exit classes, and observed event-field categories are in "
                  "`artifacts/P0/provider-probes/`. Unsupported, authentication, quota, and missing fields remain "
                  "first-class local observations rather than successful probes."])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--matrix", required=True)
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    output = Path(args.output_dir).resolve()
    matrix_path = Path(args.matrix).resolve()
    if not (root / ".git").exists():
        raise SystemExit("project root must be a git repository")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="artifex-provider-probe-") as temp_name:
        temp = Path(temp_name)
        subprocess.run(["git", "init", "-q"], cwd=temp, check=True)
        records = [observe(provider, root, output, temp) for provider in PROVIDERS]
        data = matrix(records)
        for record in records:
            assert_safe(record)
            (output / f"{record['provider']}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        assert_safe(data)
        matrix_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        finding_path = root / "plans/2026.08.03-ARTIFEX-SUPERVISOR/findings/P0-provider-capability-matrix-2026-08-03.md"
        finding_path.write_text(finding(data), encoding="utf-8")
    print("project_delta=[]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
