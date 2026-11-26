"""Data classifications shared across host and control-plane boundaries."""

from typing import Final, Literal

__all__ = ["HOST_PRIVATE"]

HOST_PRIVATE: Final[Literal["HOST_PRIVATE"]] = "HOST_PRIVATE"
