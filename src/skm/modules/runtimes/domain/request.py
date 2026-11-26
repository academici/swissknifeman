"""Session request (runtimes §4.5, ``urn:skm:runtimes:agent-request:v1``).

The adapter receives an already admitted, pinned ``AgentRequest`` and never reroutes it. ``ProcessOwner`` /
``ProcessOwnership`` are host-only execution binding (plain UUIDs, so runtimes does not depend on execution):
never rendered into model context or labels. Secrets (only the assignment token ``SKM_TOKEN``, K17) never
appear in ``repr``, labels, argv, transcript or serialized requests.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, cast, override
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.isolation import IsolationProfile, PluginIsolationProfile, parse_isolation_profile
from skm.kernel.json_types import JsonValue

from .capability import Capability
from .classes import Effort, RoleId
from .ids import is_digest, is_runtime_id

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject
    from skm.modules.runtimes.domain.capability import RuntimeCapabilities, VerificationContext
    from skm.modules.runtimes.domain.ids import Digest, ModelId, RuntimeId, SessionRef

__all__ = [
    "ALLOWED_SECRET_ENV",
    "REDACTED",
    "AgentRequest",
    "CommandRules",
    "McpServerSpec",
    "NetworkRules",
    "PathRule",
    "PathRules",
    "PermissionGrant",
    "ProcessOwner",
    "ProcessOwnership",
    "ResultFormat",
    "RuntimeLimits",
    "SecretStr",
    "UnitKind",
    "process_ownership_to_json",
    "request_to_json",
    "validate_request",
]

ALLOWED_SECRET_ENV: Final = frozenset({"SKM_TOKEN"})
REDACTED: Final = "***"
_NONCE_MIN: Final = 16
_NONCE_MAX: Final = 128
_PATH_MAX: Final = 4096

type UnitKind = Literal["step", "check", "git_effect"]


class ResultFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


class SecretStr:
    """A secret value that prints as ``***``; only ``reveal()`` gives the value to the adapter."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not value:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("a secret is a non-empty string")
        self._value = value

    def reveal(self) -> str:
        return self._value

    @override
    def __repr__(self) -> str:
        return f"SecretStr({REDACTED!r})"

    @override
    def __str__(self) -> str:
        return REDACTED

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, SecretStr) and other._value == self._value

    @override
    def __hash__(self) -> int:
        return hash((SecretStr, self._value))


@dataclass(frozen=True, slots=True)
class RuntimeLimits:
    timeout_seconds: int  # local Monotonic elapsed, 30..14400; UTC is not a deadline clock
    idle_timeout_seconds: int  # idle suspicion threshold, 10..3600; not a hard deadline
    max_turns: int | None
    max_output_tokens: int | None
    max_output_bytes: int  # stdout capture cap; beyond it truncation + flag


def _uuid(value: object, name: str) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{name} must be a UUID")


@dataclass(frozen=True, slots=True)
class ProcessOwner:
    """Host-only execution binding of a spawned unit: real stage record and unit IDs, no fictitious StepId.

    ``unit_kind = step`` with ``unit_id`` = StepId (``AgentRequest.request_id``); checks use their
    CheckExecutionId (``check``), trusted Git helpers their EffectId (``git_effect``).
    """

    host_id: UUID
    worker_id: UUID
    attempt_id: UUID
    stage_record_id: UUID
    unit_kind: UnitKind
    unit_id: UUID
    owner_nonce: str
    identity_dir: str

    def __post_init__(self) -> None:
        for name in ("host_id", "worker_id", "attempt_id", "stage_record_id", "unit_id"):
            _uuid(getattr(self, name), name)
        if self.unit_kind not in ("step", "check", "git_effect"):
            raise ValueError(f"unknown unit_kind {self.unit_kind!r}")
        if not isinstance(self.owner_nonce, str) or not _NONCE_MIN <= len(self.owner_nonce) <= _NONCE_MAX:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("owner_nonce must have 16..128 characters")
        if not isinstance(self.identity_dir, str) or not 1 <= len(self.identity_dir) <= _PATH_MAX:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("identity_dir must have 1..4096 characters")

    @override
    def __repr__(self) -> str:
        # The nonce proves ownership of the unit on the host; it stays out of logs.
        return (
            f"ProcessOwner(unit_kind={self.unit_kind!r}, unit_id={self.unit_id}, "
            f"stage_record_id={self.stage_record_id}, attempt_id={self.attempt_id}, owner_nonce={REDACTED!r})"
        )


