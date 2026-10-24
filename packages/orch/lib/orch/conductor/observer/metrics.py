"""The numbers of an observer report, computed from what ``reader`` read: no file is opened here."""
from __future__ import annotations

from collections import Counter, defaultdict
import re

from aicore.util import timefmt
from orch.conductor import progress as progress_mod

IDLE_S = 30
TOP_BLOCKS = 5
PROVENANCE_MAX = 5
_MODULE_SCRIPT = re.compile(r"packages/([A-Za-z0-9_.-]+)/scripts/(validate|test)\.sh\b")
_SUBSET_FLAG = re.compile(r"(?:^|\s)(?:-p|--pattern)(?:\s|=|$)")


def seconds_of(ts: str) -> float:
    value = timefmt.epoch(ts)
    if value is None:
        raise ValueError(f"not a timestamp: {ts!r}")
    return value


def count_events(found: list, since: str, until: str, correlations: set) -> dict:
    """Count only events of this run within the inclusive UTC window."""
    start, end = seconds_of(since), seconds_of(until)
    counts: Counter = Counter()
    for event in found:
        try:
            moment = seconds_of(event.time)
        except (AttributeError, ValueError):
            continue
        if start <= moment <= end and (event.subject in correlations or event.correlationid in correlations):
            counts[event.type] += 1
    return dict(sorted(counts.items()))


def prompt_blocks(manifests: list) -> dict:
    """``{role: rows}``: the ``TOP_BLOCKS`` prompt blocks with the most estimated tokens over the run, by role. Blocks of
    one kind, origin and id add up over the steps (``steps`` counts them); a manifest that cannot be read is skipped."""
    totals: dict = defaultdict(dict)
    for doc in manifests:
        try:
            rows = [(row["kind"], row["origin"], row.get("id") or "", int(row["tokens"])) for row in doc["blocks"]]
        except (ValueError, KeyError, TypeError):
            continue
        for kind, origin, ident, tokens in rows:
            entry = totals[doc.get("role", "-")].setdefault((kind, origin, ident), {"tokens": 0, "steps": 0})
            entry["tokens"] += tokens
            entry["steps"] += 1
    return {role: [{"kind": kind, "origin": origin, **({"id": ident} if ident else {}), **entry}
                   for (kind, origin, ident), entry in sorted(found.items(), key=lambda row: (-row[1]["tokens"], row[0]))[:TOP_BLOCKS]]
            for role, found in sorted(totals.items())}


def prompt_budgets(manifests: list) -> dict:
    """``{role: {class: {max_tokens, limit, steps, over}}}``: for each budget class of a role's prompts, the largest
    estimated tokens of a step, its limit, the steps measured and how many of them were past the limit (a limit of 0 is
    none). Manifests without ``budgets`` or that cannot be read are skipped."""
    found: dict = defaultdict(dict)
    for doc in manifests:
        try:
            rows = {name: (int(row["tokens"]), int(row["limit"])) for name, row in doc["budgets"].items()}
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        for name, (tokens, limit) in rows.items():
            entry = found[doc.get("role", "-")].setdefault(name, {"max_tokens": 0, "limit": limit, "steps": 0, "over": 0})
            entry["max_tokens"] = max(entry["max_tokens"], tokens)
            entry["limit"] = limit
            entry["steps"] += 1
            entry["over"] += 1 if limit and tokens > limit else 0
    return {role: dict(sorted(classes.items())) for role, classes in sorted(found.items())}


