"""P00 declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class VaultProjectMatch:
    folder: str
    name: str
    via: Literal["catalog", "control_note"]
