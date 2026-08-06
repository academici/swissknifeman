"""Provider-neutral, closed helpers for untrusted adapter observations."""
from __future__ import annotations

import decimal
import hashlib
import json
from pathlib import Path


# `economy-evidence-v2` `declared-set: metric_fields` (D123/D127) — both `worker` and
# `coordinator` envelopes carry exactly these seven keys.
METRIC_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
                  "cost_microunits", "duration_ms", "turns")

# The one frozen `zero_basis_components` instantiation (`economy-evidence-v2` rule 2):
# `packages/artifex/lib/artifex/scheduler.py` never imports a provider adapter and makes
# no model call itself (verified by `test_integration.test_p2_core_remains_provider_free_...`);
# only the injected activity port crosses the one authorized side-effect boundary. The
# exact path/statement below is byte-identical to the already-frozen P5.7 fixture
# (`artifacts/P1/economy-evidence-cases-v2.json` `base_input.zero_bases`).
_COORDINATOR_ZERO_BASIS = {
    "component": "coordinator",
    "path": "packages/artifex/lib/artifex/scheduler.py",
    "statement": ("the Artifex coordinator is the deterministic scheduler in this file; by D3 "
                  "every model call is an activity behind the side-effect boundary, so the "
                  "coordinator envelope is a measured all-zero, not an unmeasured one"),
}

# The one frozen `inclusion_basis_instantiations` row: claude-code `reasoning_tokens` is
# definitionally inside `output_tokens` (F10). Byte-identical to the P5.7 fixture.
CLAUDE_REASONING_INCLUSION_BASIS = {
    "provider": "claude-code",
    "contained_field": "reasoning_tokens",
    "containing_field": "output_tokens",
    "evidence_ref": ("findings/P5.4-metric-surface-gap-2026-08-06.md F10: the claude-code result "
                      "record exports usage.{input_tokens,cache_read_input_tokens,output_tokens} "
                      "and no separate reasoning field; extended-thinking tokens are billed and "
                      "reported inside output_tokens"),
}


def zero_coordinator_envelope() -> dict:
    """A measured all-zero `coordinator` envelope plus its mandatory `zero_bases` entry."""
    return {
        "coordinator": {field: 0 for field in METRIC_FIELDS},
        "zero_bases": {"coordinator": dict(_COORDINATOR_ZERO_BASIS)},
    }


def extract_metric(source: dict | None, key: str, *, reason: str) -> tuple[int | None, str | None]:
    """Extraction only: a present non-negative int, or `(None, reason)` — never a guess."""
    if isinstance(source, dict):
        value = source.get(key)
        if not isinstance(value, bool) and isinstance(value, int) and value >= 0:
            return value, None
    return None, reason


def usd_to_cost_microunits(value: object) -> int | None:
    """Deterministic `Decimal`/`ROUND_HALF_UP` conversion; never binary float arithmetic."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    quantized = (decimal.Decimal(str(value)) * decimal.Decimal(1_000_000)).quantize(
        decimal.Decimal(1), rounding=decimal.ROUND_HALF_UP)
    return int(quantized)


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
