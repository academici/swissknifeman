"""Resolved configuration of one scope chain (settings §B.7); built by ``resolver.resolve``.

Invalid keys fail closed and lazily: ``resolve`` never raises for them, it records an ``InvalidKey`` with its
provenance. Reading an invalid key (``get``/``present``) or a section that holds one (``section``) raises
``ValidationFailed(CONFIG_INVALID)``; every other key and section stays readable. ``MISSING`` (no value; a
nullable key without contributions) differs from a JSON ``null`` value: ``present`` tells them apart, the
digest includes ``null`` and omits ``MISSING``.

The digest is the tagged SHA-256 of canonical JSON v1 ``{key: value}`` over valid present keys. Canonical
JSON refuses floats, so every float is encoded as its ``repr`` string first (settings §A.11, §B.6 step 8:
``0.5`` → ``"0.5"``, ``20.0`` → ``"20.0"``); integers, booleans and SecretRef strings stay as they are.
Frozen digests additionally bind the schema and the versioned registry descriptor (§B.7).
"""

import math
import threading
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol, cast, override
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.outcomes import Diagnostic, Severity
from skm.platform.jsonc.digest import digest
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator

from .generated import FrozenConfigDoc
from .keys import MISSING, Chain, Level, Missing, Reload, Sensitivity, copy_json, freeze_json
from .layers import Contribution, LayerRef
from .merge import ContributionTrace, KeyResolution
from .registry import SettingsRegistry
from .scopes import ScopeChain, ScopeRef
from .secrets import SecretRef
from .validation import check_section_validators

__all__ = [
    "EffectiveConfig",
    "FrozenConfig",
    "InvalidKey",
    "InvalidReason",
    "ProcessConfig",
    "Provenance",
    "normalize_numbers",
    "registry_descriptor_digest",
    "safe_value",
    "values_digest",
]

type InvalidReason = Literal["missing", "schema", "validator", "frozen_registry_incompatible"]

_REASONS: Final = frozenset({"missing", "schema", "validator", "frozen_registry_incompatible"})
FROZEN_SCHEMA: Final = "urn:skm:config:frozen:v1"
# Bump a component whenever its interpretation changes. A schema digest alone cannot identify code semantics.
_ALGORITHMS: Final = {"merge": "settings-B.5-v1", "normalization": "float-repr-v1", "snapshot": "v1"}


def registry_descriptor_digest(registry: SettingsRegistry) -> str:
    """Bind section schemas/defaults, referenced value schemas, enabled owners and algorithm versions."""
    return digest(
        {
            "schemas": registry.digest,
            "algorithms": _ALGORITHMS,
            "owners": sorted({section.owner for section in registry.sections()}),
            "value_schemas": {
                spec.key: normalize_numbers(dict(spec.value_schema))
                for spec in registry.keys()  # noqa: SIM118
            },
            "views": {
                section.id: getattr(section.view, "SCHEMA_DIGEST", "") for section in registry.sections()
            },
        }
    )


def _frozen_digest(registry_digest: str, values: Mapping[str, JsonValue]) -> str:
    return digest(
        {
            "schema": FROZEN_SCHEMA,
            "registry_digest": registry_digest,
            "values": {key: normalize_numbers(value) for key, value in values.items()},
        }
    )


@lru_cache(maxsize=1)
def _snapshot_validator() -> SchemaValidator:
    return SchemaRegistry.load_default().validator(FROZEN_SCHEMA)


def _snapshot_invalid(reason: str = "frozen_registry_incompatible") -> ValidationFailed:
    # Never include unvalidated snapshot values or SecretRef paths in an error.
    return ValidationFailed(
        ErrorCode.CONFIG_INVALID, "run configuration snapshot cannot be used", details={"reason": reason}
    )


