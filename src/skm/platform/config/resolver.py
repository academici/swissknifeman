"""Pure resolver: layers of one scope chain → ``EffectiveConfig`` (settings §B.6).

``resolve`` receives already loaded layers in the fixed order of §B.3 and checks that order (a wrong order is
a programming error: ``ValueError``). For every key of the chain it collects the contributions, folds them
(``merge.fold``), expands paths, validates the result against the key schema and then runs the cross-key
validators of each section on the candidate slice of valid values. Invalid configuration never raises here:
it is recorded per key with its provenance, so one invalid section fails closed on read while every other
section stays readable. Only a request for an unknown key or a key of the other chain raises.

Contributions of unknown keys are ignored with ``CONFIG_UNKNOWN_KEY``; contributions of a deprecated key move
to its replacement with ``CONFIG_DEPRECATED_KEY`` (an entry of the replacement in the same layer wins).
Keys of the other chain are skipped: silently at a level both chains have (``default``, ``pack``,
``instance``, ``invocation``), with ``CONFIG_SCOPE_NOT_ALLOWED`` at a level their chain cannot have (a host
key in a project layer), so misplaced data is not hidden.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from typing import Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Diagnostic, Severity

from .effective import EffectiveConfig, InvalidKey, InvalidReason, Provenance, values_digest
from .keys import (
    CHAIN_LEVELS,
    STORED_LEVELS,
    Chain,
    KeySpec,
    Level,
    Missing,
    Sensitivity,
)
from .layers import Contribution, Layer, LayerRef
from .merge import KeyResolution, fold
from .registry import SettingsRegistry
from .scopes import ScopeChain
from .validation import check_section_validators, validate_value

__all__ = ["resolve"]

_INVOCATION_ORDER: Final = ("env", "config-file", "cli")


def resolve(
    registry: SettingsRegistry,
    chain: ScopeChain,
    layers: Sequence[Layer],
    *,
    keys: Iterable[str] | None = None,
    generation: int,
    pack_generation: int,
    expand: Callable[[str], str] | None = None,
) -> EffectiveConfig:
    """Resolve ``keys`` (default: every key of ``chain.kind``) from ``layers`` (§B.6 steps 1-9).

    ``expand`` rewrites the strings of ``path`` keys (``~``, ``${state_dir}``); the loader passes it.
    """
    specs = _selected(registry, chain, keys)
    _check_layers(chain, layers)
    collector = _Collector(registry, chain.kind, (spec.key for spec in specs))
    for layer in layers:
        collector.add(layer)
    diagnostics = collector.diagnostics()

    resolutions: dict[str, KeyResolution] = {}
    invalid: dict[str, InvalidKey] = {}
    for spec in specs:
        resolution = fold(spec, collector.contributions[spec.key])
        resolution, problem = _final(registry, spec, resolution, expand)
        resolutions[spec.key] = resolution
        if problem is not None:
            invalid[spec.key] = problem

    _run_validators(registry, specs, resolutions, invalid)

    for spec in specs:
        diagnostics.extend(resolutions[spec.key].diagnostics)
        problem = invalid.get(spec.key)
        if problem is not None:
            diagnostics.append(_invalid_diagnostic(problem))
    values: dict[str, JsonValue] = {}
    for spec in specs:
        value = resolutions[spec.key].value
        if spec.key not in invalid and not isinstance(value, Missing):
            values[spec.key] = value
    return EffectiveConfig(
        registry=registry,
        chain=chain,
        resolutions=resolutions,
        invalid=invalid,
        diagnostics=tuple(diagnostics),
        generation=generation,
        pack_generation=pack_generation,
        digest=values_digest(values),
    )


# ---------------------------------------------------------------------------------------------------------
# Step 1: keys


def _selected(
    registry: SettingsRegistry, chain: ScopeChain, keys: Iterable[str] | None
) -> tuple[KeySpec, ...]:
    """Specs to resolve, in registry order. A requested key brings every key of the validators that check it,
    so a validator always sees its whole candidate slice."""
    ordered = registry.keys(chain=chain.kind)
    if keys is None:
        return ordered
    pending: list[str] = []
    for key in keys:
        spec = registry.spec(key)  # CONFIG_UNKNOWN_KEY
        if spec.chain is not chain.kind:
            raise ValidationFailed(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
                f"settings key {key!r} belongs to the {spec.chain.value} chain, not {chain.kind.value}",
                details={"key": key, "chain": chain.kind.value, "key_chain": spec.chain.value},
            )
        pending.append(key)
    wanted: set[str] = set()
    while pending:
        key = pending.pop()
        if key in wanted:
            continue
        wanted.add(key)
        for declared in registry.section(registry.spec(key).section).validators:
            if key in declared.keys:
                pending.extend(other for other in declared.keys if registry.spec(other).chain is chain.kind)
    return tuple(spec for spec in ordered if spec.key in wanted)


# ---------------------------------------------------------------------------------------------------------
# Step 2: layer order (§B.3)


def _invocation_rank(ref: LayerRef) -> int:
    source = cast("str", ref.source)
    return _INVOCATION_ORDER.index("config-file" if source.startswith("config-file:") else source)


def _check_contributions(layer: Layer) -> None:
    ref = layer.ref
    for key, contribution in layer.contributions.items():
        own = contribution.layer
        if (own.scope_id, own.pack_id, own.source) != (ref.scope_id, ref.pack_id, ref.source):
            raise ValueError(f"{key}: contribution of {own.display} does not belong to layer {ref.display}")


def _check_layers(chain: ScopeChain, layers: Sequence[Layer]) -> None:
    """``default`` → ``pack`` (priority ascending, ties by id) → exactly ``chain.scopes`` → ``invocation``
    (env → ``--config`` files → ``--set``)."""
    phase = 0  # 0 default, 1 pack, 2 stored, 3 invocation
    packs: list[tuple[int, str]] = []
    stored: list[LayerRef] = []
    invocation = 0
    for index, layer in enumerate(layers):
        ref = layer.ref
        level = ref.level
        if level is Level.DEFAULT:
            if index != 0:
                raise ValueError("the default layer comes first and only once")
            current = 0
        elif level is Level.PACK:
            current = 1
            order = (ref.pack_priority or 0, cast("str", ref.pack_id))
            if packs and order <= packs[-1]:
                raise ValueError(f"pack {ref.display}: packs go by priority ascending, then id, each once")
            packs.append(order)
        elif level in STORED_LEVELS:
            current = 2
            stored.append(ref)
        elif level is Level.INVOCATION:
            current = 3
            rank = _invocation_rank(ref)
            if rank < invocation:
                raise ValueError(f"invocation {ref.display}: env, then --config files, then --set")
            invocation = rank
        else:
            raise ValueError(f"level {level.value!r} is provenance only and never a resolver layer")
        if current < phase:
            raise ValueError(f"layer {ref.display} is out of order: default, pack, stored, invocation")
        phase = current
        _check_contributions(layer)
    expected = [(scope.level, scope.scope_id) for scope in chain.scopes]
    if [(ref.level, ref.scope_id) for ref in stored] != expected:
        raise ValueError(
            "stored layers must be exactly the chain scopes, farthest first: "
            + ", ".join(f"{level.value}:{scope_id}" for level, scope_id in expected)
        )


# ---------------------------------------------------------------------------------------------------------
# Step 3: contributions per key


class _Collector:
    def __init__(self, registry: SettingsRegistry, kind: Chain, selected: Iterable[str]) -> None:
        self.registry = registry
        self.kind = kind
        self.contributions: dict[str, list[Contribution]] = {key: [] for key in selected}
        self.unknown: dict[str, list[LayerRef]] = {}
        self.misplaced: dict[str, list[LayerRef]] = {}  # other-chain key at a level its chain lacks
        self.deprecated: dict[str, list[tuple[LayerRef, str, bool]]] = {}  # alias → (layer, target, applied)

    def target(self, key: str) -> str:
        """The live key a deprecated key stands for, following replacements (a cycle stops the walk)."""
        seen = {key}
        spec = self.registry.spec(key)
        while spec.deprecated is not None and spec.deprecated.replacement is not None:
            following = spec.deprecated.replacement
            if following in seen:
                break
            seen.add(following)
            key, spec = following, self.registry.spec(following)
        return key

    def add(self, layer: Layer) -> None:
        for key, contribution in layer.contributions.items():
            spec = self.registry.find(key)
            if spec is None:
                self.unknown.setdefault(key, []).append(contribution.layer)
                continue
            # the schema default belongs to the key itself; only entries of a deprecated key move
            alias = spec.deprecated is not None and contribution.op != "default"
            target = self.target(key) if alias else key
            if target not in self.contributions:
                owner = self.registry.spec(target).chain
                if owner is not self.kind and contribution.layer.level not in CHAIN_LEVELS[owner]:
                    self.misplaced.setdefault(key, []).append(contribution.layer)
                continue  # a key of the other chain, or not requested
            if alias:
                applied = target == key or target not in layer.contributions
                self.deprecated.setdefault(key, []).append((contribution.layer, target, applied))
                if not applied:
                    continue  # the replacement's own entry in the same layer wins
            self.contributions[target].append(contribution)

    def diagnostics(self) -> list[Diagnostic]:
        found = [
            Diagnostic(
                code="CONFIG_UNKNOWN_KEY",
                message=f"{len(refs)} contribution(s) of unknown key {key!r} ignored",
                severity=Severity.WARNING,
                target=key,
                details={"layers": [ref.to_json() for ref in refs]},
            )
            for key, refs in self.unknown.items()
        ]
        found.extend(
            Diagnostic(
                code="CONFIG_SCOPE_NOT_ALLOWED",
                message=f"{len(refs)} contribution(s) of {self.registry.spec(key).chain.value}-chain key "
                f"{key!r} ignored at a level outside its chain",
                severity=Severity.WARNING,
                target=key,
                details={"layers": [ref.to_json() for ref in refs]},
            )
            for key, refs in self.misplaced.items()
        )
        for key, entries in self.deprecated.items():
            deprecation = self.registry.spec(key).deprecated
            since = "" if deprecation is None else deprecation.since
            target = entries[0][1]
            moved = target != key
            found.append(
                Diagnostic(
                    code="CONFIG_DEPRECATED_KEY",
                    message=f"key {key!r} is deprecated since {since}"
                    + (f"; its contributions apply to {target!r}" if moved else ""),
                    severity=Severity.WARNING,
                    target=key,
                    details={
                        "replacement": target if moved else None,
                        "layers": [ref.to_json() for ref, _target, applied in entries if applied],
                        "ignored": [ref.to_json() for ref, _target, applied in entries if not applied],
                    },
                )
            )
        return found


# ---------------------------------------------------------------------------------------------------------
# Steps 5-6: paths and the final schema


def _expanded(value: JsonValue, expand: Callable[[str], str]) -> JsonValue:
    if isinstance(value, str):
        return expand(value)
    if isinstance(value, list):
        return [expand(item) if isinstance(item, str) else item for item in value]
    if isinstance(value, dict):
        return {key: expand(item) if isinstance(item, str) else item for key, item in value.items()}
    return value


def _invalid(
    spec: KeySpec,
    resolution: KeyResolution,
    reason: InvalidReason,
    message: str,
    *,
    issues: Sequence[dict[str, JsonValue]] = (),
    validator: str | None = None,
    blocked_by: Sequence[str] = (),
) -> InvalidKey:
    return InvalidKey(
        key=spec.key,
        reason=reason,
        message=message,
        provenance=Provenance.of(resolution),
        issues=tuple(issues),
        validator=validator,
        blocked_by=tuple(blocked_by),
        redact=spec.sensitivity is Sensitivity.SECRET,
    )


def _final(
    registry: SettingsRegistry,
    spec: KeySpec,
    resolution: KeyResolution,
    expand: Callable[[str], str] | None,
) -> tuple[KeyResolution, InvalidKey | None]:
    value = resolution.value
    if isinstance(value, Missing):
        if spec.nullable:
            return resolution, None
        return resolution, _invalid(spec, resolution, "missing", "no value and no default for a required key")
    if spec.path and expand is not None:
        try:
            resolution = replace(resolution, value=_expanded(value, expand))
        except (ValueError, TypeError, KeyError, OSError) as exc:
            issue: dict[str, JsonValue] = {
                "pointer": "",
                "schema_pointer": "",
                "code": "path",
                "message": f"path expansion failed: {type(exc).__name__}",
            }
            return resolution, _invalid(spec, resolution, "schema", "path expansion failed", issues=[issue])
    issues = validate_value(registry, spec.key, resolution.value)
    if issues:
        found = [issue.to_json() for issue in issues]
        return resolution, _invalid(spec, resolution, "schema", issues[0].message, issues=found)
    return resolution, None


# ---------------------------------------------------------------------------------------------------------
# Step 7: cross-key validators on the candidate slice


def _run_validators(
    registry: SettingsRegistry,
    specs: Sequence[KeySpec],
    resolutions: dict[str, KeyResolution],
    invalid: dict[str, InvalidKey],
) -> None:
    candidate = {key: res.value for key, res in resolutions.items() if key not in invalid}
    sections = dict.fromkeys(spec.section for spec in specs)
    findings = check_section_validators(registry, candidate, sections, unavailable=frozenset(invalid))
    by_key = {spec.key: spec for spec in specs}
    for finding in findings:
        for key in finding.keys:
            spec = by_key.get(key)
            if spec is None or key in invalid or key in finding.blocked_by:
                continue  # not resolved here, or already invalid for its own reason
            invalid[key] = _invalid(
                spec,
                resolutions[key],
                "validator",
                finding.message,
                validator=finding.validator,
                blocked_by=finding.blocked_by,
            )


def _invalid_diagnostic(problem: InvalidKey) -> Diagnostic:
    details: dict[str, JsonValue] = {"reason": problem.reason}
    if problem.validator is not None:
        details["validator"] = problem.validator
    if problem.blocked_by:
        details["blocked_by"] = list(problem.blocked_by)
    return Diagnostic(
        code="CONFIG_INVALID",
        message=f"{problem.key}: {problem.message}",
        severity=Severity.ERROR,
        target=problem.key,
        details=details,
    )