def check_rows(state: dict, inputs: dict) -> list:
    """Every command check result of the run: ``{item, stage, row, view, cadence}`` from ``state.items.*.steps.checks.*
    .result[]`` (and the steps of earlier attempts). ``view`` is ``progress.check_view``; ``cadence`` is the check's
    cadence from the item's ``input.json`` (``inputs[ref]``; ``None`` when that file is not there). A check without a
    command is a manual procedure and is not a command."""
    found = []
    for ref, item in (state.get("items") or {}).items():
        if not isinstance(item, dict):
            continue
        input_doc = inputs.get(ref)
        checks = ((input_doc or {}).get("acceptance") or {}).get("checks") if isinstance(input_doc, dict) else None
        cadence = {check.get("id"): check.get("cadence", "item") for check in checks or [] if isinstance(check, dict)} \
            if isinstance(checks, list) else None
        groups = [(0, item.get("steps"))] + [(attempt.get("n", 0), attempt.get("steps"))
                                              for attempt in item.get("attempts") or [] if isinstance(attempt, dict)]
        for attempt, steps in groups:
            for stage, step in (steps.items() if isinstance(steps, dict) else []):
                if not str(stage).startswith("checks.") or not isinstance(step, dict):
                    continue
                for row in progress_mod.check_rows({"items": {ref: {"steps": {stage: step}}}}, ref, stage):
                    if row.get("cmd"):
                        found.append({"item": ref, "stage": f"{stage}" if not attempt else f"{stage}@{attempt}", "row": row,
                                      "view": progress_mod.check_view(row),
                                      "cadence": None if cadence is None else cadence.get(row.get("id"), "item")})
    return found


def checks_by_command(rows: list) -> list:
    """``[{cmd, runs, executed, invocations, seconds, red, skipped, reused, retried, ids, contexts, items, ...}]`` from
    ``check_rows``, the most expensive command first. ``runs`` counts every row; ``executed`` rows ran a process
    (``invocations``, ``seconds`` is their elapsed time, not CPU time); ``red`` counts only executed rows that failed,
    never ``skipped`` or ``reused`` ones; ``retried`` counts executions of a check that an earlier round of the same item
    had already executed; ``saved_s`` is the time of the runs that ``reused`` rows stand for and ``reused_from`` lists
    their evidence."""
    table: dict = {}
    seen: Counter = Counter()
    for entry in rows:
        row, view = entry["row"], entry["view"]
        out = table.setdefault(row["cmd"], {"cmd": row["cmd"], "runs": 0, "executed": 0, "invocations": 0, "seconds": 0.0,
                                            "red": 0, "skipped": 0, "reused": 0, "retried": 0, "saved_s": 0,
                                            "ids": set(), "contexts": set(), "items": set(), "reused_from": []})
        out["runs"] += 1
        out["ids"].add(view["id"])
        out["contexts"].add(view["context"])
        out["items"].add(entry["item"])
        if view["skipped"]:
            out["skipped"] += 1
        elif view["reused"]:
            out["reused"] += 1
            out["saved_s"] += view.get("original_seconds") or 0
            if view.get("reused_from") and view["reused_from"] not in out["reused_from"] \
                    and len(out["reused_from"]) < PROVENANCE_MAX:
                out["reused_from"].append(view["reused_from"])
        else:
            out["executed"] += 1
            out["invocations"] += 1
            out["seconds"] += view["seconds"] if isinstance(view["seconds"], (int, float)) else 0
            out["red"] += 0 if view["green"] else 1
            key = (entry["item"], view["id"], row["cmd"])
            out["retried"] += 1 if seen[key] else 0
            seen[key] += 1
    return [dict(row, seconds=round(row["seconds"], 1), ids=sorted(map(str, row["ids"])), contexts=sorted(row["contexts"]),
                 items=sorted(map(str, row["items"])))
            for row in sorted(table.values(), key=lambda row: (-row["seconds"], row["cmd"]))]


def _module_runs(cmd: str) -> dict:
    """``{module: "validate" | "full" | "subset"}`` of the module scripts a command runs (``validate`` only when it does
    not skip its tests); ``{"": "affected"}`` for ``affected-tests.py --run`` without a tier."""
    found = {}
    for match in _MODULE_SCRIPT.finditer(cmd):
        module, script = match.groups()
        if script == "validate":
            if "SKM_VALIDATE_SKIP_TESTS=1" not in cmd:
                found[module] = "validate"
        else:
            found[module] = "subset" if _SUBSET_FLAG.search(cmd[match.end():].split("&&")[0].split(";")[0]) else "full"
    if "affected-tests.py" in cmd and "--run" in cmd and "--tier" not in cmd:
        found[""] = "affected"
    return found


