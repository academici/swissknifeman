"""Proposals to improve the run options, from the numbers of an observer report: plain rules, no model."""
from __future__ import annotations

from orch.conductor import prompts as prompts_mod


def proposals(report: dict) -> list:
    """Changes to the run options or the work that the numbers point at; plain rules, no model."""
    found = []
    if report["red_checks"]:
        names = ", ".join(sorted(report["red_checks"]))
        found.append(f"Checks {names} went red after the executor: add a run rule that names the concrete new or failing "
                     "diagnostics to run, or give the checks a faster local variant; the conductor keeps the named "
                     "acceptance checks and phase gates, so the executor need not rerun unchanged acceptance or full suites.")
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
    if beacons.get("REVIEW_DEBT"):
        found.append(f"{beacons['REVIEW_DEBT']} piece(s) had findings in their last review round, corrected without a "
                     "further review (review_debt in their state): the work likely left the executor unfinished; look at "
                     "what the review found there and sharpen the self-check or the item, not the number of reviews.")
    findings = report.get("check_findings") or {}
    for row in findings.get("duplicate_modules", []):
        found.append(f"item {row['item']} runs the tests of {row['module']} twice ({row['cmds'][0]}, {row['cmds'][1]}): "
                     "keep one, or run validate.sh with SKM_VALIDATE_SKIP_TESTS=1 after the full test.")
    for row in findings.get("phase_after_red", []):
        found.append(f"phase checks of {row['item']} ran after a red item check ({row['step']}): run them only when the "
                     "item checks are green (checks.fail_fast gates them), or leave them to the closing piece.")
    if findings.get("executor_runs_checks"):
        found.append("checks.executor_runs_checks is true: the executor and the conductor run the same checks ("
                     + ", ".join(findings["executor_runs_checks"]) + "); keep it false and let the executor run only "
                     "the tests of the code it changed.")
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
                             "orch conduct prompt explain, then shorten its source or raise the limit; the conductor cuts nothing.")
    overdue = [row for row in report.get("open_questions", []) if row["overdue"]]
    if overdue:
        found.append(f"{len(overdue)} question(s) wait for an answer past limits.question_warn_s: "
                     + ", ".join(f"{row['item']} {row['id']}" for row in overdue)
                     + "; orch conduct answer, then resume --retry.")
    tokens = report["tokens_by_role"]
    total = sum(value["input"] + value["output"] for value in tokens.values())
    for role, value in tokens.items():
        share = (value["input"] + value["output"]) / total if total else 0
        if role in ("context-scout", "triager") and share > 0.4:
            found.append(f"{role} used {int(share * 100)} % of the tokens: give it a cheaper model class.")
    return found
