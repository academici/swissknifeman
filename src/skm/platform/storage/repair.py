"""Select repair candidates and report their outcomes."""

from collections.abc import Iterable
from types import MappingProxyType
from typing import Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.platform.generated.results import RepairStorageSafeResult
from skm.platform.storage.verify import CATALOG, Finding

ACTIONS: Final = MappingProxyType(
    {
        "STAGED_EXPIRED": "artifacts.expire_staged_blobs",
        "OUTBOX_DEAD": "platform.retry_outbox",
    }
)


def selected_codes(requested: tuple[str, ...] | None) -> frozenset[str]:
    codes = frozenset(CATALOG if requested is None else requested)
    if codes.difference(CATALOG):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Unsupported storage finding code")
    return codes


def repair_report(
    findings: Iterable[Finding],
    repaired: frozenset[tuple[str, str]],
    *,
    dry_run: bool,
) -> RepairStorageSafeResult:
    applied: list[JsonObject] = []
    skipped: list[JsonObject] = []
    for item in findings:
        row = {"code": item.code, "target": item.target.to_json()}
        if (item.code, item.target.id) in repaired:
            applied.append({**row, "action": ACTIONS[item.code]})
        else:
            reason = "manual_repair_required"
            if item.repairability == "safe":
                reason = "dry_run" if dry_run else "state_changed"
            skipped.append({**row, "reason": reason})
    return RepairStorageSafeResult.from_json({"repaired": applied, "skipped": skipped})