@dataclass(frozen=True, slots=True)
class ProcessOwnership:
    """Prepared containment of one owner, with a durable backend ref; reusable by check host adapters."""

    owner: ProcessOwner
    kind: Literal["cgroup", "container", "pgroup_best_effort"]
    ref: str  # durable backend reference (cgroup path, container id, pgid)
    daemon_identity: str | None = None  # container: immutable daemon identity, not a client PID

    def __post_init__(self) -> None:
        if not isinstance(self.owner, ProcessOwner):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("owner must be a ProcessOwner")
        if self.kind not in ("cgroup", "container", "pgroup_best_effort"):
            raise ValueError(f"unknown ownership kind {self.kind!r}")
        if not isinstance(self.ref, str) or not 1 <= len(self.ref) <= _PATH_MAX:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("ownership ref must have 1..4096 characters")
        if self.kind == "container" and not self.daemon_identity:
            raise ValueError("container ownership needs the daemon identity")


def process_ownership_to_json(ownership: ProcessOwnership) -> JsonObject:
    """The shared ownership wire form omits an absent optional daemon identity."""
    owner = ownership.owner
    doc: JsonObject = {
        "owner": {
            "host_id": str(owner.host_id),
            "worker_id": str(owner.worker_id),
            "attempt_id": str(owner.attempt_id),
            "stage_record_id": str(owner.stage_record_id),
            "unit_kind": owner.unit_kind,
            "unit_id": str(owner.unit_id),
            "owner_nonce": owner.owner_nonce,
            "identity_dir": owner.identity_dir,
        },
        "kind": ownership.kind,
        "ref": ownership.ref,
    }
    if ownership.daemon_identity is not None:
        doc["daemon_identity"] = ownership.daemon_identity
    return doc


@dataclass(frozen=True, slots=True)
class PathRule:
    root: str  # absolute
    pattern: str


@dataclass(frozen=True, slots=True)
class PathRules:
    allow: tuple[PathRule, ...]
    deny: tuple[PathRule, ...]

    def roots(self) -> tuple[str, ...]:
        return tuple(rule.root for rule in (*self.allow, *self.deny))


@dataclass(frozen=True, slots=True)
class CommandRules:
    mode: Literal["none", "allowlist", "denylist", "any"]
    programs: tuple[str, ...]
    deny_patterns: tuple[str, ...]
    ask_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NetworkRules:
    mode: Literal["none", "allowlist", "any"]
    hosts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    """Normalized permissions (``policy.PermissionSet`` in serializable form)."""

    fs_read: PathRules
    fs_write: PathRules
    commands: CommandRules
    network: NetworkRules
    tools: frozenset[str]
    external_effects: frozenset[str]


@dataclass(frozen=True, slots=True)
class McpServerSpec:
    name: str
    command: tuple[str, ...]
    env: Mapping[str, str]  # Explicit non-secret values or SecretRefs
    secret_env_names: tuple[str, ...]  # names of AgentRequest.secret_env passed to the server


