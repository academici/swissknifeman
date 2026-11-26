"""External plugins: a manifest that is checked before anything runs, a handshake, calls and events.

A plugin is a command described by an ``extension.json`` (``extension/v1``) and registered by the machine in
``[aicore.plugins.<id>]``. The order is fixed and every step refuses with an :class:`ExtError` before the next:

1. :func:`load_manifest` reads and checks the manifest without starting anything (schema, kind requirements, an
   entrypoint that stays inside the manifest folder, protocol range, required contracts, permission profile);
2. :func:`describe_plugin` starts the plugin with ``op: describe`` and compares the answer with the manifest
   (id, version, kind, protocol, capabilities digest, transport); there is no cache: every use describes again;
3. only then :func:`invoke_point` sends ``op: invoke`` and :func:`deliver_event` sends ``op: event``.

A plugin runs through :func:`aicore.ext.process.run_json` in the cleaned environment of
:func:`aicore.ext.environment.clean_environment`; only a *trusted* plugin receives the variables and ``env://``
secrets its manifest asks for. Plugin output is data: texts taken from it are escaped and shortened before they
reach a message. stdlib and ``aicore`` only.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from ..config import ConfigError
from ..config.units import foundation_root
from ..util import schema as _schema
from ..util.digest import digest_json
from ..util.paths import is_within, resolve_path
from . import settings as _settings
from . import units as _units
from .environment import clean_environment, effective_profile, ignored_requests
from .errors import ExtError
from .process import MAX_STDOUT, ProcessResult, run_json

HOST_PROTOCOL = (1, 1)
DESCRIBE_DEADLINE_S = 10
DEFAULT_TIMEOUT_S = 60
MAX_DIAGNOSTICS = 20
INTERPRETERS = ("python3", "sh")
REQUEST_SCHEMA = "urn:swissknifeman:aicore:plugin-request:v1"

_SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas"
_CONTRACTS: Dict[str, Tuple[Any, str]] = {}
_MESSAGE_LIMIT = 200
_ISSUES_SHOWN = 3
_CONTROL = re.compile(r"[^\x20-\x7e -\U0010ffff]|[  \u0085]")

PathLike = Union[str, "os.PathLike[str]"]


class PluginCallError(ExtError):
    """An :class:`ExtError` of a call that may have run a process; ``result`` is that process, if any."""

    def __init__(self, code: str, message: str, result: Optional[ProcessResult] = None):
        super().__init__(code, message)
        self.result = result


@dataclass(frozen=True)
class Manifest:
    """A checked ``extension.json``; ``entrypoint`` is the argv to run, its script absolute and inside ``directory``."""

    path: Path
    directory: Path
    id: str
    kind: str
    version: str
    description: str
    protocol: Tuple[int, int]
    entrypoint: Tuple[str, ...]
    requires: Tuple[Dict[str, Any], ...]
    provides: Dict[str, Any]
    permissions: Optional[Dict[str, Any]]
    timeout_seconds: Optional[int]
    example_input: Optional[Dict[str, Any]]
    document: Dict[str, Any] = field(repr=False, compare=False)

    @property
    def max_stdout(self) -> int:
        """The stdout limit of one call: ``limits.max_stdout_bytes`` of the manifest, else ``MAX_STDOUT``."""
        return (self.document.get("limits") or {}).get("max_stdout_bytes", MAX_STDOUT)

    @property
    def points(self) -> List[str]:
        return list(self.provides.get("points") or [])

    @property
    def events(self) -> List[str]:
        return list(self.provides.get("events") or [])

    @property
    def capabilities_digest(self) -> str:
        return digest_json(self.provides)


@dataclass(frozen=True)
class Registration:
    """A plugin of the configuration. ``problem`` (``{"code", "message"}``) says why it cannot be used."""

    id: str
    manifest_path: str
    trusted: bool
    timeout_seconds: int
    enabled: bool
    manifest: Optional[Manifest]
    problem: Optional[Dict[str, str]]
    unknown_points: Tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.enabled and self.manifest is not None and self.problem is None


@dataclass(frozen=True)
class Describe:
    """The checked answer to ``op: describe``."""

    id: str
    kind: str
    version: str
    protocol: str
    capabilities_digest: str
    transport: str
    duration_ms: int

    def to_json(self) -> Dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "version": self.version, "protocol": self.protocol,
                "capabilities_digest": self.capabilities_digest, "transport": self.transport,
                "duration_ms": self.duration_ms}


@dataclass(frozen=True)
class PluginResult:
    """The outcome of one plugin for one call. ``status`` is ``ok``, ``skipped`` or ``error``."""

    plugin: str
    status: str
    output: Optional[Dict[str, Any]]
    error: Optional[str]
    code: Optional[str]
    duration_ms: int

    def to_json(self) -> Dict[str, Any]:
        return {"plugin": self.plugin, "status": self.status, "output": self.output, "error": self.error,
                "code": self.code, "duration_ms": self.duration_ms}


# --- contracts -----------------------------------------------------------------------------------------------


def _validate(doc: object, contract: str) -> List[str]:
    """Messages of every violation of ``<contract>/v1`` by ``doc`` (empty when valid)."""
    if contract not in _CONTRACTS:
        _CONTRACTS[contract] = _schema.load_contract(_SCHEMA_ROOT / contract / "v1")
    registry, kind = _CONTRACTS[contract]
    return [f"{issue.path or '/'}: {issue.message}" for issue in _schema.validate(doc, kind, registry)]


def safe_text(value: object, limit: int = _MESSAGE_LIMIT) -> str:
    """``value`` as one safe line: control characters escaped, long text cut."""
    text = value if isinstance(value, str) else repr(value)
    text = _CONTROL.sub(lambda match: match.group(0).encode("unicode_escape").decode("ascii"), text)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _issues(messages: Sequence[str]) -> str:
    shown = "; ".join(safe_text(message) for message in messages[:_ISSUES_SHOWN])
    return shown + (f"; and {len(messages) - _ISSUES_SHOWN} more" if len(messages) > _ISSUES_SHOWN else "")


def _host_contracts() -> Dict[str, List[str]]:
    """Contract id -> major versions that the foundation provides (``provides.contracts`` of its unit.json)."""
    try:
        doc = json.loads((foundation_root() / "unit.json").read_text(encoding="utf-8"))
        entries = doc["provides"]["contracts"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    found: Dict[str, List[str]] = {}
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("version"), str):
            found.setdefault(entry["id"], []).append(entry["version"])
    return found


# --- the manifest --------------------------------------------------------------------------------------------


def _inside(root: Path, path: Path) -> bool:
    return is_within(path, root)


def _resolve_entrypoint(argv: Sequence[str], directory: Path) -> Tuple[str, ...]:
    """The argv to run: the script resolved from ``directory`` and proven to stay inside it and to exist."""
    interpreter = argv[0] in INTERPRETERS
    index = 1 if interpreter else 0
    if len(argv) <= index:
        raise ExtError("PLUGIN_MANIFEST_INVALID", f"entrypoint {argv[0]!r} needs a script path after it")
    script = argv[index]
    if os.path.isabs(script):
        raise ExtError("PLUGIN_MANIFEST_INVALID", "the entrypoint path must be relative to the manifest folder")
    try:
        root = resolve_path(directory)
        resolved = resolve_path(root / script)
    except (OSError, ValueError, RuntimeError):  # a symlink loop, an unresolvable component
        raise ExtError("PLUGIN_MANIFEST_INVALID", "the entrypoint path cannot be resolved") from None
    if not _inside(root, resolved) or resolved == root:
        raise ExtError("PLUGIN_MANIFEST_INVALID", "the entrypoint must stay inside the folder of the manifest")
    if not resolved.is_file():
        raise ExtError("PLUGIN_MANIFEST_INVALID", f"the entrypoint file {script!r} does not exist")
    if not interpreter and not os.access(str(resolved), os.X_OK):
        raise ExtError("PLUGIN_MANIFEST_INVALID", f"the entrypoint file {script!r} is not executable")
    return tuple(list(argv[:index]) + [str(resolved)] + list(argv[index + 1:]))


def load_manifest(path: PathLike) -> Manifest:
    """Read and check ``path`` without starting anything; any problem is an :class:`ExtError`.

    Checks, in order: JSON and ``extension/v1``; ``command`` needs ``provides.points`` and ``subscriber``
    ``provides.events``; the entrypoint stays inside the manifest folder and is runnable; the protocol range
    meets the host's; every required contract and major is provided by the foundation; the permission profile
    is available (``read-only`` is not: ``PLUGIN_PROFILE_UNAVAILABLE``).
    """
    manifest_path = Path(path)
    try:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExtError("PLUGIN_MANIFEST_INVALID", f"the manifest cannot be read: {exc.__class__.__name__}") from None
    except ValueError:
        raise ExtError("PLUGIN_MANIFEST_INVALID", "the manifest is not valid JSON") from None
    problems = _validate(doc, "extension")
    if problems:
        raise ExtError("PLUGIN_MANIFEST_INVALID", f"the manifest does not match extension/v1: {_issues(problems)}")
    provides = doc["provides"]
    if doc["kind"] == "command" and not provides.get("points"):
        raise ExtError("PLUGIN_MANIFEST_INVALID", "a command plugin must list provides.points")
    if doc["kind"] == "subscriber" and not provides.get("events"):
        raise ExtError("PLUGIN_MANIFEST_INVALID", "a subscriber plugin must list provides.events")
    directory = manifest_path.parent
    entrypoint = _resolve_entrypoint(doc["entrypoint"], directory)
    low, high = int(doc["protocol"]["min"]), int(doc["protocol"]["max"])
    if low > high:
        raise ExtError("PLUGIN_MANIFEST_INVALID", "protocol.min is greater than protocol.max")
    if high < HOST_PROTOCOL[0] or low > HOST_PROTOCOL[1]:
        raise ExtError("PLUGIN_PROTOCOL_UNSUPPORTED", f"the plugin speaks protocol {low}-{high}; this host speaks "
                       f"{HOST_PROTOCOL[0]}-{HOST_PROTOCOL[1]}")
    host = _host_contracts()
    for requirement in doc.get("requires", []):
        if not set(requirement["versions"]) & set(host.get(requirement["contract"], [])):
            raise ExtError("PLUGIN_REQUIRES_UNSATISFIED", f"the plugin needs {requirement['contract']} "
                           f"{'/'.join(requirement['versions'])}, which this host does not provide")
    permissions = doc.get("permissions")
    effective_profile(permissions)
    return Manifest(path=manifest_path, directory=directory, id=doc["id"], kind=doc["kind"], version=doc["version"],
                    description=doc["description"], protocol=(low, high), entrypoint=entrypoint,
                    requires=tuple(doc.get("requires", [])), provides=provides, permissions=permissions,
                    timeout_seconds=doc.get("timeout_seconds"), example_input=doc.get("example_input"),
                    document=doc)


# --- registrations -------------------------------------------------------------------------------------------


def _problem(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


def registered_plugins(settings: "_settings.ExtSettings", *,
                       units: Optional[Mapping[str, "_units.UnitDoc"]] = None,
                       env: Optional[Mapping[str, str]] = None
                       ) -> Tuple[List[Registration], List[Dict[str, Any]]]:
    """The plugins of ``[aicore.plugins]`` ordered by id, and the problems of the enabled ones.

    Each manifest is loaded (not run). A problem is ``{"code", "plugin", "message"}``: a missing, relative or
    invalid manifest, ``PLUGIN_ID_MISMATCH`` when the entry name differs from the manifest id (the plugin is not
    used) and ``PLUGIN_POINT_UNKNOWN`` for a point no module declares in ``extension_points`` (the plugin is
    still used for its other points).
    """
    declared = _units.extension_points(units if units is not None else _units.discover_units(env))
    registrations: List[Registration] = []
    problems: List[Dict[str, Any]] = []
    for name in sorted(settings.plugins):
        body = settings.plugins[name]
        enabled = body.get("enabled", True) is not False
        manifest: Optional[Manifest] = None
        problem: Optional[Dict[str, str]] = None
        raw = body.get("manifest")
        if not isinstance(raw, str) or not raw:
            problem = _problem("PLUGIN_MANIFEST_INVALID", f"plugin {name} has no manifest path")
        elif not os.path.isabs(raw):
            problem = _problem("PLUGIN_MANIFEST_INVALID", f"the manifest path of plugin {name} must be absolute or "
                               "start with ~")
        else:
            try:
                manifest = load_manifest(raw)
            except ExtError as exc:
                problem = _problem(exc.code, exc.message)
        if manifest is not None and manifest.id != name:
            problem = _problem("PLUGIN_ID_MISMATCH", f"plugin entry {name} points to a manifest with id "
                               f"{manifest.id}")
        unknown = tuple(point for point in (manifest.points if manifest else []) if point not in declared)
        if name in settings.plugin_timeouts_set:
            timeout = body["timeout_seconds"]
        else:
            timeout = ((manifest.timeout_seconds if manifest else None) or body.get("timeout_seconds")
                       or DEFAULT_TIMEOUT_S)
        registrations.append(Registration(id=name, manifest_path=raw if isinstance(raw, str) else "",
                                          trusted=body.get("trusted", False) is True, timeout_seconds=timeout,
                                          enabled=enabled, manifest=manifest, problem=problem,
                                          unknown_points=unknown))
        if enabled:
            if problem:
                problems.append({"code": problem["code"], "plugin": name, "message": problem["message"]})
            for point in unknown:
                problems.append({"code": "PLUGIN_POINT_UNKNOWN", "plugin": name,
                                 "message": f"plugin {name} provides point {point}, which no module declares"})
    return registrations, problems


def _covered(pattern: str, declared: Sequence[str]) -> bool:
    return any(pattern == item or fnmatch.fnmatchcase(pattern, item) for item in declared)


def subscriber_problem(registrations: Sequence[Registration], plugin_id: str,
                       on: Sequence[str]) -> Optional[Tuple[str, str]]:
    """Why a subscription ``plugin = plugin_id`` with patterns ``on`` cannot be delivered, or None.

    ``PLUGIN_UNAVAILABLE`` for an unknown, disabled or broken plugin, ``SUBSCRIPTION_INVALID`` for a plugin that
    is not a subscriber or whose ``provides.events`` do not cover every pattern of ``on``.
    """
    registration = {item.id: item for item in registrations}.get(plugin_id)
    if registration is None:
        return "PLUGIN_UNAVAILABLE", f"plugin {plugin_id} is not registered in [aicore.plugins]"
    if not registration.enabled:
        return "PLUGIN_UNAVAILABLE", f"plugin {plugin_id} is disabled"
    if registration.problem is not None or registration.manifest is None:
        problem = registration.problem or _problem("PLUGIN_MANIFEST_INVALID", "no manifest")
        return "PLUGIN_UNAVAILABLE", f"plugin {plugin_id} cannot be used: {problem['code']}: {problem['message']}"
    manifest = registration.manifest
    if manifest.kind != "subscriber":
        return "SUBSCRIPTION_INVALID", f"plugin {plugin_id} is a {manifest.kind} plugin, not a subscriber"
    uncovered = [pattern for pattern in on if not _covered(pattern, manifest.events)]
    if uncovered:
        return "SUBSCRIPTION_INVALID", (f"plugin {plugin_id} does not declare the event pattern(s) "
                                        f"{', '.join(uncovered)} in provides.events")
    return None


# --- running a plugin ----------------------------------------------------------------------------------------


def _source_env(env: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if env is None else env


def _failure(registration: Registration, result: ProcessResult) -> PluginCallError:
    code = result.code or "PROCESS_EXIT"
    detail = f"exit {result.exit}" if result.exit is not None else "no exit status"
    tail = [line for line in result.stderr_tail.splitlines() if line.strip()]
    suffix = f"; stderr: {safe_text(tail[-1])}" if tail else ""
    return PluginCallError(code, f"plugin {registration.id}: {code} ({detail}){suffix}", result)


def _usable(registration: Registration) -> Manifest:
    """The manifest to run, freshly loaded (it may have changed since the registration was read)."""
    if registration.problem is not None:
        raise ExtError(registration.problem["code"], registration.problem["message"])
    if registration.manifest is None:
        raise ExtError("PLUGIN_MANIFEST_INVALID", f"plugin {registration.id} has no manifest")
    manifest = load_manifest(registration.manifest.path)
    if manifest.id != registration.id:
        raise ExtError("PLUGIN_ID_MISMATCH", f"plugin entry {registration.id} points to a manifest with id "
                       f"{manifest.id}")
    return manifest


def _launch(registration: Registration, manifest: Manifest, fields: Mapping[str, Any], *, deadline_s: float,
            env: Optional[Mapping[str, str]], project: Optional[PathLike],
            attempt: int = 1) -> Tuple[Dict[str, Any], ProcessResult]:
    """Run the plugin once and return its validated ``plugin-response/v1`` document and the process result."""
    try:
        child_env, secrets = clean_environment(_source_env(env), permissions=manifest.permissions,
                                               trusted=registration.trusted)
    except ConfigError as exc:
        raise ExtError("PLUGIN_SECRET_UNRESOLVED", f"a secret of plugin {registration.id} cannot be resolved "
                       f"({exc.code})") from None
    request: Dict[str, Any] = {"$schema": REQUEST_SCHEMA, "protocol": "1", "request_id": uuid.uuid4().hex,
                               "deadline_ms": max(1, int(deadline_s * 1000))}
    request.update(fields)
    request["context"] = {"project_root": str(project) if project is not None else None, "attempt": attempt,
                          "trusted": registration.trusted}
    result = run_json(list(manifest.entrypoint), request, deadline_s=deadline_s, env=child_env,
                      cwd=str(project) if project is not None else str(manifest.directory),
                      secrets_to_redact=secrets, max_stdout=manifest.max_stdout)
    if not result.ok:
        raise _failure(registration, result)
    document = result.document
    if document is None:
        raise PluginCallError("PLUGIN_RESPONSE_INVALID", f"plugin {registration.id} answered nothing", result)
    problems = _validate(document, "plugin-response")
    if problems:
        raise PluginCallError("PLUGIN_RESPONSE_INVALID", f"plugin {registration.id} answered a document that does "
                              f"not match plugin-response/v1: {_issues(problems)}", result)
    if document["request_id"] != request["request_id"]:
        raise PluginCallError("PLUGIN_RESPONSE_INVALID", f"plugin {registration.id} answered another request id",
                              result)
    if document["status"] == "error" and "error" not in document:
        raise PluginCallError("PLUGIN_RESPONSE_INVALID", f"plugin {registration.id} reported an error without "
                              "error.code", result)
    if len(document.get("diagnostics", [])) > MAX_DIAGNOSTICS:
        raise PluginCallError("PLUGIN_RESPONSE_INVALID", f"plugin {registration.id} sent more than "
                              f"{MAX_DIAGNOSTICS} diagnostics", result)
    return document, result


def describe_plugin(registration: Registration, *, env: Optional[Mapping[str, str]] = None,
                    project: Optional[PathLike] = None) -> Describe:
    """Start the plugin with ``op: describe`` and compare its answer with the manifest.

    Raises ``PLUGIN_HANDSHAKE_MISMATCH`` naming the first field that differs, or the code of a failed
    start/answer. Nothing is cached: every call starts the plugin.
    """
    manifest = _usable(registration)
    document, result = _launch(registration, manifest, {"op": "describe"}, deadline_s=DESCRIBE_DEADLINE_S, env=env,
                               project=project)
    if document["status"] != "ok" or not isinstance(document.get("output"), dict):
        code = safe_text(document.get("error", {}).get("code", "")) or document["status"]
        raise PluginCallError("PLUGIN_HANDSHAKE_MISMATCH", f"plugin {registration.id} answered describe with "
                              f"{code} instead of its description", result)
    output = document["output"]
    problems = _validate(output, "plugin-describe")
    if problems:
        raise PluginCallError("PLUGIN_HANDSHAKE_MISMATCH", f"plugin {registration.id} sent a description that does "
                              f"not match plugin-describe/v1: {_issues(problems)}", result)
    expected = {"id": manifest.id, "version": manifest.version, "kind": manifest.kind,
                "capabilities_digest": manifest.capabilities_digest}
    for name, value in expected.items():
        if output[name] != value:
            raise PluginCallError("PLUGIN_HANDSHAKE_MISMATCH", f"plugin {registration.id}: {name} is "
                                  f"{safe_text(output[name])!r} in the description but {value!r} in the manifest",
                                  result)
    protocol = int(output["protocol"])
    shared = (max(manifest.protocol[0], HOST_PROTOCOL[0]), min(manifest.protocol[1], HOST_PROTOCOL[1]))
    if not shared[0] <= protocol <= shared[1]:
        raise PluginCallError("PLUGIN_HANDSHAKE_MISMATCH", f"plugin {registration.id}: protocol {protocol} is "
                              "outside the range shared by the manifest and the host", result)
    return Describe(id=output["id"], kind=output["kind"], version=output["version"], protocol=output["protocol"],
                    capabilities_digest=output["capabilities_digest"], transport=output["transport"],
                    duration_ms=result.duration_ms)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def invoke_one(registration: Registration, point: str, input: Mapping[str, Any], *,
               env: Optional[Mapping[str, str]] = None, project: Optional[PathLike] = None) -> PluginResult:
    """Describe, then invoke one plugin at ``point``; a refusal or failure is an ``error`` result, not an exception."""
    started = time.monotonic()
    try:
        manifest = _usable(registration)
        if manifest.kind != "command" or point not in manifest.points:
            raise ExtError("PLUGIN_POINT_UNKNOWN", f"plugin {registration.id} does not provide point {point}")
        describe_plugin(registration, env=env, project=project)
        document, _result = _launch(registration, _usable(registration),
                                    {"op": "invoke", "point": point, "input": dict(input)},
                                    deadline_s=registration.timeout_seconds, env=env, project=project)
    except ExtError as exc:
        return PluginResult(registration.id, "error", None, exc.message, exc.code, _elapsed_ms(started))
    if document["status"] == "error":
        error = document["error"]
        return PluginResult(registration.id, "error", None, safe_text(error["message"]), error["code"],
                            _elapsed_ms(started))
    return PluginResult(registration.id, document["status"], document.get("output"), None, None,
                        _elapsed_ms(started))


def invoke_point(point: str, input: Mapping[str, Any], *, project: Optional[PathLike] = None,
                 env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
                 config_file: Optional[PathLike] = None) -> List[PluginResult]:
    """Call every enabled command plugin that provides ``point``, by plugin id.

    ``point`` must be declared by a module (``PLUGIN_POINT_UNKNOWN`` otherwise). One plugin failing does not
    stop the others; the caller decides what an ``error`` result means. A broken configuration raises
    ``CONFIG_INVALID``.
    """
    if not isinstance(input, Mapping):
        raise ValueError("input must be a mapping")
    units = _units.discover_units(env)
    if point not in _units.extension_points(units):
        raise ExtError("PLUGIN_POINT_UNKNOWN", f"no module declares the extension point {point}")
    settings = _settings.load(project, env=env, home=home, config_file=config_file)
    registrations, _problems = registered_plugins(settings, units=units, env=env)
    return [invoke_one(registration, point, input, env=env, project=project) for registration in registrations
            if registration.enabled and registration.manifest is not None and registration.manifest.kind == "command"
            and point in registration.manifest.points]


def deliver_event(registration: Registration, event: Mapping[str, Any], *, attempt: int = 1,
                  deadline_s: float = DEFAULT_TIMEOUT_S, env: Optional[Mapping[str, str]] = None,
                  project: Optional[PathLike] = None) -> Tuple[str, Optional[str], ProcessResult]:
    """Describe, then send ``event`` to a subscriber plugin: ``(outcome, code, result)``.

    ``outcome`` is ``ok``, ``skipped`` or ``failed``; ``code`` names a failure (the plugin's own code when it
    answered ``status: error``). Never raises for a plugin or process problem.
    """
    started = time.monotonic()

    def failed(code: str, result: Optional[ProcessResult]) -> Tuple[str, Optional[str], ProcessResult]:
        base = result or ProcessResult(False, code, None, None, "", 0, False)
        return "failed", code, base._replace(duration_ms=_elapsed_ms(started))

    try:
        manifest = _usable(registration)
        if manifest.kind != "subscriber":
            raise ExtError("SUBSCRIPTION_INVALID", f"plugin {registration.id} is not a subscriber")
        describe_plugin(registration, env=env, project=project)
        document, result = _launch(registration, _usable(registration), {"op": "event", "event": dict(event)},
                                   deadline_s=deadline_s, env=env, project=project, attempt=attempt)
    except PluginCallError as exc:
        return failed(exc.code, exc.result)
    except ExtError as exc:
        return failed(exc.code, None)
    if document["status"] == "error":
        return failed(document["error"]["code"], result)
    return document["status"], None, result._replace(duration_ms=_elapsed_ms(started))


# --- status --------------------------------------------------------------------------------------------------


def list_plugins(project: Optional[PathLike] = None, *, env: Optional[Mapping[str, str]] = None,
                 home: Optional[PathLike] = None, config_file: Optional[PathLike] = None) -> Dict[str, Any]:
    """``{"plugins": [row, ...], "problems": [...]}``; nothing is started.

    A row has ``id, kind, version, manifest`` (with ``~``), ``trusted, enabled, profile`` (``{"profile",
    "enforced"}``), ``points, events, ignored`` (what an untrusted plugin asked for and did not get),
    ``unknown_points`` and ``problem``.
    """
    environment = _source_env(env)
    settings = _settings.load(project, env=env, home=home, config_file=config_file)
    registrations, problems = registered_plugins(settings, env=env)
    rows = []
    for registration in registrations:
        manifest = registration.manifest
        permissions = manifest.permissions if manifest else None
        rows.append({
            "id": registration.id, "kind": manifest.kind if manifest else None,
            "version": manifest.version if manifest else None,
            "manifest": _settings.collapse_home(registration.manifest_path, environment, home),
            "trusted": registration.trusted, "enabled": registration.enabled,
            "profile": {"profile": (permissions or {}).get("profile", "trusted-local"), "enforced": False},
            "points": manifest.points if manifest else [], "events": manifest.events if manifest else [],
            "ignored": ignored_requests(permissions, trusted=registration.trusted) if manifest else [],
            "unknown_points": list(registration.unknown_points), "problem": registration.problem})
    return {"plugins": rows, "problems": problems}


def find_registration(plugin_id: str, project: Optional[PathLike] = None, *,
                      env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
                      config_file: Optional[PathLike] = None) -> Registration:
    """The registration named ``plugin_id`` (``PLUGIN_NOT_FOUND`` when the configuration has none)."""
    settings = _settings.load(project, env=env, home=home, config_file=config_file)
    registrations, _problems = registered_plugins(settings, env=env)
    for registration in registrations:
        if registration.id == plugin_id:
            return registration
    raise ExtError("PLUGIN_NOT_FOUND", f"no plugin {plugin_id} in [aicore.plugins]")
