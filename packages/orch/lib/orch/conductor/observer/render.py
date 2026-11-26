"""The markdown form of an observer report (``observer.md``)."""
from __future__ import annotations


def _counted(counts: dict) -> str:
    return ", ".join(f"{name}×{number}" for name, number in counts.items()) or "none"


def markdown(report: dict) -> str:
    lines = [f"# Observer report {report['run']}", "",
             f"- Status: {report['status']}" + (f" ({report['stop']['code']}: {report['stop']['message']})"
                                                 if report.get("stop") else "")
             + (f"; last stop {report['last_stop']['code']} before resume {report['last_stop']['resume']}"
                if report.get("last_stop") else ""),
             f"- Time: {report['started']} → {report['ended']}; resumes {report['resumes']}",
             f"- Repeated role runs: {len(report['repeats'])}",
             *([f"- Discarded progress lines: {report['discarded_lines']}"] if report.get("discarded_lines") else []),
             f"- Red checks: {', '.join(f'{k}×{v}' for k, v in report['red_checks'].items()) or 'none'}",
             f"- Review findings: {', '.join(f'{k} {v}' for k, v in report['findings_by_severity'].items()) or ('unavailable' if report.get('incomplete_group_reviews') else 'none')}"
             f"; triage confirmed {report['triage']['confirmed']}, rejected {report['triage']['rejected']}"
             + (f"; incomplete group reviews {', '.join(report['incomplete_group_reviews'])}"
                if report.get("incomplete_group_reviews") else ""),
             f"- Idle between stages: {report['idle']['total_s']} s (longest {report['idle']['max_s']} s"
             + (f", {report['idle']['max_between']}" if report['idle']['max_between'] else "") + ")",
             f"- Scout cache: {report['scout_cache']['hits']}/{report['scout_cache']['runs']} hits",
             *([f"- Executor sessions: resumed {_counted(report['sessions']['resumed'])}; fresh {_counted(report['sessions']['fresh'])}"]
               if report.get("sessions") and (report["sessions"]["resumed"] or report["sessions"]["fresh"]) else []),
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
    found = (report.get("metrics") or {}).get("items") or []
    if found:
        lines += ["", "## Item metrics", "", "Always written, debug or not; active seconds by role group, rounds "
                  "executor/review/checks, mends healed/repaired/unrepairable, tokens fresh in/cached/out.", "",
                  "| Item | Wall s | Active s | Checks share | Rounds | Repeats after resume | Mends | Beacons | Tokens | "
                  "Deviations | Findings confirmed/rejected | Health |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for row in found:
            rounds, heal, tokens = row["rounds"], row["heal"], row["tokens"]
            health = " → ".join([row["health_transitions"][0]["from"] or "-"] + [step["to"] for step in row["health_transitions"]]) \
                if row["health_transitions"] else "-"
            lines.append(f"| {row['item']} | {row['wall_s']} | {', '.join(f'{k} {v}' for k, v in row['active_s'].items()) or '-'} | {int(row['checks_share'] * 100)} % | "
                         f"{rounds['executor']}/{rounds['review']}/{rounds['checks']} | {row['resume_repeats']} | "
                         f"{heal['healed']}/{heal['repaired']}/{heal['unrepairable']} | {_counted(row['beacons'])} | "
                         f"{tokens['input']}/{tokens['cached']}/{tokens['output']} | {row['deviations']} | "
                         f"{row['findings']['confirmed']}/{row['findings']['rejected']} | {health} |")
    retried = [item for item in report["items"] if item.get("attempts")]
    if retried:
        lines += ["", "## Retried pieces", "", "| Item | Earlier attempts | Reviews in all attempts |", "| --- | --- | --- |"]
        for item in retried:
            lines.append(f"| {item['item']} | " + "; ".join(
                f"{attempt['n']}: " + ", ".join(f"{key} {verdict or '-'}" for key, verdict in attempt["steps"].items())
                for attempt in item["attempts"]) + f" | {item['reviews']} |")
    if report.get("usage_unavailable"):
        lines += ["", "Usage unavailable: token tables contain known portions only, not complete spend.",
                  *["- " + reason for reason in report["usage_unavailable"]]]
    lines += ["", "## Roles", "", "| Role | Seconds | Tokens in/out |", "| --- | --- | --- |"]
    for role in sorted(set(report["seconds_by_role"]) | set(report["tokens_by_role"])):
        value = report["tokens_by_role"].get(role, {"input": 0, "output": 0})
        amount = ("unavailable" if any(reason.startswith(role + ": legacy") for reason in report.get("usage_unavailable", []))
                  else f"{value['input']}/{value['output']}")
        lines.append(f"| {role} | {report['seconds_by_role'].get(role, 0)} | {amount} |")
    if report.get("checks_by_command"):
        lines += ["", "## Checks by command", "", "Seconds are elapsed time of executed runs, not CPU time; skipped and reused "
                  "rows ran no process.", "", "| Command | Ids | Context | Runs | Executed | Seconds | Red | Skipped | Reused | Retried |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        lines += [f"| `{row['cmd']}` | {', '.join(row['ids'])} | {', '.join(row['contexts'])} | {row['runs']} | "
                  f"{row['executed']} | {row['seconds']} | {row['red']} | {row['skipped']} | {row['reused']} | "
                  f"{row['retried']} |" for row in report["checks_by_command"]]
    refusals = report.get("refusals_by_source") or {}
    if refusals.get("by_kind"):
        lines += ["", "## Refusals by source", "", "Total: " + _counted(refusals["by_kind"]), "",
                  "| Role | Refusals |", "| --- | --- |"]
        lines += [f"| {role} | {_counted(counts)} |" for role, counts in refusals["by_role"].items()]
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