@dataclass(frozen=True, slots=True)
class AgentRequest:
    request_id: str  # = StepId
    runtime_id: RuntimeId
    model: ModelId  # resolved by admission/catalog; the adapter does not reroute
    effort: Effort | None
    role: RoleId
    rendered_prompt: str
    prompt_digest: Digest
    result_format: ResultFormat
    result_schema_urn: str | None
    workdir: str  # absolute path of the attempt environment on the worker host
    permissions: PermissionGrant
    isolation_profile: IsolationProfile | PluginIsolationProfile  # 4 built-in or "<plugin_id>:<name>"
    process_owner: ProcessOwner = field(repr=False)  # unit_kind=step, unit_id=request_id; host metadata
    config_mode: Literal["isolated", "inherit"]
    client_home: str | None  # isolated: worker.state_dir/client-homes/<attempt_id>/<runtime_id>/
    resume_session_ref: SessionRef | None
    session_policy: Literal["ephemeral", "persistent"]
    env_allowlist: tuple[str, ...]
    extra_env: Mapping[str, str]
    secret_env: Mapping[str, SecretStr] = field(repr=False)
    mcp_servers: tuple[McpServerSpec, ...]
    limits: RuntimeLimits
    labels: Mapping[str, str]  # run_id, task_id, attempt_id, step_id
    verification_context: VerificationContext | None = None
    verification_key: Digest | None = None
    expected_runtime_version: str | None = None
    stage_tool_socket: str | None = field(default=None, repr=False)  # set by the worker after admission

    def __post_init__(self) -> None:
        object.__setattr__(self, "isolation_profile", parse_isolation_profile(self.isolation_profile))
        object.__setattr__(self, "role", RoleId(self.role))
        object.__setattr__(self, "result_format", ResultFormat(self.result_format))
        if self.effort is not None:
            object.__setattr__(self, "effort", Effort(self.effort))
        for name, value in self.secret_env.items():
            if not isinstance(value, SecretStr):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise TypeError(f"secret_env.{name} must be a SecretStr")

    @override
    def __repr__(self) -> str:
        # A secret duplicated into an open field (prompt, MCP argv, labels, ...) is masked even before
        # validate_request refuses the request.
        secrets = _secret_values(self)
        parts = ", ".join(
            f"{item.name}={_safe_repr(getattr(self, item.name), secrets)}"
            for item in fields(self)
            if item.repr
        )
        return f"{type(self).__name__}({parts})"


def _secret_values(req: AgentRequest) -> tuple[str, ...]:
    # Longest first, so a secret containing another one is masked whole.
    return tuple(sorted({secret.reveal() for secret in req.secret_env.values()}, key=len, reverse=True))


def _scrub(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    return text


def _safe_repr(value: object, secrets: tuple[str, ...]) -> str:
    """``repr`` with every string scrubbed before it is quoted, so escaping cannot hide a secret."""
    if isinstance(value, str):
        return repr(_scrub(value, secrets))
    if isinstance(value, StrEnum):
        return repr(value)
    if isinstance(value, tuple):
        items = [_safe_repr(item, secrets) for item in cast("tuple[object, ...]", value)]
        return f"({items[0]},)" if len(items) == 1 else f"({', '.join(items)})"
    if isinstance(value, frozenset):
        items = sorted(_safe_repr(item, secrets) for item in cast("frozenset[object]", value))
        return f"frozenset({{{', '.join(items)}}})" if items else "frozenset()"
    if isinstance(value, Mapping):
        pairs = cast("Mapping[object, object]", value).items()
        return "{" + ", ".join(f"{_safe_repr(k, secrets)}: {_safe_repr(v, secrets)}" for k, v in pairs) + "}"
    if is_dataclass(value) and not isinstance(value, type):
        parts = ", ".join(
            f"{item.name}={_safe_repr(getattr(value, item.name), secrets)}"
            for item in fields(value)
            if item.repr
        )
        return f"{type(value).__name__}({parts})"
    return _scrub(repr(value), secrets)


def _invalid(reason: str, message: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, message, details={"reason": reason, **details})


def _schema(reason: str, message: str) -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, message, details={"reason": reason})


def _inside(path: str, root: str) -> bool:
    """Lexical containment of normalized absolute paths (the adapter re-checks resolved paths at spawn)."""
    normal, base = posixpath.normpath(path), posixpath.normpath(root)
    return normal == base or normal.startswith(base.rstrip("/") + "/")


