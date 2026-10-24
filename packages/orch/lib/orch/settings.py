"""Layered ``[orch]`` configuration and the choice of the execution engine (docs/configuration.md).

``load`` resolves the section through ``aicore.config`` (defaults -> machine file -> project file -> environment ->
``--config`` file -> flags); orch never reads ``config.toml`` itself. ``affecting`` and ``digest`` name the values
that change what preparation produces, so a launch-plan can record the configuration it was built from.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
from pathlib import Path
import tempfile

from aicore.config import ResolvedConfig, resolve
from aicore.config.units import foundation_root
from aicore.util import digest as _digest

from orch.conductor import questions, risk
from orch.port import BINDINGS

ORCH_ROOT = Path(__file__).resolve().parents[2]
ENGINE_REASONS = {
    "flag": "ENGINE_FROM_FLAG",
    "role": "ENGINE_FROM_ROLE",
    "config": "ENGINE_FROM_CONFIG",
}


class SettingsError(ValueError):
    """``ENGINE_UNKNOWN``: a requested engine is not one of the bindings; ``PROFILES_DIR_RELATIVE``: a relative pack folder;
    ``LAUNCH_CATALOG_RELATIVE``: a relative launch catalog file."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Settings:
    """The effective ``[orch]`` configuration. ``profiles_dirs`` are absolute paths with ``~`` expanded."""

    engine: str
    engine_by_role: Mapping[str, str]
    default_profile: str
    work_source: str
    capabilities_stale: str
    profiles_dirs: tuple
    events_enabled: bool
    resolved: ResolvedConfig | None = None
    conductor: Mapping[str, object] = field(default_factory=dict)
    aicore: ResolvedConfig | None = None  # the ``aicore`` module: ``providers.available`` is read from it (routing)
    research: Mapping[str, object] = field(default_factory=dict)  # ``[orch.research]``: ``policy`` and ``sources``
    advisor: Mapping[str, object] = field(default_factory=dict)  # ``[orch.advisor]``: ``enabled``, ``max_rounds``, ``human_gate``, ``panel``, ``panel_on``
    stubs: Mapping[str, object] = field(default_factory=dict)  # ``[orch.stubs]``: ``enabled``, ``layers``
    launch: Mapping[str, object] = field(default_factory=dict)  # ``[orch.launch]``: ``catalog`` (a file), ``access`` and ``entries``
    supervisor: Mapping[str, object] = field(default_factory=dict)  # ``[orch.supervisor]``: ``recover`` (already the lowest of the layers), ``max_recoveries``, ...
    debug: bool = False  # ``[orch] debug`` / ``--debug``: the observer protocol and journal of a run (conductor.debug_mode)

    def explain_text(self, key: str | None = None) -> str:
        """Where each value comes from (empty when the settings were built by hand)."""
        return "" if self.resolved is None else self.resolved.explain_text(key)


def _dirs(resolved: ResolvedConfig) -> tuple:
    """``profiles.dirs`` as absolute paths. ``~`` is expanded; a relative entry is refused (``PROFILES_DIR_RELATIVE``),
    because the folder of the file that wrote it cannot be told once a higher layer appends to the array."""
    found = []
    for text in resolved.get("profiles.dirs"):
        path = Path(os.path.expanduser(text))
        if not path.is_absolute():
            raise SettingsError("PROFILES_DIR_RELATIVE", f"profiles.dirs entry {text!r} must be absolute or start with ~")
        found.append(path)
    return tuple(found)


