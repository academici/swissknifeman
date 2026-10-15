"""Run options of the conductor: layers, their merge and the selectors of roles.

Layers merge from the general to the specific: the defaults, ``[orch.conductor]`` of the configuration, the run-policy
pack, then the layers the work source hands over (the options of the plan, the phase and the item, in that order). A
more specific layer overrides a value; ``rules`` append (a repeated rule is kept once), ``limits`` and ``on_error`` merge by
key (``fallback_routes`` is replaced as a list; ``[]`` switches the routes of the layers below off),
``skills`` replace the list of each role a layer names, and ``stages`` merge by role (a layer that names a model or a
model class replaces both of the role). Every layer of the source is checked against ``conductor/v1``
``run-options`` and the bounds of ``LIMIT_BOUNDS`` before it is used. The merged options keep ``skills`` as a map
from role to names.
"""
from __future__ import annotations

import copy
import re

from aicore.util.digest import digest_json

from orch.conductor import contract

# Limits are targets and beacons, not walls: no role and no check is stopped for being long (the owner or an observer
# reads the STAGE_SLOW / STAGE_IDLE / CHECK_SLOW beacons and decides); rounds go past their target while they make
# progress, up to ``ceiling_factor`` times it. The *_timeout_s ceilings stay available, off by default.
DEFAULT_LIMITS = {"review_rounds": 2, "corrections": 1, "check_fixes": 1, "retries": 1, "tokens_max": 0,
                  "stage_timeout_s": 0, "stage_idle_timeout_s": 0, "check_timeout_s": 0, "ceiling_factor": 2,
                  "repairs": 1, "stage_warn_s": 2700, "stage_idle_warn_s": 600, "check_warn_s": 900, "provider_wait_max_s": 900,
                  "run_warn_s": 7200, "run_timeout_s": 0, "review_rounds_batch": 0, "corrections_batch": 0,
                  "findings_batch": 0, "question_warn_s": 1800, "skill_tokens_max": 5000,
                  "prompt_core_tokens": 12000, "prompt_supporting_tokens": 30000, "prompt_retrieval_tokens": 50000}
DEFAULT_REVIEW = {"correct_min_severity": "Major", "pre_final": True, "final_correction": False,
                  "audit_scope": "corrected", "dynamic": True, "dynamic_threshold": 60,
                  "strategy": "auto", "strategist": "model"}
REVIEW_BOUNDS = {"dynamic_threshold": (0, 100)}
DEFAULT_INSTRUCTIONS = {"isolate_roles": ["context-scout", "executor", "bounded-implementer", "reviewer", "triager", "registrar",
                                         "report-fixer", "researcher", "advisor"],
                        "module_rules": ["module-folders", "module-boundaries", "engineering-invariants"],
                        "sandbox": "prefer", "sandbox_domains": []}
# ``fence``: ``project`` (default) lets the executor change any file of the project and report the paths outside the plan's
# write set as deviations; ``plan`` keeps the write set a fence (a path outside it blocks the piece). ``extra_paths``:
# directories outside the project the executor may also change (the filesystem guard gets them as ``--rw``).
DEFAULT_SCOPE = {"outside": "deviation", "fence": "project", "extra_paths": []}
# One executor session for all pieces of a run: a piece (and a correction round of it) resumes the session of the
# previous executor, so the later pieces start with what the earlier ones learned. ``per-item``: a fresh session each.
SESSION_MODES = ("shared", "per-item")
DEFAULT_SESSION = {"executor": "shared"}
DEFAULT_CHECKS = {"parallel": 1, "overlap_review": False, "executor_runs_checks": False,
                  "red_first": True,
                  "kinds": ["acceptance", "impact"], "cadence": ["item", "phase"]}
CHECKS_BOUNDS = {"parallel": (1, 8)}
SEVERITIES = ("Blocker", "Major", "Minor", "Nit")  # most severe first
# A review is too dear to lose when its provider cannot start, is gated or fails: the default reviewer (grok) has a fallback.
# A layer with its own ``fallback_routes`` replaces this list, ``fallback_routes: []`` ends it.
DEFAULT_FALLBACK_ROUTES = [{"role": "reviewer", "provider": "claude-code", "model_class": "frontier", "effort": "high"}]
AUTO_SKILLS = "auto"  # the one name of a role's skills that asks the skills bridge to choose them from the work
DEFAULTS = {"stages": [], "reviewer": "grok/grok-4.7/high", "rules": [], "skills": {}, "limits": DEFAULT_LIMITS,
            "review": DEFAULT_REVIEW, "checks": DEFAULT_CHECKS, "instructions": DEFAULT_INSTRUCTIONS, "scope": DEFAULT_SCOPE,
            "session": DEFAULT_SESSION, "on_blocked": "stop", "on_error": {}, "fallback_routes": DEFAULT_FALLBACK_ROUTES}
