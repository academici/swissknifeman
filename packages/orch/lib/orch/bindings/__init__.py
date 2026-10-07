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

from orch import CONTRACT_VERSION, contracts
from orch.catalog import CLASS_RANK, Catalog, CatalogError
from orch.port import BINDINGS as BINDING_NAMES, PortError

ORCH_ROOT = Path(__file__).resolve().parents[3]
CAPABILITY_DIR = ORCH_ROOT / "bindings" / "capabilities"
MODEL_KINDS = ("scout", "primary", "bounded", "review")
# Policy role id -> role manifest id, and manifest id -> launch catalog role, where the names differ.
ROLE_ALIASES = {"scout": "context-scout"}
LAUNCH_ROLES = {"context-scout": "scout"}
NOT_SET = ("unsupported", "unknown")


class Unmet(Exception):
    """A requirement of one stage that the binding cannot honour."""

    def __init__(self, capability: str, reason: str):
        super().__init__(reason)
        self.capability = capability
        self.reason = reason


def load_capabilities(directory: str | Path | None = None) -> dict[tuple[str, str], dict]:
    """Capability records keyed by ``(binding, provider)``."""
    base = Path(directory) if directory is not None else CAPABILITY_DIR
    records = {}
    for path in sorted(base.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["_path"] = _relative(path)
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


def _stage_requirements(binding: str, policy: dict, stage: dict, manifest: dict, cap: dict | None,
                        provider: str, primary_provider: str | None) -> None:
    """Raise ``Unmet`` for the first requirement of step 5 that fails."""
    if cap is None:
        raise Unmet("model.set", f"no capability record for ({binding}, {provider}); treated as unknown")
    model_set = cap["model"]["set"]
    if model_set == "unknown":
        raise Unmet("model.set", "model selection is unknown; the route is not guaranteed")
    if model_set == "unsupported" and binding != "claude-only":
        raise Unmet("model.set", f"{binding} on {provider} cannot select a model")
    delivery = cap["skill_delivery"]["mode"]
    if any(item["required"] for item in manifest.get("skills") or []) and delivery in NOT_SET:
        raise Unmet("skill_delivery", f"required skills cannot be delivered (mode {delivery})")
    if stage["kind"] == "review" and policy["review"]["independent_provider"] and provider == primary_provider:
        raise Unmet("independent_provider", f"review must not run on the primary provider {provider!r}")
    restrictions = cap["restrictions"]
    if manifest["write_authority"] == "none" and restrictions["tools_native"] in NOT_SET \
            and not restrictions["prompt_only"]:
        raise Unmet("read_only_enforcement", f"{provider} cannot enforce a read-only role")


def prepare_common(binding: str, input_doc: dict, policy: dict, roles: Mapping[str, dict],
                   capabilities: Mapping[tuple[str, str], dict], *, provider: str | None, catalog: Catalog,
                   project: Callable[[dict, dict, dict, dict, dict], dict] | None = None,
                   now: str | None = None) -> dict:
    """The launch-plan of a dry run. ``project(input_doc, base, manifest, cap, resolved)`` returns the
    binding's extra stage fields or raises ``Unmet``."""
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
    minimum = input_doc["route"]["minimum"]
    ordered = _order(policy["stages"])
    primary = next((stage for stage in ordered if stage["kind"] == "primary"), None)
    primary_provider = (primary.get("provider") or provider) if primary else None
    stages, refusals, blocked = [], [], False
    for stage in ordered:
        if stage["kind"] not in MODEL_KINDS:
            continue
        manifest = roles.get(ROLE_ALIASES.get(stage["role"], stage["role"]))
        if manifest is None:
            raise PortError("ROLE_UNKNOWN", f"stage {stage['id']!r} uses role {stage['role']!r} without a manifest")
        model_class = stage.get("model_class") or manifest["model_class_min"]
        if stage["kind"] == "primary" and CLASS_RANK[model_class] < CLASS_RANK[minimum["class"]]:
            raise PortError("ROUTE_UNDERSHOOT", f"stage {stage['id']!r} class {model_class!r} is below the "
                            f"input minimum {minimum['class']!r}")
        effort = stage.get("effort") or minimum["effort"]
        stage_provider = stage.get("provider") or provider
        if not stage_provider:
            raise PortError("INPUT_INVALID", f"stage {stage['id']!r} has no provider; pass one")
        cap = capabilities.get((binding, stage_provider))
        base = {"stage_id": stage["id"], "role": stage["role"], "kind": stage["kind"], "provider": stage_provider}
        try:
            _stage_requirements(binding, policy, stage, manifest, cap, stage_provider, primary_provider)
            resolved = {"class": model_class}
            if cap["model"]["set"] != "unsupported":
                resolved["model"] = _catalog(lambda: catalog.resolve_model(stage_provider, model_class), "model.set")
                base["model"] = resolved["model"]
            if cap["effort"]["set"] != "unsupported":
                resolved["effort"] = _catalog(lambda: catalog.resolve_effort(stage_provider, effort), "effort.set")
                base["effort"] = effort
            base["capability_ref"] = cap["_path"]
            base["delivery"] = {"mode": cap["skill_delivery"]["mode"], "paths": []}
            extra = project(input_doc, base, manifest, cap, resolved) if project else {}
        except Unmet as unmet:
            refusals.append({"stage_id": stage["id"], "capability": unmet.capability, "reason": unmet.reason})
            blocked = blocked or stage["required"]
            continue
        stages.append({**base, **extra})
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
        "created_at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
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
        raise Unmet(capability, str(error)) from error


class Binding:
    """Shared parts of a binding. A subclass sets ``binding`` and implements ``project``."""

    binding = ""

    def __init__(self, out: str | Path, *, catalog: Catalog, roles_dir: str | Path | None = None,
                 capabilities: Mapping[tuple[str, str], dict] | None = None, cwd: str = ".",
                 now: str | None = None):
        self.out = Path(out)
        self.catalog = catalog
        self.roles_dir = roles_dir
        self._capabilities = capabilities if capabilities is not None else load_capabilities()
        self.cwd = cwd
        self.now = now
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
                              catalog=self.catalog, project=self.project, now=self.now)
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

    def watch(self, run_id: str) -> Iterator[dict]:
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
