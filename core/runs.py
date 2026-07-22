"""Run-report'ы Claude Code — общий stdlib-only примитив монорепо.

Поиск свежего run-report'а (<project>/.claude/runs/*.json) копировался в analyst
(digest) и maind (analyze) с расхождением: analyst раскрывал `~` в пути
(os.path.expanduser), maind — нет, и на `~`-пути молча возвращал None. Сведено сюда
с единой нормализацией пути. stdlib-only."""
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
        if not all(isinstance(value[name], str) and value[name] for name in (
                "session_id", "project_id", "event_id", "event_kind", "outcome")):
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


def find_run_report(project_path, session=None):
    """Разобранный свежий (или по session) run-report из <project>/.claude/runs/*.json.

    None если нет каталога/файла/битый JSON. Путь нормализуется через expanduser —
    `~/...` раскрывается (иначе отчёт молча «не находится»)."""
    runs = Path(os.path.expanduser(str(project_path))) / ".claude" / "runs"
    if not runs.is_dir():
        return None
    if session:
        f = runs / f"{session}.json"
        return safe_load_json(f, None) if f.is_file() else None
    files = [p for p in runs.glob("*.json") if p.is_file()]
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return safe_load_json(latest, None)