@dataclass(frozen=True, slots=True, repr=False)
class FrozenConfig:
    """Original run data. Deserialization validates integrity, independently of executable compatibility.

    Unknown descriptors remain readable by diagnostic explain; only ``require_compatible`` admits execution.
    No defaults are ever added to a saved document. Documents returned to callers are independent copies.
    """

    run_scope_id: UUID
    generation: int
    pack_generation: int
    registry_digest: str
    digest: str
    values: Mapping[str, JsonValue]
    provenance: Mapping[str, str]

    def __post_init__(self) -> None:
        try:
            if not isinstance(cast("object", self.run_scope_id), UUID):
                raise _snapshot_invalid("frozen_document_invalid")
            values = {key: freeze_json(value, key) for key, value in self.values.items()}
            provenance = dict(self.provenance)
            object.__setattr__(self, "values", MappingProxyType(values))
            object.__setattr__(self, "provenance", MappingProxyType(provenance))
            if _snapshot_validator().issues(self.to_document()):
                raise _snapshot_invalid("frozen_document_invalid")
            if self.digest != _frozen_digest(self.registry_digest, values):
                raise _snapshot_invalid("frozen_digest_mismatch")
        except (TypeError, ValueError, AttributeError) as exc:
            raise _snapshot_invalid("frozen_document_invalid") from exc

    def to_document(self) -> FrozenConfigDoc:
        return {
            "schema": FROZEN_SCHEMA,
            "run_scope_id": str(self.run_scope_id),
            "generation": self.generation,
            "pack_generation": self.pack_generation,
            "registry_digest": self.registry_digest,
            "digest": self.digest,
            "values": {key: copy_json(value, key) for key, value in self.values.items()},
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_document(cls, doc: Mapping[str, object]) -> "FrozenConfig":
        if _snapshot_validator().issues(doc):
            raise _snapshot_invalid("frozen_document_invalid")
        return cls(
            run_scope_id=UUID(cast("str", doc["run_scope_id"])),
            generation=cast("int", doc["generation"]),
            pack_generation=cast("int", doc["pack_generation"]),
            registry_digest=cast("str", doc["registry_digest"]),
            digest=cast("str", doc["digest"]),
            values=cast("Mapping[str, JsonValue]", doc["values"]),
            provenance=cast("Mapping[str, str]", doc["provenance"]),
        )

    def require_compatible(self, registry: SettingsRegistry) -> None:
        """Only an exact known descriptor is executable in v2; other versions need a new run/bundle."""
        if self.registry_digest != registry_descriptor_digest(registry):
            raise _snapshot_invalid()
        specs = {
            spec.key: spec for spec in registry.keys(chain=Chain.WORK) if spec.reload is Reload.RUN_FROZEN
        }
        if set(self.values) - specs.keys() or set(self.provenance) - specs.keys():
            raise _snapshot_invalid()
        for key, spec in specs.items():
            if key not in self.values:
                if not spec.nullable:
                    raise _snapshot_invalid()
            elif registry.value_issues(key, self.values[key]):
                raise _snapshot_invalid()

    @override
    def __repr__(self) -> str:
        return (
            f"FrozenConfig(run_scope_id={self.run_scope_id}, digest={self.digest}, keys={len(self.values)})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProcessConfig:
    """Restart values captured at process start. The loader consumes this DTO (§B.13)."""

    work: Mapping[str, JsonValue]
    host: Mapping[str, JsonValue]
    generation: int
    instance_scope_id: UUID | None = None
    host_target: ScopeRef | None = None

    def __post_init__(self) -> None:
        if self.instance_scope_id is not None and not isinstance(
            cast("object", self.instance_scope_id), UUID
        ):
            raise TypeError("instance_scope_id must be a UUID")
        if self.host_target is not None and (
            not isinstance(cast("object", self.host_target), ScopeRef)
            or self.instance_scope_id is None
            or self.host_target.level not in (Level.INSTANCE, Level.HOST)
            or (
                self.host_target.level is Level.INSTANCE
                and self.host_target.scope_id != self.instance_scope_id
            )
        ):
            raise ValueError("invalid process host target")
        if (
            not isinstance(cast("object", self.generation), int)
            or isinstance(self.generation, bool)
            or self.generation < 0
        ):
            raise ValueError("generation must be non-negative")
        for name in ("work", "host"):
            values: Mapping[str, JsonValue] = getattr(self, name)
            object.__setattr__(
                self, name, MappingProxyType({k: freeze_json(v, k) for k, v in values.items()})
            )

    @classmethod
    def capture(cls, work: "EffectiveConfig", host: "EffectiveConfig | None" = None) -> "ProcessConfig":
        if work.chain.kind is not Chain.WORK or work.chain.target.level is not Level.INSTANCE:
            raise ValueError("process work config must be the instance chain")
        if host is not None and (
            host.chain.kind is not Chain.HOST
            or host.chain.scopes[0].scope_id != work.chain.target.scope_id
            or host.generation != work.generation
            or registry_descriptor_digest(host.registry) != registry_descriptor_digest(work.registry)
        ):
            raise ValueError("process host config must be a host chain at the same generation")
        return cls(
            work.restart_values(),
            {} if host is None else host.restart_values(),
            work.generation,
            work.chain.target.scope_id,
            None if host is None else host.chain.target,
        )

    @override
    def __repr__(self) -> str:
        return f"ProcessConfig(generation={self.generation}, work={len(self.work)}, host={len(self.host)})"


def normalize_numbers(value: JsonValue) -> JsonValue:
    """The digest form of a JSON value: every float becomes its ``repr`` string, recursively."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite float is not JSON")
        return repr(value)
    if isinstance(value, list):
        return [normalize_numbers(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_numbers(item) for key, item in value.items()}
    return value


def safe_value(value: JsonValue, schema: Mapping[str, JsonValue], resolver: Any = None) -> JsonValue:
    """Keep SecretRef metadata, mask rejected literals, including references inside map/array schemas."""
    if value is None:
        return None
    if schema.get("$ref") == "urn:skm:config:secret-ref:v1" or schema.get("x-skm-secret") is True:
        if isinstance(value, str):
            try:
                return str(SecretRef.parse(value))
            except (ValueError, ValidationFailed):
                pass
        return "<redacted>"
    reference = schema.get("$ref")
    if isinstance(reference, str):
        try:
            resolved = (resolver or SchemaRegistry.load_default().registry.resolver()).lookup(reference)
        except Exception:  # noqa: BLE001 - unavailable schema interpretation must fail closed in diagnostics
            return "<redacted>"
        return safe_value(value, resolved.contents, resolved.resolver)
    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            for branch in branches:
                if isinstance(branch, dict):
                    value = safe_value(value, branch, resolver)
    if isinstance(value, dict):
        properties = cast("Mapping[str, JsonValue]", schema.get("properties", {}))
        additional = schema.get("additionalProperties", {})
        return {
            key: safe_value(
                item,
                cast("Mapping[str, JsonValue]", properties.get(key, additional))
                if isinstance(properties.get(key, additional), dict)
                else {},
                resolver,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        items = schema.get("items", {})
        return [safe_value(item, items if isinstance(items, dict) else {}, resolver) for item in value]
    return value


def values_digest(values: Mapping[str, JsonValue]) -> str:
    """``sha256:…`` of canonical JSON ``{key: value}`` after ``normalize_numbers``."""
    return digest({key: normalize_numbers(value) for key, value in values.items()})


def _ref(layer: LayerRef | None) -> JsonValue:
    return None if layer is None else layer.to_json()


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where the value of a key came from: the deciding, base and locking layers and every contribution."""

    key: str
    winner: LayerRef | None
    base: LayerRef | None
    locked_by: LayerRef | None
    trace: tuple[ContributionTrace, ...]

    @classmethod
    def of(cls, resolution: KeyResolution) -> "Provenance":
        return cls(
            key=resolution.key,
            winner=resolution.winner,
            base=resolution.base,
            locked_by=resolution.locked_by,
            trace=resolution.trace,
        )

    def to_json(self, *, values: bool = True) -> JsonObject:
        """JSON for errors and diagnostics; ``values=False`` drops contribution values (secret keys)."""
        contributions: list[JsonValue] = []
        for item in self.trace:
            entry: JsonObject = {
                "layer": item.contribution.layer.to_json(),
                "op": item.contribution.op,
                "status": item.status,
            }
            if values and item.contribution.op != "unset":
                entry["value"] = item.contribution.value
            if item.contribution.locked:
                entry["locked"] = True
            if item.reason is not None:
                entry["reason"] = item.reason
            contributions.append(entry)
        return {
            "winner": _ref(self.winner),
            "base": _ref(self.base),
            "locked_by": _ref(self.locked_by),
            "contributions": contributions,
        }


@dataclass(frozen=True, slots=True)
class InvalidKey:
    """A key whose effective value cannot be used; reading it raises ``CONFIG_INVALID``."""

    key: str
    reason: InvalidReason
    message: str
    provenance: Provenance
    issues: tuple[JsonObject, ...] = ()
    validator: str | None = None
    blocked_by: tuple[str, ...] = ()  # validator inputs that were invalid themselves
    redact: bool = False  # secret key: provenance without values

    def __post_init__(self) -> None:
        if self.reason not in _REASONS:
            raise ValueError(f"reason must be one of {sorted(_REASONS)}, not {self.reason!r}")
        if (self.reason == "validator") != (self.validator is not None):
            raise ValueError("validator is given exactly for reason 'validator'")
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "blocked_by", tuple(self.blocked_by))

    def to_json(self) -> JsonObject:
        document: JsonObject = {"key": self.key, "reason": self.reason, "message": self.message}
        if self.issues:
            document["issues"] = list(self.issues)
        if self.validator is not None:
            document["validator"] = self.validator
        if self.blocked_by:
            document["blocked_by"] = list(self.blocked_by)
        document["provenance"] = self.provenance.to_json(values=not self.redact)
        return document


class _SettingsView(Protocol):
    @classmethod
    def from_settings(cls, values: Mapping[str, JsonValue], /) -> object: ...


class EffectiveConfig:
    """Values, provenance, invalid keys and diagnostics of one chain at one generation. Immutable."""

    __slots__ = (
        "_chain",
        "_diagnostics",
        "_digest",
        "_generation",
        "_invalid",
        "_lock",
        "_pack_generation",
        "_registry",
        "_resolutions",
        "_views",
    )

    def __init__(
        self,
        *,
        registry: SettingsRegistry,
        chain: ScopeChain,
        resolutions: Mapping[str, KeyResolution],
        invalid: Mapping[str, InvalidKey],
        diagnostics: tuple[Diagnostic, ...],
        generation: int,
        pack_generation: int,
        digest: str,
    ) -> None:
        unknown = set(invalid) - set(resolutions)
        if unknown:
            raise ValueError(f"invalid keys without a resolution: {sorted(unknown)}")
        self._registry = registry
        self._chain = chain
        self._resolutions: Mapping[str, KeyResolution] = MappingProxyType(dict(resolutions))
        self._invalid: Mapping[str, InvalidKey] = MappingProxyType(dict(invalid))
        self._diagnostics = tuple(diagnostics)
        self._generation = generation
        self._pack_generation = pack_generation
        self._digest = digest
        self._views: dict[type, object] = {}
        self._lock = threading.Lock()

    @property
    def chain(self) -> ScopeChain:
        return self._chain

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def pack_generation(self) -> int:
        return self._pack_generation

    @property
    def digest(self) -> str:
        return self._digest

    @property
    def registry(self) -> SettingsRegistry:
        return self._registry

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        return self._diagnostics

    def resolved_keys(self) -> tuple[str, ...]:
        """Keys resolved in this config, in registry order."""
        return tuple(self._resolutions)

    def invalid_keys(self) -> Mapping[str, InvalidKey]:
        return self._invalid

    def _resolved(self, key: str) -> KeyResolution:
        spec = self._registry.spec(key)  # CONFIG_UNKNOWN_KEY
        found = self._resolutions.get(key)
        if found is None:
            other = spec.chain is not self._chain.kind
            raise ValidationFailed(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
                f"settings key {key!r} is not resolved in the {self._chain.kind.value} chain",
                details={
                    "key": key,
                    "chain": self._chain.kind.value,
                    "reason": "other_chain" if other else "not_resolved",
                },
            )
        return found

    def _valid(self, key: str) -> KeyResolution:
        resolution = self._resolved(key)
        invalid = self._invalid.get(key)
        if invalid is not None:
            document = self._invalid_document(invalid)
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"settings key {key!r} is invalid: {document['message']}",
                details=document,
            )
        return resolution

    def _invalid_document(self, problem: InvalidKey) -> JsonObject:
        document = copy_json(problem.to_json(), "invalid")
        provenance = cast("JsonObject", document["provenance"])
        redacted = problem.redact
        schema = self.registry.spec(problem.key).value_schema
        for contribution in cast("list[JsonObject]", provenance["contributions"]):
            if "value" in contribution:
                original = contribution["value"]
                contribution["value"] = safe_value(original, schema)
                redacted = redacted or original != contribution["value"]
        if redacted:
            message = "invalid configuration (secret value redacted)"
            document["message"] = message
            for issue in cast("list[JsonObject]", document.get("issues", [])):
                issue["message"] = message
        return document

    def get(self, key: str) -> JsonValue | None:
        """The value; ``None`` for an absent nullable key (see ``present``). Invalid → ``CONFIG_INVALID``."""
        value = self._valid(key).value
        return None if isinstance(value, Missing) else value

    def present(self, key: str) -> bool:
        """Whether the key has a value (a JSON ``null`` is a value). Invalid → ``CONFIG_INVALID``."""
        return self._valid(key).value is not MISSING

    def resolution(self, key: str) -> KeyResolution:
        """The merge result of a resolved key, invalid or not."""
        return self._resolved(key)

    def provenance(self, key: str) -> Provenance:
        return Provenance.of(self._resolved(key))

    def section[T](self, view: type[T]) -> T:
        """The typed view of a section, memoized per class. Fails closed for the whole section when one of
        its keys is invalid (``CONFIG_INVALID`` listing them) or is not resolved in this chain
        (``CONFIG_SCOPE_NOT_ALLOWED``); other sections are unaffected."""
        with self._lock:
            cached = self._views.get(view)
        if cached is not None:
            return cast("T", cached)
        info = self._registry.section_of_view(view)  # CONFIG_UNKNOWN_KEY
        view_chain = getattr(view, "CONFIG_CHAIN", None)
        if view_chain is not None and view_chain != self._chain.kind.value:
            raise ValidationFailed(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
                f"section {info.id!r} view is for the {view_chain} chain",
                details={"section": info.id, "chain": self._chain.kind.value, "view_chain": view_chain},
            )
        keys = tuple(
            key
            for key in info.keys
            if view_chain is None or self._registry.spec(key).chain is self._chain.kind
        )
        unresolved: list[JsonValue] = [key for key in keys if key not in self._resolutions]
        if unresolved:
            raise ValidationFailed(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
                f"section {info.id!r} has keys outside the {self._chain.kind.value} chain",
                details={"section": info.id, "chain": self._chain.kind.value, "keys": unresolved},
            )
        invalid = [self._invalid[key] for key in keys if key in self._invalid]
        if invalid:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"section {info.id!r} has {len(invalid)} invalid key(s): {', '.join(i.key for i in invalid)}",
                details={"section": info.id, "keys": [self._invalid_document(item) for item in invalid]},
            )
        values: dict[str, JsonValue] = {}
        for key in keys:
            value = self._resolutions[key].value
            if not isinstance(value, Missing):
                values[key] = value
        built = self._build(cast("type[_SettingsView]", view), info.id, values)
        with self._lock:
            return cast("T", self._views.setdefault(view, built))

    def _build(self, view: type[_SettingsView], section_id: str, values: dict[str, JsonValue]) -> object:
        try:
            return view.from_settings(MappingProxyType(values))
        except (ValueError, TypeError, KeyError) as exc:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"section {section_id!r} does not fit its view: {exc}",
                details={"section": section_id, "reason": "view"},
            ) from exc

    def freeze(self, registry: SettingsRegistry) -> FrozenConfig:
        """Freeze every run_frozen key of a run's work chain; live and restart values stay outside it."""
        if self._chain.kind is not Chain.WORK or self._chain.target.level is not Level.RUN:
            raise ValidationFailed(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED, "a run snapshot requires a run work scope"
            )
        if registry_descriptor_digest(registry) != registry_descriptor_digest(self._registry):
            raise _snapshot_invalid()
        values: dict[str, JsonValue] = {}
        provenance: dict[str, str] = {}
        for spec in registry.keys(chain=Chain.WORK):
            if spec.reload is not Reload.RUN_FROZEN:
                continue
            if spec.key not in self._resolutions:
                raise _snapshot_invalid()  # partial resolves cannot create an execution bundle
            resolution = self._valid(spec.key)
            if not isinstance(resolution.value, Missing):
                values[spec.key] = resolution.value
                if resolution.winner is not None:
                    provenance[spec.key] = resolution.winner.display
        descriptor = registry_descriptor_digest(registry)
        return FrozenConfig(
            self._chain.target.scope_id,
            self.generation,
            self.pack_generation,
            descriptor,
            _frozen_digest(descriptor, values),
            values,
            provenance,
        )

    def restart_values(self) -> dict[str, JsonValue]:
        values: dict[str, JsonValue] = {}
        for spec in self._registry.keys(chain=self._chain.kind):
            if spec.reload is Reload.RESTART:
                if spec.key not in self._resolutions:
                    raise _snapshot_invalid("process_snapshot_incomplete")
                resolution = self._valid(spec.key)
                if not isinstance(resolution.value, Missing):
                    values[spec.key] = resolution.value
        return values

    def with_overrides(
        self, frozen: FrozenConfig | None = None, process: ProcessConfig | None = None
    ) -> "EffectiveConfig":
        """Select run/process values before consumers can read configuration; keep live values current.

        Incompatible run data fails immediately, including callers that would read only live keys. For
        historical inspection pass the snapshot directly to ``build_explain`` instead.
        """
        if frozen is not None:
            if (
                self.chain.kind is not Chain.WORK
                or self.chain.target.level is not Level.RUN
                or self.chain.target.scope_id != frozen.run_scope_id
            ):
                raise _snapshot_invalid()
            frozen.require_compatible(self.registry)
        if process is not None and (
            process.instance_scope_id is None
            or process.instance_scope_id != self.chain.scopes[0].scope_id
            or (self.chain.kind is Chain.HOST and process.host_target != self.chain.target)
        ):
            raise _snapshot_invalid("process_snapshot_scope_incompatible")
        resolutions = dict(self._resolutions)
        invalid = dict(self._invalid)
        replaced: set[str] = set()
        pending: list[Diagnostic] = []
        for key, current in self._resolutions.items():
            reload = self.registry.spec(key).reload
            if reload is Reload.RUN_FROZEN and frozen is not None:
                values, level = frozen.values, Level.RUN_BUNDLE
            elif reload is Reload.RESTART and process is not None:
                values = process.work if self.chain.kind is Chain.WORK else process.host
                level = Level.PROCESS
            else:
                continue
            value = values.get(key, MISSING)
            if level is Level.PROCESS:
                self._check_process_value(key, value)
                # A failed cross-key validator does not change this key's value: only an unreadable or
                # schema-invalid configured value, or a different JSON value, applies after restart.
                problem = invalid.get(key)
                changed = problem is not None and problem.reason != "validator"
                if changed or not _same_json(current.value, value):
                    pending.append(
                        Diagnostic(
                            code="CONFIG_RESTART_PENDING",
                            severity=Severity.INFO,
                            target=key,
                            message="the configured value will apply after process restart",
                            details={
                                "layer": LayerRef(Level.PROCESS).to_json(),
                                "process_generation": process.generation if process is not None else 0,
                            },
                        )
                    )
            resolutions[key] = _snapshot_resolution(current, value, level)
            replaced.add(key)
            invalid.pop(key, None)
        _revalidate_overrides(self.registry, resolutions, invalid, replaced)
        affected = {self.registry.spec(key).section for key in replaced}
        refreshed = {key for key in resolutions if self.registry.spec(key).section in affected}
        diagnostics = (
            tuple(
                d
                for d in self.diagnostics
                if d.target not in replaced and not (d.code == "CONFIG_INVALID" and d.target in refreshed)
            )
            + tuple(pending)
            + tuple(
                Diagnostic(
                    code="CONFIG_INVALID",
                    message=f"{key}: {problem.message}",
                    severity=Severity.ERROR,
                    target=key,
                    details=_invalid_diagnostic_details(problem),
                )
                for key, problem in invalid.items()
                if key in refreshed
            )
        )
        values = {
            key: res.value
            for key, res in resolutions.items()
            if key not in invalid and not isinstance(res.value, Missing)
        }
        return EffectiveConfig(
            registry=self.registry,
            chain=self.chain,
            resolutions=resolutions,
            invalid=invalid,
            diagnostics=diagnostics,
            generation=self.generation,
            pack_generation=self.pack_generation,
            digest=values_digest(values),
        )

    def _check_process_value(self, key: str, value: JsonValue | Missing) -> None:
        spec = self.registry.spec(key)
        if isinstance(value, Missing):
            bad = not spec.nullable
        else:
            bad = bool(self.registry.value_issues(key, value))
        if bad:
            raise _snapshot_invalid("process_snapshot_incompatible")

    @override
    def __repr__(self) -> str:
        return (
            f"EffectiveConfig(chain={self._chain.kind.value}, target={self._chain.target.level.value}, "
            f"generation={self._generation}, keys={len(self._resolutions)}, invalid={len(self._invalid)})"
        )


