"""Engine bindings and the prepare algorithm they share (docs/engine-port.md, prepare algorithm).

``prepare_common`` decides, for every model stage, whether the binding can honour the request and which
model/effort it means. A binding adds only its own projection of a stage: argv, a CAO profile or a prompt.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import aicore
from aicore.util import digest as _digest

import orch
from orch import CONTRACT_VERSION, contracts, settings as orch_settings
from orch.catalog import CLASS_RANK, Catalog, CatalogError
from orch.port import BINDINGS as BINDING_NAMES, PortError

ORCH_ROOT = Path(__file__).resolve().parents[3]
CAPABILITY_DIR = ORCH_ROOT / "bindings" / "capabilities"
MODEL_KINDS = ("scout", "primary", "bounded", "review", "condense")
# Policy role id -> role manifest id, and manifest id -> launch catalog role, where the names differ.
ROLE_ALIASES = {"scout": "context-scout"}
LAUNCH_ROLES = {"context-scout": "scout"}
NOT_SET = ("unsupported", "unknown")
# Reason code of an unmet requirement when the raiser names none, by capability.
DEFAULT_REASON_CODES = {"model.set": "MODEL_SET_UNSUPPORTED", "effort.set": "CATALOG_UNKNOWN",
                        "launch": "LAUNCH_UNKNOWN"}


class Unmet(Exception):
    """A requirement of one stage that the binding cannot honour; ``code`` is the stable reason code."""

    def __init__(self, capability: str, reason: str, code: str | None = None):
        super().__init__(reason)
        self.capability = capability
        self.reason = reason
        self.code = code or DEFAULT_REASON_CODES.get(capability, "REQUIREMENT_UNMET")


def load_capabilities(directory: str | Path | None = None) -> dict[tuple[str, str], dict]:
    """Capability records keyed by ``(binding, provider)``."""
    base = Path(directory) if directory is not None else CAPABILITY_DIR
    records = {}
    for path in sorted(base.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["_path"] = str(path.resolve())  # made relative when a plan names it
        records[(record["binding"], record["provider"])] = record
    return records


def _relative(path: Path, start: Path | None = None) -> str:
    """Repository-relative POSIX form that the launch-plan ``path`` type accepts (no leading slash)."""
    return Path(os.path.relpath(path, start or Path.cwd())).as_posix()


def _errors(doc: object, kind: str) -> list[dict]:
    return [issue._asdict() for issue in contracts.validate(doc, kind) if issue.level == "error"]


def _order(stages: list[dict]) -> list[dict]:
    """Stages in dependency order; an omitted ``depends_on`` means the previous stage."""
    depends, previous = {}, None
    for stage in stages:
        depends[stage["id"]] = list(stage.get("depends_on", [previous] if previous else []))
        previous = stage["id"]
    by_id = {stage["id"]: stage for stage in stages}
    ordered, placed = [], set()
    while len(ordered) < len(stages):
        ready = [stage for stage in stages if stage["id"] not in placed and set(depends[stage["id"]]) <= placed]
        if not ready:  # run-policy validation rules a cycle out; stay safe for hand-built input
            raise PortError("POLICY_INVALID", "stage dependencies contain a cycle")
        ordered.append(by_id[ready[0]["id"]])
        placed.add(ready[0]["id"])
    return ordered


def _moment(text: str) -> datetime:
    """A launch-plan timestamp (UTC, optional fraction) as a datetime; the fraction counts."""
    whole, _, fraction = text.rstrip("Z").partition(".")
    return datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(microsecond=int((fraction + "000000")[:6]))


def is_stale(cap: Mapping, now: str) -> bool:
    """A record is stale when it names ``fresh_until`` and that moment has passed."""
    until = cap.get("fresh_until")
    return until is not None and _moment(until) < _moment(now)


def _stage_requirements(binding: str, policy: dict, stage: dict, manifest: dict, cap: dict | None,
                        provider: str, primary_provider: str | None, *, refuse_stale: bool = False,
                        now: str | None = None) -> None:
    """Raise ``Unmet`` for the first requirement of step 5 that fails."""
    if cap is None:
        raise Unmet("model.set", f"no capability record for ({binding}, {provider}); treated as unknown",
                    "CAP_RECORD_MISSING")
    if refuse_stale and now is not None and is_stale(cap, now):
        raise Unmet("capability.fresh", f"the capability record for ({binding}, {provider}) was fresh until "
                    f"{cap['fresh_until']}", "CAPABILITY_STALE")
    model_set = cap["model"]["set"]
    if model_set == "unknown":
        raise Unmet("model.set", "model selection is unknown; the route is not guaranteed", "MODEL_SET_UNKNOWN")
    if model_set == "unsupported" and binding != "claude-only":
        raise Unmet("model.set", f"{binding} on {provider} cannot select a model", "MODEL_SET_UNSUPPORTED")
    delivery = cap["skill_delivery"]["mode"]
    if any(item["required"] for item in manifest.get("skills") or []) and delivery in NOT_SET:
        raise Unmet("skill_delivery", f"required skills cannot be delivered (mode {delivery})",
                    "SKILL_DELIVERY_UNAVAILABLE")
    if stage["kind"] == "review" and policy["review"]["independent_provider"] and provider == primary_provider:
        raise Unmet("independent_provider", f"review must not run on the primary provider {provider!r}",
                    "INDEPENDENT_PROVIDER")
    restrictions = cap["restrictions"]
    if manifest["write_authority"] == "none" and restrictions["tools_native"] in NOT_SET \
            and not restrictions["prompt_only"]:
        raise Unmet("read_only_enforcement", f"{provider} cannot enforce a read-only role",
                    "READ_ONLY_UNENFORCEABLE")


def _available(cap: Mapping, name: str):
    """``(available, state)`` of the capability ``name`` (a dotted path into the record) a record depends on."""
    value: object = cap
    for part in name.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return False, "not recorded"
        value = value[part]
    if isinstance(value, Mapping):
        value = value.get("mode", value.get("set", "recorded"))
    return value not in (*NOT_SET, "none", False), str(value)


def _chain(unmet: Unmet, cap: Mapping | None) -> list[dict]:
    """Why a capability is unavailable: the requested one, then each capability the record depends on that is itself
    unavailable."""
    chain = [{"capability": unmet.capability, "reason": unmet.reason}]
    for name in (cap or {}).get("depends_on", []):
        available, state = _available(cap, name)
        if not available and name != unmet.capability:
            chain.append({"capability": name, "reason": f"{name} is {state}"})
    return chain


def check_skills(skills: object) -> None:
    """``skills`` must map role ids to lists of ``{name, digest}`` objects; ``INPUT_INVALID`` otherwise."""
    if skills is not None and not (isinstance(skills, Mapping) and all(
            isinstance(role, str) and isinstance(items, list) and all(isinstance(item, Mapping) for item in items)
            for role, items in skills.items())):
        raise PortError("INPUT_INVALID", "skills must map role ids to lists of {name, digest} objects")


def _digest_of(value: object) -> str:
    return _digest.sha256_hex(_digest.canonical_json_bytes(value))


def _digests(input_doc: dict, policy: dict, roles: Mapping[str, dict], binding: str,
             capabilities: Mapping[tuple[str, str], dict], catalog: Catalog, config: str,
             model_catalog_doc: dict | None, launch_catalog_doc: dict | None) -> dict:
    records = {f"{name}--{provider}": {key: value for key, value in record.items() if key != "_path"}
               for (name, provider), record in sorted(capabilities.items()) if name == binding}
    return {"input": input_doc["digest"], "policy": contracts.canonical_digest(policy), "roles": _digest_of(dict(roles)),
            "launch_catalog": _digest_of(launch_catalog_doc if launch_catalog_doc is not None else catalog.launch),
            "model_catalog": _digest_of(model_catalog_doc if model_catalog_doc is not None else catalog.model_document()),
            "capabilities": _digest_of(records), "config": config}


def catalog_digests(catalog: Catalog, capabilities: Mapping[tuple[str, str], dict] | None = None) -> dict:
    """``{launch, models, capabilities}``: digests of the effective launch catalog (with the ``[orch.launch]``
    overlays), the model catalog and every capability record, as the dry run of a launch plan digests them; the
    provenance of the catalogs a conductor run started with."""
    records = {f"{name}--{provider}": {key: value for key, value in record.items() if key != "_path"}
               for (name, provider), record in sorted((capabilities if capabilities is not None
                                                       else load_capabilities()).items())}
    return {"launch": _digest_of(catalog.launch), "models": _digest_of(catalog.model_document()),
            "capabilities": _digest_of(records)}


def _proof_entry(binding: str, provider: str, cap: Mapping, stale: bool) -> dict:
    entry = {"binding": binding, "provider": provider, "source": cap.get("source", "declared"), "stale": stale}
    observed = cap.get("observed_at", cap.get("recorded_at"))
    if observed is not None:
        entry["observed_at"] = observed
    if "fresh_until" in cap:
        entry["fresh_until"] = cap["fresh_until"]
    return entry


def prepare_common(binding: str, input_doc: dict, policy: dict, roles: Mapping[str, dict],
                   capabilities: Mapping[tuple[str, str], dict], *, provider: str | None, catalog: Catalog,
                   project: Callable[[dict, dict, dict, dict, dict], dict] | None = None,
                   now: str | None = None, settings: orch_settings.Settings | None = None,
                   submission_id: str | None = None, skills: Mapping[str, list] | None = None,
                   model_catalog_doc: dict | None = None, launch_catalog_doc: dict | None = None,
                   engine_decision: dict | None = None) -> dict:
    """The launch-plan of a dry run. ``project(input_doc, base, manifest, cap, resolved)`` returns the
    binding's extra stage fields or raises ``Unmet``.

    The result is a function of the arguments and ``now``: digests of every input, the configuration snapshot, the
    route decisions with the candidates considered, the policy decision, the proof of the capability records and
    the digest of the plan itself, computed last. ``engine_decision`` is the ``select_engine`` decision that chose
    ``binding``; without it the caller is taken to have named the binding explicitly.
    """
    if binding not in BINDING_NAMES:
        raise ValueError(f"unknown binding: {binding!r}")
    issues = _errors(input_doc, "execution-input")
    if issues:
        raise PortError("INPUT_INVALID", "execution-input does not match exec/v1", {"issues": issues})
    issues = _errors(policy, "run-policy")
    if issues:
        raise PortError("POLICY_INVALID", "run-policy does not match exec/v1", {"issues": issues})
    for role_id, manifest in roles.items():
        issues = _errors(manifest, "role-manifest")
        if issues:
            raise PortError("INPUT_INVALID", f"role manifest {role_id!r} does not match exec/v1", {"issues": issues})
    check_skills(skills)
    current = settings if settings is not None else orch_settings.defaults()
    created = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    refuse_stale = current.capabilities_stale == "refuse"
    minimum = input_doc["route"]["minimum"]
    ordered = _order(policy["stages"])
    primary = next((stage for stage in ordered if stage["kind"] == "primary"), None)
    primary_provider = (primary.get("provider") or provider) if primary else None
    stages, refusals, decisions, blocked = [], [], [], []
    proof, warnings = {}, {}
    for stage in ordered:
        if stage["kind"] not in MODEL_KINDS:
            continue
        manifest = roles.get(ROLE_ALIASES.get(stage["role"], stage["role"]))
        if manifest is None:
            raise PortError("ROLE_UNKNOWN", f"stage {stage['id']!r} uses role {stage['role']!r} without a manifest")
        model_class = stage.get("model_class") or manifest["model_class_min"]
        if stage["kind"] == "primary" and not stage.get("model_class") \
                and CLASS_RANK[model_class] < CLASS_RANK[minimum["class"]]:
            model_class = minimum["class"]  # a pack that does not pin the class follows the route minimum of the piece
        if stage["kind"] == "primary" and CLASS_RANK[model_class] < CLASS_RANK[minimum["class"]]:
            raise PortError("ROUTE_UNDERSHOOT", f"stage {stage['id']!r} class {model_class!r} is below the "
                            f"input minimum {minimum['class']!r}")
        effort = stage.get("effort") or minimum["effort"]
        stage_provider = stage.get("provider") or provider
        if not stage_provider:
            raise PortError("INPUT_INVALID", f"stage {stage['id']!r} has no provider; pass one")
        cap = capabilities.get((binding, stage_provider))
        stale = cap is not None and is_stale(cap, created)
        if cap is not None:
            proof[stage_provider] = _proof_entry(binding, stage_provider, cap, stale)
        base = {"stage_id": stage["id"], "role": stage["role"], "kind": stage["kind"], "provider": stage_provider}
        reason_codes = []
        try:
            _stage_requirements(binding, policy, stage, manifest, cap, stage_provider, primary_provider,
                                refuse_stale=refuse_stale, now=created)
            if stale:  # only reached when stale records are warned about
                reason_codes.append("CAPABILITY_STALE")
                warnings[stage_provider] = {"code": "CAPABILITY_STALE", "message":
                                            f"the capability record for ({binding}, {stage_provider}) was fresh until "
                                            f"{cap['fresh_until']}"}
            resolved = {"class": model_class}
            if cap["model"]["set"] != "unsupported":
                resolved["model"] = _catalog(
                    lambda provider=stage_provider, cls=model_class: catalog.resolve_model(provider, cls), "model.set")
                base["model"] = resolved["model"]
            if cap["effort"]["set"] != "unsupported":
                resolved["effort"] = _catalog(
                    lambda provider=stage_provider, level=effort: catalog.resolve_effort(provider, level), "effort.set")
                base["effort"] = effort
            base["capability_ref"] = _relative(Path(cap["_path"]))
            base["delivery"] = {"mode": cap["skill_delivery"]["mode"], "paths": []}
            # The manifest role id wins, even with an empty list; the policy role is the fallback.
            key = next((name for name in (manifest["role_id"], stage["role"]) if name in (skills or {})), None)
            delivered = skills[key] if key is not None else None
            if delivered:
                base["delivery"]["skills"] = [dict(item) for item in delivered]
            extra = project(input_doc, base, manifest, cap, resolved) if project else {}
        except Unmet as unmet:
            refusals.append({"stage_id": stage["id"], "capability": unmet.capability, "reason": unmet.reason,
                             "reason_code": unmet.code, "chain": _chain(unmet, cap)})
            decisions.append({"stage_id": stage["id"], "kind": "route", "chosen": "none", "tie_break": "policy-order",
                              "considered": [{"candidate": stage_provider, "accepted": False,
                                              "reason_codes": [unmet.code]}]})
            if stage["required"]:
                blocked.append(unmet.code)
            continue
        chosen = f"{stage_provider}/{resolved.get('model', model_class)}"
        decisions.append({"stage_id": stage["id"], "kind": "route", "chosen": chosen, "tie_break": "policy-order",
                          "considered": [{"candidate": stage_provider, "accepted": True,
                                          "reason_codes": reason_codes}]})
        stages.append({**base, **extra})
    decisions.append(engine_decision if engine_decision is not None else
                     {"stage_id": "*", "kind": "binding", "chosen": binding,
                      "considered": [{"candidate": binding, "accepted": True, "reason_codes": ["ENGINE_FROM_FLAG"]}]})
    config = {"digest": orch_settings.digest(current), "values": orch_settings.affecting(current)}
    digests = _digests(input_doc, policy, roles, binding, capabilities, catalog, config["digest"],
                       model_catalog_doc, launch_catalog_doc)
    plan = {
        "$schema": contracts.URN_PREFIX + "launch-plan:v1",
        "contract_version": CONTRACT_VERSION,
        "binding": binding,
        "run_id": "dry-" + input_doc["digest"][:12],
        "input_digest": input_doc["digest"],
        "policy_id": policy["policy_id"],
        "dry_run": True,
        "stages": stages,
        "refusals": refusals,
        "created_at": created,
        "digests": digests,
        "config": config,
        "modules": [{"id": "aicore", "version": aicore.__version__}, {"id": "orch", "version": orch.__version__}],
        "decisions": decisions,
        "policy_decision": {"decision": "refuse" if blocked else "allow",
                            "reason_codes": list(dict.fromkeys(blocked)), "policy_digest": digests["policy"]},
        "proof": {"capabilities": [proof[name] for name in sorted(proof)],
                  "warnings": [warnings[name] for name in sorted(warnings)]},
    }
    if submission_id is not None:
        plan["submission_id"] = submission_id
    plan["digest"] = contracts.canonical_digest(plan)
    issues = _errors(plan, "launch-plan")
    if issues:
        raise PortError("INPUT_INVALID", "prepared launch-plan does not match exec/v1", {"issues": issues})
    if blocked:
        raise PortError("CAPABILITY_UNSUPPORTED", "a required stage needs a capability the binding lacks",
                        {"launch_plan": plan})
    return plan


def _catalog(lookup: Callable[[], str], capability: str) -> str:
    try:
        return lookup()
    except CatalogError as error:
        raise Unmet(capability, str(error), "CATALOG_UNKNOWN") from error


class Binding:
    """Shared parts of a binding. A subclass sets ``binding`` and implements ``project``."""

    binding = ""

    def __init__(self, out: str | Path, *, catalog: Catalog, roles_dir: str | Path | None = None,
                 capabilities: Mapping[tuple[str, str], dict] | None = None, cwd: str = ".",
                 now: str | None = None, settings: orch_settings.Settings | None = None,
                 submission_id: str | None = None, skills: Mapping[str, list] | None = None,
                 engine_decision: dict | None = None):
        self.out = Path(out)
        self.catalog = catalog
        self.roles_dir = roles_dir
        self._capabilities = capabilities if capabilities is not None else load_capabilities()
        self.cwd = cwd
        self.now = now
        self.settings = settings
        self.submission_id = submission_id
        self.skills = skills
        self.engine_decision = engine_decision
        self._files: list[tuple[Path, str]] = []

    def capabilities(self) -> list[dict]:
        return [{key: value for key, value in record.items() if key != "_path"}
                for (binding, _), record in sorted(self._capabilities.items()) if binding == self.binding]

    def prepare(self, input_doc: dict, policy: dict, roles: Mapping[str, dict], *,
                provider: str | None = None, dry_run: bool = True) -> dict:
        if not dry_run:
            raise PortError("NOT_IMPLEMENTED", "prepare without dry_run is not available in this version")
        self._files = []
        plan = prepare_common(self.binding, input_doc, policy, roles, self._capabilities, provider=provider,
                              catalog=self.catalog, project=self.project, now=self.now,
                              settings=self.settings, submission_id=self.submission_id, skills=self.skills,
                              engine_decision=self.engine_decision)
        for path, text in self._files:  # nothing is written when the preparation was refused
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return plan

    def project(self, input_doc: dict, base: dict, manifest: dict, cap: dict, resolved: dict) -> dict:
        raise NotImplementedError

    def _write(self, name: str, text: str) -> str:
        """Queue a file under ``out``; returns its launch-plan path."""
        path = self.out / name
        self._files.append((path, text))
        return _relative(path)

    def run(self, launch_plan: dict) -> str:
        raise PortError("NOT_IMPLEMENTED", "run is not available in this version")

    def watch(self, run_id: str, after_seq: int | None = None) -> Iterator[dict]:
        raise PortError("NOT_IMPLEMENTED", "watch is not available in this version")

    def cancel(self, run_id: str) -> dict:
        raise PortError("NOT_IMPLEMENTED", "cancel is not available in this version")

    def resume(self, run_id: str) -> str:
        raise PortError("NOT_IMPLEMENTED", "resume is not available in this version")

    def results(self, run_id: str) -> dict:
        raise PortError("NOT_IMPLEMENTED", "results is not available in this version")


from orch.bindings.cao import Cao  # noqa: E402
from orch.bindings.claude_only import ClaudeOnly  # noqa: E402
from orch.bindings.native import Native  # noqa: E402

BINDINGS = {"native": Native, "cao": Cao, "claude-only": ClaudeOnly}
