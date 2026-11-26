"""Configured-state findings for an already authorized, supplied scope inventory.

This is an internal engine entrypoint, not a facade or an authorization boundary. The caller supplies a
complete inventory for one instance, including empty scopes, and ports from the same read-only UoW after
authorizing that coverage. No inventory lookup, nested UoW, host IO, secret resolution, invocation layer,
run snapshot or process snapshot is used here. Restart observations belong to the serving-loader provider;
this slice explicitly reports that observation as unknown, never as an empty pending set.
"""

import json
from collections.abc import Iterable, Mapping
from contextlib import suppress
from typing import Final
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.generated.documents import CheckResult, CheckResultDetails
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import CheckStatus
from skm.kernel.scopes import ALLOWED_PARENTS, ScopeKind, ScopeRecord

from .effective import EffectiveConfig
from .keys import Chain, Level
from .loader import ConfigLoader
from .registry import SettingsRegistry
from .scopes import ScopeRef
from .store import ConfigStore, PackConfigSource, ScopeTree

__all__ = ["diagnose_config"]

_MESSAGES: Final[Mapping[str, str]] = {
    "CONFIG_UNKNOWN_KEY": "Unknown configuration key; contribution ignored.",
    "CONFIG_DEPRECATED_KEY": "Deprecated configuration key is stored.",
    "CONFIG_SCOPE_NOT_ALLOWED": "Configuration contribution or lock is disallowed for this key or level.",
    "CONFIG_PACK_NOT_ALLOWED": "Pack contribution is disallowed for this key.",
    "CONFIG_OVERRIDE_NOT_ALLOWED": "Configuration override is disallowed for this key.",
    "CONFIG_LOCKED": "Stored contribution below an ancestor lock is ignored.",
    "CONFIG_OP_NOT_ALLOWED": "Configuration operation is disallowed for this key.",
    "CONFIG_NARROWING_VIOLATION": "Configuration contribution would widen an inherited limit.",
    "CONFIG_INVALID": "Configured value or section validator is invalid.",
}
_REG_CODES: Final = frozenset(f"REG-{index:02}" for index in range(1, 21))


def _identifier(value: str) -> str:
    # Identifiers are allowed, arbitrary messages and values are not. Bound even corrupt unknown keys.
    return value[:200]


def _finding(
    code: str, status: CheckStatus, message: str, target: str, metadata: Mapping[str, JsonValue]
) -> CheckResult:
    return CheckResult(
        id=f"config.{code}",
        status=status,
        message=message,
        hint=None,
        details=CheckResultDetails(
            target=target,
            detail=json.dumps(dict(metadata), sort_keys=True, ensure_ascii=True, separators=(",", ":")),
            path=None,
        ),
    )