def duplicate_modules(rows: list) -> list:
    """``[(item, module, cmd1, cmd2)]``: two commands that really ran in one round of an item, in the same context, and
    repeat the tests of a module (validate.sh with its tests next to the full test.sh or ``affected-tests.py --run``, a
    full test.sh next to its ``-p`` subset). Skipped and reused rows ran nothing; other contexts are not duplicates."""
    rounds: dict = defaultdict(dict)
    for entry in rows:
        if entry["view"]["executed"]:
            rounds[(entry["item"], entry["stage"], entry["view"]["context"])].setdefault(entry["row"]["cmd"], None)
    found, seen = [], set()
    for (item, _stage, _context), commands in sorted(rounds.items(), key=lambda pair: str(pair[0])):
        runs = {cmd: _module_runs(cmd) for cmd in commands}
        for module in sorted({module for kinds in runs.values() for module in kinds if module}):
            for first in sorted(runs):
                for second in sorted(runs):
                    if first < second and _repeats(module, runs[first], runs[second]) \
                            and (item, module, first, second) not in seen:
                        seen.add((item, module, first, second))
                        found.append((item, module, first, second))
    return found


def _repeats(module: str, first: dict, second: dict) -> bool:
    kinds = (first.get(module), second.get(module))
    if "validate" in kinds and kinds[0] != kinds[1]:
        other = second if kinds[0] == "validate" else first
        return other.get(module) == "full" or other.get("") == "affected"
    return set(kinds) == {"full", "subset"}


def phase_after_red(rows: list) -> list:
    """``[(item, stage)]``: rounds in which a ``phase`` check was started or reused although an item check of the round
    was red (rows of a conductor that did not gate them); needs the cadence from ``input.json``."""
    rounds: dict = defaultdict(lambda: {"red": False, "phase": False})
    for entry in rows:
        view, cadence = entry["view"], entry["cadence"]
        if cadence == "item" and view["executed"] and not view["green"]:
            rounds[(entry["item"], entry["stage"])]["red"] = True
        elif cadence == "phase" and not view["skipped"]:
            rounds[(entry["item"], entry["stage"])]["phase"] = True
    return sorted(key for key, value in rounds.items() if value["red"] and value["phase"])


def executor_runs_checks(options_docs: dict) -> list:
    """The pieces whose effective options set ``checks.executor_runs_checks`` true (``{ref: options.json or None}``)."""
    found = []
    for ref, doc in options_docs.items():
        options = (doc or {}).get("options") if isinstance(doc, dict) else None
        checks = options.get("checks") if isinstance(options, dict) else None
        if isinstance(checks, dict) and checks.get("executor_runs_checks") is True:
            found.append(ref)
    return found


def journal_totals(lines: list, outcomes: dict) -> dict:
    """Red checks, tokens and seconds by role and the idle time between stages, from the progress lines. ``outcomes`` is
    ``{(item, stage, check id): view}`` of the checks that the state recorded."""
    red: Counter = Counter()
    tokens: dict = defaultdict(lambda: {"input": 0, "output": 0})
    seconds: Counter = Counter()
    idle_total, idle_max, idle_where = 0.0, 0.0, None
    previous_end = None
    for line in lines:
        event = line.get("event")
        if event == "stage.end":
            stage = line.get("stage", "")
            verdict = line.get("verdict", "")
            if stage.startswith("checks.") and verdict.startswith("red "):
                for name in verdict[4:].split(","):
                    shown = outcomes.get((line.get("item"), stage, name.strip()))
                    if shown is not None and (shown["skipped"] or shown["reused"] or shown["green"]):
                        continue  # a journal of an older conductor named it: it did not run and fail
                    red[name.strip()] += 1
            role = line.get("role", "deterministic")
            if line.get("tokens"):
                for key in ("input", "output"):
                    tokens[role][key] += line["tokens"][key]
            seconds[role] += line.get("duration_s") or 0
            previous_end = line
        elif event == "stage.start" and previous_end is not None:
            gap = seconds_of(line["ts"]) - seconds_of(previous_end["ts"])
            if gap > IDLE_S:
                idle_total += gap
                if gap > idle_max:
                    idle_max, idle_where = gap, f"{previous_end.get('stage')} → {line.get('stage')}"
            previous_end = None
        elif event in ("item.start", "run.resume"):
            previous_end = None
    return {"red": red, "tokens": tokens, "seconds": seconds,
            "idle": {"total": idle_total, "max": idle_max, "where": idle_where}}


