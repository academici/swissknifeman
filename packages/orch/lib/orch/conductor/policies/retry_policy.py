"""A role that failed at the provider: one ``retry.decide`` call chooses a repeat, a wait, a continuation, another
route or a stop; a quota with a known reset gates the provider on the machine."""
from __future__ import annotations

import time
from typing import Optional

from aicore.util import timefmt

from orch import retry
from orch.conductor import gates, options as opts, prompts
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import write_json

# An unclassified failure was always repeated (within ``limits.retries``); retry.decide would stop on it by default.
CONDUCTOR_ON_ERROR = {"unknown": {"action": "retry"}}
# The stop code of a failure class; a class that is not listed keeps the code of the failed role (``ROLE_FAILED``, ...).
PROVIDER_STOP_CODES = {"authentication": "PROVIDER_AUTH", "authorization": "PROVIDER_AUTHZ", "quota": "PROVIDER_QUOTA",
                       "rate_limit": "PROVIDER_QUOTA", "invalid_request": "PROVIDER_REFUSED",
                       "content_policy": "PROVIDER_REFUSED", "context_limit": "PROVIDER_CONTEXT",
                       "model_unavailable": "MODEL_UNAVAILABLE"}
TRANSIENT_CLASSES = ("provider_internal", "transport", "rate_limit")  # the provider CLI repeats these itself
JITTER_CAP_S, JITTER_BASE_S = 300, 30


def routed_blocks(self, role: str, route: dict, blocks: list) -> list:
    """``blocks`` with the stub of the role for the actual route of the attempt (a fallback route has its own stub)."""
    origin, text = self._stub(role, route)
    routed = [block for block in blocks if block.kind != "stub"]
    if text:
        routed.insert(1, prompts.Block("stub", origin, text.rstrip() + "\n\n"))
    return routed


def prompt_for_route(self, item: Item, key: str, role: str, route: dict, blocks: list,
                     first_prompt: str, prompt: str, resumed: Optional[list] = None,
                     digest: Optional[str] = None) -> tuple:
    """Rebuild only the stub for the actual attempt, preserving the other blocks and retry instructions. ``resumed``
    (the delta blocks of a round in a resumed session, when this attempt sends them) is what the role gets instead of the
    whole prompt; ``prompts/<key>.md`` keeps the full prompt of the step and ``<key>.resumed.md`` the delta one."""
    routed = self._routed_blocks(role, route, blocks)
    suffix = prompt[len(first_prompt):]
    sent = list(resumed) if resumed else routed
    first_prompt = prompts.render(sent)
    full = list(routed)
    if suffix:
        retry = prompts.Block("instruction", "conductor:retry", suffix)
        sent.append(retry)
        full.append(retry)
    prompt = prompts.render(sent)
    path = item.directory / "prompts" / f"{key}.md"
    path.write_text(prompts.render(full), encoding="utf-8")
    delta_path = path.with_suffix(".resumed.md")
    if resumed:
        delta_path.write_text(prompt, encoding="utf-8")
    elif delta_path.exists():  # an earlier attempt of the step sent a delta; this one sends the whole prompt
        delta_path.unlink()
    limits = {name: int(item.options.get("limits", {}).get(option, opts.DEFAULT_LIMITS[option]))
              for name, option in prompts.BUDGET_LIMITS.items()}
    write_json(path.with_suffix(".manifest.json"),
               prompts.manifest(sent, step=key, role=role, route=route,
                                excluded=self._skills_excluded(item, role), limits=limits,
                                resumed_session=bool(resumed), digest=digest))
    return first_prompt, prompt


