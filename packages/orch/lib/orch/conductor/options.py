"""Run options of the conductor: layers, their merge and the selectors of roles.

Layers merge from the general to the specific: the defaults, ``[orch.conductor]`` of the configuration, the run-policy
pack, then the layers the work source hands over (the options of the plan, the phase and the item, in that order). A
more specific layer overrides a value; ``rules`` append (a repeated rule is kept once), ``limits`` and ``on_error`` merge by
key (``fallback_routes`` is replaced as a list; ``[]`` switches the routes of the layers below off),
``skills`` replace the list of each role a layer names, and ``stages`` merge by role (a layer that names a model or a
model class replaces both of the role). Every layer of the source is checked against ``conductor/v1``
``run-options`` (its numeric bounds included) before it is used. The merged options keep ``skills`` as a map
from role to names.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re

from aicore.util.digest import digest_json

from orch.conductor import contract

# Most limits are targets and beacons: no role and no check is stopped for being long (the owner or an observer
# reads the STAGE_SLOW / STAGE_IDLE / CHECK_SLOW beacons and decides); rounds go past their target while they make
# progress, up to ``ceiling_factor`` times it. The wall-clock ceilings stage_timeout_s, check_timeout_s and run_timeout_s
# stay available, off by default. Only silence is a wall: a role whose stream has not grown for 90 minutes, or a check
# whose log has not grown for an hour, is hung, and an unattended run must not wait for it forever. Explicit hard token
# limits stop admission at the boundary of accounted usage; they do not interrupt a running model call.
DEFAULT_LIMITS = {"review_rounds": 2, "corrections": 1, "check_fixes": 1, "retries": 1, "tokens_max": 0,
                  "tokens_hard_max": 0, "run_tokens_hard_max": 0,
                  "stage_timeout_s": 0, "stage_idle_timeout_s": 5400, "check_timeout_s": 0,
                  "check_idle_timeout_s": 3600, "ceiling_factor": 2,
                  "repairs": 1, "stage_warn_s": 2700, "stage_idle_warn_s": 600, "check_warn_s": 900, "provider_wait_max_s": 900,
                  "run_warn_s": 7200, "run_timeout_s": 0, "review_rounds_batch": 0, "corrections_batch": 0,
                  "findings_batch": 0, "question_warn_s": 1800, "skill_tokens_max": 5000,
                  "prompt_core_tokens": 12000, "prompt_supporting_tokens": 30000, "prompt_retrieval_tokens": 50000,
                  "disk_min_gb": 5}
DEFAULT_REVIEW = {"correct_min_severity": "Major", "pre_final": True, "final_correction": False,
                  "audit_scope": "corrected", "dynamic": True, "dynamic_threshold": 60,
                  "strategy": "auto", "strategist": "rules"}
DEFAULT_INSTRUCTIONS = {"isolate_roles": ["context-scout", "executor", "bounded-implementer", "reviewer", "triager", "registrar",
                                         "report-fixer", "researcher", "advisor"],
                        "module_rules": ["module-folders", "module-boundaries", "engineering-invariants"],
                        "sandbox": "prefer", "sandbox_domains": [], "file_tools_rule": True}
# ``fence``: ``project`` (default) lets the executor change any file of the project and report the paths outside the plan's
# write set as deviations; ``plan`` keeps the write set a fence (a path outside it blocks the piece). ``extra_paths``:
# directories outside the project the executor may also change (the filesystem guard gets them as ``--rw``).
DEFAULT_SCOPE = {"outside": "deviation", "fence": "project", "extra_paths": []}
# How the executor sessions of a run of several pieces are kept. ``handoff`` (default): each piece starts a fresh session
# that its correction rounds resume, and its prompt carries the handoff of the earlier pieces (summary, commit, notes), so
# a later piece does not re-read the whole transcript of the earlier ones on every turn. ``shared``: one session for all
# pieces (a piece resumes the session of the previous executor). ``per-item``: a fresh session for every executor step.
SESSION_MODES = ("handoff", "shared", "per-item")
DEFAULT_SESSION = {"executor": "handoff"}
DEFAULT_CHECKS = {"parallel": 2, "overlap_review": False, "executor_runs_checks": False,
                  "red_first": True, "fail_fast": True, "reuse": True,
                  "kinds": ["acceptance", "impact"], "cadence": ["item", "phase"]}
SEVERITIES = ("Blocker", "Major", "Minor", "Nit")  # most severe first
# A review is too dear to lose when its provider cannot start, is gated or fails: the default reviewer (grok) has a fallback.
# A layer with its own ``fallback_routes`` replaces this list, ``fallback_routes: []`` ends it.
DEFAULT_FALLBACK_ROUTES = [{"role": "reviewer", "provider": "claude-code", "model_class": "frontier", "effort": "high"}]
AUTO_SKILLS = "auto"  # the one name of a role's skills that asks the skills bridge to choose them from the work
DEFAULTS = {"stages": [], "reviewer": "grok/grok-4.7/high", "rules": [], "skills": {}, "limits": DEFAULT_LIMITS,
            "review": DEFAULT_REVIEW, "checks": DEFAULT_CHECKS, "instructions": DEFAULT_INSTRUCTIONS, "scope": DEFAULT_SCOPE,
            "session": DEFAULT_SESSION, "on_blocked": "stop", "on_error": {}, "fallback_routes": DEFAULT_FALLBACK_ROUTES}
ROLE_ALIASES = {"scout": "context-scout"}
MODEL_ROLES = ("context-scout", "executor", "bounded-implementer", "reviewer", "triager", "registrar", "report-fixer",
               "researcher", "advisor")
_SELECTOR = re.compile(r"^(?P<provider>[a-z][a-z0-9-]*)/(?P<model>[A-Za-z0-9][A-Za-z0-9._:-]*)"
                       r"(?:/(?P<context>[0-9]+[kKmM]?))?(?:/(?P<effort>low|medium|high|xhigh|max|ultra))?$")
_ACTOR = re.compile(r"^(?P<provider>[a-z][a-z0-9-]*)/(?P<model>[A-Za-z0-9][A-Za-z0-9._:-]*)"
                    r"(?:/(?P<effort>low|medium|high|xhigh|max|ultra))?$")


# Layers that come from the machine or the operator: the configuration, the run-policy pack and the invocation layers
# the conductor itself marks ``trusted`` (``--options``, flags). Every other layer is handed over by the work source (the
# plan, a phase, an item, an overlay document, an input file): text a model may have written, so it can tighten the
# isolation of a run, never loosen it. Trust is a mark the conductor sets, never read from the layer's own ``source``.
# Ordered keys: a work-source layer may only move them to the right.
FLOOR_ORDER = {("instructions", "sandbox"): ("off", "prefer", "require"),
               ("scope", "fence"): ("project", "plan"),
               ("scope", "outside"): ("deviation", "block")}
# Set keys: a work-source layer may only shrink ``narrow`` ones (a subset of what the layers below allow) and only grow
# ``widen`` ones; ``extra_paths`` it may only repeat or shrink, so a plan cannot open a directory outside the project.
FLOOR_NARROW = (("instructions", "sandbox_domains"), ("scope", "extra_paths"))
FLOOR_WIDEN = (("instructions", "isolate_roles"),)
# Folders an extra writable path may never be, contain, or lie in (besides the root, HOME and the project's ancestors).
SYSTEM_DIRS = ("/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/proc", "/run", "/sbin", "/sys", "/usr", "/var")
HOME_SECRETS = (".ssh", ".gnupg", ".aws", ".kube", ".docker", ".netrc", ".password-store")


class OptionsError(ValueError):
    """``OPTIONS_INVALID``: a layer is outside ``run-options``; ``SELECTOR_INVALID``: a selector does not parse;
    ``OPTIONS_UNTRUSTED``: a work-source layer loosens the isolation the layers below set; ``OPTIONS_UNSAFE_PATH``: an
    extra writable path is a system, home or ancestor folder."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def parse_selector(text: str) -> dict:
    """``PROVIDER/MODEL[/CONTEXT][/EFFORT]`` as ``{provider, model[, context][, effort]}``."""
    match = _SELECTOR.match(text or "")
    if match is None:
        raise OptionsError("SELECTOR_INVALID", f"{text!r} is not PROVIDER/MODEL[/CONTEXT][/EFFORT]")
    return {key: value for key, value in match.groupdict().items() if value}


