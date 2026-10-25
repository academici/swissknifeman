"""The isolation of a role from the provider's own settings (``instructions.isolate_roles``, ``instructions.isolation``):
the profiles of ``configs/isolation-profiles.json`` (``conductor/v1`` ``isolation-profiles``) say per provider which
arguments, environment and home directories keep the repository instructions, memory, plugins, hooks, MCP servers and
personal skills out, and what is left. Data, never a branch by provider name.

The guarantee is honest: ``full`` only when every required surface of the profile is ``off`` or confirmed off by a live
probe of this CLI version (``isolation-probes``, written by ``scripts/isolation-probe.py --live``); a flag the CLI does
not list, a command that is not a provider CLI it can ask (a wrapper), a surface left unconfirmed or a drift seen in the
init event of the stream make it ``partial``. ``require``
refuses a role whose plan is not ``full`` (``ISOLATION_UNAVAILABLE``); ``prefer`` runs it and says so; ``off`` adds
nothing. The probes (the flags the CLI lists, its version, the probe record) are the caller's: these functions get
their results as arguments."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from orch.conductor import contract
from orch.conductor.domain.stop import Stop
from orch.settings import ORCH_ROOT

PROFILES_PATH = ORCH_ROOT / "configs" / "isolation-profiles.json"
PROBES_FILE = "isolation-probes.json"  # under the orch state folder of the machine
MODES = ("off", "prefer", "require")  # weakest first: a work-source layer may only move to the right
# The surfaces that decide the guarantee; ``project_permissions`` is authority, not an instruction surface.
REQUIRED_SURFACES = ("repository_instructions", "memory", "plugins", "hooks", "mcp", "user_skills")
UNAVAILABLE_HINT = "set instructions.isolation = prefer in a trusted layer or remove the role from isolate_roles"
_CACHE: dict = {}  # (path, mtime_ns, size) -> profiles


def load_profiles(path: Path = PROFILES_PATH) -> dict:
    """``{provider: profile}`` of the profiles file, checked against its schema and against itself (a declared
    guarantee must agree with the surfaces); ``Stop ISOLATION_PROFILES_INVALID: <path>: <first problem>`` otherwise."""
    path = Path(path)
    try:
        status = path.stat()
        key = (str(path), status.st_mtime_ns, status.st_size)
        if key in _CACHE:
            return _CACHE[key]
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Stop("ISOLATION_PROFILES_INVALID", f"{path}: {error}") from None
    issues = contract.problems(doc, "isolation-profiles") or profile_problems(doc)
    if issues:
        raise Stop("ISOLATION_PROFILES_INVALID", f"{path}: {issues[0]}")
    _CACHE[key] = doc["providers"]
    return doc["providers"]


def profile_problems(doc: dict) -> list:
    """What the schema cannot see: a declared ``full`` with a required surface that is not ``off``, a ``partial``
    whose required surfaces are all ``off``."""
    issues = []
    for provider, profile in sorted(doc.get("providers", {}).items()):
        open_ = [name for name in REQUIRED_SURFACES if profile["surfaces"][name] != "off"]
        if profile["guarantee"] == "full" and open_:
            issues.append(f"/providers/{provider}/guarantee: full, but {', '.join(open_)} is not off")
        if profile["guarantee"] == "partial" and not open_:
            issues.append(f"/providers/{provider}/guarantee: partial, but every required surface is off")
    return issues


def confirmed(probes: list, provider: str, version: Optional[str]) -> list:
    """The surfaces a live probe of ``provider`` at ``version`` found not loaded (claims ``false``)."""
    if not version:
        return []
    return sorted({name for entry in probes if entry.get("provider") == provider and entry.get("version") == version
                   for name, loaded in (entry.get("claims") or {}).items() if loaded is False})


def probes_problems(doc: object) -> list:
    """Violations of ``isolation-probes`` by ``doc``."""
    return contract.problems(doc, "isolation-probes")


def guarantee_of(profile: dict, confirmed_surfaces=()) -> tuple:
    """``(guarantee, unconfirmed)``: ``full`` when every required surface is ``off`` or confirmed, else ``partial``
    with the surfaces that are not; a profile that declares ``none`` stays ``none``."""
    unconfirmed = [name for name in REQUIRED_SURFACES
                   if profile["surfaces"][name] != "off" and name not in confirmed_surfaces]
    if profile["guarantee"] == "none":
        return "none", unconfirmed
    return ("partial" if unconfirmed else "full"), unconfirmed


def plan(role: str, route: dict, *, isolated: bool, mode: str, profile: Optional[dict], probe: Optional[dict] = None,
         auth: Optional[str] = None) -> dict:
    """The isolation of ``role`` on ``route``: ``{role, provider, mode, isolated, guarantee, args, env, home, missing,
    unconfirmed, degraded}``. ``probe`` holds what the caller found: ``listed`` (flag -> whether the CLI lists it),
    ``failed`` (its help could not be read), ``confirmed`` (surfaces a live probe of this version confirmed) and
    ``drift`` (an earlier role of the run showed what the profile keeps out) and ``unprobed`` (the command of the route is
    not a provider CLI that could be asked: the flags are passed, the guarantee stays partial). ``auth`` is ``link`` or ``copy`` from the
    configuration. A role that is not isolated, or ``mode`` ``off``, gets nothing and the guarantee ``none``."""
    provider = route.get("provider") or ""
    found = {"role": role, "provider": provider, "mode": mode, "isolated": bool(isolated) and mode != "off",
             "guarantee": "none", "args": [], "env": {}, "home": None, "missing": [], "unconfirmed": [], "degraded": []}
    if not found["isolated"]:
        return found
    if profile is None:
        found["degraded"].append({"code": "PROFILE_MISSING", "detail": f"no isolation profile for {provider}"})
        return found
    probe = probe or {}
    listed = probe.get("listed") or {}
    missing = [flag for flag in profile["probe"]["flags"] if not listed.get(flag)]
    guarantee, unconfirmed = guarantee_of(profile, probe.get("confirmed") or ())
    degraded = []
    if probe.get("unprobed"):  # a wrapper or a stand-in: its flags are passed as asked, never confirmed
        degraded.append({"code": "PROBE_UNAVAILABLE",
                         "detail": "the command of the route is not a provider CLI the profile can probe"})
    if probe.get("failed"):
        degraded.append({"code": "PROBE_FAILED", "detail": f"{' '.join(profile['probe']['help'])} could not be read"})
    if missing:
        degraded.append({"code": "FLAG_MISSING", "detail": f"the CLI does not list {' '.join(missing)}"})
    if unconfirmed:
        degraded.append({"code": "SURFACES_UNCONFIRMED", "detail": ", ".join(
            f"{name} {profile['surfaces'][name]}" for name in unconfirmed)})
    if probe.get("drift"):
        degraded.append({"code": "ISOLATION_DRIFT", "detail": f"an earlier {provider} role of this run loaded "
                                                              "what the profile keeps out"})
    if guarantee == "full" and (missing or probe.get("drift") or probe.get("failed") or probe.get("unprobed")):
        guarantee = "partial"
    home = profile.get("home")
    found.update(guarantee=guarantee, args=[arg for arg in profile["args"] if arg not in missing],
                 env=dict(profile["env"]), home=dict(home, mode=auth or home["mode"]) if home else None,
                 missing=missing, unconfirmed=unconfirmed, degraded=degraded)
    return found


def problem(isolation: dict) -> Optional[str]:
    """``ISOLATION_UNAVAILABLE: <role>/<provider>: <guarantee> isolation (<why>); <hint>`` when ``instructions.isolation``
    is ``require`` and the plan of an isolated role is not ``full``; ``None`` otherwise."""
    if isolation["mode"] != "require" or not isolation["isolated"]:
        return None
    if isolation["guarantee"] == "full" and not isolation["missing"]:
        return None
    why = "; ".join(entry["detail"] for entry in isolation["degraded"]) or "no isolation"
    return (f"ISOLATION_UNAVAILABLE: {isolation['role']}/{isolation['provider']}: {isolation['guarantee']} isolation "
            f"({why}); {UNAVAILABLE_HINT}")


def partial_notes(isolation: dict) -> list:
    """``[(reason, message)]`` of a ``prefer`` plan that is not ``full``: what ``ISOLATION_PARTIAL`` says, once per run,
    provider and reason. A missing flag is said by the flag probe itself."""
    if not isolation["isolated"] or isolation["mode"] != "prefer" or isolation["guarantee"] == "full":
        return []
    return [(entry["code"], f"{isolation['provider']}: {isolation['guarantee']} isolation ({entry['detail']})")
            for entry in isolation["degraded"] if entry["code"] != "FLAG_MISSING"]


def drift(profile: Optional[dict], init: Optional[dict]) -> list:
    """``[(field, names)]``: the fields of the init event the profile wants empty that are not (``observe.empty``)."""
    observe = (profile or {}).get("observe")
    if not observe or not init:
        return []
    return [(name, list(init[name])) for name in observe["empty"] if init.get(name)]


def home_dir(isolation: dict, run_dir: Path) -> str:
    """The home of the provider in an isolated launch (the first variable of ``home.vars``, ``<run dir>/isolation/<name>``),
    ``""`` when the provider keeps its own."""
    home = isolation.get("home")
    if not home:
        return ""
    return str(Path(run_dir) / "isolation" / next(iter(home["vars"].values())))
