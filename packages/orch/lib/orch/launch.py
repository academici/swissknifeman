"""Launch catalog: how each orchestration role starts on each provider CLI. Builds argv only; never runs a process."""
from __future__ import annotations

from collections.abc import Mapping
import copy
import json
import os
from pathlib import Path
import re

ROLES = ("scout", "executor", "bounded-implementer", "reviewer", "triager", "registrar", "report-fixer",
         "researcher", "advisor")
ANTIGRAVITY_AUTHORITY_PROBLEM = (
    "AGY_AUTHORITY_UNPROVEN: Antigravity tool network, IPC and host read isolation "
    "has no verified enforcement; HOME and Landlock write guards are insufficient"
)
AGY_OPT_IN = "SKM_ORCH_AGY_UNSAFE_EXECUTOR"
AGY_OPT_IN_VALUE = "accept-unisolated-network-docker-host-reads"


def agy_executor_opted_in(role: str) -> bool:
    """A per-process, explicit owner opt-in, never an implicit provider capability."""
    return role == "executor" and os.environ.get(AGY_OPT_IN) == AGY_OPT_IN_VALUE
PROVIDERS = ("claude-code", "codex", "grok", "antigravity")
MODEL_CLASSES = ("economy", "implementation", "frontier")
EFFORTS = ("low", "medium", "high", "xhigh")
TRANSPORTS = ("text", "jsonl", "acp")
MODEL_SETS = ("supported", "unknown")
PLACEHOLDERS = frozenset({"model", "effort", "cwd", "orch", "write_sandbox"})
# ``resume_argv`` is the optional command line that continues a provider session (``codex exec resume {session}``): the same
# placeholders and one more, ``{session}``, which only the conductor knows when it starts the role.
RESUME_PLACEHOLDERS = PLACEHOLDERS | {"session"}
# How far a role that writes may reach (``[orch.launch] access``): ``open`` gives the provider CLI its widest mode, ``confined``
# keeps it inside the workspace. ``{write_sandbox}`` in an argv is the sandbox mode of a provider CLI for such a role; a role
# that must not write names its read-only mode itself, whatever the access.
ACCESS = ("open", "confined")
WRITE_SANDBOX = {"open": "danger-full-access", "confined": "workspace-write"}
ENTRY_KEYS = frozenset({"model_class", "effort", "transport", "argv", "timeout_s", "model_set"})
OPTIONAL_ENTRY_KEYS = frozenset({"resume_argv"})
ORCH_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ORCH_ROOT / "configs" / "launch-catalog.json"
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class LaunchError(ValueError):
    """``LAUNCH_INVALID`` for malformed input, ``LAUNCH_UNKNOWN`` for a missing pair,
    ``LAUNCH_REFUSED`` for a pair explicitly refused by the catalog."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _invalid(where: str, message: str) -> LaunchError:
    return LaunchError("LAUNCH_INVALID", f"{where}: {message}")


def _validate_entry(where: str, role: str, entry: object) -> None:
    if not isinstance(entry, dict) or not ENTRY_KEYS <= set(entry) <= ENTRY_KEYS | OPTIONAL_ENTRY_KEYS:
        raise _invalid(where, f"entry must hold exactly: {', '.join(sorted(ENTRY_KEYS))}"
                              f" (and optionally {', '.join(sorted(OPTIONAL_ENTRY_KEYS))})")
    for key, allowed in (("model_class", MODEL_CLASSES), ("effort", EFFORTS), ("transport", TRANSPORTS),
                         ("model_set", MODEL_SETS)):
        if entry[key] not in allowed:
            raise _invalid(f"{where}/{key}", f"must be one of {', '.join(allowed)}")
    if role == "scout" and entry["transport"] != "text":
        raise _invalid(f"{where}/transport", "scout output is plain text")
    timeout = entry["timeout_s"]
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise _invalid(f"{where}/timeout_s", "must be a positive integer")
    argv = entry["argv"]
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv) or not argv[0]:
        raise _invalid(f"{where}/argv", "must be a non-empty list of strings starting with the command")
    if "--bare" in argv:
        raise _invalid(f"{where}/argv", "--bare is forbidden")
    used = {name for arg in argv for name in _PLACEHOLDER_RE.findall(arg)}
    if used - PLACEHOLDERS:
        raise _invalid(f"{where}/argv", f"unknown placeholder(s) {sorted(used - PLACEHOLDERS)}; allowed {sorted(PLACEHOLDERS)}")
    if (entry["model_set"] == "supported") != ("model" in used):
        raise _invalid(f"{where}/argv", "{model} must appear exactly when model_set is supported")
    if "resume_argv" in entry:
        _validate_resume(f"{where}/resume_argv", entry["resume_argv"], entry["model_set"])


def _validate_resume(where: str, argv: object, model_set: str) -> None:
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv) or not argv[0]:
        raise _invalid(where, "must be a non-empty list of strings starting with the command")
    if "--bare" in argv:
        raise _invalid(where, "--bare is forbidden")
    used = {name for arg in argv for name in _PLACEHOLDER_RE.findall(arg)}
    if used - RESUME_PLACEHOLDERS:
        raise _invalid(where, f"unknown placeholder(s) {sorted(used - RESUME_PLACEHOLDERS)}; "
                              f"allowed {sorted(RESUME_PLACEHOLDERS)}")
    if "session" not in used:
        raise _invalid(where, "{session} must appear: it is the session the command continues")
    if (model_set == "supported") != ("model" in used):
        raise _invalid(where, "{model} must appear exactly when model_set is supported")


# The file may state a catalog compactly: ``defaults`` for every entry, per role the fields its providers share, named argv
# ``parts`` (an ``@name`` item of an argv stands for the whole part; ``@@`` is a literal ``@``) and per provider only what
# differs. ``expand_catalog`` gives the resolved form (``launch`` -> role -> provider -> entry) that everything else reads.
COMPACT_KEYS = frozenset({"catalog_version", "defaults", "parts", "roles", "refusals"})
FIELD_KEYS = ENTRY_KEYS - {"argv"}
ENTRY_ORDER = ("model_class", "effort", "transport", "argv", "resume_argv", "timeout_s", "model_set")
_PART_NAME = re.compile(r"^[a-z][a-z0-9.-]*$")


def _expand_argv(where: str, argv: object, parts: dict, used: set) -> list:
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
        raise _invalid(where, "must be a non-empty list of strings")
    out: list = []
    for arg in argv:
        if arg.startswith("@@"):
            out.append(arg[1:])
        elif arg.startswith("@"):
            if arg[1:] not in parts:
                raise _invalid(where, f"unknown part {arg!r}")
            used.add(arg[1:])
            out.extend(parts[arg[1:]])
        else:
            out.append(arg)
    return out


def expand_catalog(raw: object) -> object:
    """The resolved catalog of a file in the compact form; a file in the resolved form (it has ``launch``) is returned
    as it is. Raises ``LaunchError`` for a compact file that is malformed; the result is still to be validated."""
    if not isinstance(raw, dict) or "roles" not in raw:
        return raw
    if "launch" in raw or set(raw) - COMPACT_KEYS or not {"catalog_version", "roles"} <= set(raw):
        raise _invalid("/", "a compact catalog holds catalog_version, roles and optionally defaults, parts and refusals "
                            "(and no launch)")
    defaults, parts, roles = raw.get("defaults", {}), raw.get("parts", {}), raw["roles"]
    if not isinstance(defaults, dict) or set(defaults) - FIELD_KEYS:
        raise _invalid("/defaults", f"must be an object over: {', '.join(sorted(FIELD_KEYS))}")
    if not isinstance(parts, dict):
        raise _invalid("/parts", "must be an object")
    for name, part in parts.items():
        where = f"/parts/{name}"
        if not _PART_NAME.match(name):
            raise _invalid(where, "a part name is lowercase words, dots and dashes")
        if not isinstance(part, list) or not part or not all(isinstance(arg, str) for arg in part):
            raise _invalid(where, "must be a non-empty list of strings")
        if any(arg.startswith("@") and not arg.startswith("@@") for arg in part):
            raise _invalid(where, "a part cannot name another part")
    if not isinstance(roles, dict):
        raise _invalid("/roles", "must be an object")
    launch: dict = {}
    used: set = set()
    for role, body in roles.items():
        where = f"/roles/{role}"
        if not isinstance(body, dict) or set(body) - FIELD_KEYS - {"providers"} or not isinstance(body.get("providers"), dict):
            raise _invalid(where, f"must hold providers and optionally: {', '.join(sorted(FIELD_KEYS))}")
        shared = {**defaults, **{key: value for key, value in body.items() if key != "providers"}}
        launch[role] = {}
        for provider, own in body["providers"].items():
            if not isinstance(own, dict) or set(own) - ENTRY_KEYS - OPTIONAL_ENTRY_KEYS or "argv" not in own:
                raise _invalid(f"{where}/providers/{provider}", "must hold argv and optionally the fields that differ "
                                                                "and resume_argv")
            argv = _expand_argv(f"{where}/providers/{provider}/argv", own["argv"], parts, used)
            merged = {**shared, **{key: value for key, value in own.items() if key not in ("argv", "resume_argv")},
                      "argv": argv}
            if "resume_argv" in own:
                merged["resume_argv"] = _expand_argv(f"{where}/providers/{provider}/resume_argv", own["resume_argv"],
                                                     parts, used)
            launch[role][provider] = {key: merged[key] for key in ENTRY_ORDER if key in merged}  # the order readers print
    if set(parts) - used:
        raise _invalid("/parts", f"unused part(s) {sorted(set(parts) - used)}")
    resolved = {"catalog_version": raw["catalog_version"], "launch": launch}
    if "refusals" in raw:
        resolved["refusals"] = raw["refusals"]
    return resolved


def validate_catalog(catalog: object) -> None:
    """Raise ``LaunchError`` unless every role holds known providers with fully specified entries."""
    if not isinstance(catalog, dict) or set(catalog) not in ({"catalog_version", "launch"},
                                                          {"catalog_version", "launch", "refusals"}):
        raise _invalid("/", "catalog must hold catalog_version, launch and optionally refusals")
    launch = catalog["launch"]
    if not isinstance(launch, dict) or set(launch) != set(ROLES):
        raise _invalid("/launch", f"must hold exactly the roles: {', '.join(ROLES)}")
    for role, providers in launch.items():
        if not isinstance(providers, dict) or not providers or set(providers) - set(PROVIDERS):
            raise _invalid(f"/launch/{role}", f"must be a non-empty object over providers: {', '.join(PROVIDERS)}")
        for provider, entry in providers.items():
            _validate_entry(f"/launch/{role}/{provider}", role, entry)
    refusals = catalog.get("refusals", {})
    if not isinstance(refusals, dict) or set(refusals) - set(ROLES):
        raise _invalid("/refusals", f"must be an object over roles: {', '.join(ROLES)}")
    for role, providers in refusals.items():
        if not isinstance(providers, dict) or set(providers) - set(PROVIDERS):
            raise _invalid(f"/refusals/{role}", f"must be an object over providers: {', '.join(PROVIDERS)}")
        for provider, reason in providers.items():
            where = f"/refusals/{role}/{provider}"
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
                raise _invalid(where, "reason must be a non-empty string of at most 300 characters")
            if provider in launch[role]:
                raise _invalid(where, "pair is present in both launch and refusals")


def load_catalog(path: str | Path | None = None) -> dict:
    """The validated catalog in its resolved form (a compact file is expanded first); ``LaunchError`` when unreadable or
    malformed."""
    target = Path(path) if path else CATALOG_PATH
    try:
        catalog = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _invalid(str(target), f"cannot read catalog ({error})") from error
    catalog = expand_catalog(catalog)
    validate_catalog(catalog)
    return catalog


_OVERRIDE_KEY = re.compile(r"^(?P<role>[a-z][a-z0-9-]*)_(?P<provider>[a-z][a-z0-9-]*)$")


def apply_entries(catalog: dict, entries: Mapping) -> dict:
    """A copy of ``catalog`` with the fields of ``entries`` (``{ROLE_PROVIDER: {field: value}}``, the ``[orch.launch.entries]``
    of the configuration) put over the entries they name; the result is validated like a catalog. A key of a role or
    provider the catalog has no entry for is ``LAUNCH_UNKNOWN`` (a new entry comes with a whole catalog file)."""
    merged = copy.deepcopy(catalog)
    for key, fields in entries.items():
        named = _OVERRIDE_KEY.match(key)
        found = merged["launch"].get(named["role"], {}).get(named["provider"]) if named else None
        if found is None:
            raise LaunchError("LAUNCH_UNKNOWN", f"[orch.launch.entries.{key}]: the catalog has no entry for it "
                                                "(the key is ROLE_PROVIDER)")
        found.update(copy.deepcopy(dict(fields)))
    try:
        validate_catalog(merged)
    except LaunchError as error:
        raise LaunchError(error.code, f"[orch.launch.entries] {error}") from None
    return merged


def effective_catalog(launch_settings: Mapping | None = None, path: str | Path | None = None) -> dict:
    """The catalog a run uses: ``path``, else the file ``[orch.launch] catalog`` names, else the one shipped with orch;
    with ``[orch.launch.entries]`` put over it. Without settings it is :func:`load_catalog`."""
    found = launch_settings if isinstance(launch_settings, Mapping) else {}
    catalog = load_catalog(path or found.get("catalog") or None)
    return apply_entries(catalog, found["entries"]) if found.get("entries") else catalog


def entry_origin(launch_settings: Mapping | None, role: str, provider: str, field: str) -> str | None:
    """Where ``field`` of the entry comes from when the configuration changes it: ``orch.launch.entries.<key>.<field>`` with
    its layer, else None (the catalog)."""
    entries = (launch_settings or {}).get("entries") or {}
    if field in (entries.get(f"{role}_{provider}") or {}):
        return f"orch.launch.entries.{role}_{provider}.{field}"
    return None


def entry(catalog: dict, role: str, provider: str) -> dict:
    """The catalog entry of ``role`` on ``provider``."""
    found = catalog["launch"].get(role, {}).get(provider)
    if found is None:
        reason = catalog.get("refusals", {}).get(role, {}).get(provider)
        if reason is not None:
            raise LaunchError("LAUNCH_REFUSED", f"{role}/{provider}: {reason}")
        raise LaunchError("LAUNCH_UNKNOWN", f"no launch entry for role {role!r} on provider {provider!r}")
    return found


def build_argv(catalog: dict, role: str, provider: str, *, model: str | None = None,
               effort: str | None = None, cwd: str | Path = ".", access: str = "open") -> list[str]:
    """Command line for ``role`` on ``provider``. ``model`` is required when the CLI takes one (model_set supported);
    ``access`` (``open`` or ``confined``) sets the ``{write_sandbox}`` of an entry."""
    found = entry(catalog, role, provider)
    effort = effort or found["effort"]
    if effort not in EFFORTS:
        raise _invalid("effort", f"must be one of {', '.join(EFFORTS)}")
    if found["model_set"] == "supported" and not model:
        raise _invalid("model", f"role {role!r} on {provider!r} needs a model")
    # `{orch}` is this package root, so an entry can call a launcher shipped under `scripts/`.
    if access not in ACCESS:
        raise _invalid("access", f"must be one of {', '.join(ACCESS)}")
    values = {"model": model or "", "effort": effort, "cwd": str(cwd), "orch": str(ORCH_ROOT),
              "write_sandbox": WRITE_SANDBOX[access]}
    return [_PLACEHOLDER_RE.sub(lambda m: values[m[1]], arg) for arg in found["argv"]]


def build_resume_argv(catalog: dict, role: str, provider: str, *, model: str | None = None,
                      effort: str | None = None, cwd: str | Path = ".", access: str = "open") -> list[str] | None:
    """Command line that continues a session of ``role`` on ``provider``, or ``None`` when the entry has no ``resume_argv``.
    Every placeholder is filled but ``{session}``, which the conductor fills with the session it resumes."""
    found = entry(catalog, role, provider)
    if "resume_argv" not in found:
        return None
    effort = effort or found["effort"]
    if effort not in EFFORTS:
        raise _invalid("effort", f"must be one of {', '.join(EFFORTS)}")
    if found["model_set"] == "supported" and not model:
        raise _invalid("model", f"role {role!r} on {provider!r} needs a model")
    if access not in ACCESS:
        raise _invalid("access", f"must be one of {', '.join(ACCESS)}")
    values = {"model": model or "", "effort": effort, "cwd": str(cwd), "orch": str(ORCH_ROOT),
              "write_sandbox": WRITE_SANDBOX[access], "session": "{session}"}
    return [_PLACEHOLDER_RE.sub(lambda m: values[m[1]], arg) for arg in found["resume_argv"]]
