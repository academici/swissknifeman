"""Named CLI profiles and the per-user checkout selection file (CLI §5.4)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.config._bootstrap_schema import BOOTSTRAP_URN, validate_bootstrap_document
from skm.platform.config.bootstrap import (
    BootstrapConfig,
    configure_bootstrap,
    read_bootstrap_document,
    validate_profile_roots,
)
from skm.platform.config.sources.document import decode_document
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock
from skm.platform.system_clock import SystemClock

__all__ = [
    "NewProfile",
    "ProfileCatalog",
    "add_profile",
    "cli_state_path",
    "edit_cli_state",
    "read_cli_state",
    "save_selection",
]

_STATE = "urn:skm:cli:state:v1"
_NAME = re.compile(r"[a-z][a-z0-9-]{0,31}")


def cli_state_path(environ: Mapping[str, str], home: Path) -> Path:
    return Path(environ.get("XDG_STATE_HOME") or home / ".local/state") / "skm/cli-state.json"


def read_cli_state(path: Path) -> JsonObject:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (ValueError, OSError):
        raw = None
    if isinstance(raw, dict):
        state = cast("JsonObject", raw)
        bindings = state.get("checkout_bindings", {})
        if (
            state.get("schema", _STATE) == _STATE
            and isinstance(state.get("current_instance", ""), str)
            and isinstance(bindings, dict)
            and all(Path(k).is_absolute() and isinstance(v, str) for k, v in bindings.items())
        ):
            return state
    raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Invalid CLI state")


def _remembered(path: Path, cwd: Path) -> str | None:
    state = read_cli_state(path)
    bindings = cast("dict[str, str]", state.get("checkout_bindings", {}))
    directory = cwd.resolve()
    for parent in (directory, *directory.parents):
        if str(parent) in bindings:
            return bindings[str(parent)]
    return cast("str | None", state.get("current_instance"))


@contextmanager
def edit_cli_state(path: Path) -> Generator[JsonObject]:
    """Serialize all read-modify-write operations on the per-user CLI state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(path.with_suffix(".lock")).hold(timeout_seconds=10):
        state = read_cli_state(path)
        state.setdefault("checkout_bindings", {})
        yield state
        state.update(schema=_STATE, updated_at=SystemClock().now().isoformat())
        atomic_write(path, (json.dumps(state, sort_keys=True) + "\n").encode(), mode=0o600)


def save_selection(path: Path, *, name: str | None, directory: Path | None) -> JsonObject:
    """Change exactly one selector, preserving writes made by other CLI invocations."""
    with edit_cli_state(path) as state:
        bindings = cast("dict[str, str]", state["checkout_bindings"])
        if directory is not None:
            key = str(directory.resolve())
            if name is None:
                bindings.pop(key, None)
            else:
                bindings[key] = name
        elif name is None:
            state.pop("current_instance", None)
        else:
            state["current_instance"] = name
    return state


@dataclass(frozen=True, slots=True)
class ProfileCatalog:
    source: str
    document: JsonObject = field(repr=False)
    environ: Mapping[str, str] = field(repr=False)
    home: Path

    @classmethod
    def read(cls, path: str | None, environ: Mapping[str, str], home: Path) -> ProfileCatalog:
        source, document = read_bootstrap_document(path, environ, home)
        return cls(source, document, environ, home)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(cast("JsonObject", self.document.get("instances", {"default": {}}))))

    @property
    def default(self) -> str:
        return cast("str", self.document.get("default_instance", "default"))

    def select(self, flag: str | None, cwd: Path) -> str:
        name = flag if flag is not None else self.environ.get("SKM_INSTANCE")
        if name is None:
            name = _remembered(cli_state_path(self.environ, self.home), cwd)
        if name is None:
            name = self.default
        if name not in self.names:
            raise ValidationFailed(
                ErrorCode.INSTANCE_UNKNOWN,
                "Unknown instance profile",
                details={"name": name, "known": list(self.names)},
            )
        return name

    def config(self, name: str) -> BootstrapConfig:
        return configure_bootstrap(
            self.source,
            self.document,
            self.environ,
            self.home,
            instance=name if "instances" in self.document else None,
        )


def _profile_document(document: JsonObject) -> JsonObject:
    """Promote a legacy file without moving its state, blobs or registered host."""
    doc = dict(document)
    if "instances" in doc:
        return doc
    host = dict(cast("JsonObject", doc.pop("host", {})))
    common: JsonObject = {"schema": doc.pop("schema"), "default_instance": "default"}
    for key in ("installation_id", "machine_database"):
        if key in doc:
            common[key] = doc.pop(key)
    if "name" in host:
        common["host"] = {"name": host.pop("name")}
    if host:
        doc["host"] = host
    paths = dict(cast("JsonObject", doc.get("paths", {})))
    paths.setdefault("state_dir", "~/.local/state/skm")
    paths.setdefault("blobs_root", "~/.local/share/skm/blobs")
    doc["paths"] = paths
    # Keep the legacy profile in place. Put future profiles outside its original trees.
    common["paths"] = {
        "state_dir": "~/.local/state/skm-profiles",
        "blobs_root": "~/.local/share/skm-profiles/blobs",
    }
    common["instances"] = {"default": doc}
    return common


