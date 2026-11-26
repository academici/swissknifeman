"""Opt-in physical launch ceiling: durable authority admissions, including all historical agent runs."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from orch.conductor import agents, contract, records
from orch.conductor.domain.route import actor
from orch.conductor.domain.stop import Stop
from orch.conductor.policies.authority import digest as authority_digest


def inventory(directory: Path, *, pending_since: str = "", current: Path | None = None) -> dict:
    """Hash every request and physical admission; unknown historical launches never become zero.

    Authority is persisted before spawn. A crash in between conservatively consumes a slot; this is an admission
    ceiling, not a claim that every reserved process reached the provider.
    """
    protected, launches, requests = {}, [], []
    for path in sorted((directory / agents.AGENTS).glob("*/request.json")):
        request = records.read(path, "agent-request")
        if request is None:
            raise Stop("MODEL_LAUNCH_HISTORY_UNKNOWN", f"missing request: {path}")
        requests.append(request)
        protected[path.relative_to(directory).as_posix()] = sha256(path.read_bytes()).hexdigest()
        authorities = sorted(path.parent.glob("authority/a*.json"))
        if not authorities and path.parent != current and not (pending_since and request["started_at"] >= pending_since):
            raise Stop("MODEL_LAUNCH_HISTORY_UNKNOWN", f"{path.parent.name}: no durable physical authority history")
        for source in authorities:
            try:
                envelope = json.loads(source.read_bytes())
            except (OSError, ValueError) as error:
                raise Stop("MODEL_LAUNCH_HISTORY_UNKNOWN", f"{source}: {error}") from None
            if contract.problems(envelope, "authority-envelope") or envelope.get("digest") != authority_digest(envelope):
                raise Stop("MODEL_LAUNCH_HISTORY_UNKNOWN", f"{source}: invalid authority admission")
            name = source.relative_to(directory).as_posix()
            protected[name] = sha256(source.read_bytes()).hexdigest()
            launches.append(name)
    return {"protected": protected, "launches": launches, "requests": requests}


def latest(item):
    history = item.state.get("fresh_contexts") or []
    return history[-1] if history else None


def record_launch(owner, item, handle, role, route, attempt, envelope):
    """Called under the run-store lock at the one process-launch boundary, before any provider process."""
    fresh = latest(item)
    if not fresh:
        return agents.write_authority(handle, attempt, envelope)
    if role != "executor" or handle.get("step") != fresh["stage"] or actor(route) != fresh["route"]:
        raise Stop("FRESH_CONTEXT_ROUTE_CHANGED", "fresh continuation admits only its pinned executor stage/route; no fallback")
    if owner._tree_mark() != fresh["tree_mark"]:
        raise Stop("FRESH_CONTEXT_CANDIDATE_CHANGED", "the candidate changed since fresh-context preparation")
    snapshot = owner.directory / fresh["snapshot"]
    if sha256(snapshot.read_bytes()).hexdigest() != fresh["options_sha256"]:
        raise Stop("FRESH_CONTEXT_OPTIONS_CHANGED", "the invocation snapshot changed")
    baseline_doc = records.read(owner.directory / fresh["before"] / "item-options.json", "item-options")
    if baseline_doc is None:
        raise Stop("FRESH_CONTEXT_OPTIONS_CHANGED", "the frozen baseline options are missing")
    proposed = records.options_effective(json.loads(snapshot.read_bytes()))
    if {k: v for k, v in item.options.items() if k != "rules"} != {k: v for k, v in proposed.items() if k != "rules"}:
        raise Stop("FRESH_CONTEXT_OPTIONS_CHANGED", "effective options must match the frozen continuation options")
    found = inventory(item.directory, pending_since=fresh["since"], current=Path(handle["directory"]))
    if len(found["requests"]) != owner.state.get("agents", 0):
        raise Stop("MODEL_LAUNCH_HISTORY_UNKNOWN", "the agent counter and preserved request records disagree")
    for context in item.state["fresh_contexts"]:
        for name, digest in {**context["baseline"], **context["admissions"]}.items():
            if found["protected"].get(name) != digest:
                raise Stop("MODEL_LAUNCH_HISTORY_CHANGED", f"historical launch evidence changed: {name}")
    target = Path(handle["directory"]) / "authority" / f"a{int(attempt)}.json"
    if target.exists():
        raise Stop("MODEL_LAUNCH_REPLAY", "a physical launch admission is never reused")
    if len(found["launches"]) >= fresh["ceiling"]:
        raise Stop("MODEL_LAUNCH_CEILING", f"{len(found['launches'])} historical/admitted launches >= total ceiling {fresh['ceiling']}")
    path = agents.write_authority(handle, attempt, envelope)
    fresh["admissions"][path.relative_to(item.directory).as_posix()] = sha256(path.read_bytes()).hexdigest()
    owner._save()  # reservation survives a crash before spawn; no counter, usage or unmetered history is reset
    return path
