"""analyst orch report — what the runs of orch cost and where they went wrong, from its events and artifacts.

``analyst orch report [--plan P] [--run R] [--json] [--planned FILE] [--baseline FILE]``

Reads through ``readers/orch.py`` only (event journal + published artifact formats). Sections: tokens (by role, by model,
by skill from the prompt manifests), review (rounds, findings by severity, reviews added by risk), deviations (by class
and outcome, recorded against resolved), providers (waits, fallbacks), long stages (the agent runs that took longest),
prompt budgets over their limit, plan against actual per piece (time and tokens; ``--planned`` is a JSON object
``{item: {duration_ms, tokens}}``) and the comparison with the deviation baseline of PLAN3 (``--baseline`` is a JSON file
with a ``plan3_deviations`` object, the one written by the first piece of PLAN4). No number is invented: a part with no
source is empty and listed in ``problems``.
"""
import json
from collections import Counter

from aicore.util.cli import parse_args
from aicore.util.io import safe_load_json
from aicore.util.term import die

from .common import project_path_from_opts
from .readers import orch as reader

LONG_STAGES = 5
_TOKEN_KEYS = ("input", "cached", "output")
_HELP = ("usage: analyst orch report [--plan P] [--run R] [--json] [--planned FILE] [--baseline FILE]\n"
         "  tokens, review, deviations, fallbacks, long stages, budgets, plan against actual, baseline comparison")


def _add(total, tokens):
    for key in _TOKEN_KEYS:
        total[key] = total.get(key, 0) + int((tokens or {}).get(key, 0))


def _item(row):
    return row["data"].get("item") or row["data"].get("work_id")


def build(data, planned=None, baseline=None):
    events = data["events"]
    ended = [row for row in events if row["type"] in ("orch.agent.finished", "orch.agent.failed")]
    started = {row["data"].get("agent_run_id"): row["data"] for row in events if row["type"] == "orch.agent.started"}

    total, by_role, by_model = {}, {}, {}
    per_item = {}
    for row in ended:
        info = row["data"]
        tokens = info.get("tokens")
        model = "/".join(part for part in (info.get("route", {}).get("provider"), info.get("route", {}).get("model")) if part)
        _add(total, tokens)
        _add(by_role.setdefault(info.get("role", "-"), {}), tokens)
        _add(by_model.setdefault(model or "-", {}), tokens)
        slot = per_item.setdefault(_item(row) or "-", {"agents": 0, "duration_ms": 0, "tokens": 0, "failed": 0})
        slot["agents"] += 1
        slot["duration_ms"] += int(info.get("duration_ms", 0))
        slot["tokens"] += sum(int((tokens or {}).get(key, 0)) for key in ("input", "output"))
        slot["failed"] += row["type"] == "orch.agent.failed"
    by_skill = Counter()
    over_budget = []
    for item, run in sorted(data["runs"].items()):
        for manifest in run["manifests"]:
            for block in manifest.get("blocks", []):
                if str(block.get("origin", "")).startswith("skill:"):
                    by_skill[block["origin"][len("skill:"):]] += int(block.get("tokens", 0))
            for name, row in sorted((manifest.get("budgets") or {}).items()):
                if row.get("limit") and row.get("tokens", 0) > row["limit"]:
                    over_budget.append({"item": item, "step": manifest.get("step"), "role": manifest.get("role"),
                                        "class": name, "tokens": row["tokens"], "limit": row["limit"]})

    severities, verdicts, rounds = Counter(), Counter(), 0
    reports = Counter()
    for item, row in sorted(data["artifacts"].items()):
        for review_round in (row["review_verdict"] or {}).get("rounds", []):
            rounds += 1
            verdicts[review_round.get("verdict", "-")] += 1
            severities.update(str(f.get("severity", "-")).lower() for f in review_round.get("findings", []))
        status = (row["stage_report"] or {}).get("status")
        if status:
            reports[status] += 1
            per_item.setdefault(item, {"agents": 0, "duration_ms": 0, "tokens": 0, "failed": 0})["status"] = status

    recorded = [row for row in events if row["type"] == "orch.deviation.recorded"]
    resolved = [row for row in events if row["type"] == "orch.deviation.resolved"]
    limits = {kind: [row for row in events if row["type"] == f"orch.provider.{kind}"]
              for kind in ("rate-limited", "quota-exhausted", "fallback")}
    waits = Counter(row["data"].get("provider", "-") for kind in ("rate-limited", "quota-exhausted")
                    for row in limits[kind])
    long_rows = sorted(ended, key=lambda row: (-int(row["data"].get("duration_ms", 0)), row["data"].get("agent_run_id", "")))
    plan_vs_actual = []
    for item, actual in sorted(per_item.items()):
        row = {"item": item, **actual}
        if planned and item in planned:
            row["planned"] = planned[item]
            row["delta_duration_ms"] = actual["duration_ms"] - int(planned[item].get("duration_ms", 0))
            row["delta_tokens"] = actual["tokens"] - int(planned[item].get("tokens", 0))
        plan_vs_actual.append(row)

    report = {
        "agents": {"started": len(started), "ended": len(ended), "failed": sum(r["type"] == "orch.agent.failed" for r in ended)},
        "tokens": {"total": total, "by_role": dict(sorted(by_role.items())), "by_model": dict(sorted(by_model.items())),
                   "by_skill_estimated": dict(sorted(by_skill.items()))},
        "review": {"rounds": rounds, "verdicts": dict(sorted(verdicts.items())),
                   "findings_by_severity": dict(sorted(severities.items())),
                   "added_by_risk": [{"item": _item(r), "score": r["data"].get("score"),
                                      "features": [f["name"] for f in r["data"].get("features", [])]}
                                     for r in events if r["type"] == "orch.review.added"]},
        "deviations": {"recorded": len(recorded), "resolved": len(resolved),
                       "by_class": dict(sorted(Counter(r["data"].get("class") for r in recorded).items())),
                       "by_outcome": dict(sorted(Counter(r["data"].get("outcome") for r in recorded).items()))},
        "providers": {"waits_by_provider": dict(sorted(waits.items())),
                      "rate_limited": len(limits["rate-limited"]), "quota_exhausted": len(limits["quota-exhausted"]),
                      "fallbacks": [{"role": r["data"].get("role"), "from": r["data"].get("from", {}).get("provider"),
                                     "to": r["data"].get("to", {}).get("provider"),
                                     "reasons": r["data"].get("reason_codes")} for r in limits["fallback"]]},
        "warnings": dict(sorted(Counter(r["data"].get("reason_code") for r in events if r["type"] == "orch.run.warning").items())),
        "blocked": [{"item": _item(r), "code": r["data"].get("code")} for r in events if r["type"] == "orch.work.blocked"],
        "long_stages": [{"item": _item(r), "step": r["data"].get("step"), "role": r["data"].get("role"),
                         "agent": r["data"].get("agent_run_id"), "duration_ms": int(r["data"].get("duration_ms", 0))}
                        for r in long_rows[:LONG_STAGES]],
        "budgets_over": over_budget,
        "plan_vs_actual": plan_vs_actual,
        "stage_reports": dict(sorted(reports.items())),
        "problems": list(data["problems"]),
    }
    if baseline is not None:
        report["baseline"] = _compare(data, baseline, recorded, reports)
    return report