def parse_actor(text: str) -> dict:
    """``PROVIDER/MODEL[/EFFORT]`` as a work-source actor."""
    match = _ACTOR.match(text or "")
    if match is None:
        raise OptionsError("SELECTOR_INVALID", f"{text!r} is not PROVIDER/MODEL[/EFFORT]")
    return {key: value for key, value in match.groupdict().items() if value}


def _dedupe(values: list) -> list:
    seen, out = set(), []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _merge_stages(base: list, layer: list) -> list:
    out = [dict(entry) for entry in base]
    for entry in layer:
        entry = {**entry, "role": ROLE_ALIASES.get(entry["role"], entry["role"])}
        known = next((item for item in out if item["role"] == entry["role"]), None)
        if known is None:
            out.append(dict(entry))
            continue
        if "model" in entry or "model_class" in entry:
            known.pop("model", None)
            known.pop("model_class", None)
        known.update(entry)
    return out


def merge(base: dict, layer: dict) -> dict:
    """``layer`` over ``base`` by the rules of this module; neither argument is changed."""
    out = copy.deepcopy(base)
    for key, value in layer.items():
        if key == "stages":
            out["stages"] = _merge_stages(out.get("stages", []), value)
        elif key == "rules":
            out["rules"] = _dedupe(list(out.get("rules", [])) + list(value))
        elif key in ("limits", "review", "checks", "instructions", "scope", "session", "on_error"):
            out[key] = {**out.get(key, {}), **copy.deepcopy(value)}
        elif key == "skills":
            out[key] = {**out.get(key, {}), **{entry["role"]: list(entry["names"]) for entry in value}}
        else:
            out[key] = copy.deepcopy(value)
    return out