def _layer(value: JsonValue) -> dict[str, JsonValue]:
    """Project only identifiers from engine layer metadata; never copy arbitrary diagnostic details."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, JsonValue] = {}
    level = value.get("level")
    if isinstance(level, str) and level in {item.value for item in Level}:
        result["level"] = level
    for field in ("scope_id", "entry_id"):
        item = value.get(field)
        if isinstance(item, str):
            with suppress(ValueError):
                result[field] = str(UUID(item))
    pack = value.get("pack_id")
    if isinstance(pack, str):
        result["pack_id"] = _identifier(pack)
    return result


def _registry_failure(error: InternalError) -> tuple[CheckResult, ...]:
    if error.code is not ErrorCode.CONFIG_REGISTRY_INVALID:
        raise error
    findings = [
        _finding(
            "registry",
            "fail",
            "Settings registry is invalid; configured-state checks were not run.",
            "registry",
            {"code": "CONFIG_REGISTRY_INVALID", "configured_state": "not_checked"},
        )
    ]
    problems = error.details.get("problems")
    for problem in problems if isinstance(problems, list) else ():
        if not isinstance(problem, dict):
            continue
        code = problem.get("code")
        metadata: dict[str, JsonValue] = {
            "code": code if isinstance(code, str) and code in _REG_CODES else "REG-UNKNOWN"
        }
        for field in ("section", "key"):
            item = problem.get(field)
            if isinstance(item, str):
                metadata[field] = _identifier(item)
        findings.append(_finding("registry", "fail", "Settings registry rule failed.", "registry", metadata))
    return tuple(findings)


def _inventory(inventory: Iterable[ScopeRecord], scopes: ScopeTree) -> tuple[ScopeRecord, ...]:
    records = tuple(inventory)
    by_id = {record.id: record for record in records}
    roots = [record for record in records if record.kind is ScopeKind.INSTANCE]
    if len(by_id) != len(records) or len(roots) != 1:
        raise ValueError("diagnostics require unique scopes and exactly one instance")
    if scopes.instance_scope() != ScopeRef(Level.INSTANCE, roots[0].id):
        raise ValueError("diagnostic inventory and scope tree belong to different instances")
    for record in records:
        parent = by_id.get(record.parent_id) if record.parent_id is not None else None
        parent_kind = parent.kind if parent is not None else None
        if (record.parent_id is not None and parent is None) or parent_kind not in ALLOWED_PARENTS[
            record.kind
        ]:
            raise ValueError("diagnostic inventory must include each scope's canonical ancestors")
    return tuple(sorted(records, key=lambda item: (item.kind.value, item.id)))


def _configured_findings(config: EffectiveConfig) -> tuple[CheckResult, ...]:
    target = f"{config.chain.target.level.value}:{config.chain.target.scope_id}"
    context: dict[str, JsonValue] = {
        "chain": config.chain.kind.value,
        "generation": config.generation,
        "pack_generation": config.pack_generation,
    }
    findings: list[CheckResult] = []
    for diagnostic in config.diagnostics:
        code = diagnostic.code if diagnostic.code in _MESSAGES else "CONFIG_DIAGNOSTIC_UNKNOWN"
        metadata = dict(context)
        metadata["code"] = code
        if diagnostic.target is not None:
            metadata["key"] = _identifier(diagnostic.target)
        # A rejected pack contribution (settings §B.4) names its pack at the top level, not in layers.
        # It is an engine-owned source rejection: keep its pack origin and never join it to the effective
        # key's InvalidKey, which may fail independently under the same code and key.
        pack = diagnostic.details.get("pack_id")
        rejected_pack = isinstance(pack, str)
        if rejected_pack:
            metadata["contributions"] = [{"level": Level.PACK.value, "pack_id": _identifier(pack)}]
        layers = diagnostic.details.get("layers")
        if isinstance(layers, list):
            metadata["contributions"] = [projected for item in layers if (projected := _layer(item))]
        ignored = diagnostic.details.get("ignored")
        if isinstance(ignored, list):
            metadata["ignored"] = [projected for item in ignored if (projected := _layer(item))]
        locked = _layer(diagnostic.details.get("layer"))
        if code == "CONFIG_LOCKED" and locked:
            metadata["locked_by"] = locked
        problem = (
            config.invalid_keys().get(diagnostic.target or "")
            if code == "CONFIG_INVALID" and not rejected_pack
            else None
        )
        if problem is not None:
            metadata["reason"] = problem.reason
            if problem.validator is not None:
                metadata["validator"] = _identifier(problem.validator)
            if problem.blocked_by:
                metadata["blocked_by"] = [_identifier(key) for key in problem.blocked_by]
            metadata["contributions"] = [
                _layer(item.contribution.layer.to_json()) for item in problem.provenance.trace
            ]
        # Registry/engine severity is known here. A rejected pack value remains a warning; an invalid
        # configured key or an unrecognized diagnostic fails closed. No callback controls this severity.
        status: CheckStatus = "fail" if problem is not None or code == "CONFIG_DIAGNOSTIC_UNKNOWN" else "warn"
        findings.append(
            _finding(
                code, status, _MESSAGES.get(code, "Unrecognized configuration diagnostic."), target, metadata
            )
        )
    if not findings:
        findings.append(
            _finding(
                "configured_state", "ok", "Configured state is valid for this scope chain.", target, context
            )
        )
    return tuple(findings)


def _stored_lock_findings(
    registry: SettingsRegistry, record: ScopeRecord, store: ConfigStore
) -> tuple[CheckResult, ...]:
    # The resolver diagnoses invalid lock levels and rows below locks. R9 also forbids locks on
    # non-lockable keys; inspect the stored key itself, before a deprecated alias loses its identity.
    findings: list[CheckResult] = []
    rows = store.entries_for((record.id,)).get(record.id, {})
    for key, row in sorted(rows.items()):
        spec = registry.find(key)
        if row.locked and spec is not None and not spec.lockable:
            findings.append(
                _finding(
                    "CONFIG_SCOPE_NOT_ALLOWED",
                    "warn",
                    _MESSAGES["CONFIG_SCOPE_NOT_ALLOWED"],
                    f"{record.kind.value}:{record.id}",
                    {
                        "code": "CONFIG_SCOPE_NOT_ALLOWED",
                        "reason": "key_not_lockable",
                        "key": _identifier(key),
                        "contributions": [
                            {
                                "scope_id": str(record.id),
                                "level": record.kind.value,
                                "entry_id": str(row.entry_id),
                            }
                        ],
                    },
                )
            )
    return tuple(findings)


def diagnose_config(
    *,
    registry: SettingsRegistry | InternalError,
    inventory: Iterable[ScopeRecord],
    store: ConfigStore,
    scopes: ScopeTree,
    packs: PackConfigSource,
) -> tuple[CheckResult, ...]:
    """Check configured state only, using caller-authorized inventory and same-UoW owner ports.

    ``registry`` may be the original ``CONFIG_REGISTRY_INVALID`` startup exception, whose REG codes and
    identifiers are projected without retrying the build or pretending downstream checks ran. Other
    exceptions propagate. An incomplete, duplicate or cross-instance inventory is rejected. Supplying
    inventory is never evidence of permission: an instance-wide caller must authorize config.read at
    instance before acquiring it. This function neither authorizes nor certifies inventory completeness.
    """
    if isinstance(registry, InternalError):
        return _registry_failure(registry)
    records = _inventory(inventory, scopes)
    by_id = {record.id: record for record in records}
    loader = ConfigLoader(registry, packs, cache_size=0)
    findings = [_finding("registry", "ok", "Settings registry passed REG checks.", "registry", {})]
    for record in records:
        target = ScopeRef(Level(record.kind.value), record.id)
        expected = [record.id]
        parent_id = record.parent_id
        while parent_id is not None:
            expected.append(parent_id)
            parent_id = by_id[parent_id].parent_id
        expected_ids = tuple(reversed(expected))
        kinds = (
            (Chain.WORK, Chain.HOST)
            if record.kind is ScopeKind.INSTANCE
            else (Chain.HOST if record.kind is ScopeKind.HOST else Chain.WORK,)
        )
        for kind in kinds:
            # Check inventory coverage before loading values or invoking validators. The caller's
            # repeatable-read UoW keeps this ancestry stable for the loader's own chain lookup.
            chain = scopes.chain_for(target, kind)
            if chain.kind is not kind or chain.target != target or chain.ids() != expected_ids:
                raise ValueError("diagnostic inventory and scope tree have different ancestry")
            config = loader.effective(store, scopes, target, kind)
            if config.chain.ids() != expected_ids:
                raise ValueError("diagnostic inventory and scope tree have different ancestry")
            findings.extend(_configured_findings(config))
        findings.extend(_stored_lock_findings(registry, record, store))
    findings.append(
        _finding(
            "restart_pending",
            "warn",
            "Current-process restart-pending state is unknown; baseline not observed.",
            "current_process",
            {"state": "unknown", "reason": "serving_loader_observation_required"},
        )
    )
    return tuple(findings)
