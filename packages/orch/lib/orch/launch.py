"""Launch catalog: how each orchestration role starts on each provider CLI. Builds argv only; never runs a process."""
from __future__ import annotations

import json
from pathlib import Path
import re

ROLES = ("scout", "executor", "bounded-implementer", "reviewer", "triager", "registrar", "report-fixer",
         "researcher", "advisor")
PROVIDERS = ("claude-code", "codex", "grok")
MODEL_CLASSES = ("economy", "implementation", "frontier")
EFFORTS = ("low", "medium", "high", "xhigh")
TRANSPORTS = ("text", "jsonl", "acp")
MODEL_SETS = ("supported", "unknown")
PLACEHOLDERS = frozenset({"model", "effort", "cwd", "orch"})
ENTRY_KEYS = frozenset({"model_class", "effort", "transport", "argv", "timeout_s", "model_set"})
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
    if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
        raise _invalid(where, f"entry must hold exactly: {', '.join(sorted(ENTRY_KEYS))}")
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
    """The validated catalog; ``LaunchError`` when unreadable or malformed."""
    target = Path(path) if path else CATALOG_PATH
    try:
        catalog = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _invalid(str(target), f"cannot read catalog ({error})") from error
    validate_catalog(catalog)
    return catalog


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
               effort: str | None = None, cwd: str | Path = ".") -> list[str]:
    """Command line for ``role`` on ``provider``. ``model`` is required when the CLI takes one (model_set supported)."""
    found = entry(catalog, role, provider)
    effort = effort or found["effort"]
    if effort not in EFFORTS:
        raise _invalid("effort", f"must be one of {', '.join(EFFORTS)}")
    if found["model_set"] == "supported" and not model:
        raise _invalid("model", f"role {role!r} on {provider!r} needs a model")
    # `{orch}` is this package root, so an entry can call a launcher shipped under `scripts/`.
    values = {"model": model or "", "effort": effort, "cwd": str(cwd), "orch": str(ORCH_ROOT)}
    return [_PLACEHOLDER_RE.sub(lambda m: values[m[1]], arg) for arg in found["argv"]]