def _literal(value: JsonValue) -> str:
    # Validated bootstrap tables have bare ASCII keys and TOML-compatible JSON scalars.
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_literal(v)}" for k, v in value.items()) + " }"
    return json.dumps(value, ensure_ascii=False, allow_nan=False).replace("\x7f", "\\u007f")


def _encode_profiles(doc: JsonObject) -> bytes:
    lines = [f"{key} = {_literal(value)}" for key, value in doc.items() if key != "instances"]
    for name, profile in cast("dict[str, JsonObject]", doc["instances"]).items():
        lines.extend(("", f"[instances.{name}]"))
        lines.extend(f"{key} = {_literal(value)}" for key, value in profile.items())
    return ("\n".join(lines) + "\n").encode()


@dataclass(frozen=True, slots=True)
class NewProfile:
    name: str
    instance_id: UUID
    mode: str
    database_url: str | None = field(repr=False)
    endpoint: str | None = field(repr=False)
    credential: str | None = field(repr=False)
    ca_bundle: Path | None = None

    def validate(self) -> None:
        name, mode = self.name, self.mode
        database_url, endpoint, credential = self.database_url, self.endpoint, self.credential
        if not _NAME.fullmatch(name):
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Invalid instance profile name")
        if mode == "http":
            if database_url is not None or not endpoint or not credential:
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "HTTP requires an endpoint and credential")
            try:
                parsed = urlsplit(endpoint)
            except ValueError:
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Invalid API endpoint") from None
            if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Invalid API endpoint")
        elif credential is not None or endpoint is not None or self.ca_bundle is not None:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Embedded mode only accepts a database URL")


def _http_document(profile: JsonObject, new: NewProfile) -> JsonObject:
    api = dict(cast("JsonObject", profile.get("api", {})))
    api.update(endpoint=new.endpoint, credential=new.credential)
    if new.ca_bundle is not None:
        api["ca_bundle"] = str(new.ca_bundle)
    else:
        api.pop("ca_bundle", None)
    return api


def add_profile(
    target: Path,
    new: NewProfile,
    *,
    home: Path | None = None,
    replace_http: bool = False,
    before_write: Callable[[JsonObject], None] | None = None,
) -> None:
    new.validate()
    name, instance_id, mode = new.name, new.instance_id, new.mode
    database_url = new.database_url
    target.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(target.with_suffix(".lock")).hold(timeout_seconds=10):
        doc: JsonObject = {"schema": BOOTSTRAP_URN, "default_instance": name, "instances": {}}
        try:
            document = decode_document(target.read_text(encoding="utf-8"), "toml")
        except FileNotFoundError:
            document = None
        except (OSError, ValueError, TypeError, RecursionError):
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Unreadable bootstrap document") from None
        if document is not None:
            validate_bootstrap_document(document)
            doc = _profile_document(document)
        profiles = cast("JsonObject", doc["instances"])
        existing = profiles.get(name)
        if replace_http and (
            mode != "http"
            or not isinstance(existing, dict)
            or existing.get("instance_id") != str(instance_id)
            or existing.get("access") != {"mode": "http"}
        ):
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Rebind requires the existing HTTP profile")
        if not replace_http and existing is not None:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "Instance profile already exists")
        profile: JsonObject = (
            dict(existing)
            if isinstance(existing, dict)
            else {"instance_id": str(instance_id), "access": {"mode": mode}}
        )
        secret_file = None
        if mode == "http":
            profile["api"] = _http_document(profile, new)
        else:
            ref = database_url if database_url is not None else "secret://env/SKM_DATABASE_URL"
            if database_url is not None and not database_url.startswith("secret://"):
                if not database_url.startswith(("postgresql://", "postgres://")):
                    raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Expected a PostgreSQL URL or SecretRef")
                secret_file = target.absolute().parent / "secrets" / f"{name}-{instance_id}.dsn"
                ref = f"secret://file/{secret_file}"
            profile["database"] = {"url": ref}
        profiles[name] = profile
        validate_bootstrap_document(doc)
        validate_profile_roots(doc, home or Path.home())
        if before_write is not None:
            before_write(doc)
            validate_bootstrap_document(doc)
            validate_profile_roots(doc, home or Path.home())
        encoded = _encode_profiles(doc)
        if secret_file is not None and database_url is not None:
            atomic_write(secret_file, database_url.encode(), mode=0o600)
        try:
            atomic_write(target, encoded, mode=0o600)
        except OSError:
            # A directory fsync can fail after rename. Keep the DSN if the new document is visible.
            if secret_file is not None and (not target.exists() or target.read_bytes() != encoded):
                secret_file.unlink(missing_ok=True)
            raise