def config_layer(conductor: dict) -> dict:
    """The layer of ``[orch.conductor]``."""
    layer = {key: conductor[key] for key in ("reviewer", "rules", "on_blocked") if conductor.get(key) is not None}
    limits = {key: value for key, value in (conductor.get("limits") or {}).items() if value is not None}
    if limits:
        layer["limits"] = limits
    if conductor.get("session_executor") is not None:
        layer["session"] = {"executor": conductor["session_executor"]}
    return layer


def policy_layer(policy: dict) -> dict:
    """The layer of a run-policy pack: the routes its model stages request, the triage and the review limits."""
    stages = []
    for stage in policy.get("stages", []):
        role = ROLE_ALIASES.get(stage.get("role"), stage.get("role"))
        if role in MODEL_ROLES:
            stages.append({"role": role, **{key: stage[key] for key in ("provider", "model_class", "effort")
                                            if key in stage}})
    review = policy.get("review") or {}
    triage = review.get("triage")
    if isinstance(triage, dict) and triage.get("role") in MODEL_ROLES:
        stages.append({"role": triage["role"], **({"model_class": triage["model_class"]}
                                                   if "model_class" in triage else {})})
    limits = {}
    if "max_rounds" in review:
        limits["review_rounds"] = review["max_rounds"]
    if "max_corrections" in review:
        limits["corrections"] = review["max_corrections"]
    budget = (policy.get("retries_budget") or {}).get("total_max")
    if isinstance(budget, int):
        limits["retries"] = budget
    layer = {"stages": stages}
    if limits:
        layer["limits"] = limits
    return layer


def effective(conductor: dict, policy: dict, layers: list) -> tuple:
    """``(options, sources)``: the merged options and, per key, the layer that set it last.

    ``layers`` are ``{"source": text, "options": object[, "trusted": true]}`` entries, general first: those of the work
    source, then the invocation ones the conductor marks ``trusted``.
    """
    sources: dict = {}
    current = copy.deepcopy(DEFAULTS)

    def apply(name: str, layer: dict) -> None:
        nonlocal current
        current = merge(current, layer)
        for key, value in layer.items():
            if key in ("limits", "review", "checks", "instructions", "scope", "session", "on_error"):
                sources.update({f"{key}.{sub}": name for sub in value})
            elif key == "skills":
                sources.update({f"skills.{entry['role']}": name for entry in value})
            elif key == "stages":
                sources.update({f"stages.{ROLE_ALIASES.get(entry['role'], entry['role'])}": name for entry in value})
            else:
                sources[key] = name

    apply("config:orch.conductor", config_layer(conductor))
    apply(f"policy:{policy.get('policy_id', '-')}", policy_layer(policy))
    for layer in layers:
        name, found = layer.get("source", "source"), layer.get("options")
        issues = layer_problems(found)
        if issues:
            raise OptionsError("OPTIONS_INVALID", f"{name}: {'; '.join(issues[:3])}")
        if layer.get("trusted") is not True:
            if "run_tokens_hard_max" in (found.get("limits") or {}):
                raise OptionsError("OPTIONS_INVALID", "run_tokens_hard_max is a run limit; set it in the configuration or --options")
            loosened = floor_problems(current, found, sources)
            if loosened:
                raise OptionsError("OPTIONS_UNTRUSTED", f"{name}: {'; '.join(loosened)} (only the configuration, the "
                                   "run-policy pack or the invocation (--options, flags) may loosen the isolation)")
        apply(name, found)
    validate_limits(current["limits"])
    parse_selector(current["reviewer"])
    return current, sources


