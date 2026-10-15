"""The observer of a conductor run: it only reads.

It reads the progress journal and the state of the run, and the ``orch.run.*`` and ``planner.*`` events of the
project's aicore event journal since the run started, and writes ``observer.json`` and ``observer.md`` into the
reports folder (``.swissknifeman/orch/reports/<run>/``, ignored run output): repeats and resumes, red checks, review
findings by class, idle time between stages, tokens and time by role, the beacons and mends of the run (slow or
silent steps, rounds past a target, healed and repaired results), the share of the wall time spent in checks, stops,
the blocks that cost the most prompt tokens by role and the prompt budget classes against their limits (both from
``prompts/*.manifest.json``), and proposals to improve the run
options.
``follow`` prints the notable lines of a run that is still going.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import time

from aicore.util.redact import env_secrets, redact_document
from orch.conductor import agents as agents_mod, progress as progress_mod, prompts as prompts_mod, questions as questions_mod

IDLE_S = 30
TOP_BLOCKS = 5
EVENT_TYPES = ("orch.run.*", "planner.*")


def _seconds(ts: str) -> float:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").timestamp()


def _events(project: Path, since: str) -> tuple:
    """``(counts by type, problems)`` of the journal events at or after ``since``; an unreadable journal is a problem."""
    try:
        from aicore.ext import events as journal
        found, problems = journal.read_events(project, types=list(EVENT_TYPES))
    except Exception as error:  # noqa: BLE001 — the observer reports what it could not read
        return {}, [f"{type(error).__name__}: {error}"]
    start = _seconds(since)
    counts: Counter = Counter()
    for event in found:
        try:
            moment = datetime.fromisoformat(event.time.replace("Z", "+00:00")).timestamp()
        except (AttributeError, ValueError):
            continue
        if moment >= start:
            counts[event.type] += 1
    return dict(sorted(counts.items())), [f"{item.get('code')}: {item.get('message')}" for item in problems[:5]]


def prompt_blocks(directory: Path) -> dict:
    """``{role: rows}``: the ``TOP_BLOCKS`` prompt blocks with the most estimated tokens over the run, by role. Blocks of
    one kind, origin and id add up over the steps (``steps`` counts them); a manifest that cannot be read is skipped."""
    totals: dict = defaultdict(dict)
    for file in sorted(Path(directory).glob("*/prompts/*.manifest.json")):
        try:
            doc = json.loads(file.read_text(encoding="utf-8"))
            rows = [(row["kind"], row["origin"], row.get("id") or "", int(row["tokens"])) for row in doc["blocks"]]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        for kind, origin, ident, tokens in rows:
            entry = totals[doc.get("role", "-")].setdefault((kind, origin, ident), {"tokens": 0, "steps": 0})
            entry["tokens"] += tokens
            entry["steps"] += 1
    return {role: [{"kind": kind, "origin": origin, **({"id": ident} if ident else {}), **entry}
                   for (kind, origin, ident), entry in sorted(found.items(), key=lambda row: (-row[1]["tokens"], row[0]))[:TOP_BLOCKS]]
            for role, found in sorted(totals.items())}


def prompt_budgets(directory: Path) -> dict:
    """``{role: {class: {max_tokens, limit, steps, over}}}``: for each budget class of a role's prompts, the largest
    estimated tokens of a step, its limit, the steps measured and how many of them were past the limit (a limit of 0 is
    none). Manifests without ``budgets`` or that cannot be read are skipped."""
    found: dict = defaultdict(dict)
    for file in sorted(Path(directory).glob("*/prompts/*.manifest.json")):
        try:
            doc = json.loads(file.read_text(encoding="utf-8"))
            rows = {name: (int(row["tokens"]), int(row["limit"])) for name, row in doc["budgets"].items()}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        for name, (tokens, limit) in rows.items():
            entry = found[doc.get("role", "-")].setdefault(name, {"max_tokens": 0, "limit": limit, "steps": 0, "over": 0})
            entry["max_tokens"] = max(entry["max_tokens"], tokens)
            entry["limit"] = limit
            entry["steps"] += 1
            entry["over"] += 1 if limit and tokens > limit else 0
    return {role: dict(sorted(classes.items())) for role, classes in sorted(found.items())}


def build(directory: Path, project: Path) -> dict:
    """The observer report of the run in ``directory``."""
    lines = progress_mod.read_lines(directory)
    try:
        state = json.loads((Path(directory) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    run_id = lines[0]["run"] if lines else Path(directory).name
    started = lines[0]["ts"] if lines else None
    repeats = [line for line in lines if line.get("event") == "info" and "repeating" in line.get("message", "")]
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
                    red[name.strip()] += 1
            role = line.get("role", "deterministic")
            if line.get("tokens"):
                for key in ("input", "output"):
                    tokens[role][key] += line["tokens"][key]
            seconds[role] += line.get("duration_s") or 0
            previous_end = line
        elif event == "stage.start" and previous_end is not None:
            gap = _seconds(line["ts"]) - _seconds(previous_end["ts"])
            if gap > IDLE_S:
                idle_total += gap
                if gap > idle_max:
                    idle_max, idle_where = gap, f"{previous_end.get('stage')} → {line.get('stage')}"
            previous_end = None
        elif event in ("item.start", "run.resume"):
            previous_end = None
    severities: Counter = Counter()
    confirmed = rejected = 0
    scout_hits = scout_runs = 0
    items = []
    for ref, item in (state.get("items") or {}).items():
        steps = item.get("steps", {})
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
                      "retries": item.get("retries_used", 0), "tokens": item.get("tokens", {"input": 0, "output": 0})})
    by_agent = []
    for folder in sorted(Path(directory).glob("*/")):
        for row in agents_mod.read(folder):
            by_agent.append({"item": folder.name, **row})
    counts, problems = _events(project, started) if started else ({}, [])
    codes = Counter(line.get("reason_code") for line in lines if line.get("event") == "info" and line.get("reason_code"))
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
        "resumes": sum(1 for line in lines if line.get("event") == "run.resume"),
        "repeats": [{"item": line.get("item"), "stage": line.get("stage"), "message": line.get("message")}
                    for line in repeats],
        "red_checks": dict(sorted(red.items())),
        "findings_by_severity": dict(sorted(severities.items())),
        "triage": {"confirmed": confirmed, "rejected": rejected},
        "idle": {"total_s": round(idle_total, 1), "max_s": round(idle_max, 1), "max_between": idle_where},
        "tokens_by_role": {role: value for role, value in sorted(tokens.items())},
        "tokens_by_agent": by_agent,
        "prompt_blocks_by_role": prompt_blocks(directory),
        "prompt_budgets_by_role": prompt_budgets(directory),
        "open_questions": questions_mod.listing(directory, time.time()),
        "seconds_by_role": {role: round(value, 1) for role, value in sorted(seconds.items())},
        "scout_cache": {"runs": scout_runs, "hits": scout_hits},
        "items": items, "events": counts, "event_problems": problems,
    }
    report["proposals"] = proposals(report)
    return redact_document(report, secrets=env_secrets())


def proposals(report: dict) -> list:
    """Changes to the run options or the work that the numbers point at; plain rules, no model."""
    found = []
    if report["red_checks"]:
        names = ", ".join(sorted(report["red_checks"]))
        found.append(f"Checks {names} went red after the executor: add a run rule that names the exact commands to run "
                     "before reporting, or give the checks a faster local variant.")
    if report["triage"]["rejected"] and report["triage"]["rejected"] >= report["triage"]["confirmed"]:
        found.append("Most review findings did not reproduce: tighten the reviewer brief (scope, contract) or its "
                     "skills before paying for another round.")
    if report["repeats"]:
        found.append(f"{len(report['repeats'])} role run(s) were repeated (failed run or output outside its "
                     "contract): check the provider and the result block of that role.")
    beacons = report.get("beacons") or {}
    if beacons.get("RESULT_HEALED", 0) + beacons.get("RESULT_REPAIRED", 0) >= 2:
        found.append("Role results needed mending more than once: compare the result blocks in the streams with the "
                     "contract text of the prompt; a recurring mend is a prompt or contract to fix at its source.")
    if beacons.get("LIMIT_OVER"):
        found.append(f"{beacons['LIMIT_OVER']} round(s) went past a target: the item was larger or riskier than its "
                     "plan said; split items like it, or raise the target in their options.")
    if report.get("checks_share", 0) > 0.5:
        found.append(f"Checks took {int(report['checks_share'] * 100)} % of the wall time: move repository-wide checks "
                     "to phase.validation, turn on checks.red_first, or run them in parallel (checks.parallel).")
    if report["idle"]["total_s"] > 300:
        found.append(f"{int(report['idle']['total_s'])} s of idle time between stages, the longest at "
                     f"{report['idle']['max_between']}: look at the work source calls there.")
    if report["scout_cache"]["runs"] and not report["scout_cache"]["hits"] and report["resumes"]:
        found.append("The scout ran again after a resume without a cache hit: the brief changed between the runs.")
    for item in report["items"]:
        if item["outcome"] == "blocked":
            found.append(f"{item['item']} is blocked: answer its escalation, then resume or run it again.")
        elif item["outcome"] == "stopped" and item.get("stop"):
            found.append(f"{item['item']} stopped with {item['stop']['code']}: fix the cause, then resume.")
    for role, classes in (report.get("prompt_budgets_by_role") or {}).items():
        for name, row in classes.items():
            if row["over"]:
                found.append(f"The {name} part of the {role} prompt was past limits.{prompts_mod.BUDGET_LIMITS[name]} ({row['limit']}) in "
                             f"{row['over']} of {row['steps']} step(s), up to {row['max_tokens']} tokens: read it with "
                             "conduct.py prompt explain, then shorten its source or raise the limit; the conductor cuts nothing.")
    overdue = [row for row in report.get("open_questions", []) if row["overdue"]]
    if overdue:
        found.append(f"{len(overdue)} question(s) wait for an answer past limits.question_warn_s: "
                     + ", ".join(f"{row['item']} {row['id']}" for row in overdue)
                     + "; conduct.py answer, then resume --retry.")
    tokens = report["tokens_by_role"]
    total = sum(value["input"] + value["output"] for value in tokens.values())
    for role, value in tokens.items():
        share = (value["input"] + value["output"]) / total if total else 0
        if role in ("context-scout", "triager") and share > 0.4:
            found.append(f"{role} used {int(share * 100)} % of the tokens: give it a cheaper model class.")
    return found


def markdown(report: dict) -> str:
    lines = [f"# Observer report {report['run']}", "",
             f"- Status: {report['status']}" + (f" ({report['stop']['code']}: {report['stop']['message']})"
                                                 if report.get("stop") else ""),
             f"- Time: {report['started']} → {report['ended']}; resumes {report['resumes']}",
             f"- Repeated role runs: {len(report['repeats'])}",
             f"- Red checks: {', '.join(f'{k}×{v}' for k, v in report['red_checks'].items()) or 'none'}",
             f"- Review findings: {', '.join(f'{k} {v}' for k, v in report['findings_by_severity'].items()) or 'none'}"
             f"; triage confirmed {report['triage']['confirmed']}, rejected {report['triage']['rejected']}",
             f"- Idle between stages: {report['idle']['total_s']} s (longest {report['idle']['max_s']} s"
             + (f", {report['idle']['max_between']}" if report['idle']['max_between'] else "") + ")",
             f"- Scout cache: {report['scout_cache']['hits']}/{report['scout_cache']['runs']} hits",
             f"- Wall time {report['wall_s']} s; checks {int(report['checks_share'] * 100)} % of it",
             f"- Beacons and mends: {', '.join(f'{k}×{v}' for k, v in report['beacons'].items()) or 'none'}", "",
             "## Items", "", "| Item | Outcome | Check fixes | Corrections | Repeats | Tokens in/out |",
             "| --- | --- | --- | --- | --- | --- |"]
    for item in report["items"]:
        outcome = item["outcome"] or "-"
        if item.get("stop"):
            outcome += f" ({item['stop']['code']})"
        lines.append(f"| {item['item']} | {outcome} | {item['check_fixes']} | {item['corrections']} | "
                     f"{item['retries']} | {item['tokens'].get('input', 0)}/{item['tokens'].get('output', 0)} |")
    lines += ["", "## Roles", "", "| Role | Seconds | Tokens in/out |", "| --- | --- | --- |"]
    for role in sorted(set(report["seconds_by_role"]) | set(report["tokens_by_role"])):
        value = report["tokens_by_role"].get(role, {"input": 0, "output": 0})
        lines.append(f"| {role} | {report['seconds_by_role'].get(role, 0)} | {value['input']}/{value['output']} |")
    if report.get("tokens_by_agent"):
        lines += ["", "## Agent runs", "", "| Agent | Item | Role | Step | Status | Tokens in/out |",
                  "| --- | --- | --- | --- | --- | --- |"]
        lines += [f"| {row['agent_run_id']} | {row['item']} | {row['role']} | {row['step']} | {row['status']} | "
                  f"{row['tokens']['input']}/{row['tokens']['output']} |" for row in report["tokens_by_agent"]]
    if report.get("prompt_blocks_by_role"):
        lines += ["", "## Prompt blocks", "", "Top blocks by estimated tokens, over the steps of the run.", "",
                  "| Role | Kind | Origin | Tokens | Steps |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {role} | {row['kind']}{' ' + row['id'] if row.get('id') else ''} | {row['origin']} | {row['tokens']} | "
                  f"{row['steps']} |" for role, rows in report["prompt_blocks_by_role"].items() for row in rows]
    if report.get("prompt_budgets_by_role"):
        lines += ["", "## Prompt budgets", "", "Largest estimated tokens of a step by class of blocks, against the limit "
                  "(0 is none); a prompt is never cut.", "", "| Role | Class | Max tokens | Limit | Steps | Steps over |",
                  "| --- | --- | --- | --- | --- | --- |"]
        lines += [f"| {role} | {name} | {row['max_tokens']} | {row['limit']} | {row['steps']} | {row['over']} |"
                  for role, classes in report["prompt_budgets_by_role"].items() for name, row in classes.items()]
    if report.get("open_questions"):
        lines += ["", "## Open questions", "", "| Item | Question | Revision | Age s | Overdue |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {row['item']} | {row['id']}: {row['text']} | {row['revision']} | {row['age_s']} | "
                  f"{'yes' if row['overdue'] else 'no'} |" for row in report["open_questions"]]
    lines += ["", "## Events", ""]
    lines += [f"- {name}: {count}" for name, count in report["events"].items()] or ["- none"]
    lines += [f"- not read: {problem}" for problem in report["event_problems"]]
    lines += ["", "## Proposals", ""]
    lines += [f"- {text}" for text in report["proposals"]] or ["- none"]
    return "\n".join(lines) + "\n"


def write_report(directory: Path, project: Path, target: Path) -> dict:
    report = build(directory, project)
    target.mkdir(parents=True, exist_ok=True)
    (target / "observer.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target / "observer.md").write_text(markdown(report), encoding="utf-8")
    return {"json": str(target / "observer.json"), "markdown": str(target / "observer.md")}


def follow(directory: Path, *, stream, poll_s: float = 2.0, idle_exit_s: float = 0.0) -> int:
    """Print the notable lines of a running run (stops, red checks, repeats, item ends) until ``run.end``."""
    seen = 0
    quiet_since = time.monotonic()
    while True:
        lines = progress_mod.read_lines(directory)
        for line in lines[seen:]:
            event = line.get("event")
            notable = (event in ("item.end", "run.end", "run.resume") or line.get("reason_code")
                       or (event == "info" and "repeating" in line.get("message", ""))
                       or (event == "stage.end" and str(line.get("verdict", "")).startswith("red")))
            if notable:
                print("observer: " + progress_mod.text_line(line), file=stream, flush=True)
            if event == "run.end":
                return 0
        if len(lines) > seen:
            quiet_since = time.monotonic()
        seen = len(lines)
        if idle_exit_s and time.monotonic() - quiet_since > idle_exit_s:
            return 0
        time.sleep(poll_s)
