"""Value and cross-key validation of resolved settings (settings §B.6 steps 6-7, §B.8.3).

``validate_value`` checks one value against the schema of its key. Section validators run on the *candidate
slice* of their section: a read-only mapping that holds exactly the keys the validator declares, with ``None``
for an absent nullable key. Validation is fail-closed: a validator whose input key is itself invalid (or not
resolvable in this chain) cannot prove its rule, so the validator's other keys are reported as blocked
instead of being trusted; a callback that raises or returns something other than text or ``None`` counts as
a failed rule. Nothing here raises for invalid configuration; findings are returned to the resolver.
"""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final, cast

from skm.kernel.json_types import JsonValue
from skm.platform.schema.findings import SchemaIssue

from .keys import MISSING, Missing, Sensitivity
from .registry import SectionValidatorFn, SettingsRegistry

__all__ = [
    "SectionValidatorFn",
    "ValidatorFinding",
    "check_section_validators",
    "run_section_validators",
    "validate_value",
]

_MESSAGE_LIMIT: Final = 500
_SECRET_MESSAGE: Final = "secret_ref_required: the value must be a secret:// reference (value not shown)"


@dataclass(frozen=True, slots=True)
class ValidatorFinding:
    """A section validator that failed (``message``) or could not run (``blocked_by`` its invalid inputs)."""

    validator: str
    keys: tuple[str, ...]
    message: str
    blocked_by: tuple[str, ...] = ()


def validate_value(
    registry: SettingsRegistry, key: str, value: JsonValue | Missing
) -> tuple[SchemaIssue, ...]:
    """Schema findings of ``value`` for ``key`` (``CONFIG_UNKNOWN_KEY`` for an unknown key).

    The registry holds the key schema compiled once at build time, so it is passed instead of the bare
    ``KeySpec`` of §B.8.3. ``MISSING`` has no findings when the key is nullable and one ``missing``
    finding otherwise; a JSON ``null`` is a value and is checked against the schema like any other.
    """
    spec = registry.spec(key)
    if isinstance(value, Missing):
        if spec.nullable:
            return ()
        return (SchemaIssue(pointer="", schema_pointer="", code="missing", message="a value is required"),)
    issues = registry.value_issues(key, value)
    if spec.sensitivity is Sensitivity.SECRET:
        # R6: a rejected secret value is never quoted; the schema validator's message would repeat it
        return tuple(replace(issue, message=_SECRET_MESSAGE) for issue in issues)
    return issues


def _bounded(text: str) -> str:
    return text if len(text) <= _MESSAGE_LIMIT else text[: _MESSAGE_LIMIT - 1] + "…"


def _call(validator: SectionValidatorFn, values: Mapping[str, JsonValue]) -> str | None:
    """The validator's message; an exception or a non-text result is a failed rule (fail closed)."""
    try:
        result = cast("object", validator(values))
    except Exception as exc:  # noqa: BLE001 - a broken callback must not make the whole config unreadable
        return _bounded(f"validator failed: {type(exc).__name__}: {exc}")
    if result is None:
        return None
    if isinstance(result, str):
        return _bounded(result or "validator rule is violated")
    return f"validator returned {type(result).__name__}, not a message or None"


def _unavailable(
    registry: SettingsRegistry,
    key: str,
    values: Mapping[str, JsonValue | Missing],
    unavailable: Collection[str],
) -> bool:
    if key in unavailable or key not in values:
        return True
    return values[key] is MISSING and not registry.spec(key).nullable


def check_section_validators(
    registry: SettingsRegistry,
    values: Mapping[str, JsonValue | Missing],
    sections: Iterable[str],
    *,
    unavailable: Collection[str] = (),
) -> tuple[ValidatorFinding, ...]:
    """Run the validators of ``sections`` on their candidate slices.

    ``values`` holds the candidate value of every valid key (``MISSING`` for an absent nullable key);
    ``unavailable`` names keys that are invalid. A validator key in neither (another chain or not resolved),
    or ``MISSING`` for a key that is not nullable, is unavailable too: only a nullable absence reaches the
    callback as ``None``. Such a validator does not run: it yields a finding ``blocked_by`` those keys.
    """
    findings: list[ValidatorFinding] = []
    for section_id in dict.fromkeys(sections):
        for declared in registry.section(section_id).validators:
            blocked = tuple(key for key in declared.keys if _unavailable(registry, key, values, unavailable))
            if blocked:
                findings.append(
                    ValidatorFinding(
                        validator=declared.id,
                        keys=declared.keys,
                        message=f"cannot check {declared.id}: unavailable input {', '.join(blocked)}",
                        blocked_by=blocked,
                    )
                )
                continue
            candidate: dict[str, JsonValue] = {}
            for key in declared.keys:
                value = values[key]
                candidate[key] = None if value is MISSING else cast("JsonValue", value)
            message = _call(registry.validator(declared.id), MappingProxyType(candidate))
            if message is not None:
                findings.append(ValidatorFinding(validator=declared.id, keys=declared.keys, message=message))
    return tuple(findings)


def run_section_validators(
    registry: SettingsRegistry, values: Mapping[str, JsonValue], sections: Iterable[str]
) -> tuple[tuple[str, str], ...]:
    """``(validator_id, message)`` of every failed validator of ``sections`` (§B.8.3).

    ``values`` are valid key values. An absent nullable key reaches the validator as ``None``; an absent
    required key blocks the validator, which is reported as failed with the unavailable keys.
    """
    section_ids = tuple(dict.fromkeys(sections))
    candidate: dict[str, JsonValue | Missing] = {}
    for section_id in section_ids:
        for declared in registry.section(section_id).validators:
            for key in declared.keys:
                candidate[key] = values.get(key, MISSING)
    return tuple(
        (finding.validator, finding.message)
        for finding in check_section_validators(registry, candidate, section_ids)
    )
