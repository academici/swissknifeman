#!/usr/bin/env python3
"""Create a privacy-minimized exact-set P0 provider and skills baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


PLAN_ID = "2026.08.02-PROVIDER-CONTRACT-LOCALE"
ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "plans" / PLAN_ID / "artifacts" / "P0.1" / "evidence"
REGISTRY = Path.home() / ".swissknifeman" / "projects.json"
PROVIDERS = ("claude-code", "codex")
CARRIERS = (
    "CLAUDE.md", "AGENTS.md", ".claude", ".codex", ".agents", ".claude-plugin",
    ".codex-plugin", ".ai", ".mcp.json", ".swissknife.json",
)
SECRET_NAME = re.compile(r"(?:secret|token|password|api[_-]?key|credential|private[_-]?key)", re.I)
SECRET_VALUE = re.compile(r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})")
CONFIG_SUFFIXES = {".json", ".toml", ".yaml", ".yml", ".ini", ".env"}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(text: str) -> str:
    return SECRET_VALUE.sub("<secret-like>", re.sub(r"/(?:home|tmp|private|var)/[^\s'\"]+", "<absolute-path>", text))


def run(command: list[str], *, cwd: Path = ROOT, timeout: int = 60, retain_stdout: bool = False, capture_sha: bool = False) -> dict[str, Any]:
    """Run an observer command while retaining only redacted structural evidence."""
    try:
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return {"command": command[:1], "availability": "unavailable", "exit_code": None, "stdout_schema": "none", "warnings": []}
    except subprocess.TimeoutExpired:
        return {"command": command[:1], "availability": "unavailable", "exit_code": None, "stdout_schema": "none", "warnings": ["timeout"]}

    raw = completed.stdout.encode("utf-8")
    warnings = sorted(set(redact(line) for line in completed.stderr.splitlines() if line.strip()))
    safe_command = ["<absolute-path>" if arg.startswith("/") else arg for arg in command]
    evidence = {
        "command": safe_command,
        "availability": "available" if completed.returncode == 0 else "command-error",
        "exit_code": completed.returncode,
        "stdout_schema": "json" if completed.stdout.lstrip().startswith(("{", "[")) else "text",
        "warnings": warnings,
    }
    if capture_sha:
        evidence["stdout_sha256"] = sha256(raw)
    if retain_stdout:
        evidence["_stdout"] = completed.stdout
    return evidence


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False).stdout.strip()


def stable_project_id(root: Path, records: list[dict[str, Any]]) -> str:
    identity = "|".join(sorted(f"{record.get('provider', 'generic')}:{record.get('channel', '')}" for record in records))
    return "project-" + sha256((str(root) + "|" + identity).encode())[:16]


def redacted_record(record: dict[str, Any], project_id: str) -> dict[str, Any]:
    allowed = ("channel", "provider", "agent", "profile", "profile_source", "skills_path", "hub", "plugins", "buckets", "exclude", "settings_file", "updated_at", "first_connected_at")
    return {"project_id": project_id, **{key: record[key] for key in allowed if key in record}}


def config_shape(path: Path, raw: bytes) -> dict[str, Any]:
    if path.suffix == ".json":
        try:
            data = json.loads(raw.decode("utf-8"))
            found: list[str] = []

            def walk(value: Any, prefix: str = "") -> None:
                if isinstance(value, dict):
                    for key, nested in value.items():
                        part = f"{prefix}.{key}" if prefix else key
                        found.append(part + ":" + type(nested).__name__)
                        walk(nested, part)
                elif isinstance(value, list):
                    found.append(prefix + ":list[" + str(len(value)) + "]")

            walk(data)
            return {"kind": "structural", "key_paths": sorted(found), "contains_secret_key": any(SECRET_NAME.search(x) for x in found)}
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    return {"kind": "structural", "bytes": len(raw), "contains_secret_key": bool(SECRET_NAME.search(path.name))}


def node(path: Path, repo: Path) -> dict[str, Any]:
    stat = path.lstat()
    relative = path.relative_to(repo).as_posix()
    record: dict[str, Any] = {"path": relative, "mode": stat.st_mode, "managed": any(part in {".claude", ".codex", ".agents"} for part in path.parts)}
    if path.is_symlink():
        resolved = path.resolve(strict=False)
        record.update({"node": "symlink", "target_state": "broken" if not resolved.exists() else ("out-of-root" if repo not in resolved.parents and resolved != repo else "in-root")})
        return record
    if path.is_dir():
        record["node"] = "directory"
        return record
    record["node"] = "file"
    raw = path.read_bytes()
    record["content"] = config_shape(path, raw) if path.suffix in CONFIG_SUFFIXES or SECRET_NAME.search(path.name) or SECRET_VALUE.search(raw.decode("utf-8", "ignore")) else {"kind": "sha256", "value": sha256(raw), "bytes": len(raw)}
    return record


def carrier_paths(repo: Path) -> list[Path]:
    paths: list[Path] = []
    for name in CARRIERS:
        candidate = repo / name
        if not candidate.exists() and not candidate.is_symlink():
            continue
        paths.append(candidate)
        if candidate.is_dir() and not candidate.is_symlink():
            paths.extend(sorted(item for item in candidate.rglob("*") if item.is_file() or item.is_symlink()))
    return sorted(set(paths), key=lambda item: item.as_posix())


def inventory_project(root: Path, records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    project_id = stable_project_id(root, records)
    selected = {str(record.get("provider")) for record in records if record.get("provider") in PROVIDERS}
    project: dict[str, Any] = {"project_id": project_id, "record_count": len(records), "records": [redacted_record(record, project_id) for record in records], "repository": {"state": "available" if root.is_dir() else "unavailable"}}
    if not root.is_dir():
        return project, [{"artifact_id": f"{project_id}:{provider}", "project_id": project_id, "provider": provider, "selected": provider in selected, "status": "unavailable", "carrier_paths": [], "diagnostics": ["project-root-unavailable"]} for provider in PROVIDERS]

    project["repository"].update({"head": git(root, "rev-parse", "HEAD") or None, "dirty_tracked": git(root, "status", "--porcelain", "--untracked-files=no").splitlines(), "untracked": git(root, "ls-files", "--others", "--exclude-standard").splitlines()})
    paths = [node(path, root) for path in carrier_paths(root)]
    tracked = set(git(root, "ls-files").splitlines())
    for item in paths:
        item["artifact_id"] = "artifact-" + sha256(f"{project_id}:{item['path']}".encode())[:16]
        item["tracked"] = item["path"] in tracked
    project["provider_paths"] = paths

    rows = []
    for provider in PROVIDERS:
        families = {"claude-code": ("CLAUDE.md", ".claude", ".claude-plugin"), "codex": ("AGENTS.md", ".codex", ".agents", ".codex-plugin")}[provider]
        relevant = [item["path"] for item in paths if item["path"].split("/", 1)[0] in families]
        status = "green" if provider in selected and relevant else ("not-selected" if provider not in selected else "red")
        rows.append({"artifact_id": f"{project_id}:{provider}", "project_id": project_id, "provider": provider, "selected": provider in selected, "status": status, "carrier_paths": relevant, "diagnostics": [] if status in {"green", "not-selected"} else ["selected-provider-has-no-carrier"]})
    return project, rows


def previous_observations() -> dict[str, str]:
    path = EVIDENCE / "command-results-redacted.json"
    try:
        prior = json.loads(path.read_text(encoding="utf-8"))
        return {entry["raw_sha256"]: entry["observed_at"] for entry in prior.get("skills_baseline", {}).get("profile_measurements", []) if isinstance(entry, dict) and isinstance(entry.get("raw_sha256"), str) and isinstance(entry.get("observed_at"), str)}
    except (OSError, ValueError, TypeError):
        return {}


def observed_at(raw_sha: str, prior: dict[str, str]) -> tuple[str, str]:
    timestamp = prior.get(raw_sha) or os.environ.get("P0_BASELINE_OBSERVED_AT") or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return timestamp, (parsed + timedelta(days=90)).date().isoformat()


def skills_baseline() -> dict[str, Any]:
    bucket = run(["packages/skiller/bin/skiller", "bucket-audit", "--since", "90", "--json"], retain_stdout=True, capture_sha=True)
    budget = run(["packages/skiller/bin/skiller", "budget", "--profiles", "--json"], retain_stdout=True, capture_sha=True)
    result: dict[str, Any] = {"schema_version": 1, "bucket_audit": bucket, "budget_profiles": budget, "availability": "available"}
    if bucket["availability"] != "available" or budget["availability"] != "available":
        result["availability"] = "command-error"
        return result
    try:
        bucket_data = json.loads(bucket.pop("_stdout"))
        budget_data = json.loads(budget.pop("_stdout"))
        items = bucket_data["items"]
        if not isinstance(items, list) or not isinstance(budget_data, list):
            raise ValueError("unexpected structured output")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        bucket.pop("_stdout", None)
        budget.pop("_stdout", None)
        result["availability"] = "parse-error"
        return result

    source_classes = Counter(str(item.get("channel", "unknown")) for item in items)
    observations = []
    for item in items:
        labels = sorted({str(item.get("channel", "unknown")), str(item.get("verdict", "unknown")), *( ["overlap"] if item.get("overlap_with") else [] ), *( ["direct-use"] if int(item.get("loaded_count", 0)) else ["zero-direct-use"] )})
        observations.append({"skill": item.get("key"), "labels": labels})
    prior = previous_observations()
    measurements = []
    for profile in budget_data:
        for provider in PROVIDERS:
            reading = profile.get(provider)
            if not isinstance(reading, dict):
                raise ValueError("profile provider measurement missing")
            raw_sha = budget["stdout_sha256"]
            timestamp, expiry = observed_at(raw_sha, prior)
            measurements.append({"profile": profile.get("profile"), "provider": provider, "model": "unreported", "surface": "profile-listing", "unit": reading.get("unit"), "value": reading.get("raw"), "budget": reading.get("budget"), "over": reading.get("over"), "method": "packages/skiller/bin/skiller budget --profiles --json", "tool_version": git(ROOT, "rev-parse", "HEAD"), "raw_sha256": raw_sha, "observed_at": timestamp, "expires_at": expiry, "availability": "available"})
    result.update({"source_skill_count": bucket_data.get("skills"), "bucket_count": len({item.get("bucket") for item in items}), "source_class_distribution": dict(sorted(source_classes.items())), "multi_label_observations": observations, "repeated_warning_set": sorted(set(bucket["warnings"] + budget["warnings"])), "profile_measurements": measurements})
    return result


def collect() -> dict[str, Any]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("projects"), list):
        raise ValueError("registry projects must be a list")
    grouped: dict[Path, list[dict[str, Any]]] = {}
    for record in registry["projects"]:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError("registry record missing path")
        grouped.setdefault(Path(record["path"]), []).append(record)
    projects, rows = [], []
    for root, records in sorted(grouped.items(), key=lambda pair: str(pair[0])):
        project, provider_rows = inventory_project(root, records)
        projects.append(project)
        rows.extend(provider_rows)
    commands = {
        "hooks_relative": run(["packages/harness/bin/harness", "hooks", "--target", ".", "--provider", "codex", "--observer", "--trusted", "--dry-run"]),
        "hooks_absolute": run(["packages/harness/bin/harness", "hooks", "--target", str(ROOT), "--provider", "codex", "--observer", "--trusted", "--dry-run"]),
        "provider_audit": run(["packages/harness/bin/harness", "doctor", "--provider-audit", "--json"]),
        "maind_health": run(["packages/maind/bin/maind", "health", "--cwd", "--strict"]),
        "codex_doctor": run(["codex", "doctor", "--json"]),
        "codex_plugins": run(["codex", "plugin", "list", "--json"]),
    }
    return {"registry": {"version": registry.get("version"), "record_count": len(registry["projects"]), "project_count": len(projects)}, "projects": projects, "provider_rows": rows, "commands": commands, "skills_baseline": skills_baseline()}


def write() -> int:
    evidence = collect()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    registry = {"schema_version": 2, "record_count": evidence["registry"]["record_count"], "project_count": evidence["registry"]["project_count"], "projects": [{"project_id": project["project_id"], "records": project["records"]} for project in evidence["projects"]]}
    snapshot = {"schema_version": 2, "projects": [{"project_id": project["project_id"], "repository": project["repository"], "provider_paths": project.get("provider_paths", [])} for project in evidence["projects"]]}
    fleet = {"schema_version": 2, "registry": evidence["registry"], "provider_rows": evidence["provider_rows"]}
    commands = {"schema_version": 2, "commands": evidence["commands"], "skills_baseline": evidence["skills_baseline"]}
    files = {"project-registry-redacted.json": registry, "provider-source-snapshot.json": snapshot, "provider-fleet-inventory.json": fleet, "command-results-redacted.json": commands}
    for name, value in files.items():
        (EVIDENCE / name).write_text(canonical(value), encoding="utf-8")
    manifest = {"bundle_id": "P0.1-provider-fleet-baseline", "files": sorted(files), "privacy": {"minimized": True, "excluded_classes": ["raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets"]}, "producer": "PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-provider-fleet-inventory.py --write"}
    (EVIDENCE / "manifest.json").write_text(canonical(manifest), encoding="utf-8")
    print(f"P0.5 exact baseline written: {evidence['registry']['record_count']} records, {evidence['registry']['project_count']} projects")
    return 0


def check() -> int:
    required = {"manifest.json", "verify.py", "project-registry-redacted.json", "provider-source-snapshot.json", "provider-fleet-inventory.json", "command-results-redacted.json"}
    missing = sorted(name for name in required if not (EVIDENCE / name).is_file())
    if missing:
        print("missing evidence: " + ", ".join(missing), file=sys.stderr)
        return 1
    manifest = json.loads((EVIDENCE / "manifest.json").read_text(encoding="utf-8"))
    actual = sorted(path.name for path in EVIDENCE.iterdir() if path.is_file() and path.name not in {"manifest.json", "verify.py"})
    if manifest.get("files") != actual or manifest.get("privacy", {}).get("minimized") is not True:
        print("manifest mismatch", file=sys.stderr)
        return 1
    print("P0.5 exact baseline check: allow")
    return 0


def self_test() -> int:
    if not SECRET_VALUE.search("sk-abcdefghijklmnop") or not SECRET_NAME.search("api_key"):
        return 1
    if stable_project_id(Path("/a"), []) == stable_project_id(Path("/b"), []):
        return 1
    print("P0.5 baseline self-test: allow")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    return write() if args.write else check() if args.check else self_test()


if __name__ == "__main__":
    raise SystemExit(main())
