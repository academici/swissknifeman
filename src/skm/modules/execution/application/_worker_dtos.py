"""Wire codecs shared by the eight fenced worker commands."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.outcomes import Waiting
from skm.modules.execution.application._plain import plain


def document(value: Any) -> Any:
    return plain(value)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        document(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class WireRecord(dict[str, Any]):
    """Bus adapter for generated JSON-mode codecs (which deliberately return plain mappings)."""

    SCHEMA_URN: str

    @classmethod
    def from_json(cls, data: Any) -> Any:
        return cls(data)

    @override
    def __repr__(self) -> str:
        return repr(
            {key: "<redacted>" if key == "runtime_token_secret" else value for key, value in self.items()}
        )

    def to_json(self) -> Any:
        return document(dict(self))


class ClaimAssignment(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:claim-assignment:v1"


class ClaimAssignmentResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:claim-assignment:v1"
    __slots__ = ("waiting",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Do not cache nothing_to_claim as an idempotency receipt across long-poll retries.
        self.waiting = (
            Waiting(ErrorCode.NOTHING_TO_CLAIM, "no work available")
            if self.get("outcome") == "nothing_to_claim"
            else None
        )


class BeginStage(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:begin-stage:v1"


class BeginStageResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:begin-stage:v1"


class RenewLease(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:renew-lease:v1"


class RenewLeaseResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:renew-lease:v1"


class SealOutput(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:seal-output:v1"


class SealOutputResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:seal-output:v1"


class RecordStageResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:record-stage-result:v1"


class RecordStageResultResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:record-stage-result:v1"


class ReleaseAssignment(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:release-assignment:v1"


class ReleaseAssignmentResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:release-assignment:v1"


class ReportAttemptFailure(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:report-attempt-failure:v1"


class ReportAttemptFailureResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:report-attempt-failure:v1"


class RecordStepNote(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:record-step-note:v1"


class RecordStepNoteResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:record-step-note:v1"
