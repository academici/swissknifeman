"""Provider-neutral, closed helpers for untrusted adapter observations."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class AdapterRefusal(ValueError):
    """A closed refusal which callers map to a neutral worker result."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def load_json(path: str | Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AdapterRefusal("MAPPING_UNKNOWN") from error
    if not isinstance(value, dict):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    return value


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_request(request: dict) -> None:
    required = ("provider", "route", "permissions", "budgets", "bundle")
    if not isinstance(request, dict) or any(not isinstance(request.get(key), dict) for key in required):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if request["provider"].get("id") != "codex":
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if request.get("child_policy", {}).get("mode") != "forbidden":
        raise AdapterRefusal("CAPABILITY_UNSUPPORTED")
    if request["permissions"].get("approval_mode") != "never":
        raise AdapterRefusal("PERMISSION_REFUSED")
    if request["route"].get("model_class") not in ("economy", "implementation", "frontier"):
        raise AdapterRefusal("MAPPING_UNKNOWN")
    if request["route"].get("effort") not in ("low", "medium", "high", "xhigh"):
        raise AdapterRefusal("MAPPING_UNKNOWN")


def failed(reason: str, exit_class: str = "internal_failure") -> dict:
    return {"worker_succeeded": False, "acceptance_state": "not_evaluated", "exit_class": exit_class,
            "reason_code": reason}