def _invalid_diagnostic_details(problem: InvalidKey) -> JsonObject:
    """Keep the same metadata as resolver._invalid_diagnostic after selecting snapshot values."""
    details: JsonObject = {"reason": problem.reason}
    if problem.validator is not None:
        details["validator"] = problem.validator
    if problem.blocked_by:
        details["blocked_by"] = list(problem.blocked_by)
    return details


def _same_json(left: JsonValue | Missing, right: JsonValue | Missing) -> bool:
    """Equal JSON values of equal JSON kinds at every depth: ``true``, ``1`` and ``1.0`` stay distinct.

    Python equality alone treats ``True == 1 == 1.0`` inside containers as well. Objects and arrays compare
    by kind, so plain and frozen copies of the same document are the same value.
    """
    if isinstance(left, Mapping):
        if not isinstance(right, Mapping) or left.keys() != right.keys():
            return False
        return all(_same_json(item, right[key]) for key, item in left.items())
    if isinstance(left, list):
        if not isinstance(right, list) or len(left) != len(right):
            return False
        return all(_same_json(a, b) for a, b in zip(left, right, strict=True))
    return type(left) is type(right) and left == right


def _snapshot_resolution(current: KeyResolution, value: JsonValue | Missing, level: Level) -> KeyResolution:
    layer = LayerRef(level)
    trace = (
        ()
        if isinstance(value, Missing)
        else (ContributionTrace(Contribution(layer, "set", value), "winner"),)
    )
    return replace(
        current,
        value=value,
        winner=layer if trace else None,
        base=None,
        locked_by=None,
        trace=trace,
        diagnostics=(),
    )


def _revalidate_overrides(
    registry: SettingsRegistry,
    resolutions: Mapping[str, KeyResolution],
    invalid: dict[str, InvalidKey],
    replaced: set[str],
) -> None:
    """Cross-key rules must see the selected snapshot/live slice, never today's frozen defaults."""
    affected = {registry.spec(key).section for key in replaced}
    for key, problem in tuple(invalid.items()):
        if registry.spec(key).section in affected and problem.reason == "validator":
            del invalid[key]
    values = {key: resolution.value for key, resolution in resolutions.items()}
    for finding in check_section_validators(registry, values, sorted(affected), unavailable=invalid):
        for key in finding.keys:
            if key in resolutions and key not in invalid:
                invalid[key] = InvalidKey(
                    key=key,
                    reason="validator",
                    message=finding.message,
                    provenance=Provenance.of(resolutions[key]),
                    validator=finding.validator,
                    blocked_by=finding.blocked_by,
                    redact=registry.spec(key).sensitivity is Sensitivity.SECRET,
                )
