"""Internal documentation."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from core import find_monorepo_root

from ..common import die, parse_args
from . import plan_reader
from . import worker
from . import gate
from . import journal

RUN_USAGE = (
    "harness run <PLAN-ID> <Pn> [--dry-run] [--limit N] [--timeout S]\n"
    "                            [--plans-root PATH] [--json]\n"
    "  <PLAN-ID>          plan (directory `<plans-root>/<PLAN-ID>`)\n"
    "  <Pn>               phase (for example P4)\n"
    "  --dry-run          queue only/routes/argv/reasons for failures, WITHOUT spawn and\n"
    "                     WITHOUT a single entry (read-only, is being checked `git status --porcelain`)\n"
    "  --limit N          maximum item'ov waves (default - entire queue)\n"
    f"  --timeout S        timeout for ONE worker run, seconds (default {worker.DEFAULT_TIMEOUT})\n"
    "  --plans-root PATH  directory where to look `<PLAN-ID>/plan.json` (default — `<monorepo>/plans`)\n"
    "  --json             same summary machine (valid JSON, ensure_ascii=False)\n"
    "Sequential wave (D8) and stops at the FIRST RED; ATTENTION not\n"
    "stops the wave, but is included in the report by name. Retraya there is not a single shooting gallery (D9).\n"
    "exit-code: 0 — wave completed (RED in the middle of the wave - verdict, not an error\n"
    "usage); non-zero - ONLY flag parsing failure / structural inaccessibility\n"
    "(monorepo-root / queue does not resolve)."
)


def _resolve_plan_dir(env, opts, plan_id):
    monorepo_root = find_monorepo_root(env.root)
    if monorepo_root is None:
        die("monorepo root not found - package `task` not available (standalone-layout)")
        return None, None
    plans_root = Path(opts["plans_root"]) if opts["plans_root"] else monorepo_root / "plans"
    return monorepo_root, plans_root / plan_id


def _dry_run_argv(plan_id, item, *, monorepo_root, claude_bin):
    """Internal documentation."""
    if not item["drivable"]:
        return None, None
    if claude_bin is None:
        return None, f"client claude not found ({worker.CLAUDE_BIN_ENV} / PATH)"
    route = item["route"]
    try:
        argv = worker.build_argv(plan_id, item["item_id"], model_class=route["model_class"],
                                 effort=route["effort"], monorepo_root=monorepo_root,
                                 claude_bin=claude_bin)
    except worker.WorkerUnavailable as exc:
        return None, str(exc)
    return argv, None


def _print_dry_run(queue, plan_id, phase_id, *, monorepo_root, as_json):
    claude_bin = worker.resolve_claude_bin()
    items = []
    for item in queue["items"]:
        argv, argv_error = _dry_run_argv(plan_id, item, monorepo_root=monorepo_root,
                                         claude_bin=claude_bin)
        items.append({**item, "argv": argv, "argv_error": argv_error})
    payload = {
        "mode": "dry-run", "plan_id": plan_id, "phase_id": phase_id,
        "degraded": queue["degraded"], "degraded_reasons": queue["degraded_reasons"],
        "next_form": queue["next_form"], "client_bin": claude_bin,
        "items": items, "excluded_terminal": queue["excluded_terminal"],
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"dry-run: {plan_id} {phase_id} (client: {claude_bin or 'NOT FOUND'})")
    if queue["degraded"]:
        print(f"  QUEUE NOT AVAILABLE: {'; '.join(queue['degraded_reasons'])}")
        return
    print(f"  next_form: {queue['next_form']['kind']!r} ({queue['next_form']['declaring_line']!r})")
    print(f"  terminal (dequeued): {len(queue['excluded_terminal'])}")
    for item in items:
        marker = "DRIVING" if item["drivable"] else "FAILURE"
        print(f"  [{marker}] {item['item_id']} — status={item['status']!r} exec={item['exec']!r}")
        if item["route"]:
            print(f"      route: {item['route']['model_class']}/{item['route']['effort']}")
        if not item["drivable"]:
            print(f"      reason: {item['refusal']} — {item['refusal_detail']}")
        elif item["argv"]:
            print(f"      argv: {item['argv']}")
        elif item["argv_error"]:
            print(f"      argv not available: {item['argv_error']}")
    for excl in queue["excluded_terminal"]:
        print(f"  [TERMINAL] {excl['item_id']} — status={excl['status']!r}")


def _run_wave(env, opts, plan_id, phase_id, monorepo_root, plan_dir, *, limit, timeout):
    queue = plan_reader.queue(plan_dir, phase_id, monorepo_root=monorepo_root)
    if queue["degraded"]:
        die(f"queue unavailable: {'; '.join(queue['degraded_reasons'])}")
        return None

    items = queue["items"]
    if limit is not None:
        items = items[:limit]

    run_id = f"wave-{plan_id}-{phase_id}-{uuid.uuid4().hex[:12]}"
    records = []
    for item in items:
        item_id = item["item_id"]

        if not item["drivable"]:
            verdict = gate.pre_launch_verdict(item)
            jrec = journal.maybe_write(
                plan_dir, item_id, run_id=run_id, pre_launch=True,
                refusal_detail=item.get("refusal_detail"), monorepo_root=monorepo_root)
            records.append({"item_id": item_id, "verdict": verdict["verdict"],
                            "outcome": None, "wrote_driver_line": jrec is not None,
                            "verdict_detail": verdict})
        else:
            before = gate.snapshot_before(plan_dir)
            outcome = worker.run(plan_id, item_id, model_class=item["route"]["model_class"],
                                 effort=item["route"]["effort"], monorepo_root=monorepo_root,
                                 timeout=timeout)
            verdict = gate.verdict(plan_id, item_id, phase_id, plan_dir, before, outcome,
                                   monorepo_root=monorepo_root)
            item_status = (verdict["raw"]["item_after"] or {}).get("status")
            jrec = journal.maybe_write(
                plan_dir, item_id, run_id=run_id, pre_launch=False, outcome=outcome,
                item_status=item_status, monorepo_root=monorepo_root)
            records.append({"item_id": item_id, "verdict": verdict["verdict"],
                            "outcome": outcome, "wrote_driver_line": jrec is not None,
                            "verdict_detail": verdict})

        if records[-1]["verdict"] == gate.RED:
            break

    return run_id, records


def _print_wave(run_id, records, plan_id, phase_id, *, as_json):
    summary = journal.summarize_wave(run_id, records)
    if as_json:
        print(json.dumps({**summary, "plan_id": plan_id, "phase_id": phase_id,
                          "records": records}, ensure_ascii=False, indent=2, default=str))
        return

    print(f"wave {run_id} — {plan_id} {phase_id}")
    print(f"  entered {summary['queued']} — GREEN {summary['green']} / "
         f"ATTENTION {summary['attention']} / RED {summary['red']}")
    print(f"  driver interventions: {summary['interventions']}")
    if summary["cost_usd_total"] is not None:
        print(f"  cost_usd: {summary['cost_usd_total']:.4f}")
    if summary["duration_ms_total"] is not None:
        print(f"  duration_ms: {summary['duration_ms_total']:.0f}")
    if summary["client_versions"]:
        print(f"  client_versions: {', '.join(summary['client_versions'])}")
    for v in summary["verdicts"]:
        print(f"  [{v['verdict']}] {v['item_id']}")


def cmd_run(env, argv):
    """Internal documentation."""
    opts, positionals = parse_args(argv, {
        "--dry-run": "bool", "--limit": "str", "--timeout": "str",
        "--plans-root": "str", "--json": "bool",
    }, max_pos=2)
    if opts["help"] or not positionals:
        print(RUN_USAGE)
        return
    if len(positionals) != 2:
        die(f"exactly 2 positional arguments are expected: <PLAN-ID> <Pn>, received: {positionals!r}")
        return
    plan_id, phase_id = positionals

    limit = None
    if opts["limit"]:
        try:
            limit = int(opts["limit"])
        except ValueError:
            die(f"--limit expects an integer, received: {opts['limit']!r}")
            return

    timeout = worker.DEFAULT_TIMEOUT
    if opts["timeout"]:
        try:
            timeout = float(opts["timeout"])
        except ValueError:
            die(f"--timeout expects number of seconds, received: {opts['timeout']!r}")
            return

    monorepo_root, plan_dir = _resolve_plan_dir(env, opts, plan_id)
    if monorepo_root is None:
        return

    if opts["dry_run"]:
        queue = plan_reader.queue(plan_dir, phase_id, monorepo_root=monorepo_root)
        _print_dry_run(queue, plan_id, phase_id, monorepo_root=monorepo_root,
                       as_json=opts["json"])
        return

    result = _run_wave(env, opts, plan_id, phase_id, monorepo_root, plan_dir,
                       limit=limit, timeout=timeout)
    if result is None:
        return
    run_id, records = result
    _print_wave(run_id, records, plan_id, phase_id, as_json=opts["json"])
