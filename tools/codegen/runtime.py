"""Runtime conversion primitives emitted verbatim into kernel/generated/_codec.py.

Conversion is independent of a global registry. The bus validates the full source schema first;
these helpers additionally enforce the conversion shape and never coerce bool into an integer.
"""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from importlib import import_module
from reprlib import Repr
from types import MappingProxyType
from typing import Any, Literal, cast, override
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

_REFERENCE = re.compile(
    r"secret://(?:(?P<env>env)/(?P<env_path>[A-Z_][A-Z0-9_]{0,127})"
    r"|(?P<file>file)/(?P<file_path>[^\s]{1,1024})"
    r"|(?P<keyring>keyring)/(?P<keyring_path>[A-Za-z0-9._-]{1,128}/[A-Za-z0-9._@-]{1,128}))"
)


@dataclass(frozen=True, slots=True)
class SecretRef:
    """Pure reference value shared by generated views; platform owns secret resolution."""

    scheme: Literal["env", "file", "keyring"]
    path: str

    def __post_init__(self) -> None:
        if not _REFERENCE.fullmatch(f"secret://{self.scheme}/{self.path}"):
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Invalid secret reference", details={"reason": "secret_ref_invalid"}
            )

    @classmethod
    def parse(cls, text: str) -> "SecretRef":
        match = _REFERENCE.fullmatch(text)
        if match is None:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Invalid secret reference", details={"reason": "secret_ref_invalid"}
            )
        scheme = next(s for s in ("env", "file", "keyring") if match.group(s))
        return cls(cast('Literal["env", "file", "keyring"]', scheme), match.group(scheme + "_path"))

    @override
    def __str__(self) -> str:
        return f"secret://{self.scheme}/{self.path}"


def _resolve(reference: tuple[str, str]) -> Any:
    return getattr(import_module(reference[0]), reference[1])