def validate_limits(limits: dict) -> None:
    """The informational target must fit inside an enabled hard limit."""
    soft, hard = limits.get("tokens_max", 0), limits.get("tokens_hard_max", 0)
    if soft > 0 and hard > 0 and soft > hard:
        raise OptionsError("OPTIONS_INVALID", "tokens_max must not exceed tokens_hard_max")


def floor_problems(current: dict, layer: dict, sources: dict) -> list:
    """How ``layer`` would loosen the isolation of the options merged so far (empty when it only keeps or tightens it)."""
    issues = []

    def below(group: str, key: str) -> str:
        return sources.get(f"{group}.{key}", "defaults")

    for (group, key), order in FLOOR_ORDER.items():
        if key in (layer.get(group) or {}):
            old, new = current[group][key], layer[group][key]
            if order.index(new) < order.index(old):
                issues.append(f"{group}.{key} {new} is weaker than {old} of {below(group, key)}")
    for group, key in FLOOR_NARROW:
        if key in (layer.get(group) or {}):
            added = sorted(set(layer[group][key]) - set(current[group][key]))
            if added:
                issues.append(f"{group}.{key} adds {', '.join(added)} to what {below(group, key)} allows")
    for group, key in FLOOR_WIDEN:
        if key in (layer.get(group) or {}):
            dropped = sorted(set(current[group][key]) - set(layer[group][key]))
            if dropped:
                issues.append(f"{group}.{key} drops {', '.join(dropped)} kept by {below(group, key)}")
    return issues


def checked_extra_paths(paths, project, home=None) -> list:
    """``scope.extra_paths`` as canonical folders (``~`` expanded, symlinks resolved), refused with
    ``OPTIONS_UNSAFE_PATH`` when one is the root, a system folder, HOME or an ancestor of it, an ancestor of the project
    (or the project itself), a folder of secrets under HOME, or lies in a ``.git`` folder."""
    import os

    home = os.path.realpath(os.path.expanduser("~") if home is None else str(home))
    project = os.path.realpath(str(project))
    out = []
    for path in paths or []:
        expanded = os.path.expanduser(path) if path.startswith("~") else path
        real = os.path.realpath(expanded)

        def within(base: str, real=real) -> bool:
            return real == base or real.startswith(base.rstrip("/") + "/")

        why = None
        if real == "/" or not os.path.isabs(expanded):
            why = "the root or a relative path"
        elif any(within(system) for system in SYSTEM_DIRS) and not within(home):
            why = "a system folder"
        elif home == real or home.startswith(real.rstrip("/") + "/"):
            why = "HOME or one of its ancestors"
        elif project == real or project.startswith(real.rstrip("/") + "/"):
            why = "the project or one of its ancestors"
        elif any(within(os.path.join(home, name)) for name in HOME_SECRETS):
            why = "a folder of secrets under HOME"
        elif ".git" in Path(real).parts:
            why = "inside a .git folder"
        if why:
            raise OptionsError("OPTIONS_UNSAFE_PATH", f"scope.extra_paths {path!r} ({real}) is {why}")
        out.append(real)
    return out


def layer_problems(layer: dict) -> list:
    """Problems of one layer: ``run-options`` (its bounds included), then what the schema cannot say (``auto`` listed
    together with other skills)."""
    return contract.problems(layer, "run-options") or [f"/skills/{entry['role']}: \"auto\" cannot be listed together with other skills"
            for entry in layer.get("skills") or [] if AUTO_SKILLS in entry["names"] and len(entry["names"]) > 1]


def digest(options: dict) -> str:
    """Tagged digest of the merged options of a piece of work: the same layers give the same digest."""
    return digest_json(options)


def stage_route(options: dict, role: str) -> dict:
    """The route of ``role`` in the merged options (``{}`` when no layer names it)."""
    return next((dict(entry) for entry in options.get("stages", []) if entry["role"] == role), {})
