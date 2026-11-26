"""Slug value object shared by workspaces and projects."""

import re
from dataclasses import dataclass
from typing import override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = ["Slug"]

# Same language as the ``slug`` definition of ``urn:skm:workspace:defs:v1``.
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


@dataclass(frozen=True, slots=True)
class Slug:
    value: str

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.value) or "--" in self.value or self.value.endswith("-"):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "slug must be 2-63 chars of a-z, 0-9 and single hyphens",
                details={"field": "slug", "value": self.value},
            )

    @override
    def __str__(self) -> str:
        return self.value
