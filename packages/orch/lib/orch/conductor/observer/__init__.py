"""The observer of a conductor run: it only reads.

It reads the progress journal and the state of the run, and the correlated ``orch.*`` and ``planner.*`` events of the
project's aicore event journal within the run's UTC window, and writes ``observer.json`` and ``observer.md`` into the
reports folder (``.swissknifeman/orch/reports/<run>/``, ignored run output): repeats and resumes, red checks, review
findings by class, idle time between stages, tokens and time by role, the beacons and mends of the run (slow or
silent steps, rounds past a target, healed and repaired results), the share of the wall time spent in checks, stops,
the blocks that cost the most prompt tokens by role and the prompt budget classes against their limits (both from
``prompts/*.manifest.json``), the metrics of every piece (``metrics``: wall and active time by role, rounds, repeats after
a resume, mends, beacons, tokens, deviations, findings, health transitions of ``supervisor.jsonl``; always, debug or
not, never from a raw stream), and proposals to improve the run options.
``follow`` prints the notable lines of a run that is still going.

The package keeps the seams apart: ``reader`` (the only module that opens a file, and the incremental
``ProgressCursor``), ``metrics`` (the numbers, no I/O), ``proposals``, ``render`` (markdown) and ``follow``. This module
assembles the report and writes it; the names the callers and the tests use are importable from here.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import time

from aicore.util.redact import env_secrets, redact_document
from orch.conductor import questions as questions_mod, records
from orch.conductor.observer import metrics, reader
from orch.conductor.observer.follow import follow
from orch.conductor.observer.metrics import IDLE_S, TOP_BLOCKS, checks_by_command, duplicate_modules, phase_after_red
from orch.conductor.observer.metrics import seconds_of as _seconds
from orch.conductor.observer.proposals import proposals
from orch.conductor.observer.reader import EVENT_TYPES
from orch.conductor.policies import review_strategy as strategy
from orch.conductor.observer.render import markdown
from orch.conductor.infrastructure.files import safe

__all__ = ["EVENT_TYPES", "IDLE_S", "TOP_BLOCKS", "build", "follow", "item_metrics", "markdown", "proposals",
           "prompt_blocks", "prompt_budgets", "write_report"]


def prompt_blocks(directory: Path) -> dict:
    """``{role: rows}``: the ``TOP_BLOCKS`` prompt blocks with the most estimated tokens over the run, by role (see
    ``metrics.prompt_blocks``)."""
    return metrics.prompt_blocks(reader.manifests(directory))


def prompt_budgets(directory: Path) -> dict:
    """``{role: {class: {max_tokens, limit, steps, over}}}`` of the prompt manifests of the run (see
    ``metrics.prompt_budgets``)."""
    return metrics.prompt_budgets(reader.manifests(directory))


def _item_metrics(directory: Path, lines: list, state: dict, by_agent: list) -> dict:
    folders = {safe(str(ref)): ref for ref in (state.get("items") or {})}
    agents: dict = {}
    for row in by_agent:
        agents.setdefault(folders.get(row["item"], row["item"]), []).append(row)
    return metrics.item_metrics(lines, state, agents, reader.supervisor_actions(directory))


def item_metrics(directory: Path) -> dict:
    """``{items: [row], health_transitions}``: the metrics of every piece of the run in ``directory`` (see
    ``metrics.item_metrics``), from its journal, state, agent records and ``supervisor.jsonl``; debug or not."""
    lines, _discarded = reader.journal(directory)
    return _item_metrics(directory, lines, reader.state(directory), reader.agent_runs(directory))


def build(directory: Path, project: Path) -> dict:
    """The observer report of the run in ``directory``."""
    lines, discarded = reader.journal(directory)
    state = reader.state(directory)
    run_id = lines[0]["run"] if lines else Path(directory).name
    started = lines[0]["ts"] if lines else None
    repeats = [line for line in lines if line.get("event") == "info" and "repeating" in line.get("message", "")]
    rows = metrics.check_rows(state, reader.input_docs(directory, state))
    outcomes = {(entry["item"], entry["stage"], entry["view"]["id"]): entry["view"] for entry in rows}
    totals = metrics.journal_totals(lines, outcomes)
    red, tokens, seconds, idle = totals["red"], totals["tokens"], totals["seconds"], totals["idle"]
    found = metrics.item_totals(state)
    severities, items = found["severities"], found["items"]
    group_reviews = state.get("group_reviews") or {}
    incomplete_groups = metrics.group_review_totals(group_reviews, severities)
    by_agent = reader.agent_runs(directory)
    correlations = {run_id} | {item.get("orch_run") for item in (state.get("items") or {}).values()
                               if item.get("orch_run")}
    until = (state.get("ended") if state.get("status") != "running" else None) or (lines[-1]["ts"] if lines else None)
    counts, problems = _events(project, started, until, correlations) if started else ({}, [])
    codes = Counter(line.get("reason_code") for line in lines if line.get("event") == "info" and line.get("reason_code"))
    if codes.get("GROUP_REVIEW_FAILED") and not incomplete_groups:
        incomplete_groups.append("GROUP_REVIEW_FAILED")
    incomplete_groups += [f"{number} not run ({', '.join(done)} unreviewed)"
                          for number, done, _open in strategy.unreviewed_groups(state)]
    wall = (_seconds(lines[-1]["ts"]) - _seconds(lines[0]["ts"])) if len(lines) > 1 else 0.0
    report = {
        "schema": "orch-conductor-observer/v1", "run": run_id, "started": started,
        "beacons": dict(sorted(codes.items())),
        "long_run": ({"active_s": state.get("active_s", 0), "share": {
            "retries": sum(item.get("retries_used", 0) for item in (state.get("items") or {}).values()),
            "review_s": round(seconds.get("reviewer", 0), 1), "checks_s": round(seconds.get("deterministic", 0), 1),
            "repeats": len(repeats)}} if codes.get("RUN_SLOW") else None),
        "wall_s": round(wall, 1),
        "checks_share": round(seconds.get("deterministic", 0) / wall, 2) if wall else 0.0,
        "ended": lines[-1]["ts"] if lines else None, "status": state.get("status"), "stop": state.get("stop"),
        "last_stop": state.get("last_stop"),
        "resumes": sum(1 for line in lines if line.get("event") == "run.resume"),
        "repeats": [{"item": line.get("item"), "stage": line.get("stage"), "message": line.get("message")}
                    for line in repeats],
        "red_checks": dict(sorted(red.items())),
        "checks_by_command": checks_by_command(rows),
        "check_findings": {
            "duplicate_modules": [{"item": item, "module": module, "cmds": [first, second]}
                                  for item, module, first, second in duplicate_modules(rows)],
            "phase_after_red": [{"item": item, "step": stage} for item, stage in phase_after_red(rows)],
            "executor_runs_checks": metrics.executor_runs_checks(reader.item_options(directory, state))},
        "findings_by_severity": dict(sorted(severities.items())),
        "group_reviews": group_reviews, "incomplete_group_reviews": incomplete_groups,
        "triage": {"confirmed": found["confirmed"], "rejected": found["rejected"]},
        "idle": {"total_s": round(idle["total"], 1), "max_s": round(idle["max"], 1), "max_between": idle["where"]},
        "tokens_by_role": {role: value for role, value in sorted(tokens.items())},
        "tokens_by_agent": by_agent,
        "prompt_blocks_by_role": prompt_blocks(directory),
        "prompt_budgets_by_role": prompt_budgets(directory),
        "open_questions": questions_mod.listing(directory, time.time()),
        "seconds_by_role": {role: round(value, 1) for role, value in sorted(seconds.items())},
        "scout_cache": {"runs": found["scout_runs"], "hits": found["scout_hits"]},
        "sessions": metrics.session_totals(lines),
        "items": items, "metrics": _item_metrics(directory, lines, state, by_agent),
        "events": counts, "event_problems": problems,
    }
    if discarded:  # lines of progress.jsonl that were left out (not progress-line documents) or quarantined at write
        report["discarded_lines"] = discarded
    report["proposals"] = proposals(report)
    return redact_document(report, secrets=env_secrets())


def _events(project: Path, since: str, until: str, correlations: set) -> tuple:
    """Count only events of this run within the inclusive UTC window; report an unreadable journal."""
    found, problems = reader.events(project)
    if found is None:
        return {}, problems
    return metrics.count_events(found, since, until, correlations), problems


def write_report(directory: Path, project: Path, target: Path) -> dict:
    """``observer.json`` (records/v1 ``observer-report``, checked first: ``RECORD_INVALID`` writes nothing) and
    ``observer.md`` of the run in ``directory``."""
    report = records.check(build(directory, project), "observer-report", target / "observer.json",
                           hint=records.WRITER_HINT)
    target.mkdir(parents=True, exist_ok=True)
    records.write(target / "observer.json", report, "observer-report")
    (target / "observer.md").write_text(markdown(report), encoding="utf-8")
    return {"json": str(target / "observer.json"), "markdown": str(target / "observer.md")}