def _check_shape(req: AgentRequest) -> None:
    try:
        step_id = UUID(req.request_id)
    except (ValueError, TypeError) as exc:
        raise _schema("request_id_not_uuid", "request_id must be the StepId (a UUID)") from exc
    if not is_runtime_id(req.runtime_id):
        raise _schema("runtime_id_invalid", "runtime_id does not match ^[a-z][a-z0-9_]{1,31}$")
    if not is_digest(req.prompt_digest):
        raise _schema("prompt_digest_invalid", "prompt_digest must be a sha256 digest")
    if req.result_format is ResultFormat.JSON and not req.result_schema_urn:
        raise _schema("result_schema_missing", "result_format json needs result_schema_urn")
    owner = req.process_owner
    if owner.unit_kind != "step" or owner.unit_id != step_id:
        raise _schema(
            "process_owner_mismatch", "process_owner must be unit_kind=step with unit_id=request_id"
        )
    if (req.config_mode == "isolated") != (req.client_home is not None):
        raise _schema("client_home_mismatch", "config_mode isolated iff client_home is set")
    if req.resume_session_ref is not None and req.session_policy != "persistent":
        raise _schema("resume_requires_persistent", "resume_session_ref needs session_policy persistent")


def _check_paths(req: AgentRequest) -> None:
    if not posixpath.isabs(req.workdir):
        raise _schema("workdir_not_absolute", "workdir must be an absolute path")
    if req.client_home is not None and (
        not posixpath.isabs(req.client_home) or _inside(req.client_home, req.workdir)
    ):
        raise _invalid("client_home_inside_worktree", "client_home must be absolute and outside workdir")
    grants = (*req.permissions.fs_read.roots(), *req.permissions.fs_write.roots())
    for root in grants:
        if not posixpath.isabs(root) or not _inside(root, req.workdir):
            raise _invalid("grant_outside_worktree", "file grants stay inside workdir (S-55)", root=root)


def _check_secrets(req: AgentRequest) -> None:
    names = set(req.secret_env)
    if not names <= ALLOWED_SECRET_ENV:
        raise _invalid(
            "secret_env_not_allowed",
            "secret_env carries only SKM_TOKEN",
            names=_json_list(sorted(names - ALLOWED_SECRET_ENV)),
        )
    clash = names & (set(req.extra_env) | set(req.env_allowlist))
    if clash:
        raise _invalid(
            "secret_env_conflict",
            "secret_env names overlap extra_env/env_allowlist",
            names=_json_list(sorted(clash)),
        )
    for server in req.mcp_servers:
        missing = set(server.secret_env_names) - names
        if missing:
            raise _invalid(
                "mcp_secret_missing", "MCP secret_env_names are keys of secret_env", server=server.name
            )
    # Every open string of the request (prompt, labels, env, MCP name/argv/env, paths, permissions, ...):
    # a secret travels only by name through secret_env/secret_env_names, never by value.
    secrets = _secret_values(req)
    for place, text in _open_strings(_raw_json(req), ""):
        if any(secret in text for secret in secrets):
            # The path carries object keys, which may themselves hold the secret.
            raise _invalid(
                "secret_exposed", "a secret value appears outside secret_env", field=_scrub(place, secrets)
            )
    owner = req.process_owner
    for marker in (owner.owner_nonce, owner.identity_dir):
        if any(marker in text for text in (req.rendered_prompt, *req.labels.values())):
            raise _invalid("owner_exposed", "process owner metadata never enters model context or labels")


def validate_request(req: AgentRequest, caps: RuntimeCapabilities) -> None:
    """Invariants of §4.5 before a session starts; raises ``SCHEMA_INVALID``/``RUNTIME_INVALID_REQUEST``
    (with ``details.reason``) or ``CAPABILITY_UNAVAILABLE``. The adapter checks that ``workdir`` exists."""
    if caps.runtime_id != req.runtime_id:
        raise _schema("capabilities_mismatch", "capabilities belong to another runtime")
    _check_shape(req)
    _check_paths(req)
    _check_secrets(req)
    if req.resume_session_ref is not None and not caps.supports(Capability.SESSION_RESUME):
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "runtime cannot resume a session",
            details={"capability": Capability.SESSION_RESUME.value, "runtime_id": req.runtime_id},
        )


def _json_list(values: Iterable[str]) -> list[JsonValue]:
    return list[JsonValue](values)