def _conductor(resolved: ResolvedConfig) -> dict:
    """``[orch.conductor]`` as plain data: the global layer of the run options and the role command lines."""
    question_mode = resolved.get("conductor.questions")
    if question_mode not in questions.MODES:
        raise SettingsError("QUESTIONS_UNKNOWN", f"conductor.questions must be one of {', '.join(questions.MODES)}")
    return {
        "provider": resolved.get("conductor.provider"),
        # only a reviewer a layer sets is an explicit one: the shipped default leaves the plan's review route its say
        "reviewer": resolved.get("conductor.reviewer")
        if resolved.explain("conductor.reviewer")[0].layer != "defaults" else None,
        "registrar": resolved.get("conductor.registrar"),
        "rules": list(resolved.get("conductor.rules") or []),
        "on_blocked": resolved.get("conductor.on_blocked"),
        "foreign_untracked": resolved.get("conductor.foreign_untracked"),
        "session_executor": resolved.get("conductor.session_executor"),
        "questions": question_mode,
        # Internal authority evidence, separate from the customizable heuristic risk score.
        "_category_patterns": _category_patterns(resolved),
        "limits": {key: resolved.get(f"conductor.limits.{key}")
                   for key in ("tokens_max", "tokens_hard_max", "run_tokens_hard_max",
                               "stage_timeout_s", "stage_idle_timeout_s", "check_timeout_s",
                               "check_idle_timeout_s", "unmetered", "unmetered_charge_tokens", "role_timeout_s")},
        "risk": {"weights": {key: resolved.get(f"conductor.risk.weights.{key}") for key in risk.DEFAULT_WEIGHTS},
                 "patterns": {key: list(resolved.get(f"conductor.risk.patterns.{key}") or [])
                              for key in risk.DEFAULT_PATTERNS},
                 "diff_lines": resolved.get("conductor.risk.diff_lines"),
                 "critical": resolved.get("conductor.risk.critical")},
        "skills_bridge": list(resolved.get("conductor.skills_bridge") or []),
        "generate": list(resolved.get("conductor.generate") or []),
        "generate_check": list(resolved.get("conductor.generate_check") or []),
        "generated_paths": list(resolved.get("conductor.generated_paths") or []),
        "argv": {role: list(argv) for role, argv in (resolved.get("conductor.argv") or {}).items()},
    }


def _category_patterns(resolved: ResolvedConfig) -> dict:
    """Retain builtin and established trusted patterns even across replacement and _unset history."""
    patterns = {}
    for feature in ("security", "public_cli", "schema"):
        entry = resolved.explain(f"conductor.risk.patterns.{feature}")[0]
        floor = set(risk.DEFAULT_PATTERNS[feature])
        for setting in [entry, *entry.overridden]:
            if setting.layer in ("machine", "invocation", "flags") and setting.source != "_unset":
                floor.update(setting.value or [])
        patterns[feature] = sorted(floor)
    return patterns


def _launch(resolved: ResolvedConfig) -> dict:
    """``[orch.launch]`` as plain data: the catalog file (absolute, ``~`` expanded; empty for the shipped one) and the
    changes to single entries by ``ROLE_PROVIDER``."""
    named = resolved.get("launch.catalog") or ""
    path = Path(os.path.expanduser(named)) if named else None
    if path is not None and not path.is_absolute():
        raise SettingsError("LAUNCH_CATALOG_RELATIVE", f"launch.catalog {named!r} must be absolute or start with ~")
    return {"catalog": str(path) if path else "", "access": _access(resolved),
            "entries": {key: dict(fields) for key, fields in (resolved.get("launch.entries") or {}).items()}}


def _access(resolved: ResolvedConfig) -> str:
    """``launch.access``: project and environment settings can only tighten the trusted access floor."""
    found = resolved.explain("launch.access")[0]
    history: list = list(reversed(found.overridden))  # the overridden settings, then the winner
    if found.layer == "defaults":
        # After _unset the default is reported as the winner, while the reset stays in overridden.
        history.insert(0, found)
    else:
        history.append(found)
    access = found.default
    for setting in history:
        value = found.default if setting.source == "_unset" else setting.value
        if setting.layer in ("defaults", "machine", "invocation", "flags") or value == "confined":
            access = value
    return access


RECOVER_ORDER = ("notify", "stop-only", "resume")  # from the weakest policy to the strongest


