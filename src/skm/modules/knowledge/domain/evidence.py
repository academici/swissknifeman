"""Evidence identity without an upward dependency on learning."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    kind: str
    id: str