def json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ValueError("JSON object keys must be strings")
        return {k: json_copy(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_copy(v) for v in value]
    if type(value) is float and not math.isfinite(value):
        raise ValueError("non-finite number is not JSON")
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise ValueError(f"not a JSON value: {type(value).__name__}")


def _priority(spec: tuple, seen: frozenset = frozenset()) -> int:
    """Named aliases keep the dispatch priority of their underlying conversion."""
    tag, _args, _values, reference = spec
    if tag == "ref" and reference not in seen:
        module = import_module(reference[0])
        return _priority(getattr(module, "_SPEC_" + reference[1]), seen | {reference})
    return {"literal": 0, "uuid": 1, "datetime": 1, "date": 1, "int": 2, "float": 3}.get(tag, 4)


class _LiteralRepr(Repr):
    """Bound schema choices without splitting escapes or decimalizing wide integers."""

    @override
    def repr_str(self, x: str, level: int) -> str:
        text = repr(x[: self.maxstring])
        if len(x) <= self.maxstring and len(text) <= self.maxstring:
            return text
        # Bound source slices first, then remove whole characters until their repr fits.
        # Slicing escaped text can split a backslash escape or introduce literal digits.
        size = min(len(x), self.maxstring - len(self.fillvalue) - 2)
        head = x[: size // 2]
        tail = x[len(x) - (size - size // 2) :]
        while len(text := repr(head + self.fillvalue + tail)) > self.maxstring:
            if len(repr(head)) > len(repr(tail)):
                head = head[:-1]
            else:
                tail = tail[1:]
        return text

    @override
    def repr_int(self, x: int, level: int) -> str:
        # 128 bits fit in 40 decimal characters, safely below every interpreter limit.
        if x.bit_length() > 128:
            return f"<integer: {x.bit_length()} bits>"
        return super().repr_int(x, level)


_LITERAL_REPR = _LiteralRepr()


def convert(spec: tuple, value: Any, *, encode: bool = False, json_mode: bool = False) -> Any:  # noqa: PLR0911, PLR0912, PLR0915
    tag, args, values, reference = spec
    if tag == "ref":
        module = import_module(reference[0])
        target = getattr(module, reference[1])
        if isinstance(target, type) and issubclass(target, StrEnum):
            return target(value).value if encode or json_mode else target(value)
        descriptor = getattr(module, "_SPEC_" + reference[1])
        json_mode = json_mode or getattr(module, "_JSON_MODE_" + reference[1], False)
        if descriptor[0] == "record":
            if json_mode or getattr(target, "_JSON_MODE", False):
                return record_from_json(target, value, json_mode=True)
            if encode and not isinstance(value, target):
                raise ValueError(f"expected {target.__name__}")
            return record_to_json(value) if encode else target.from_json(value)
        return convert(descriptor, value, encode=encode, json_mode=json_mode)
    if tag == "union":
        errors = []
        # Constants and formatted strings precede their wider JSON primitive types.
        for child in sorted(args, key=_priority):
            try:
                return convert(child, value, encode=encode, json_mode=json_mode)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                errors.append(str(exc))
        raise ValueError("value matches no union conversion: " + "; ".join(errors))
    if tag == "literal":
        if not any(type(value) is type(v) and value == v for v in values):
            raise ValueError(f"expected one of {_LITERAL_REPR.repr(values)}")
        return value
    if tag in ("uuid", "datetime", "date"):
        if json_mode:
            convert(spec, value)
            return value
        if tag == "uuid":
            if encode:
                if not isinstance(value, UUID):
                    raise ValueError("expected UUID")
                return str(value)
            if not isinstance(value, str):
                raise ValueError("expected UUID string")
            return UUID(value)
        if tag == "date":
            if encode:
                if type(value) is not date:
                    raise ValueError("expected date")
                return value.isoformat()
            if not isinstance(value, str):
                raise ValueError("expected date string")
            return date.fromisoformat(value)
        if not encode and not isinstance(value, str):
            raise ValueError("expected date-time string")
        dt = value if encode else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("date-time must have a timezone")
        return dt.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z") if encode else dt
    if tag == "secret":
        if encode:
            return str(value)
        return SecretRef.parse(value)
    if tag in ("array", "tuple"):
        if not isinstance(value, (list, tuple)):
            raise ValueError("expected array")
        if tag == "tuple" and len(value) != len(args):
            raise ValueError("wrong tuple length")
        result = [
            convert(args[i] if tag == "tuple" else args[0], v, encode=encode, json_mode=json_mode)
            for i, v in enumerate(value)
        ]
        return result if encode or json_mode else tuple(result)
    if tag == "map":
        if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
            raise ValueError("expected string-keyed mapping")
        result = {k: convert(args[0], v, encode=encode, json_mode=json_mode) for k, v in value.items()}
        return result if encode or json_mode else MappingProxyType(result)
    if tag == "object":
        if not isinstance(value, Mapping):
            raise ValueError("expected object")
        return json_copy(value)
    expected = {"str": str, "int": int, "float": (int, float), "bool": bool, "null": type(None)}
    if tag in expected:
        if type(value) not in (expected[tag] if isinstance(expected[tag], tuple) else (expected[tag],)):
            raise ValueError(f"expected {tag}")
        if tag == "float":
            try:
                number = float(value)
            except OverflowError as exc:
                raise ValueError("number is outside float range") from exc
            if not math.isfinite(number):
                raise ValueError("non-finite number is not JSON")
            return value if json_mode else number
        return value
    if tag == "never":
        raise ValueError("false schema has no values")
    return json_copy(value)


type RequiredWhen = tuple[tuple[str, str, str, bool], ...]


def _condition_matches(data: Mapping[str, Any], discriminator: str, value: str, absent: bool) -> bool:
    if discriminator not in data:
        return absent
    return data[discriminator] == value


def record_from_json(
    cls: Any, data: Any, *, json_mode: bool = False, required_when: RequiredWhen = ()
) -> Any:
    if not isinstance(data, Mapping):
        raise ValueError("expected object")
    fields = cls._FIELDS
    known = {f[0] for f in fields}
    for key in data:
        if key not in known:
            raise ValueError(f"unknown field {key!r}")
    result = {}
    for wire, name, spec, required, default, has_default, _settings_key in fields:
        if wire not in data:
            if required:
                raise ValueError(f"missing required field {wire!r}")
            if json_mode:
                continue
            if not has_default or default is None:
                result[name] = None
                continue
            value = default
        else:
            value = data[wire]
        result[wire if json_mode else name] = convert(spec, value, json_mode=json_mode)
    for wire, discriminator, value, absent in required_when:
        if wire not in data and _condition_matches(data, discriminator, value, absent):
            condition = "is absent" if discriminator not in data else f"is {value!r}"
            raise ValueError(f"missing field {wire!r} required when {discriminator!r} {condition}")
    return result if json_mode else cls(**result)


def record_to_json(obj: Any, *, required_when: RequiredWhen = ()) -> dict[str, Any]:
    result = {}
    for wire, name, spec, required, _default, _has_default, _settings_key in obj._FIELDS:
        value = getattr(obj, name)
        if value is None and not required:
            continue
        result[wire] = convert(spec, value, encode=True)
    # A conditionally required nullable field spells its ``None`` as an explicit null, not an absence.
    for wire, discriminator, value, absent in required_when:
        if wire not in result and _condition_matches(result, discriminator, value, absent):
            result[wire] = None
    return result


def from_settings(cls: Any, values: Mapping[str, Any]) -> Any:
    result = {}
    for _wire, name, spec, _required, _default, _has_default, key in cls._FIELDS:
        if key:
            result[name] = convert(spec, values.get(key))
        else:
            result[name] = from_settings(_resolve(spec[3]), values)
    return cls(**result)
