"""Narrow stage values and bounded, assignment-owned local recovery evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from skm.platform.logging.redaction import Redactor

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from skm.kernel.json_types import JsonValue
    from skm.modules.context.public import FinalizedContext
    from skm.modules.execution.domain.assignment import StageInstruction
    from skm.modules.execution.domain.contracts import BeginStageResult, Diagnostic, OutputManifestDraft
    from skm.modules.execution.domain.stage_record import StageOutcomeKind
    from skm.modules.execution.host.evidence import EvidenceFile
    from skm.modules.runtimes.public import AgentRequest, UsageReport


@dataclass(frozen=True, slots=True)
class StageRequest:
    instruction: StageInstruction
    begin: BeginStageResult
    context: FinalizedContext | None
    task: Mapping[str, JsonValue]
    runtime_request: AgentRequest | None = field(default=None, repr=False)
    capture: StageCapture | None = field(default=None, repr=False)
    process_started: Callable[[Any], None] = field(default=lambda _handle: None, repr=False)
    offer_live: Callable[[bytes], bool] | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class StageOutcome:
    kind: StageOutcomeKind
    payload: Mapping[str, JsonValue]
    files: tuple[EvidenceFile, ...] = ()
    usage: UsageReport | None = None
    activity: Mapping[str, JsonValue] | None = None
    output_manifest: OutputManifestDraft | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    observations: tuple[Mapping[str, JsonValue], ...] = ()
    reaped: bool = True


class CleanupUnconfirmed(RuntimeError):
    """Retain ownership and evidence; another assignment must not start on this slot."""


class StageCapture:
    """Finite write reservation held until every file is fsynced and closed; no age-based deletion."""

    def __init__(self, root: Any, budget: Any, *, owner: str, max_bytes: int, floor: int) -> None:
        self.root, self.owner, self.max_bytes = root, owner, max_bytes
        self.redactor = Redactor()
        self._reservation = budget.reserve(
            root, owner_id=owner, max_bytes=max_bytes, min_free_bytes=floor, max_files=4
        )
        self._paths: dict[str, Any] = {}
        self._written = 0

    def write(self, name: str, text: str, *, limit: int | None = None) -> Any:
        if name not in {"raw.json", "environment.patch", "journal.json", "transcript.txt"}:
            raise ValueError("unknown recovery evidence role")
        if name in self._paths:
            raise ValueError("evidence is immutable once written")
        data = self.redactor.text(text).encode()
        ceiling = min(self.max_bytes - self._written, len(data) if limit is None else limit)
        # Do not leave malformed UTF-8 at a capture boundary.
        data = data[:ceiling].decode("utf-8", "ignore").encode()
        path = self.root / name
        self._paths[name] = path
        target = self._reservation.open_file(path)
        target.write(data)
        target.close()
        self._written += len(data)
        return path

    def journal(self, **facts: JsonValue) -> Any:
        return self.write("journal.json", json.dumps({"owner": self.owner, **facts}, sort_keys=True))

    def close(self) -> None:
        try:
            self._reservation.close()
        finally:
            self.redactor = Redactor()
