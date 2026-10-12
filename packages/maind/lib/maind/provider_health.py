"""Exact-set provider health orchestration over public package CLIs.

The sealed evidence set declares intent and immutable owner evidence.  mAInd
adds only observations owned by Skiller, Harness, or mAInd itself, then passes
the complete rows to the shared pure evaluator.  It never reads provider
targets, imports sibling package internals, repairs a project, or retries with
another provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Callable

from aicore.provider.health import (
    HEALTH_CONTRACT_VERSION, HealthEvidence, HealthRequirement, evaluate_fleet,
    evaluate_project)

from .probe import provider_health_probe


EVIDENCE_SET_VERSION = "provider-health-evidence-set/v1"
REQUIRED_PROVIDERS = frozenset({"claude-code", "codex", "cursor"})
DEFAULT_TIMEOUT = 20
_PRODUCERS = frozenset({"sealed", "skiller", "harness", "maind"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SENSITIVE = re.compile(
    r"(?:/home/|/Users/|[A-Za-z]:\\|secret|token|password|api[-_.]?key)", re.I,
)


@dataclass(frozen=True)
class DeclaredRequirement:
    requirement: HealthRequirement
    producer: str


@dataclass(frozen=True)
class ProjectInput:
    project_id: str
    requirements: tuple[DeclaredRequirement, ...]
    evidence: tuple[HealthEvidence, ...]


@dataclass(frozen=True)
class EvidenceSet:
    evidence_set_id: str
    projects: tuple[ProjectInput, ...]


@dataclass(frozen=True)
class CommandResult:
    state: str
    payload: dict[str, object] | None
    diagnostic: str
    returncode: int | None


def load_evidence_set(path: str | Path) -> EvidenceSet:
    """Load one closed, self-digested evidence-set descriptor."""
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("PH_EVIDENCE_SET_UNREADABLE") from error
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "contract_version", "evidence_set_id", "projects", "seal",
    }:
        raise ValueError("PH_EVIDENCE_SET_SCHEMA_INVALID")
    if payload["schema_version"] != EVIDENCE_SET_VERSION:
        raise ValueError("PH_EVIDENCE_SET_VERSION_UNSUPPORTED")
    if payload["contract_version"] != HEALTH_CONTRACT_VERSION:
        raise ValueError("PH_CONTRACT_VERSION_UNSUPPORTED")
    evidence_set_id = _identity(payload["evidence_set_id"], "PH_EVIDENCE_SET_ID_INVALID")
    seal = payload["seal"]
    if not isinstance(seal, dict) or set(seal) != {"sha256"}:
        raise ValueError("PH_EVIDENCE_SET_SEAL_INVALID")
    unsigned = {key: value for key, value in payload.items() if key != "seal"}
    expected = "sha256:" + hashlib.sha256(_canonical(unsigned).encode("utf-8")).hexdigest()
    if seal["sha256"] != expected:
        raise ValueError("PH_EVIDENCE_SET_SEAL_INVALID")
    projects_raw = payload["projects"]
    if not isinstance(projects_raw, list) or not projects_raw:
        raise ValueError("PH_PROJECT_SET_INVALID")
    projects = tuple(_project_input(item) for item in projects_raw)
    project_ids = [item.project_id for item in projects]
    if project_ids != sorted(project_ids) or len(project_ids) != len(set(project_ids)):
        raise ValueError("PH_PROJECT_SET_INVALID")
    return EvidenceSet(evidence_set_id=evidence_set_id, projects=projects)


def seal_evidence_set(payload: dict[str, object]) -> dict[str, object]:
    """Return a sealed copy; useful to producers and isolated tests."""
    if "seal" in payload:
        raise ValueError("PH_EVIDENCE_SET_SEAL_INVALID")
    result = dict(payload)
    result["seal"] = {
        "sha256": "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
    }
    return result


def evaluate(env, config: dict[str, object], selected_projects: list[dict[str, object]],
             evidence_set: EvidenceSet, *, evaluated_at: str | None = None,
             timeout: int = DEFAULT_TIMEOUT,
             runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> dict[str, object]:
    """Collect owner rows and return the shared exact-set fleet result."""
    now = evaluated_at or _now()
    expected_ids = tuple(item.project_id for item in evidence_set.projects)
    actual_ids = tuple(sorted(str(item.get("id")) for item in selected_projects))
    if actual_ids != expected_ids or len(actual_ids) != len(set(actual_ids)):
        raise ValueError("PH_PROJECT_SET_MISMATCH")
    by_id = {str(item["id"]): item for item in selected_projects}
    skiller_bin = _worktree_bin(env, "skiller")
    harness_bin = _worktree_bin(env, "harness")
    project_results = []
    for declaration in evidence_set.projects:
        project = by_id[declaration.project_id]
        requirements = tuple(item.requirement for item in declaration.requirements)
        _require_provider_set(requirements)
        evidence = list(declaration.evidence)
        by_producer = {
            producer: tuple(item.requirement for item in declaration.requirements
                            if item.producer == producer)
            for producer in _PRODUCERS
        }
        local = project.get("local_path")
        target = Path(str(local)).expanduser() if local else None
        evidence.extend(_skiller_evidence(
            declaration.project_id, target, by_producer["skiller"], skiller_bin,
            now=now, timeout=timeout, runner=runner,
        ))
        evidence.extend(_harness_evidence(
            declaration.project_id, target, by_producer["harness"], harness_bin,
            now=now, timeout=timeout, runner=runner,
        ))
        evidence.extend(_maind_evidence(
            env, config, project, by_producer["maind"], now=now,
        ))
        project_results.append(evaluate_project(
            project_id=declaration.project_id,
            requirements=requirements,
            evidence=tuple(evidence),
            evaluated_at=now,
        ))
    fleet = evaluate_fleet(
        required_project_ids=expected_ids,
        projects=tuple(project_results),
        evaluated_at=now,
    )
    result = fleet.to_dict()
    result["evidence_set_id"] = evidence_set.evidence_set_id
    _assert_redacted(result)
    return result


def _project_input(value: object) -> ProjectInput:
    if not isinstance(value, dict) or set(value) != {
        "project_id", "requirements", "evidence",
    }:
        raise ValueError("PH_EVIDENCE_SET_SCHEMA_INVALID")
    project_id = _project_identity(value["project_id"])
    requirements_raw = value["requirements"]
    evidence_raw = value["evidence"]
    if not isinstance(requirements_raw, list) or not requirements_raw:
        raise ValueError("PH_REQUIREMENTS_INVALID")
    if not isinstance(evidence_raw, list):
        raise ValueError("PH_EVIDENCE_INVALID")
    requirements = tuple(_declared_requirement(item) for item in requirements_raw)
    keys = [item.requirement.key for item in requirements]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise ValueError("PH_REQUIREMENTS_INVALID")
    evidence = tuple(_health_evidence(item) for item in evidence_raw)
    if list(evidence) != sorted(evidence):
        raise ValueError("PH_EVIDENCE_INVALID")
    declared = {item.requirement.key for item in requirements if item.producer == "sealed"}
    if {item.key for item in evidence} - declared:
        raise ValueError("PH_EVIDENCE_PRODUCER_MISMATCH")
    return ProjectInput(project_id, requirements, evidence)


def _declared_requirement(value: object) -> DeclaredRequirement:
    if not isinstance(value, dict) or set(value) != {
        "provider_id", "axis_id", "selected", "required", "producer",
    }:
        raise ValueError("PH_REQUIREMENTS_INVALID")
    producer = value["producer"]
    if producer not in _PRODUCERS:
        raise ValueError("PH_PRODUCER_UNKNOWN")
    requirement = HealthRequirement(
        value["provider_id"], value["axis_id"], value["selected"], value["required"],
    )
    return DeclaredRequirement(requirement, str(producer))


def _health_evidence(value: object) -> HealthEvidence:
    if not isinstance(value, dict) or set(value) != {
        "provider_id", "axis_id", "state", "evidence_id", "source_id",
        "observed_at", "expires_at",
    }:
        raise ValueError("PH_EVIDENCE_INVALID")
    return HealthEvidence(
        value["provider_id"], value["axis_id"], value["state"],
        value["evidence_id"], value["source_id"], value["observed_at"],
        value["expires_at"],
    )


def _require_provider_set(requirements: tuple[HealthRequirement, ...]) -> None:
    declared = {item.provider_id for item in requirements}
    if not REQUIRED_PROVIDERS <= declared:
        raise ValueError("PH_REQUIRED_PROVIDER_SET_MISMATCH")


def _worktree_bin(env, package: str) -> Path:
    path = env.monorepo_root / "packages" / package / "bin" / package
    return path


def _run_json(argv: list[str], *, timeout: int,
              runner: Callable[..., subprocess.CompletedProcess[str]]) -> CommandResult:
    try:
        completed = runner(
            argv, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult("unavailable", None, "PH_SUBPROCESS_TIMEOUT", None)
    except (OSError, subprocess.SubprocessError):
        return CommandResult("unavailable", None, "PH_SUBPROCESS_UNAVAILABLE", None)
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        return CommandResult("error", None, "PH_SUBPROCESS_JSON_INVALID", completed.returncode)
    if not isinstance(payload, dict):
        return CommandResult("error", None, "PH_SUBPROCESS_SCHEMA_INVALID",
                             completed.returncode)
    return CommandResult("pass", payload, "", completed.returncode)


def _skiller_evidence(project_id: str, target: Path | None,
                      requirements: tuple[HealthRequirement, ...], skiller_bin: Path,
                      *, now: str, timeout: int,
                      runner: Callable[..., subprocess.CompletedProcess[str]]) -> tuple[HealthEvidence, ...]:
    if not requirements:
        return ()
    if target is None or not target.is_dir() or not skiller_bin.is_file():
        return _failure_rows(requirements, "unavailable", "PH_SKILLER_UNAVAILABLE", now)
    result = _run_json(
        [str(skiller_bin), "status", "--target", str(target), "--json"],
        timeout=timeout, runner=runner,
    )
    if result.payload is None:
        return _failure_rows(requirements, result.state, result.diagnostic, now)
    if result.returncode:
        return _failure_rows(requirements, "error", "PH_SKILLER_EXIT_NONZERO", now)
    payload = result.payload
    closure = payload.get("dependency_closure")
    measurements = payload.get("measurements")
    if (not isinstance(closure, dict)
            or set(closure) != {"status", "diagnostics"}
            or closure.get("status") not in {"green", "non-green", "unknown"}
            or not isinstance(closure.get("diagnostics"), list)
            or not isinstance(measurements, dict)
            or set(measurements) != {"status", "rows"}
            or measurements.get("status") not in {"green", "non-green"}
            or not isinstance(measurements.get("rows"), list)):
        return _failure_rows(requirements, "error", "PH_SKILLER_SCHEMA_INVALID", now)
    observations: dict[tuple[str, str], HealthEvidence] = {}
    closure_state = {"green": "pass", "non-green": "unresolved", "unknown": "unknown"}[
        str(closure["status"])
    ]
    for requirement in requirements:
        if requirement.axis_id == "skill.dependency":
            observations[requirement.key] = _observation(
                requirement, closure_state, "skiller.dependency-closure", now,
                closure,
            )
    for measurement in measurements["rows"]:
        parsed = _measurement(measurement)
        if parsed is None:
            return _failure_rows(requirements, "error", "PH_SKILLER_SCHEMA_INVALID", now)
        provider_id, axis_id, state, observed_at, expires_at, source_id, identity = parsed
        key = (provider_id, axis_id)
        requirement = next((item for item in requirements if item.key == key), None)
        if requirement is not None:
            observations[key] = _observation(
                requirement, state, source_id, observed_at, identity,
                expires_at=expires_at,
            )
    return tuple(
        observations.get(requirement.key)
        or _observation(requirement, "unknown", "skiller.status", now,
                        {"project_id": project_id, "axis_id": requirement.axis_id})
        for requirement in requirements
    )


def _measurement(value: object) -> tuple[str, str, str, str, str, str, object] | None:
    if not isinstance(value, dict):
        return None
    required = {
        "provider", "surface", "value", "unit", "method", "uncertainty",
        "measurement_class", "observed_at", "expires_at", "source_id", "status",
        "threshold",
    }
    model_keys = {key for key in ("model", "model_family") if key in value}
    if set(value) != required | model_keys or len(model_keys) != 1:
        return None
    numeric = isinstance(value["value"], (int, float)) and not isinstance(value["value"], bool)
    if ((value["measurement_class"] == "unknown") != (value["value"] is None)
            or (value["value"] is not None and not numeric)
            or not isinstance(value["threshold"], (int, float))
            or isinstance(value["threshold"], bool)
            or value["surface"] not in {"listing", "loaded-body", "runtime"}
            or value["measurement_class"] not in {
                "exact", "estimate", "lower-bound", "upper-bound", "unknown",
            }
            or not all(isinstance(value[key], str) and value[key]
                       for key in required - {"value", "threshold"})
            or not isinstance(value[next(iter(model_keys))], str)
            or not value[next(iter(model_keys))]):
        return None
    state = {
        "pass": "pass", "over-budget": "unresolved", "stale": "unknown",
        "unknown": "unknown",
    }.get(value["status"])
    if state is None:
        return None
    axis_id = str(value.get("axis_id") or f"skill.measurement.{value['surface']}")
    return (str(value["provider"]), axis_id, str(state), str(value["observed_at"]),
            str(value["expires_at"]), str(value["source_id"]), value)


def _harness_evidence(project_id: str, target: Path | None,
                      requirements: tuple[HealthRequirement, ...], harness_bin: Path,
                      *, now: str, timeout: int,
                      runner: Callable[..., subprocess.CompletedProcess[str]]) -> tuple[HealthEvidence, ...]:
    if not requirements:
        return ()
    if target is None or not target.is_dir() or not harness_bin.is_file():
        return _failure_rows(requirements, "unavailable", "PH_HARNESS_UNAVAILABLE", now)
    observations = []
    for provider_id in sorted({item.provider_id for item in requirements}):
        selected = tuple(item for item in requirements if item.provider_id == provider_id)
        result = _run_json(
            [str(harness_bin), "doctor", "--settings", "--provider", provider_id,
             "--target", str(target), "--json"],
            timeout=timeout, runner=runner,
        )
        if result.payload is None:
            observations.extend(_failure_rows(selected, result.state, result.diagnostic, now))
            continue
        payload = result.payload
        counts = payload.get("counts")
        if (payload.get("provider") != provider_id
                or payload.get("status") not in {"clean", "warning", "error"}
                or not isinstance(counts, dict)
                or set(counts) != {"error", "warn", "info"}
                or not all(isinstance(counts[key], int) and counts[key] >= 0 for key in counts)
                or not isinstance(payload.get("findings"), list)
                or not isinstance(payload.get("exit"), int)
                or payload.get("exit") != result.returncode):
            observations.extend(_failure_rows(
                selected, "error", "PH_HARNESS_SCHEMA_INVALID", now,
            ))
            continue
        expected_status = "error" if counts["error"] else (
            "warning" if counts["warn"] else "clean"
        )
        if payload["status"] != expected_status:
            observations.extend(_failure_rows(
                selected, "error", "PH_HARNESS_SCHEMA_INVALID", now,
            ))
            continue
        state = "error" if counts["error"] else ("unresolved" if counts["warn"] else "pass")
        identity = {"provider_id": provider_id, "counts": counts,
                    "finding_ids": sorted(str(item.get("id")) for item in payload["findings"]
                                          if isinstance(item, dict))}
        observations.extend(
            _observation(item, state, "harness.settings", now, identity)
            for item in selected
        )
    return tuple(observations)


def _maind_evidence(env, config: dict[str, object], project: dict[str, object],
                    requirements: tuple[HealthRequirement, ...], *, now: str) -> tuple[HealthEvidence, ...]:
    if not requirements:
        return ()
    states = provider_health_probe(env, config, project)
    return tuple(
        _observation(
            requirement,
            states.get(requirement.axis_id, "unknown"),
            "maind.probe",
            now,
            {"project_id": project.get("id"), "axis_id": requirement.axis_id,
             "state": states.get(requirement.axis_id, "unknown")},
        )
        for requirement in requirements
    )


def _failure_rows(requirements: tuple[HealthRequirement, ...], state: str,
                  code: str, now: str) -> tuple[HealthEvidence, ...]:
    return tuple(
        _observation(item, state, code.lower().replace("_", "."), now,
                     {"code": code, "provider_id": item.provider_id,
                      "axis_id": item.axis_id})
        for item in requirements
    )


def _observation(requirement: HealthRequirement, state: str, source_id: str,
                 observed_at: str, identity: object, *, expires_at: str | None = None) -> HealthEvidence:
    digest = hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()[:24]
    return HealthEvidence(
        requirement.provider_id,
        requirement.axis_id,
        state,
        f"ev:{digest}",
        _identity(source_id, "PH_SOURCE_ID_INVALID"),
        observed_at,
        expires_at or _later(observed_at),
    )


def _identity(value: object, code: str) -> str:
    if (not isinstance(value, str) or not _SAFE_ID.fullmatch(value)
            or _SENSITIVE.search(value)):
        raise ValueError(code)
    return value


def _project_identity(value: object) -> str:
    if not isinstance(value, str) or not _PROJECT_ID.fullmatch(value):
        raise ValueError("PH_PROJECT_ID_INVALID")
    return value


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _assert_redacted(value: object) -> None:
    if _SENSITIVE.search(_canonical(value)):
        raise ValueError("PH_REDACTION_REQUIRED")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _later(value: str) -> str:
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return (parsed + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
