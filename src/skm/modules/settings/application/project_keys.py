"""Settings owned by the machine operator are outside the project settings surface."""

from collections.abc import Mapping

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = ["MACHINE_ONLY_KEYS", "project_keys", "require_project_key"]

MACHINE_ONLY_KEYS = frozenset(
    {
        "runtimes.binaries",
        "runtimes.credentials.copy",
        "runtimes.codex.allow_full_access",
        "runtimes.claude_code.allow_skip_permissions",
    }
)


def require_project_key(key: str) -> None:
    if key in MACHINE_ONLY_KEYS:
        raise ValidationFailed(
            ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
            "This setting belongs to the local machine operator",
            details={"key": key, "reason": "machine_owned"},
        )


def project_keys[T](entries: Mapping[str, T]) -> dict[str, T]:
    return {key: entry for key, entry in entries.items() if key not in MACHINE_ONLY_KEYS}
