"""Shared stdlib-only Claude Code run-report lookup helpers."""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .io import safe_load_json


ANALYTICS_CONTRACT_VERSION = "1.0.0"
ANALYTICS_PROVIDER_IDS = frozenset(("claude-code", "codex"))
ANALYTICS_METRICS = frozenset((
    "tools", "files", "workflows", "retrieval", "devloop", "maind", "usage", "reads", "errors",
))
ANALYTICS_EVENT_KINDS = frozenset(("run_summary",))
ANALYTICS_OUTCOMES = frozenset(("ok", "failed", "unknown"))
_EVENT_FIELDS = frozenset((
    "contract_version", "provider_id", "session_id", "project_id", "event_id", "occurred_at",
    "event_kind", "outcome", "metrics", "provenance",
))
_PROVENANCE_FIELDS = frozenset(("raw_ref", "sha256", "reader_id", "reader_version"))
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class EventEnvelope:
    """Minimal immutable D90 normalized-event lookup primitive.

    Provider acquisition, redaction, persistence and migration intentionally stay outside
    `core`; this validates only the public semantic envelope used by multiple consumers.
    """

    contract_version: str
    provider_id: str
    session_id: str
    project_id: str
    event_id: str
    occurred_at: str
    event_kind: str
    outcome: str
    metrics: MappingProxyType
    provenance: MappingProxyType

    @classmethod
    def from_mapping(cls, value):
        if not isinstance(value, dict) or set(value) != _EVENT_FIELDS:
            raise ValueError("invalid normalized analytics envelope")
        if value["contract_version"] != ANALYTICS_CONTRACT_VERSION:
            raise ValueError("unsupported normalized analytics contract")
        if value["provider_id"] not in ANALYTICS_PROVIDER_IDS:
            raise ValueError("unknown normalized analytics provider")
        if (not all(isinstance(value[name], str) and value[name] for name in (
                "session_id", "project_id", "event_id", "event_kind", "outcome"))
                or value["event_kind"] not in ANALYTICS_EVENT_KINDS
                or value["outcome"] not in ANALYTICS_OUTCOMES):
            raise ValueError("invalid normalized analytics identity")
        if not isinstance(value["occurred_at"], str) or not value["occurred_at"].endswith("Z"):
            raise ValueError("normalized analytics timestamp must be UTC")
        metrics = value["metrics"]
        if (not isinstance(metrics, dict) or not set(metrics).issubset(ANALYTICS_METRICS)
                or not all(isinstance(metric, (int, float)) and not isinstance(metric, bool)
                           for metric in metrics.values())):
            raise ValueError("invalid normalized analytics metrics")
        provenance = value["provenance"]
        if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE_FIELDS:
            raise ValueError("invalid normalized analytics provenance")
        if (not isinstance(provenance["raw_ref"], str)
                or not provenance["raw_ref"].startswith("local:")
                or "/" in provenance["raw_ref"].removeprefix("local:")
                or ".." in provenance["raw_ref"]
                or not isinstance(provenance["sha256"], str)
                or not _SHA256.fullmatch(provenance["sha256"])
                or not all(isinstance(provenance[name], str) and provenance[name]
                           for name in ("reader_id", "reader_version"))):
            raise ValueError("invalid normalized analytics provenance")
        return cls(
            contract_version=value["contract_version"], provider_id=value["provider_id"],
            session_id=value["session_id"], project_id=value["project_id"], event_id=value["event_id"],
            occurred_at=value["occurred_at"], event_kind=value["event_kind"], outcome=value["outcome"],
            metrics=MappingProxyType(dict(metrics)), provenance=MappingProxyType(dict(provenance)),
        )


def event_key(envelope):
    """Stable provider-qualified lookup key for one normalized source event."""
    if not isinstance(envelope, EventEnvelope):
        raise ValueError("event_key expects EventEnvelope")
    return (envelope.provider_id, envelope.project_id, envelope.session_id, envelope.event_id)


def find_analytics_events(project_path, session=None):
    """Read validated neutral events only; provider raw homes are never consulted."""
    path = Path(os.path.expanduser(str(project_path))) / ".swissknife" / "analytics" / "events.ndjson"
    if not path.is_file():
        return ()
    events = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                event = EventEnvelope.from_mapping(json.loads(line))
            except (ValueError, TypeError):
                continue
            if session is None or event.session_id == session:
                events.append(event)
    return tuple(events)


@dataclass(frozen=True)
class RunReportLookup:
    """A trusted legacy report or a typed reason why it was rejected."""

    report: dict | None
    diagnostic: MappingProxyType | None


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _run_report_project_mismatch(report, project_path: Path, source: Path,
                                 expected_session=None, expected_project_id=None):
    """Reject only positive cross-project evidence; absence remains unknown.

    ``cwd`` alone is insufficient because old copied reports have been observed with a
    rewritten cwd.  Absolute changed-file evidence is therefore checked independently.
    Relative paths carry no project identity and are left to the report consumer.
    """
    if not isinstance(report, dict):
        return None
    expected = project_path.resolve(strict=False)
    conflicts = []
    provider = report.get("provider_id", report.get("provider"))
    if provider is not None and provider != "claude-code":
        conflicts.append({"field": "provider", "value": provider})
    reported_session = report.get("session_id")
    if (expected_session is not None and reported_session is not None
            and reported_session != expected_session):
        conflicts.append({"field": "session_id", "value": reported_session})
    project_id = report.get("project_id")
    if (expected_project_id is not None and project_id is not None
            and project_id != expected_project_id):
        conflicts.append({"field": "project_id", "value": project_id})
    cwd = report.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        observed = Path(os.path.expanduser(cwd))
        if observed.is_absolute() and not _within(observed, expected):
            conflicts.append({"field": "cwd", "value": str(observed)})
    changed = report.get("files_changed")
    if isinstance(changed, list):
        for value in changed:
            if not isinstance(value, str) or not value.strip():
                continue
            observed = Path(os.path.expanduser(value))
            if observed.is_absolute() and not _within(observed, expected):
                conflicts.append({"field": "files_changed", "value": str(observed)})
    if not conflicts:
        return None
    return MappingProxyType({
        "code": "RUN_REPORT_PROJECT_MISMATCH",
        "confidence": "untrusted-run-report",
        "provider": "claude-code",
        "expected_project": str(expected),
        "source": str(source),
        "conflicts": tuple(MappingProxyType(row) for row in conflicts),
    })


def find_run_report_result(project_path, session=None, *, project_id=None):
    """Return a provenance-checked report lookup without trusting its directory."""
    project = Path(os.path.expanduser(str(project_path)))
    runs = project / ".claude" / "runs"
    if not runs.is_dir():
        return RunReportLookup(None, None)
    if session:
        f = runs / f"{session}.json"
        files = [f] if f.is_file() else []
    else:
        files = [p for p in runs.glob("*.json") if p.is_file()]
    if not files:
        return RunReportLookup(None, None)
    selected = files[0] if session else max(files, key=lambda p: p.stat().st_mtime)
    report = safe_load_json(selected, None)
    if not isinstance(report, dict):
        return RunReportLookup(None, None)
    mismatch = _run_report_project_mismatch(
        report, project, selected, expected_session=session or selected.stem,
        expected_project_id=project_id)
    return RunReportLookup(None if mismatch else report, mismatch)


def find_run_report(project_path, session=None):
    """Return only a provenance-checked legacy report, or ``None``."""
    return find_run_report_result(project_path, session=session).report
