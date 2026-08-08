"""Provider-neutral records and interface for token-calibration probes (P0.1)."""
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


RECORD_SCHEMA_VERSION = "token-probe-record-v1"


class ProbeRecordError(ValueError):
    """A provider returned a record that cannot enter the calibration core."""


@dataclass(frozen=True)
class ProbeRecord:
    schema_version: str
    provider_id: str
    provider_adapter: str
    requested_model_id: str
    effective_model_id: str | None
    protocol_version: str
    input_tokens_total: int
    usage_breakdown: Mapping[str, Any]
    wrapper_sha256: str
    environment_cli: str
    environment_version: str
    command_sha256: str

    def __post_init__(self):
        strings = {
            "schema_version": self.schema_version,
            "provider.id": self.provider_id,
            "provider.adapter": self.provider_adapter,
            "model.requested_id": self.requested_model_id,
            "protocol_version": self.protocol_version,
            "wrapper_sha256": self.wrapper_sha256,
            "environment.cli": self.environment_cli,
            "environment.version": self.environment_version,
            "environment.command_sha256": self.command_sha256,
        }
        bad = [name for name, value in strings.items() if not isinstance(value, str) or not value]
        if bad:
            raise ProbeRecordError(f"token probe: пустые/невалидные поля {bad}")
        if self.schema_version != RECORD_SCHEMA_VERSION:
            raise ProbeRecordError(
                f"token probe: schema_version={self.schema_version!r}, ожидается {RECORD_SCHEMA_VERSION!r}")
        if (not isinstance(self.input_tokens_total, int) or isinstance(self.input_tokens_total, bool)
                or self.input_tokens_total < 0):
            raise ProbeRecordError("token probe: input_tokens_total обязан быть целым числом >= 0")
        if self.effective_model_id is not None and not isinstance(self.effective_model_id, str):
            raise ProbeRecordError("token probe: model.effective_id обязан быть строкой или null")
        if not isinstance(self.usage_breakdown, Mapping):
            raise ProbeRecordError("token probe: usage_breakdown обязан быть объектом")

    @property
    def target_identity(self):
        """The fields that must never be mixed inside one calibration artifact."""
        return (
            self.provider_id, self.provider_adapter, self.requested_model_id,
            self.protocol_version, self.environment_cli, self.environment_version,
            self.wrapper_sha256, self.command_sha256,
        )

    def as_dict(self):
        return {
            "schema_version": self.schema_version,
            "provider": {"id": self.provider_id, "adapter": self.provider_adapter},
            "model": {"requested_id": self.requested_model_id,
                      "effective_id": self.effective_model_id},
            "protocol_version": self.protocol_version,
            "input_tokens_total": self.input_tokens_total,
            "usage_breakdown": dict(self.usage_breakdown),
            "wrapper_sha256": self.wrapper_sha256,
            "environment": {"cli": self.environment_cli, "version": self.environment_version,
                            "command_sha256": self.command_sha256},
        }


class ProbeAdapter(Protocol):
    """A provider edge; the calibration core deliberately sees only this interface."""

    def probe(self, payload: str) -> ProbeRecord:
        """Return one validated provider-neutral record for ``payload``."""


def ensure_same_target(records):
    """Reject records from different providers/models/protocols/fingerprints."""
    if not records:
        raise ProbeRecordError("token probe: нет records для проверки target")
    identity = records[0].target_identity
    if any(record.target_identity != identity for record in records[1:]):
        raise ProbeRecordError("token probe: смешаны provider/model/protocol/fingerprint targets")
    return identity