LIMIT_BOUNDS = {"review_rounds": (0, 5), "corrections": (0, 3), "check_fixes": (0, 3), "retries": (0, 5),
                "tokens_max": (0, None), "stage_timeout_s": (0, None), "stage_idle_timeout_s": (0, None),
                "check_timeout_s": (0, None), "ceiling_factor": (1, 5), "repairs": (0, 3), "stage_warn_s": (0, None),
                "stage_idle_warn_s": (0, None), "check_warn_s": (0, None), "provider_wait_max_s": (0, None),
                "run_warn_s": (0, None), "run_timeout_s": (0, None),
                "review_rounds_batch": (0, None), "corrections_batch": (0, None), "findings_batch": (0, None),
                "question_warn_s": (0, None), "skill_tokens_max": (0, None), "prompt_core_tokens": (0, None),
                "prompt_supporting_tokens": (0, None), "prompt_retrieval_tokens": (0, None)}
ROLE_ALIASES = {"scout": "context-scout"}
MODEL_ROLES = ("context-scout", "executor", "bounded-implementer", "reviewer", "triager", "registrar", "report-fixer",
               "researcher", "advisor")
_SELECTOR = re.compile(r"^(?P<provider>[a-z][a-z0-9-]*)/(?P<model>[A-Za-z0-9][A-Za-z0-9._:-]*)"
                       r"(?:/(?P<context>[0-9]+[kKmM]?))?(?:/(?P<effort>low|medium|high|xhigh|max|ultra))?$")
_ACTOR = re.compile(r"^(?P<provider>[a-z][a-z0-9-]*)/(?P<model>[A-Za-z0-9][A-Za-z0-9._:-]*)"
                    r"(?:/(?P<effort>low|medium|high|xhigh|max|ultra))?$")


class OptionsError(ValueError):
    """``OPTIONS_INVALID``: a layer is outside ``run-options``; ``SELECTOR_INVALID``: a selector does not parse."""

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

    ``layers`` are ``{"source": text, "options": object}`` entries of the work source, general first.
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
        issues = contract.problems(found, "run-options") or limit_problems(found)
        if issues:
            raise OptionsError("OPTIONS_INVALID", f"{name}: {'; '.join(issues[:3])}")
        apply(name, found)
    parse_selector(current["reviewer"])
    return current, sources


def limit_problems(layer: dict) -> list:
    """Limits outside ``LIMIT_BOUNDS`` (the shared schema profile has no numeric bounds)."""
    issues = []
    for key, value in (layer.get("limits") or {}).items():
        low, high = LIMIT_BOUNDS[key]
        if value < low or (high is not None and value > high):
            issues.append(f"/limits/{key}: {value} is outside {low}..{high if high is not None else '∞'}")
    for key, value in (layer.get("checks") or {}).items():
        if key in CHECKS_BOUNDS and not CHECKS_BOUNDS[key][0] <= value <= CHECKS_BOUNDS[key][1]:
            issues.append(f"/checks/{key}: {value} is outside {CHECKS_BOUNDS[key][0]}..{CHECKS_BOUNDS[key][1]}")
    for entry in layer.get("skills") or []:
        if AUTO_SKILLS in entry["names"] and len(entry["names"]) > 1:
            issues.append(f"/skills/{entry['role']}: \"auto\" cannot be listed together with other skills")
    for key, value in (layer.get("review") or {}).items():
        if key in REVIEW_BOUNDS and not REVIEW_BOUNDS[key][0] <= value <= REVIEW_BOUNDS[key][1]:
            issues.append(f"/review/{key}: {value} is outside {REVIEW_BOUNDS[key][0]}..{REVIEW_BOUNDS[key][1]}")
    return issues


def digest(options: dict) -> str:
    """Tagged digest of the merged options of a piece of work: the same layers give the same digest."""
    return digest_json(options)


def stage_route(options: dict, role: str) -> dict:
    """The route of ``role`` in the merged options (``{}`` when no layer names it)."""
    return next((dict(entry) for entry in options.get("stages", []) if entry["role"] == role), {})