def start_route(self, item: Item, key: str, role: str, route: dict, cancel) -> dict:
    """The route a role starts on: its own unless its provider was gated after the routes of the piece were chosen
    (an earlier role exhausted the account). Then the first admissible fallback route; else, when the gate ends
    within ``limits.provider_wait_max_s``, a wait for it; else ``PROVIDER_QUOTA`` before the call."""
    gate = gates.blocked(route["provider"], clock.wall())
    if gate is None:
        return route
    found, refused = self._fallback(item, role, route)
    until = f"{route['provider']} is gated until {gate['until']} ({gate['class']} {gate['code']}, set by {gate['set_by']})"
    if found is not None:
        item.routes[role] = found
        write_json(item.directory / "routes.json", item.routes)
        self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(found),
                           reason_code="CAPACITY_GATED", message=f"{role}: {until}")
        self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(found),
                           reason_code="ROUTE_FALLBACK",
                           message=f"{role}: {self.label(route)} -> {self.label(found)} (CAPACITY_GATED)")
        self._provider_limit(item, key, role, route["provider"], gate["class"], "CAPACITY_GATED", until=gate["until"])
        self._route_fallback(item, key, role, route, found, ["CAPACITY_GATED"])
        return found
    left = max(0, timefmt.epoch(gate["until"]) - clock.wall())
    if left <= item.options["limits"].get("provider_wait_max_s", 900):
        self._wait(item, key, role, {"class": gate["class"]}, int(left) + 1, cancel)
        return route
    raise Stop("PROVIDER_QUOTA", f"{role}: {until}" + (f"; no fallback: {'; '.join(refused)}" if refused else "")
               + "; resume after the reset, or remove the gate with orch conduct gates --clear")


def provider_failure(self, item: Item, key: str, role: str, route: dict, run, attempts: int, base: Optional[str],
                     first_prompt: str, trail: dict, cancel) -> tuple:
    """``(route, prompt)`` of the next attempt of a role that failed at the provider, or a ``Stop``.

    One ``retry.decide`` call decides (knowledge/provider-errors#flow). The conductor does not multiply repeats: when
    the provider CLI already repeated the request itself (``api_retry`` events) a transient failure is repeated
    only after a pause, and a writing role that left changes in the tree continues from them, never from scratch."""
    error = run.error_doc or {"class": "timeout" if run.error == "TIMEOUT" else "unknown"}
    trail["error"] = error
    limits = item.options["limits"]
    writes = self._writes(role)
    dirty = base is not None and self._tree_mark() != base
    self._gate(item, route, error)
    inputs = retry.RetryInputs(
        error_class=error["class"], stage_writes=writes, worktree_dirty=dirty, receipt_unresolved=False,
        attempts_used=attempts, stage_retries_max=limits["retries"], budget_left=limits["retries"] + 1 - attempts,
        retry_after_s=None if past_reset(error) else error.get("retry_after_s"),
        current_route={"provider": route["provider"], "model_class": route["model_class"]},
        max_wait_s=limits.get("provider_wait_max_s", 900))
    policy = {"on_error": {**CONDUCTOR_ON_ERROR, **item.options.get("on_error", {})},
              "fallback_routes": [entry for entry in item.options.get("fallback_routes", []) if entry["role"] == role]}
    decision = retry.decide(inputs, policy)
    if decision.action == "reconcile" and attempts > limits["retries"]:  # decide does not bound a reconcile
        decision = retry.RetryDecision("stop", decision.reason_codes + ("BUDGET_EXHAUSTED",))
    trail["decisions"].append({"action": decision.action, "reason_codes": list(decision.reason_codes),
                               **({"wait_s": decision.wait_s} if decision.wait_s is not None else {}),
                               **({"route": decision.route} if decision.route else {})})
    label = self.label(route)
    self.progress.emit("info", item=item.ref, stage=key, role=role, route=label,
                       message=f"attempt {attempts} failed at the provider ({error['class']}: "
                               f"{error.get('safe_message') or run.detail}); {decision.action} "
                               f"({', '.join(decision.reason_codes)})")
    if decision.action == "retry":
        if run.api_retries and error["class"] in TRANSIENT_CLASSES:
            self._wait(item, key, role, error, error.get("retry_after_s") if error.get("retry_after_s") is not None
                       else int(min(JITTER_CAP_S, JITTER_BASE_S * 2 ** (attempts - 1)) * clock.unit_random()), cancel)
        return route, first_prompt
    if decision.action == "retry_after":
        self._wait(item, key, role, error, decision.wait_s, cancel)
        return route, first_prompt
    if decision.action == "reconcile":
        return route, first_prompt + self._continuation(item)
    refused = []
    if decision.action == "fallback_route":
        found, refused = self._fallback(item, role, route, decision.route)
        if found is not None:
            item.routes[role] = found
            item.state.setdefault("route_overrides", {})[role] = {
                key: found[key] for key in ("provider", "model_class", "effort") if found.get(key)}
            self._save()
            write_json(item.directory / "routes.json", item.routes)
            self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(found),
                               reason_code="ROUTE_FALLBACK",
                               message=f"{role}: {label} -> {self.label(found)} ({error['class']}; "
                                       f"{', '.join(decision.reason_codes)})")
            self._route_fallback(item, key, role, route, found, [error["class"], *decision.reason_codes])
            return found, first_prompt
    raise Stop(*self._provider_stop(role, route, run, error, decision, refused))