def _compare(data, baseline, recorded, reports):
    """The current counters of the PLAN3 deviation baseline next to the recorded ones."""
    now = {"finish_events": sum(r["type"] == "orch.run.finished" for r in data["events"]),
           "deviation_events": len(recorded), "items_done_with_deviations": reports.get("done_with_deviations", 0),
           "items_total": sum(reports.values()), "deviations_without_impact_or_next": sum(
               1 for row in data["artifacts"].values()
               for issue in (row["stage_report"] or {}).get("open_issues", [])
               if issue.get("kind") == "deviation" and not (issue.get("impact") and issue.get("next")))}
    then = baseline.get("plan3_deviations") or {}
    return {"baseline": {key: then.get(key) for key in now}, "now": now,
            "delta": {key: now[key] - then[key] for key in now if isinstance(then.get(key), int)}}


def markdown(report):
    lines = ["analyst orch report", ""]
    tokens = report["tokens"]
    lines.append(f"agents: {report['agents']['ended']} ended, {report['agents']['failed']} failed")
    lines.append("tokens: " + ", ".join(f"{k}={v}" for k, v in sorted(tokens["total"].items())))
    for title, block in (("by role", tokens["by_role"]), ("by model", tokens["by_model"])):
        for name, row in block.items():
            lines.append(f"  {title} {name}: " + ", ".join(f"{k}={v}" for k, v in sorted(row.items())))
    for name, value in tokens["by_skill_estimated"].items():
        lines.append(f"  skill {name}: ~{value} prompt tokens")
    review = report["review"]
    lines.append(f"review: {review['rounds']} round(s), findings {review['findings_by_severity'] or '-'}")
    deviations = report["deviations"]
    lines.append(f"deviations: {deviations['recorded']} recorded, {deviations['resolved']} resolved, "
                 f"by class {deviations['by_class'] or '-'}, by outcome {deviations['by_outcome'] or '-'}")
    providers = report["providers"]
    lines.append(f"providers: {providers['rate_limited']} rate limit(s), {providers['quota_exhausted']} quota, "
                 f"{len(providers['fallbacks'])} fallback(s)")
    for row in report["long_stages"]:
        lines.append(f"  long: {row['item']} {row['step']} {row['role']} {row['duration_ms']} ms")
    for row in report["budgets_over"]:
        lines.append(f"  budget over: {row['item']} {row['step']} {row['class']} {row['tokens']}/{row['limit']}")
    for row in report["plan_vs_actual"]:
        lines.append(f"  item {row['item']}: {row['duration_ms']} ms, {row['tokens']} tokens, {row['agents']} agent(s)"
                     + (f", vs plan {row['delta_duration_ms']:+d} ms {row['delta_tokens']:+d} tokens" if "planned" in row else ""))
    if "baseline" in report:
        lines.append("baseline delta: " + ", ".join(f"{k}={v:+d}" for k, v in report["baseline"]["delta"].items()))
    lines.extend(f"problem: {text}" for text in report["problems"])
    return "\n".join(lines)


def cmd_orch(env, argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_HELP)
        return
    if argv[0] != "report":
        die(f"unknown orch command: {argv[0]}", 2)
    opts, _ = parse_args(argv[1:], {"--plan": "str", "--run": "str", "--json": "bool", "--planned": "str",
                                    "--baseline": "str"})
    if opts["help"]:
        print(_HELP)
        return
    planned = baseline = None
    for key in ("planned", "baseline"):
        if opts[key]:
            doc = safe_load_json(opts[key], None)
            if not isinstance(doc, dict):
                die(f"--{key} is not a JSON object file: {opts[key]}", 2)
            if key == "planned":
                planned = doc
            else:
                baseline = doc
    data = reader.read(project_path_from_opts(env, opts), run=opts["run"] or None, plan=opts["plan"] or None)
    report = build(data, planned, baseline)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) if opts["json"] else markdown(report))