def effective_recover(machine: str, *invocation: str | None) -> str:
    """The lowest policy of the machine value and the invocation values (a flag, a ``--config`` file): an invocation can
    only weaken what the machine allows, never widen it (I8)."""
    values = [machine, *(value for value in invocation if value is not None)]
    for value in values:
        if value not in RECOVER_ORDER:
            raise SettingsError("RECOVER_UNKNOWN", f"supervisor recover must be one of {', '.join(RECOVER_ORDER)}, not {value!r}")
    return min(values, key=RECOVER_ORDER.index)


def _layered(resolved: ResolvedConfig, key: str, lowest) -> object:
    """Effective value of an authority key: the machine value (defaults when the machine sets none), lowered by every
    invocation value (``--config`` file, flag) with ``lowest`` (``min`` or the order of the policy)."""
    found = resolved.explain(key)[0]
    history: list = list(reversed(found.overridden))  # the overridden settings, then the winner
    if found.layer == "defaults":
        history.insert(0, found)  # after _unset the default is reported as the winner, the reset stays in overridden
    else:
        history.append(found)
    machine, lowered = found.default, []
    for setting in history:
        value = found.default if setting.source == "_unset" else setting.value
        if setting.layer in ("defaults", "machine"):
            machine = value
        elif setting.layer in ("invocation", "flags"):
            lowered.append(value)
    return lowest(machine, *lowered)


def _supervisor(resolved: ResolvedConfig) -> dict:
    """``[orch.supervisor]`` as plain data: ``recover`` and ``max_recoveries`` are the lowest of the machine and invocation
    values, ``window_s`` the highest (a shorter window forgets recoveries sooner, which widens the budget)."""
    return {"recover": _layered(resolved, "supervisor.recover", effective_recover),
            "max_recoveries": _layered(resolved, "supervisor.max_recoveries", lambda *values: min(values)),
            "window_s": _layered(resolved, "supervisor.window_s", lambda *values: max(values)),
            **{key: resolved.get(f"supervisor.{key}") for key in ("interval_s", "hung_after_s", "grace_s", "notify_send")}}


def _research(resolved: ResolvedConfig) -> dict:
    """``[orch.research]`` as plain data: the policy and the sources by id (every field of an entry, defaults filled in)."""
    return {"policy": resolved.get("research.policy"),
            "sources": {name: dict(entry) for name, entry in (resolved.get("research.sources") or {}).items()}}


def _panel_member(text: str) -> dict:
    """``PROVIDER[/MODEL_CLASS[/EFFORT]]`` of ``advisor.panel`` as the route override of a stage."""
    return dict(zip(("provider", "model_class", "effort"), text.split("/")))


def _advisor(resolved: ResolvedConfig) -> dict:
    """Effective advisor authority: extra gates accumulate and confidence can only rise across layers."""
    def values(key: str) -> list:
        # explain() includes overwritten settings and _unset records, even after a reset to the default.
        entry = resolved.explain(key)[0]
        return [entry.value] + [setting.value for setting in entry.overridden if setting.value is not None]

    extra = {category for value in values("advisor.human_gate_extra") for category in value}
    ranks = {"low": 0, "medium": 1, "high": 2}
    return {"enabled": bool(resolved.get("advisor.enabled")), "max_rounds": int(resolved.get("advisor.max_rounds")),
            "human_gate": sorted(set(resolved.get("advisor.human_gate") or []) | extra),
            "min_confidence": max(values("advisor.min_confidence"), key=ranks.__getitem__),
            "panel": [_panel_member(text) for text in resolved.get("advisor.panel") or []],
            "panel_on": list(resolved.get("advisor.panel_on") or [])}