def past_reset(error: dict) -> bool:
    """A refused quota whose reset (``retry_after_s``, never negative) is 0: the provider's own reset time has passed and it
    still refuses. That is an unknown reset, not a reset now: no wait of 0 s, no gate, no "resume after <now>"."""
    return error.get("class") == "quota" and error.get("retry_after_s") == 0


def provider_stop(self, role: str, route: dict, run, error: dict, decision, refused: list) -> tuple:
    code = PROVIDER_STOP_CODES.get(error["class"]) or run.error
    text = f"{role} on {self.label(route)}: {error['class']} ({error.get('safe_message') or run.detail}); " \
           f"{', '.join(decision.reason_codes)}"
    if past_reset(error):
        text += "; the provider still refuses and its reset time is unknown" + (
            f" (it said the reset at {clock.utc_stamp(run.reset_at)}, already past)" if run.reset_at else " (its reset is already past)")
    elif error["class"] in ("quota", "rate_limit") and error.get("retry_after_s") is not None:
        reset = clock.utc_stamp(clock.wall() + error["retry_after_s"])
        text += f"; the limit resets {reset}, resume after {reset}"
    elif error["class"] in ("quota", "rate_limit"):
        text += "; the reset time is unknown, resume after the limit is lifted"
    if refused:
        text += f"; no admissible fallback route: {'; '.join(refused)}"
    return code, text


def gate(self, item: Item, route: dict, error: dict) -> None:
    """Remember an exhausted account quota with a known reset on the machine: nobody starts the provider again
    before it (``gates.py``). A gate that cannot be written does not stop the run."""
    if error["class"] != "quota" or error.get("retry_after_s") is None or past_reset(error) or error.get("scope") != "account":
        return
    now = clock.wall()
    try:
        gates.set_gate(route["provider"], until=now + error["retry_after_s"], code=error.get("code", "PROVIDER_QUOTA"),
                       run_id=self.run_id, now=now)
    except (gates.GateError, OSError) as failure:
        self.progress.emit("info", item=item.ref, reason_code="GATE_NOT_WRITTEN",
                           message=f"the capacity gate of {route['provider']} was not written: {failure}")


def wait(self, item: Item, key: str, role: str, error: dict, seconds: int, cancel) -> None:
    """Wait ``seconds`` before the repeat (a ``PROVIDER_WAIT`` beacon names the class, the wait and the reset)."""
    if seconds <= 0:
        return
    reset = clock.utc_stamp(clock.wall() + seconds)
    self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="PROVIDER_WAIT",
                       message=f"{role}: {error['class']}; waiting {seconds} s, until {reset}")
    self._provider_limit(item, key, role, (item.routes.get(role) or {}).get("provider"), error["class"],
                         "PROVIDER_WAIT", until=reset, wait_s=int(seconds))
    self._pause(seconds, cancel)


def pause(seconds: float, cancel=None) -> None:
    """Sleep ``seconds``, looking at ``cancel`` every second."""
    remaining = float(seconds)
    while remaining > 0:
        if cancel is not None and cancel.is_set():
            raise Stop("REVIEW_CANCELLED", "cancelled while waiting for the provider: the checks are red")
        step = min(1.0, remaining)
        clock.sleep(step)
        remaining -= step
