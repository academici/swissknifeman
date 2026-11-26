"""Redacted, adapter-scoped provider status rows.

The store intentionally knows no provider enum: a row is owned by the adapter
that names it, while aggregation is a pure no-write operation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import tempfile
from typing import Literal


ProviderStatus = Literal["not-selected", "ready", "unapplied", "observation-missing", "observation-stale", "drifted", "unsupported", "untrusted", "unknown", "error"]
AggregateStatus = Literal["ready", "unknown", "drifted", "blocked", "error", "no-providers-selected"]
_SECRET = re.compile(r"(?:secret|token|password|apikey|api_key|/home/|\\\\)", re.I)


@dataclass(frozen=True, order=True)
class StatusDiagnostic:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    source_ref: str

    def __post_init__(self) -> None:
        if self.severity not in {"error", "warning", "info"} or not all(isinstance(v, str) and v for v in (self.code, self.message, self.source_ref)):
            raise ValueError("STATUS_DIAGNOSTIC_INVALID")
        if _SECRET.search(self.message) or _SECRET.search(self.source_ref):
            raise ValueError("STATUS_VALUE_REDACTION_REQUIRED")


@dataclass(frozen=True)
class ProviderStatusRow:
    provider_id: str
    selected: bool
    desired_digest: str
    last_applied: bool = False
    observed: Literal["missing", "fresh", "stale", "unknown", "drifted", "unsupported", "untrusted"] = "missing"
    diagnostics: tuple[StatusDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str) or not self.provider_id or not isinstance(self.selected, bool):
            raise ValueError("STATUS_ROW_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", self.desired_digest):
            raise ValueError("STATUS_DIGEST_INVALID")
        if self.observed not in {"missing", "fresh", "stale", "unknown", "drifted", "unsupported", "untrusted"}:
            raise ValueError("STATUS_OBSERVATION_INVALID")
        if not isinstance(self.diagnostics, tuple) or not all(isinstance(item, StatusDiagnostic) for item in self.diagnostics):
            raise ValueError("STATUS_DIAGNOSTIC_INVALID")
        object.__setattr__(self, "diagnostics", tuple(sorted(self.diagnostics, key=lambda d: ({"error": 0, "warning": 1, "info": 2}[d.severity], d.source_ref, d.code))))

    @property
    def status(self) -> ProviderStatus:
        if not self.selected:
            return "not-selected"
        if any(d.severity == "error" for d in self.diagnostics):
            return "error"
        if self.observed == "unsupported": return "unsupported"
        if self.observed == "untrusted": return "untrusted"
        if not self.last_applied: return "unapplied"
        if self.observed == "missing": return "observation-missing"
        if self.observed == "stale": return "observation-stale"
        if self.observed == "unknown": return "unknown"
        if self.observed == "drifted": return "drifted"
        return "ready"


def aggregate(rows: tuple[ProviderStatusRow, ...]) -> dict[str, object]:
    if len({row.provider_id for row in rows}) != len(rows):
        raise ValueError("STATUS_DUPLICATE_PROVIDER")
    ordered = tuple(sorted(rows, key=lambda row: row.provider_id))
    selected = tuple(row for row in ordered if row.selected)
    statuses = {row.provider_id: row.status for row in ordered}
    if not selected: state: AggregateStatus = "no-providers-selected"
    elif any(row.status == "error" for row in selected): state = "error"
    elif any(row.status in {"unsupported", "untrusted"} for row in selected): state = "blocked"
    elif any(row.status in {"drifted", "unapplied"} for row in selected): state = "drifted"
    elif any(row.status in {"observation-missing", "observation-stale", "unknown"} for row in selected): state = "unknown"
    else: state = "ready"
    return {"status": state, "selected_provider_ids": [row.provider_id for row in selected], "provider_statuses": statuses}


def write_adapter_status(path: Path, *, writer_provider_id: str, row: ProviderStatusRow) -> None:
    """Atomically persist one row; cross-provider writers fail closed."""
    if writer_provider_id != row.provider_id:
        raise ValueError("STATUS_CROSS_PROVIDER_WRITER")
    payload = {"contract_version": "1.0.0", "writer_provider_id": writer_provider_id,
               "row": {**asdict(row), "diagnostics": [asdict(d) for d in row.diagnostics], "status": row.status}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)