def load(*, project: str | Path | None = None, config_file: str | Path | None = None,
         env: Mapping[str, str] | None = None, home: str | Path | None = None,
         flags: Mapping[str, object] | None = None) -> Settings:
    """Resolve ``[orch]`` for a project (``None``: no project layer). Raises ``aicore.config.ConfigError``."""
    resolved = resolve("orch", unit_root=ORCH_ROOT, project=project, config_file=config_file, env=env, home=home,
                       flags=flags)
    foundation = resolve("aicore", schema=foundation_root() / "configs" / "config.schema.json", project=project,
                         config_file=config_file, env=env, home=home)
    return Settings(
        engine=resolved.get("engine"),
        engine_by_role=dict(resolved.get("engine_by_role") or {}),
        default_profile=resolved.get("default_profile"),
        work_source=resolved.get("work_source"),
        capabilities_stale=resolved.get("capabilities.stale"),
        profiles_dirs=_dirs(resolved),
        events_enabled=resolved.get("events.enabled"),
        resolved=resolved,
        conductor=_conductor(resolved),
        aicore=foundation,
        research=_research(resolved),
        advisor=_advisor(resolved),
        stubs={"enabled": bool(resolved.get("stubs.enabled")), "layers": list(resolved.get("stubs.layers") or [])},
        launch=_launch(resolved),
        supervisor=_supervisor(resolved),
        debug=bool(resolved.get("debug")),
    )


def defaults() -> Settings:
    """The settings of the schema defaults alone: no machine, project or environment layer is read."""
    with tempfile.TemporaryDirectory(prefix="orch-defaults-") as home:
        return load(project=None, env={}, home=home)


def affecting(settings: Settings) -> dict:
    """The values that change what preparation produces (the other keys do not enter the digest)."""
    return {
        "engine": settings.engine,
        "engine_by_role": dict(sorted(settings.engine_by_role.items())),
        "default_profile": settings.default_profile,
        "capabilities.stale": settings.capabilities_stale,
    }


def digest(settings: Settings) -> str:
    """SHA-256 hex of the canonical JSON of :func:`affecting`."""
    return _digest.sha256_hex(_digest.canonical_json_bytes(affecting(settings)))


def config_digest(settings: Settings) -> str:
    """Tagged digest of the effective ``[orch]`` and ``[aicore.providers]`` (``None`` for a part that was not resolved):
    two runs with the same digest ran under the same configuration."""
    providers = settings.aicore.get("providers") if settings.aicore is not None else None
    return _digest.digest_json({"orch": settings.resolved.as_dict() if settings.resolved is not None else None,
                                "aicore.providers": providers})


def config_layers(settings: Settings) -> list:
    """The configuration layers behind the digest: ``[{layer, file, present}]``, lowest first."""
    if settings.resolved is None:
        return []
    return [{"layer": layer.name, "file": layer.file, "present": layer.present} for layer in settings.resolved.layers]


def select_engine(settings: Settings, role: str, *, flag: str | None = None, stage_id: str = "*") -> tuple:
    """``(binding, decision)``: the flag, else ``engine_by_role[role]``, else ``engine``.

    ``decision`` is an element of ``launch-plan.decisions`` of kind ``binding``; the sources that were overridden
    are listed after the chosen one. No other engine is ever substituted: whether the chosen engine can honour a
    stage is decided by preparation, which refuses when it cannot.
    """
    sources = []
    if flag is not None:
        sources.append(("flag", flag))
    if role in settings.engine_by_role:
        sources.append(("role", settings.engine_by_role[role]))
    sources.append(("config", settings.engine))
    for _, name in sources:
        if name not in BINDINGS:
            raise SettingsError("ENGINE_UNKNOWN", f"unknown engine {name!r}; one of {', '.join(BINDINGS)}")
    (first, chosen), rest = sources[0], sources[1:]
    considered = [{"candidate": chosen, "accepted": True, "reason_codes": [ENGINE_REASONS[first]]}]
    considered += [{"candidate": name, "accepted": False, "reason_codes": ["ENGINE_OVERRIDDEN"]}
                   for _, name in rest if name != chosen]
    return chosen, {"stage_id": stage_id, "kind": "binding", "chosen": chosen, "considered": considered}
