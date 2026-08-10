#!/usr/bin/env python3
"""Create and verify the privacy-minimized P0.1 provider-fleet baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


PLAN_ID = "2026.08.02-PROVIDER-CONTRACT-LOCALE"
ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "plans" / PLAN_ID / "artifacts" / "P0.1" / "evidence"
REGISTRY = Path.home() / ".swissknifeman" / "projects.json"
PROVIDERS = ("claude-code", "codex")
CARriers = (
    "CLAUDE.md", "AGENTS.md", ".claude", ".codex", ".agents", ".claude-plugin",
    ".codex-plugin", ".ai", ".mcp.json", ".swissknife.json",
)
SECRET_NAME = re.compile(r"(?:secret|token|password|api[_-]?key|credential|private[_-]?key)", re.I)
SECRET_VALUE = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})")
CONFIG_SUFFIXES = {".json", ".toml", ".yaml", ".yml", ".ini", ".env"}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(command: list[str], *, cwd: Path = ROOT, timeout: int = 30) -> dict[str, Any]:
    """Execute an observer command and retain only a safe, compact result."""
    try:
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
        output = (result.stdout + result.stderr).strip()
        output = re.sub(r"/(?:home|tmp|private|var)/[^\s'\"]+", "<absolute-path>", output)
        output = SECRET_VALUE.sub("<secret-like>", output)
        schema = "json-object" if output.startswith("{") else "text"
        observations: list[str] = []
        if "ValueError: root must be explicit and absolute" in output:
            observations.append("ValueError: root must be explicit and absolute")
        plan_match = re.search(r"План:\s*(sha256:[a-f0-9]+)", output)
        if plan_match:
            observations.append("plan-identity=" + plan_match.group(1))
        if "harness.codex.lifecycle." in output:
            observations.append("operation-set-present")
        if '"overallStatus": "ok"' in output:
            observations.append("overallStatus=ok")
        if '"pluginId": "task@swissknifeman"' in output:
            observations.append("task@swissknifeman=installed-enabled")
        if '"diagnostics": []' in output:
            observations.append("diagnostics=empty")
        if not observations:
            observations.append("exit=" + str(result.returncode))
        safe_command = ["<absolute-path>" if arg.startswith("/") else arg for arg in command]
        return {"command": safe_command, "exit_code": result.returncode, "stdout_schema": schema, "observations": observations,
                "status": "green" if result.returncode == 0 else "red"}
    except FileNotFoundError:
        return {"command": command[:1], "exit_code": None, "stdout_schema": "none", "observations": ["command-unavailable"],
                "status": "unavailable"}
    except subprocess.TimeoutExpired:
        return {"command": command[:1], "exit_code": None, "stdout_schema": "none", "observations": ["timeout"],
                "status": "unavailable"}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False).stdout.strip()


def stable_project_id(root: Path, records: list[dict[str, Any]]) -> str:
    identity = "|".join(sorted(str(record.get("provider", "generic")) + ":" + str(record.get("channel", "")) for record in records))
    return "project-" + sha256((str(root) + "|" + identity).encode())[:16]


def redacted_record(record: dict[str, Any], project_id: str) -> dict[str, Any]:
    allowed = ("channel", "provider", "agent", "profile", "profile_source", "skills_path", "hub", "plugins",
               "buckets", "exclude", "settings_file", "updated_at", "first_connected_at")
    return {"project_id": project_id, **{key: record[key] for key in allowed if key in record}}


def config_shape(path: Path, raw: bytes) -> dict[str, Any]:
    """Return schema-only data; values and value-derived hashes never leave memory."""
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
    st = path.lstat()
    rel = path.relative_to(repo).as_posix()
    record: dict[str, Any] = {"path": rel, "mode": st.st_mode, "managed": any(part in {".claude", ".codex", ".agents"} for part in path.parts)}
    if path.is_symlink():
        resolved = path.resolve(strict=False)
        record["node"] = "symlink"
        record["target_state"] = "broken" if not resolved.exists() else ("out-of-root" if repo not in resolved.parents and resolved != repo else "in-root")
        return record
    if path.is_dir():
        record["node"] = "directory"
        return record
    record["node"] = "file"
    raw = path.read_bytes()
    if path.suffix in CONFIG_SUFFIXES or SECRET_NAME.search(path.name) or SECRET_VALUE.search(raw.decode("utf-8", "ignore")):
        record["content"] = config_shape(path, raw)
    else:
        record["content"] = {"kind": "sha256", "value": sha256(raw), "bytes": len(raw)}
    return record


def carrier_paths(repo: Path) -> list[Path]:
    paths: list[Path] = []
    for name in CARriers:
        candidate = repo / name
        if not candidate.exists() and not candidate.is_symlink():
            continue
        paths.append(candidate)
        if candidate.is_dir() and not candidate.is_symlink():
            paths.extend(sorted(item for item in candidate.rglob("*") if item.is_file() or item.is_symlink()))
    return sorted(set(paths), key=lambda item: item.as_posix())


def inventory_project(root: Path, records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    project_id = stable_project_id(root, records)
    exists = root.is_dir()
    selected = {str(record.get("provider")) for record in records if record.get("provider") in PROVIDERS}
    project: dict[str, Any] = {"project_id": project_id, "record_count": len(records), "records": [redacted_record(record, project_id) for record in records], "repository": {"state": "available" if exists else "unavailable"}}
    provider_rows: list[dict[str, Any]] = []
    if not exists:
        for provider in PROVIDERS:
            provider_rows.append({"project_id": project_id, "provider": provider, "status": "unavailable", "diagnostics": ["project-root-unavailable"]})
        return project, provider_rows
    project["repository"].update({"head": git(root, "rev-parse", "HEAD") or None, "dirty_tracked": git(root, "status", "--porcelain", "--untracked-files=no").splitlines(), "untracked": git(root, "ls-files", "--others", "--exclude-standard").splitlines()})
    paths = [node(path, root) for path in carrier_paths(root)]
    tracked = set(git(root, "ls-files").splitlines())
    for item in paths:
        item["tracked"] = item["path"] in tracked
    project["provider_paths"] = paths
    for provider in PROVIDERS:
        families = {"claude-code": ("CLAUDE.md", ".claude", ".claude-plugin"), "codex": ("AGENTS.md", ".codex", ".agents", ".codex-plugin")}[provider]
        relevant = [item["path"] for item in paths if item["path"].split("/", 1)[0] in families]
        status = "green" if provider in selected and relevant else ("not-selected" if provider not in selected else "red")
        diagnostics = [] if status in {"green", "not-selected"} else ["selected-provider-has-no-carrier"]
        provider_rows.append({"project_id": project_id, "provider": provider, "selected": provider in selected, "status": status, "carrier_paths": relevant, "diagnostics": diagnostics})
    return project, provider_rows


def collect() -> dict[str, Any]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("projects"), list):
        raise ValueError("registry projects must be a list")
    grouped: dict[Path, list[dict[str, Any]]] = {}
    for record in registry["projects"]:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError("registry record missing path")
        grouped.setdefault(Path(record["path"]), []).append(record)
    projects, provider_rows = [], []
    for root, records in sorted(grouped.items(), key=lambda pair: str(pair[0])):
        project, rows = inventory_project(root, records)
        projects.append(project)
        provider_rows.extend(rows)
    commands = {
        "hooks_relative": run(["packages/harness/bin/harness", "hooks", "--target", ".", "--provider", "codex", "--observer", "--trusted", "--dry-run"]),
        "hooks_absolute": run(["packages/harness/bin/harness", "hooks", "--target", str(ROOT), "--provider", "codex", "--observer", "--trusted", "--dry-run"]),
        "provider_audit": run(["packages/harness/bin/harness", "doctor", "--provider-audit", "--json"]),
        "maind_health": run(["packages/maind/bin/maind", "health", "--cwd", "--strict"]),
        "codex_doctor": run(["codex", "doctor", "--json"]),
        "codex_plugins": run(["codex", "plugin", "list", "--json"]),
        "bucket_audit": run(["packages/skiller/bin/skiller", "bucket-audit"]),
        "budget_profiles": run(["packages/skiller/bin/skiller", "budget", "--profiles"]),
    }
    return {"schema_version": 1, "plan_id": PLAN_ID, "registry": {"version": registry.get("version"), "record_count": len(registry["projects"]), "project_count": len(projects)}, "projects": projects, "provider_rows": provider_rows, "commands": commands, "producer": "p0-provider-fleet-inventory.py --write"}


def write() -> int:
    evidence = collect()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    registry = {"schema_version": 1, "record_count": evidence["registry"]["record_count"], "project_count": evidence["registry"]["project_count"], "projects": [{"project_id": p["project_id"], "records": p["records"]} for p in evidence["projects"]]}
    snapshot = {"schema_version": 1, "projects": [{"project_id": p["project_id"], "repository": p["repository"], "provider_paths": p.get("provider_paths", [])} for p in evidence["projects"]]}
    fleet = {"schema_version": 1, "registry": evidence["registry"], "provider_rows": evidence["provider_rows"]}
    commands = {"schema_version": 1, "commands": evidence["commands"]}
    files = {"project-registry-redacted.json": registry, "provider-source-snapshot.json": snapshot, "provider-fleet-inventory.json": fleet, "command-results-redacted.json": commands}
    for name, value in files.items():
        (EVIDENCE / name).write_text(canonical(value), encoding="utf-8")
    manifest = {"bundle_id": "P0.1-provider-fleet-baseline", "files": sorted(files), "privacy": {"minimized": True, "excluded_classes": ["raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets"]}, "producer": "PYTHONPATH=. python3 plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/p0-provider-fleet-inventory.py --write"}
    (EVIDENCE / "manifest.json").write_text(canonical(manifest), encoding="utf-8")
    print("P0.1 baseline written: %d records, %d projects" % (evidence["registry"]["record_count"], evidence["registry"]["project_count"]))
    return 0


def check() -> int:
    required = {"manifest.json", "verify.py", "project-registry-redacted.json", "provider-source-snapshot.json", "provider-fleet-inventory.json", "command-results-redacted.json"}
    missing = [name for name in sorted(required) if not (EVIDENCE / name).is_file()]
    if missing:
        print("missing evidence: " + ", ".join(missing), file=sys.stderr)
        return 1
    manifest = json.loads((EVIDENCE / "manifest.json").read_text())
    actual = sorted(path.name for path in EVIDENCE.iterdir() if path.is_file() and path.name not in {"manifest.json", "verify.py"})
    if manifest.get("files") != actual or manifest.get("privacy", {}).get("minimized") is not True:
        print("manifest mismatch", file=sys.stderr)
        return 1
    combined = json.loads((EVIDENCE / "provider-fleet-inventory.json").read_text())
    projects = {project["project_id"] for project in json.loads((EVIDENCE / "project-registry-redacted.json").read_text())["projects"]}
    rows = combined["provider_rows"]
    if {row["project_id"] for row in rows} != projects or any(row["provider"] not in PROVIDERS for row in rows):
        print("coverage mismatch", file=sys.stderr)
        return 1
    if any("/home/" in (EVIDENCE / name).read_text(encoding="utf-8") for name in manifest["files"]):
        print("absolute root leaked", file=sys.stderr)
        return 1
    print("P0.1 baseline check: allow")
    return 0


def self_test() -> int:
    if not SECRET_VALUE.search("sk-abcdefghijklmnop") or not SECRET_NAME.search("api_key"):
        return 1
    if stable_project_id(Path("/a"), []) == stable_project_id(Path("/b"), []):
        return 1
    print("P0.1 baseline self-test: allow (negative fixture predicates covered by verifier)")
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
