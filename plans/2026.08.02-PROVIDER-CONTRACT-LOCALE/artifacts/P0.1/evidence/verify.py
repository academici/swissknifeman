#!/usr/bin/env python3
"""Fail closed on P0.5's privacy-minimized exact-set baseline."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "packages" / "task" / "lib"))

from task.task_contract import bundle_lint  # noqa: E402


PRIVACY = {"minimized": True, "excluded_classes": ["raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets"]}
PROVIDERS = {"claude-code", "codex"}
FAMILIES = {"claude-code": {"CLAUDE.md", ".claude", ".claude-plugin"}, "codex": {"AGENTS.md", ".codex", ".agents", ".codex-plugin"}}
ABSOLUTE = re.compile(r"(?:^|[\"'\s])/(?:home|tmp|private|var)/")
SECRET = re.compile(r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})")


def load(bundle: Path, name: str) -> Any:
    return json.loads((bundle / name).read_text(encoding="utf-8"))


def fail(message: str) -> int:
    print(message)
    return 1


def verify(bundle: Path) -> int:
    result = bundle_lint(bundle, manifest_path=bundle / "manifest.json", verifier_path=bundle / "verify.py", declared_privacy=PRIVACY)
    if result:
        return fail(str(result))
    registry = load(bundle, "project-registry-redacted.json")
    snapshot = load(bundle, "provider-source-snapshot.json")
    fleet = load(bundle, "provider-fleet-inventory.json")
    commands = load(bundle, "command-results-redacted.json")
    if any(document.get("schema_version") != 2 for document in (registry, snapshot, fleet, commands)):
        return fail("schema: version")

    projects = registry.get("projects")
    source_projects = snapshot.get("projects")
    if not isinstance(projects, list) or not isinstance(source_projects, list):
        return fail("schema: projects")
    ids = [project.get("project_id") for project in projects]
    source_ids = [project.get("project_id") for project in source_projects]
    if not all(isinstance(project_id, str) for project_id in ids) or len(ids) != len(set(ids)):
        return fail("registry: duplicate-or-malformed-project-id")
    if set(ids) != set(source_ids) or len(source_ids) != len(set(source_ids)):
        return fail("coverage: missing-project")

    source_by_id = {project["project_id"]: project for project in source_projects}
    path_sets: dict[str, set[str]] = {}
    artifact_ids: set[str] = set()
    for project_id, project in source_by_id.items():
        paths = project.get("provider_paths")
        if not isinstance(paths, list):
            return fail("schema: provider-paths")
        seen_paths: set[str] = set()
        for path in paths:
            relative = path.get("path")
            artifact_id = path.get("artifact_id")
            if not isinstance(relative, str) or relative.startswith("/") or not isinstance(artifact_id, str):
                return fail("privacy: absolute-or-malformed-path")
            if relative in seen_paths or artifact_id in artifact_ids:
                return fail("artifact: duplicate-id")
            seen_paths.add(relative)
            artifact_ids.add(artifact_id)
            if path.get("node") == "symlink" and path.get("target_state") not in {"broken", "in-root", "out-of-root"}:
                return fail("symlink: invalid-target-state")
        path_sets[project_id] = seen_paths

    rows = fleet.get("provider_rows")
    if not isinstance(rows, list):
        return fail("schema: provider-rows")
    if any(row.get("provider") not in PROVIDERS for row in rows if isinstance(row, dict)):
        return fail("coverage: unsupported-provider")
    row_keys = [(row.get("project_id"), row.get("provider")) for row in rows]
    expected_keys = {(project_id, provider) for project_id in ids for provider in PROVIDERS}
    if len(row_keys) != len(set(row_keys)):
        return fail("provider-row: duplicate")
    if set(row_keys) != expected_keys:
        return fail("coverage: provider-row-gap")
    row_artifacts = [row.get("artifact_id") for row in rows]
    if not all(isinstance(value, str) for value in row_artifacts) or len(row_artifacts) != len(set(row_artifacts)):
        return fail("artifact: duplicate-provider-row-id")
    for row in rows:
        project_id, provider = row["project_id"], row["provider"]
        if provider not in PROVIDERS:
            return fail("coverage: unsupported-provider")
        declared = row.get("carrier_paths")
        expected = {path for path in path_sets[project_id] if path.split("/", 1)[0] in FAMILIES[provider]}
        if not isinstance(declared, list) or len(declared) != len(set(declared)) or set(declared) != expected:
            return fail("coverage: provider-path-exact-set")

    skills = commands.get("skills_baseline")
    if not isinstance(skills, dict) or skills.get("availability") != "available":
        return fail("measurement: unavailable-or-parse-error")
    if not isinstance(skills.get("source_skill_count"), int) or skills["source_skill_count"] <= 0 or not isinstance(skills.get("bucket_count"), int) or skills["bucket_count"] <= 0:
        return fail("measurement: missing-source-count")
    if not isinstance(skills.get("source_class_distribution"), dict) or not skills["source_class_distribution"]:
        return fail("measurement: missing-source-class")
    observations = skills.get("multi_label_observations")
    if not isinstance(observations, list) or not observations or any(not isinstance(item.get("labels"), list) or not item["labels"] for item in observations if isinstance(item, dict)):
        return fail("measurement: missing-multi-label")
    measurements = skills.get("profile_measurements")
    if not isinstance(measurements, list) or not measurements:
        return fail("measurement: missing-profile-rows")
    measured_providers = {row.get("provider") for row in measurements if isinstance(row, dict) and row.get("availability") == "available"}
    if measured_providers != PROVIDERS:
        return fail("measurement: provider-qualified-gap")
    required_measurement = {"profile", "provider", "model", "surface", "unit", "value", "method", "tool_version", "raw_sha256", "observed_at", "expires_at", "availability"}
    if any(not required_measurement <= set(row) for row in measurements if isinstance(row, dict)):
        return fail("measurement: malformed-profile-row")

    for name, command in commands.get("commands", {}).items():
        if not isinstance(command, dict) or not isinstance(command.get("command"), list) or command.get("availability") not in {"available", "command-error", "unavailable"}:
            return fail("command-result: malformed-" + str(name))
    text = "".join((bundle / name).read_text(encoding="utf-8") for name in ("project-registry-redacted.json", "provider-source-snapshot.json", "provider-fleet-inventory.json", "command-results-redacted.json"))
    if ABSOLUTE.search(text) or SECRET.search(text) or "secret_digest" in text:
        return fail("privacy: absolute-or-secret-leak")
    print("allow")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=HERE)
    args = parser.parse_args()
    return verify(args.bundle)


if __name__ == "__main__":
    raise SystemExit(main())
