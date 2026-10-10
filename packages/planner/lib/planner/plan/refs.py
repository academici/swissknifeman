"""Resolver of qualified references to other plans (PLAN<N>.D3, repo:PLAN<N>.P2.1): facts only, read-only, no lock.

``resolve`` returns a superset of the former ``{"ref", "loaded"}`` entry. A failure never raises: it is reported as
``loaded: False`` with ``reason: "<CODE>: <text>"``; only ``brief`` turns an unresolved required decision into a refusal.
Only the fact of the other plan (id, status, title, decision text) is mixed in, never its process or instructions.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Mapping

from . import settings, store
from .model import PlanError, parse_ref

ENV_REPOS = "SKM_PLAN_REPOS"
_KEYS = {"decision": ("decision", "rationale"), "item": (), "phase": ()}


def _fail(ref: str, code: str, text: str) -> dict:
    return {"ref": ref, "loaded": False, "reason": f"{code}: {text}"}


def _env_repos() -> Mapping[str, str]:
    raw = os.environ.get(ENV_REPOS)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise PlanError("REPO_UNKNOWN", f"{ENV_REPOS} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise PlanError("REPO_UNKNOWN", f"{ENV_REPOS} must be a JSON object of name -> repository path")
    return value


def _plans_root(plan: store.Plan, repo: str | None, repos: Mapping[str, str] | None) -> tuple[Path, bool]:
    """Plans root of the referenced repository and whether it is the repository of ``plan``."""
    if repo is None or repo == plan.plan.get("repository"):
        return plan.repo_root / "plans", True
    path = (repos or {}).get(repo)
    if path is None:
        path = _env_repos().get(repo)
    if not isinstance(path, (str, os.PathLike)) or not str(path):
        raise PlanError("REPO_UNKNOWN", f"repository {repo!r} is not mapped; pass --repo {repo}=PATH or set {ENV_REPOS}")
    return Path(path) / "plans", False


def _find_plan_dir(plans_root: Path, short_id: str) -> Path:
    matches = [d for d in store.plan_dirs(plans_root) if store.short_id_of(d) == short_id]
    if len(matches) > 1:
        raise PlanError("PLAN_AMBIGUOUS", f"{short_id} matches {', '.join(d.name for d in matches)}")
    if not matches:
        raise PlanError("PLAN_NOT_FOUND", f"no plan {short_id!r} under {plans_root}")
    return matches[0]


def _document(target: store.Plan, kind: str, key: str) -> dict | None:
    return {"decision": target.decisions, "item": target.items, "phase": target.phases}[kind].get(key) or None


def resolve(plan: store.Plan, ref: str, *, repos: Mapping[str, str] | None = None) -> dict:
    try:
        parsed = parse_ref(ref)
    except ValueError as exc:
        return _fail(ref, "REF_INVALID", str(exc))
    if parsed.plan is None:  # local reference: not ours to resolve
        return {"ref": ref, "loaded": False}
    if parsed.kind not in _KEYS:  # only phases, items and decisions of other plans are resolved
        return _fail(ref, "REF_UNSUPPORTED", f"a {parsed.kind} of another plan cannot be resolved")
    try:
        plans_root, same_repo = _plans_root(plan, parsed.repo, repos)
        plan_dir = _find_plan_dir(plans_root, parsed.plan)
        target = store.load_plan(plan_dir)
    except PlanError as exc:
        return _fail(ref, exc.code, exc.message)
    kind, key, chain = parsed.kind, parsed.target, []
    while True:
        doc = _document(target, kind, key)
        if doc is None:
            return _fail(ref, "TARGET_NOT_FOUND", f"{parsed.plan} has no {kind} {key}")
        successor = doc.get("superseded_by") if kind == "decision" and doc.get("status") == "superseded" else None
        if not isinstance(successor, str):
            break
        chain.append(key)
        if successor in chain or len(chain) >= settings.for_plan(plan).get("refs.max_chain"):
            return _fail(ref, "CYCLE", f"supersede chain {' -> '.join([*chain, successor])} does not end")
        key = successor
    source = target.path(kind, key)
    shown_dir = plan_dir
    if same_repo:
        shown_dir = plan_dir.resolve().relative_to(target.repo_root.resolve())
        source = shown_dir / source.relative_to(plan_dir)
    entry = {"ref": ref, "loaded": True, "plan": parsed.plan, "plan_dir": shown_dir.as_posix(), "kind": kind,
             "status": doc.get("status"), "title": doc.get("title")}
    for name in _KEYS[kind]:
        if doc.get(name) is not None:
            entry[name] = doc[name]
    if chain:
        entry["id"] = key
        entry["superseded"] = chain
    entry["source"] = {"path": source.as_posix(),
                       "sha256": sha256(target.path(kind, key).read_bytes()).hexdigest()}
    return entry