def _path_rules(rules: PathRules) -> JsonObject:
    return {
        "allow": [{"root": rule.root, "pattern": rule.pattern} for rule in rules.allow],
        "deny": [{"root": rule.root, "pattern": rule.pattern} for rule in rules.deny],
    }


def _open_strings(value: JsonValue, place: str) -> Iterator[tuple[str, str]]:
    """``(path, text)`` of every string value and object key, except the redacted ``secret_env`` section."""
    if isinstance(value, str):
        yield place, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _open_strings(item, f"{place}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            path = f"{place}.{key}" if place else key
            if path == "secret_env":
                continue
            yield f"{path}(key)", key
            yield from _open_strings(item, path)


def _scrub_json(value: JsonValue, secrets: tuple[str, ...]) -> JsonValue:
    if isinstance(value, str):
        return _scrub(value, secrets)
    if isinstance(value, list):
        return [_scrub_json(item, secrets) for item in value]
    if isinstance(value, dict):
        return {_scrub(key, secrets): _scrub_json(item, secrets) for key, item in value.items()}
    return value


def request_to_json(req: AgentRequest) -> JsonObject:
    """Schema form for fixtures and debug dumps: secret values are replaced by ``***``, also where a secret
    was duplicated into an open field of a request that ``validate_request`` would refuse."""
    return cast("JsonObject", _scrub_json(_raw_json(req), _secret_values(req)))


def _raw_json(req: AgentRequest) -> JsonObject:
    owner = req.process_owner
    permissions = req.permissions
    return {
        "request_id": req.request_id,
        "runtime_id": req.runtime_id,
        "model": req.model,
        "effort": None if req.effort is None else req.effort.value,
        "role": req.role.value,
        "rendered_prompt": req.rendered_prompt,
        "prompt_digest": req.prompt_digest,
        "result_format": req.result_format.value,
        "result_schema_urn": req.result_schema_urn,
        "workdir": req.workdir,
        "permissions": {
            "fs_read": _path_rules(permissions.fs_read),
            "fs_write": _path_rules(permissions.fs_write),
            "commands": {
                "mode": permissions.commands.mode,
                "programs": _json_list(permissions.commands.programs),
                "deny_patterns": _json_list(permissions.commands.deny_patterns),
                "ask_patterns": _json_list(permissions.commands.ask_patterns),
            },
            "network": {"mode": permissions.network.mode, "hosts": _json_list(permissions.network.hosts)},
            "tools": _json_list(sorted(permissions.tools)),
            "external_effects": _json_list(sorted(permissions.external_effects)),
        },
        "isolation_profile": str(req.isolation_profile),
        "process_owner": {
            "host_id": str(owner.host_id),
            "worker_id": str(owner.worker_id),
            "attempt_id": str(owner.attempt_id),
            "stage_record_id": str(owner.stage_record_id),
            "unit_kind": owner.unit_kind,
            "unit_id": str(owner.unit_id),
            "owner_nonce": owner.owner_nonce,
            "identity_dir": owner.identity_dir,
        },
        "config_mode": req.config_mode,
        "client_home": req.client_home,
        "resume_session_ref": req.resume_session_ref,
        "session_policy": req.session_policy,
        "env_allowlist": _json_list(req.env_allowlist),
        "extra_env": dict[str, JsonValue](req.extra_env),
        "secret_env": dict[str, JsonValue].fromkeys(sorted(req.secret_env), REDACTED),
        "mcp_servers": [
            {
                "name": server.name,
                "command": _json_list(server.command),
                "env": dict[str, JsonValue](server.env),
                "secret_env_names": _json_list(server.secret_env_names),
            }
            for server in req.mcp_servers
        ],
        "limits": {
            "timeout_seconds": req.limits.timeout_seconds,
            "idle_timeout_seconds": req.limits.idle_timeout_seconds,
            "max_turns": req.limits.max_turns,
            "max_output_tokens": req.limits.max_output_tokens,
            "max_output_bytes": req.limits.max_output_bytes,
        },
        "labels": dict[str, JsonValue](req.labels),
    }