SESSION_REASON = re.compile(r"(?:reuse|reason)=(\S+)")


def session_totals(lines: list) -> dict:
    """``{resumed: {reuse: n}, fresh: {reason: n}}``: the executor attempts that resumed a session and those that started a
    fresh one, from the ``SESSION_RESUMED`` / ``SESSION_FRESH`` lines of the journal."""
    found: dict = {"resumed": Counter(), "fresh": Counter()}
    for line in lines:
        if line.get("event") != "info" or line.get("reason_code") not in ("SESSION_RESUMED", "SESSION_FRESH"):
            continue
        named = SESSION_REASON.search(line.get("message") or "")
        found["resumed" if line["reason_code"] == "SESSION_RESUMED" else "fresh"][named[1] if named else "unknown"] += 1
    return {name: dict(sorted(counts.items())) for name, counts in found.items()}


def item_totals(state: dict) -> dict:
    """Review findings by severity, triage and scout counts and one row per piece, from the state."""
    severities: Counter = Counter()
    confirmed = rejected = 0
    scout_hits = scout_runs = 0
    items = []
    for ref, item in (state.get("items") or {}).items():
        steps = {key: step for key, step in item.get("steps", {}).items() if step.get("status") == "done"}
        for key, step in steps.items():
            result = step.get("result") or {}
            if key.startswith("review."):
                severities.update(finding["severity"] for finding in result.get("findings", {}).get("findings", []))
            elif key.startswith("triage."):
                confirmed += len(result.get("triage", {}).get("confirmed", []))
                rejected += len(result.get("triage", {}).get("rejected", []))
            elif key == "scout":
                scout_runs += 1
                scout_hits += 1 if result.get("hit") else 0
        items.append({"item": ref, "outcome": item.get("outcome"), "stop": item.get("stop"),
                      "check_fixes": item.get("check_fixes_used", 0), "corrections": item.get("corrections_used", 0),
                      "retries": item.get("retries_used", 0), "tokens": item.get("tokens", {"input": 0, "output": 0}),
                      "attempts": [{"n": attempt["n"], "retried_at": attempt.get("retried_at"),
                                    "steps": {key: step.get("verdict") for key, step in attempt.get("steps", {}).items()}}
                                   for attempt in item.get("attempts", [])],
                      "reviews": sum(1 for key in steps if key.startswith("review.")) + sum(
                          1 for attempt in item.get("attempts", []) for key in attempt.get("steps", {}) if key.startswith("review."))})
    return {"severities": severities, "confirmed": confirmed, "rejected": rejected,
            "scout_hits": scout_hits, "scout_runs": scout_runs, "items": items}


def group_review_totals(group_reviews: dict, severities: Counter) -> list:
    """The numbers of the group reviews of the run: their findings are added to ``severities``; the result lists the groups
    whose review is incomplete (the role failed, a count is missing or the format is unknown)."""
    incomplete = []
    for number, review in group_reviews.items():
        counts = review.get("counts") if isinstance(review, dict) else None
        if not isinstance(counts, dict) or any(type(counts.get(key)) is not int or counts[key] < 0
                                               for key in ("Blocker", "Major", "Minor")) \
                or review.get("error") or review.get("format") not in ("findings", "none"):
            incomplete.append(str(number))
            continue
        severities.update({key: counts[key] for key in ("Blocker", "Major", "Minor") if counts[key]})
    return incomplete
