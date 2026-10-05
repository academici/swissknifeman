"""Scout (dossier §12, D3): a weak model of the current provider maps where to look; it never writes code.

``run`` hands the deterministic context pack to the provider's economy CLI (``orchestration.scout.<provider>`` in
``command-routing.json``; the prompt goes through stdin), keeps at most ``MAX_LINES`` lines of "path[:symbol] — why"
plus the unknowns block in ``context/<item>.scout.md`` and logs one ``scout`` event. Any failure is an outcome, never
an exception: the caller (``lifecycle.start``) continues without the map.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import time
from typing import Callable

from task.command_catalog import SCOUT_PLACEHOLDERS, load_routing_metadata

from . import context, lifecycle, store, views
from .model import PlanError
from .templating import render as _render_template

MAX_LINES = 40
_ENTRY = re.compile(r"^(?:- |[\w@./\\-]+(?::[\w.<>-]+)?\s+[—–-]\s+\S)")
_UNKNOWNS = re.compile(r"^unknowns?\s*:", re.IGNORECASE)


@dataclass(frozen=True)
class ScoutResult:
    outcome: str  # ok | failed | skipped
    provider: str
    model: str
    seconds: float
    lines: int
    path: Path | None = None
    reason: str = ""

    def text(self, item_id: str) -> str:
        detail = f"{self.lines} lines, {self.seconds:.0f}s" if self.outcome == "ok" else self.reason
        return f"scout {item_id}: {self.outcome} ({detail})"


def filter_answer(output: str, limit: int = MAX_LINES) -> list[str]:
    """Entries ("- …" or "path[:symbol] — why") and the ``Unknowns:`` block of ``output``, cut to ``limit`` lines."""
    kept: list[str] = []
    unknowns = False
    for raw in output.splitlines():
        text = raw.strip()
        if not text:
            continue
        if _UNKNOWNS.match(text):
            unknowns = True
            kept.append(text)
        elif unknowns or _ENTRY.match(text):
            kept.append(text)
    return kept[:limit]


def _prompt(plan: store.Plan, item_id: str) -> str:
    model = {"max_lines": MAX_LINES, "ref": f"{plan.plan.get('short_id') or plan.root.name}.{item_id}",
             "pack": context.render(plan, item_id, with_scout=False).rstrip("\n")}
    return _render_template(views._load_template("scout-prompt"), model, lambda name: views._load_template(f"_{name}"))


def _argv(entry: dict, cwd: Path) -> list[str]:
    values = {"model": entry["model"], "effort": entry["effort"], "cwd": str(cwd)}
    return [re.sub(r"\{(\w+)\}", lambda m: values[m[1]] if m[1] in SCOUT_PLACEHOLDERS else m[0], arg)
            for arg in entry["argv"]]


def _config(provider: str, routing_path: str | Path | None) -> dict | None:
    """The scout entry of ``provider``; None when the provider has none. Raises ``ValueError`` when unreadable."""
    metadata = load_routing_metadata(Path(routing_path) if routing_path else lifecycle.ROUTING_PATH)
    return metadata.get("orchestration", {}).get("scout", {}).get(provider)


def _attempt(plan: store.Plan, item_id: str, entry: dict, runner: Callable) -> tuple[str, str, int]:
    """``(outcome, reason, lines)``; writes or removes ``context/<item>.scout.md``."""
    target = plan.root / context.PACK_DIR / f"{item_id}.scout.md"
    reason, kept = "", []
    try:
        done = runner(_argv(entry, plan.repo_root), input=_prompt(plan, item_id), capture_output=True, text=True,
                      timeout=entry["timeout_s"], cwd=plan.repo_root)
    except subprocess.TimeoutExpired:
        reason = f"timeout after {entry['timeout_s']}s"
    except (OSError, ValueError) as exc:
        reason = f"cannot run {entry['argv'][0]}: {exc}"
    else:
        if done.returncode != 0:
            tail = (done.stderr or "").strip().splitlines()[-1:] or [""]
            reason = f"exit {done.returncode}" + (f": {tail[0][:200]}" if tail[0] else "")
        else:
            kept = filter_answer(done.stdout or "")
            if not kept:
                reason = "empty answer"
    if reason:
        target.unlink(missing_ok=True)  # a stale map must not outlive a failed run
        return "failed", reason, 0
    store.atomic_write(target, "\n".join(kept) + "\n")
    return "ok", "", len(kept)


def run(plan, item_id: str, provider: str, *, runner: Callable | None = None,
        routing_path: str | Path | None = None) -> ScoutResult:
    """Scout ``item_id`` with the provider's weak model and log the ``scout`` event; never raises for a scout failure."""
    runner = runner or subprocess.run  # looked up per call so a caller (or a test) can replace subprocess.run
    snapshot = plan if isinstance(plan, store.Plan) else store.load_plan(store.resolve_plan_dir(plan))
    if item_id not in snapshot.items:
        raise PlanError("REF_UNKNOWN", f"unknown item {item_id!r}")
    started = time.monotonic()
    try:
        entry = _config(provider, routing_path)
    except ValueError as exc:
        entry, outcome, reason, lines = None, "failed", f"routing config unreadable: {exc}", 0
    else:
        outcome, reason, lines = ("skipped", f"no scout entry for provider {provider}", 0) if entry is None else (None, "", 0)
    if entry is not None:
        outcome, reason, lines = _attempt(snapshot, item_id, entry, runner)
    seconds = round(time.monotonic() - started, 1)
    model = entry["model"] if entry else "none"
    result = ScoutResult(outcome, provider, model, seconds, lines,
                         snapshot.root / context.PACK_DIR / f"{item_id}.scout.md" if outcome == "ok" else None, reason)
    event = store.new_event("scout", result.text(item_id), {"provider": provider, "model": model}, item=item_id,
                            phase=item_id.split(".", 1)[0],
                            data={"provider": provider, "model": model, "outcome": outcome, "seconds": seconds,
                                  "lines": lines, **({"reason": reason} if reason else {})})
    with lifecycle._mutation(plan if isinstance(plan, store.Plan) else snapshot.root) as (fresh, lock):
        lifecycle._commit(fresh, [], [event], lock)
    return result
