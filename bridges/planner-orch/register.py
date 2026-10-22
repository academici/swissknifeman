"""Back-registration of an orch worker's stage-report into the plan (``register``).

Replaces the manual registrar map: every report field becomes a ``plan.py`` call. The bridge writes the plan
**only** through ``PLANNER_PLAN_PY`` as a subprocess and never touches plan files. ``plan_calls`` is a pure
function (report and arguments to argv lists); ``main`` runs the calls, all ``log`` first and then one
``finish`` or ``unit … return``, and prints a registration-receipt.

The report is checked by ``check_report`` (its codes: ``REGISTER_UNCLASSIFIED``, ``REGISTER_REPORT_INVALID``) and then,
for parity, against the orch contract ``work-source/v1`` ``register-report`` through ``orch.py validate``.

Two guards run before the first call that changes the plan. ``--owner-session SESSION`` (fencing) refuses with
``REGISTER_STALE_OWNER`` when the item's executor session is another one, for example after ``start --take-over``.
``--gate evidence`` lets only check-evidence files decide an item's acceptance checks: ``done`` and
``done_with_deviations`` need a file for every acceptance check (``REGISTER_EVIDENCE_MISSING``) whose exit is 0
(``REGISTER_EVIDENCE_RED``), and ``checks_run`` claims without a file never become ``--check``. Without the flags the
registration behaves as before.

Run as ``plan.py bridge planner-orch register <plan> <item>[/<U#>] --report REPORT.json --status STATUS --actor P/M[/E]
[--executed-by P/M[/E]] [--attempt-id ID] [--evidence V#=PATH …] [--owner-session SESSION] [--gate evidence]
[--plans-root DIR] [--dry-run]``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import partners

ISSUE_KINDS = ("pending", "deviation", "blocker", "difficulty", "assumption", "note", "escalation")
LOG_KINDS = ("deviation", "blocker", "difficulty", "assumption", "note")
STATUSES = ("done", "done_with_deviations", "blocked")
GATES = ("evidence",)
REPORT_FIELDS = ("summary", "changed_paths", "checks_run", "evidence", "open_issues")
DEVIATION_CLASSES = ("write_set", "spec_mismatch", "test_env", "docs", "dependency", "environment", "other")
DEVIATION_OUTCOMES = ("accepted", "follow_up", "owner_decision")
ISSUE_SEVERITIES = ("low", "medium", "high", "critical")
_DATA_FIELDS = ("class", "severity", "outcome", "auto_fixable", "evidence")  # kept in the journal event's data
_ISSUE_FIELDS = ("text", "kind", "impact", "next") + _DATA_FIELDS
_CHECK_ID = re.compile(r"^V[0-9]+$", re.ASCII)
_REF = re.compile(r"^(P[0-9]+\.[0-9]+)(?:/(U[0-9]+))?$", re.ASCII)


class Refusal(Exception):
    """A bridge refusal: ``CODE: message`` on stderr, exit 1, nothing written. ``gate`` is the gate state, if any."""

    def __init__(self, code: str, message: str, gate: dict | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.gate = gate


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def plan_argv() -> list:
    """``plan.py`` as set by the dispatcher (``PLANNER_PLAN_PY``), else found by ``partners`` (env or PATH)."""
    return partners.require_plan_argv()


def load_json(path: str, code: str, what: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Refusal(code, f"{what} {path} is not readable JSON ({error})") from None


# ---------------------------------------------------------------- the report


def check_report(report) -> dict:
    """The stage-report with defaults; ``REGISTER_REPORT_INVALID`` or ``REGISTER_UNCLASSIFIED`` otherwise.

    The report is closed: a field the map does not know would be lost, so it is refused.
    """
    def invalid(message: str) -> Refusal:
        return Refusal("REGISTER_REPORT_INVALID", message)

    if not isinstance(report, dict):
        raise invalid("the stage-report must be a JSON object")
    unknown = sorted(set(report) - set(REPORT_FIELDS))
    if unknown:
        raise invalid(f"unknown field(s) {', '.join(unknown)}; a stage-report carries {', '.join(REPORT_FIELDS)}")
    if not _text(report.get("summary")):
        raise invalid("summary is required")
    out = {"summary": report["summary"].strip()}
    for field in ("changed_paths", "evidence"):
        value = report.get(field, [])
        if not isinstance(value, list) or not all(_text(v) for v in value):
            raise invalid(f"{field} must be a list of non-empty strings")
        out[field] = list(value)
    checks, seen = report.get("checks_run", []), set()
    if not isinstance(checks, list):
        raise invalid("checks_run must be a list")
    for index, check in enumerate(checks):
        where = f"checks_run[{index}]"
        if not isinstance(check, dict) or not isinstance(check.get("id"), str) or not _CHECK_ID.fullmatch(check["id"]):
            raise invalid(f"{where} needs an id V<n>")
        if check["id"] in seen:
            raise invalid(f"{where} repeats {check['id']}")
        seen.add(check["id"])
        if set(check) == {"id", "cmd", "exit"}:
            if not _text(check["cmd"]) or isinstance(check["exit"], bool) or not isinstance(check["exit"], int):
                raise invalid(f"{where} needs a non-empty cmd and an integer exit")
        elif set(check) == {"id", "procedure", "verdict"}:
            if not _text(check["procedure"]) or check["verdict"] not in ("pass", "fail"):
                raise invalid(f"{where} needs a non-empty procedure and a pass|fail verdict")
        else:
            raise invalid(f"{where} is {{id, cmd, exit}} or {{id, procedure, verdict}}")
    out["checks_run"] = list(checks)
    issues = report.get("open_issues", [])
    if not isinstance(issues, list):
        raise invalid("open_issues must be a list")
    for index, issue in enumerate(issues):
        where = f"open_issues[{index}]"
        if not isinstance(issue, dict) or not _text(issue.get("text")):
            raise Refusal("REGISTER_UNCLASSIFIED", f"{where} must be an object with text and kind; "
                                                   f"classify it as one of {', '.join(ISSUE_KINDS)}")
        if issue.get("kind") not in ISSUE_KINDS:
            raise Refusal("REGISTER_UNCLASSIFIED", f"{where} kind {issue.get('kind')!r} is not one of "
                                                   f"{', '.join(ISSUE_KINDS)}")
        extra = sorted(set(issue) - set(_ISSUE_FIELDS))
        if extra or any(key in issue and not _text(issue[key]) for key in ("impact", "next")):
            raise invalid(f"{where} carries text, kind and optional non-empty impact, next, "
                          f"{', '.join(_DATA_FIELDS)} only")
        for key, allowed in (("class", DEVIATION_CLASSES), ("severity", ISSUE_SEVERITIES),
                             ("outcome", DEVIATION_OUTCOMES)):
            if key in issue and issue[key] not in allowed:
                raise invalid(f"{where} {key} {issue[key]!r} is not one of {', '.join(allowed)}")
        if "auto_fixable" in issue and not isinstance(issue["auto_fixable"], bool):
            raise invalid(f"{where} auto_fixable must be true or false")
        evidence = issue.get("evidence", [])
        if not isinstance(evidence, list) or not evidence and "evidence" in issue \
                or not all(_text(row) for row in evidence):
            raise invalid(f"{where} evidence must be a non-empty list of non-empty strings")
    out["open_issues"] = list(issues)
    return out


def check_schema(report) -> None:
    """Parity of ``check_report`` with the orch contract ``work-source/v1`` ``register-report``
    (``orch.py validate register-report``): a report ``check_report`` accepted and the schema refuses is
    ``REGISTER_REPORT_INVALID`` ``schema parity: <pointer>: <message>``, so the two checkers cannot drift apart
    unnoticed. An orch that cannot be found stops the bridge as any missing partner does."""
    with tempfile.TemporaryDirectory(prefix="planner-orch-report-") as tmp:
        path = Path(tmp) / "register-report.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        code, out = partners.orch_validate("register-report", path)
    if code == 0:
        return
    try:
        found = json.loads(out)
        lines = [f"{row['path'] or '/'}: {row['message']}" for row in found]
    except (ValueError, TypeError, KeyError):
        lines = [f"orch validate exited {code} without a verdict"]
    raise Refusal("REGISTER_REPORT_INVALID", "schema parity: " + "; ".join(lines[:3] or [f"orch validate exited {code}"]))


# ---------------------------------------------------------------- the calls


def _verdict_exit(check: dict) -> int:
    return check["exit"] if "exit" in check else (0 if check["verdict"] == "pass" else 1)


def _log(args, item: str, issue: dict, kind: str | None = None, prefix: str = "") -> list[str]:
    argv = ["log", args.plan, item, "--type", kind or issue["kind"], "--summary", prefix + issue["text"]]
    for key in ("impact", "next"):
        if issue.get(key):
            argv.append(f"--{key}={issue[key]}")  # "=" form: a value that starts with "-" is not an option
    data = {key: issue[key] for key in _DATA_FIELDS if key in issue}
    if data:  # class, severity, outcome, auto_fixable, evidence: the event keeps them in its data object
        argv += ["--data", json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))]
    return argv + _tail(args, executed=False)


def _tail(args, executed: bool = True) -> list[str]:
    """``--actor`` on every call; executor identity and attempt on the closing call; ``--plans-root``."""
    argv = ["--actor", args.actor]
    if executed and args.executed_by:
        argv += ["--executed-by", args.executed_by]
    if executed and args.attempt_id:
        argv += ["--attempt-id", args.attempt_id]
    if args.plans_root:
        argv += ["--plans-root", str(args.plans_root)]
    return argv


def plan_calls(report: dict, args) -> list[list[str]]:
    """The ``plan.py`` argv lists (without the interpreter) that register ``report``: all ``log`` calls, then one
    ``finish`` (item) or ``unit … return`` (unit). Pure: reads no file and writes nothing.

    ``args`` carries ``plan``, ``ref`` (``Pn.m`` or ``Pn.m/U#``), ``status``, ``actor``, ``executed_by``,
    ``attempt_id``, ``evidence`` (``{V#: path}``) and ``plans_root``.
    """
    report = check_report(report)
    match = _REF.fullmatch(args.ref or "")
    if not match:
        raise Refusal("REGISTER_REPORT_INVALID", f"ref {args.ref!r} must be <item> or <item>/<U#>")
    item, unit = match.groups()
    issues = report["open_issues"]
    if issues and not args.attempt_id:
        raise Refusal("REGISTER_ATTEMPT_REQUIRED", "a report with open_issues needs --attempt-id so a repeated "
                                                   "delivery does not log its issues twice")
    kinds = {issue["kind"] for issue in issues}
    evidence = dict(args.evidence or {})
    extra_evidence = [path for path in report["evidence"] if path not in evidence.values()]
    notes = [report["summary"]]
    if report["changed_paths"] and not unit:
        notes.append("Changed: " + ", ".join(report["changed_paths"]))
    if unit:
        return _unit_calls(args, item, unit, report, notes, evidence, extra_evidence)

    if args.status not in STATUSES:
        raise Refusal("REGISTER_STATUS_MISMATCH", f"an item registration needs --status {'|'.join(STATUSES)}")
    if ("deviation" in kinds) != (args.status == "done_with_deviations"):
        raise Refusal("REGISTER_STATUS_MISMATCH", "a deviation issue goes with --status done_with_deviations, "
                                                  "and done_with_deviations needs a deviation issue")
    if ("escalation" in kinds) != (args.status == "blocked"):
        raise Refusal("REGISTER_STATUS_MISMATCH", "an escalation issue goes with --status blocked, "
                                                  "and blocked needs an escalation issue")
    if extra_evidence:
        notes.append("Evidence: " + ", ".join(extra_evidence))
    calls = [_log(args, item, issue) for issue in issues if issue["kind"] in LOG_KINDS]
    finish = ["finish", args.plan, item, "--status", args.status, "--notes", "\n".join(notes)]
    for check in report["checks_run"]:
        # The evidence file carries the exit (D19); never both. Under the gate a claim without a file is not a result.
        if check["id"] not in evidence and not getattr(args, "gate", None):
            finish += ["--check", f"{check['id']}={_verdict_exit(check)}"]
    for check_id, path in evidence.items():
        finish += ["--evidence", f"{check_id}={path}"]
    for kind, flag in (("deviation", "--deviation"), ("pending", "--pending")):
        for issue in issues:
            if issue["kind"] == kind:
                finish += [flag, issue["text"]]
    for issue in issues:  # a deviation that is not simply accepted leaves its work in result.pending (D16)
        if issue["kind"] == "deviation" and issue.get("outcome") in ("follow_up", "owner_decision"):
            finish += ["--pending", f"{issue['outcome']}({issue.get('class', 'other')}): {issue['text']}"]
    escalations = [issue["text"] for issue in issues if issue["kind"] == "escalation"]
    if escalations:
        finish += ["--escalation", "; ".join(escalations)]
    if getattr(args, "owner_session", None):  # fencing again under the plan lock, at the write that closes the item
        finish += ["--owner-session", args.owner_session]
    return calls + [finish + _tail(args)]


def _unit_calls(args, item, unit, report, notes, evidence, extra_evidence) -> list[list[str]]:
    """``unit … return``: checks and evidence belong to the integrator's ``accept``, so they are named in the notes."""
    if args.status not in (None, "done"):
        raise Refusal("REGISTER_STATUS_MISMATCH", "a unit return takes no --status other than done")
    if any(issue["kind"] == "escalation" for issue in report["open_issues"]):
        raise Refusal("REGISTER_STATUS_MISMATCH", "an escalation blocks the item; register it with the item's "
                                                  "--status blocked, not with a unit return")
    if report["checks_run"]:
        notes.append("Checks: " + ", ".join(f"{c['id']}={_verdict_exit(c)}" for c in report["checks_run"]))
    named = [f"{check_id}={path}" for check_id, path in evidence.items()] + extra_evidence
    if named:
        notes.append("Evidence: " + ", ".join(named))
    calls = [_log(args, item, issue, "note", "pending: ") if issue["kind"] == "pending" else _log(args, item, issue)
             for issue in report["open_issues"]]
    ret = ["unit", args.plan, item, unit, "return", "--notes", "\n".join(notes)]
    for path in report["changed_paths"]:
        ret += ["--changed", path]
    return calls + [ret + _tail(args)]


# ---------------------------------------------------------------- guards: owner and evidence


def read_item(plan: str, plans_root, item: str) -> dict:
    """The item document from ``plan.py --output json get``; ``REGISTER_ITEM_UNREADABLE`` when it cannot be read."""
    argv = ["--output", "json", "get", plan, item] + (["--plans-root", str(plans_root)] if plans_root else [])
    done = run_plan(argv)
    try:
        doc = json.loads(done.stdout)["data"]["doc"] if done.returncode == 0 else None
    except (ValueError, KeyError, TypeError):
        doc = None
    if not isinstance(doc, dict):
        raise Refusal("REGISTER_ITEM_UNREADABLE", f"{item} cannot be read: {(done.stderr or done.stdout).strip()}")
    return doc


def check_owner(doc: dict, item: str, session: str, attempt_id: str | None = None) -> None:
    """Fencing: the run that registers must still own the item (``result.executor.session``).

    A registration replaces the executor with the worker and keeps no session, so an item already closed by this
    very attempt (``result.attempt_id``) is still this run's: the repeat after a lost answer reaches ``finish``,
    which writes nothing for it (or refuses ``ATTEMPT_CONFLICT`` when the outcome differs).
    """
    result = doc.get("result") or {}
    owner = (result.get("executor") or {}).get("session")
    if owner != session and not (attempt_id and result.get("attempt_id") == attempt_id):
        held = f"session {owner}" if owner else "no session"
        raise Refusal("REGISTER_STALE_OWNER", f"{item} is held by {held}, not by {session}; the attempt lost "
                                              "ownership and registers nothing", {"verdict": "stale", "checks": {}})


def _evidence_prover(plan: str, plans_root, item: str):
    """``(check_id, path) -> (exit | None, problem | None)`` by the planner's own check-evidence contract, the one
    ``finish`` applies (``load_evidence``): a file ``finish`` would refuse never passes the gate."""
    store, lifecycle, model = partners.planner_engine("plan.store", "plan.lifecycle", "plan.model")
    loaded = store.load_plan(store.resolve_plan_dir(plan, plans_root))

    def prove(check_id: str, path: str):
        try:
            return lifecycle.load_evidence(loaded, item, {check_id: path}, [check_id])[check_id], None
        except model.PlanError as error:
            return None, f"{error.code}: {error.message}"
    return prove


def evidence_gate(doc: dict, args, prove) -> dict:
    """``{verdict, checks}`` of the evidence gate; ``REGISTER_EVIDENCE_MISSING`` or ``REGISTER_EVIDENCE_RED``.

    Only ``done`` and ``done_with_deviations`` are gated; ``blocked`` passes without evidence (verdict ``none``).
    A file that is not valid check-evidence of the item and check counts as missing.
    """
    if args.status not in ("done", "done_with_deviations"):
        return {"verdict": "none", "checks": {}}
    acceptance = [c["id"] for c in doc.get("validation", []) if isinstance(c, dict) and c.get("kind") == "acceptance"]
    checks: dict = {}
    unusable = []
    for check_id in acceptance:
        path = args.evidence.get(check_id)
        checks[check_id], problem = prove(check_id, path) if path else (None, None)
        if problem:
            unusable.append(f"{check_id}={path} ({problem})")
    missing = [check_id for check_id, code in checks.items() if code is None]
    if missing:
        detail = f"; unusable evidence: {', '.join(unusable)}" if unusable else ""
        raise Refusal("REGISTER_EVIDENCE_MISSING", f"acceptance check(s) without check-evidence: {', '.join(missing)}"
                                                   f"{detail}", {"verdict": "missing", "checks": checks})
    red = [f"{check_id}={code}" for check_id, code in checks.items() if code != 0]
    if red:
        raise Refusal("REGISTER_EVIDENCE_RED", f"acceptance check(s) failed by their evidence: {', '.join(red)}",
                      {"verdict": "red", "checks": checks})
    return {"verdict": "pass", "checks": checks}


def guard(args, item: str, unit: str) -> dict | None:
    """Run the requested guards before anything is written; the gate state, or None without ``--gate``."""
    if not args.owner_session and not args.gate:
        return None
    doc = read_item(args.plan, args.plans_root, item)
    if args.owner_session:
        check_owner(doc, item, args.owner_session, args.attempt_id)
    if not args.gate:
        return None
    if unit:  # a unit return carries no acceptance result; the integrator's accept does
        return {"verdict": "none", "checks": {}}
    return evidence_gate(doc, args, _evidence_prover(args.plan, args.plans_root, item))


# ---------------------------------------------------------------- running them


def run_plan(argv: list[str]) -> subprocess.CompletedProcess:
    return partners.run_bounded([*plan_argv(), *argv], timeout=300, capture_output=True, text=True,
                                encoding="utf-8", check=False)


def _data_key(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if data else ""


def journal(plan: str, plans_root, item: str | None, types) -> tuple[set[tuple[str, str, str]] | None, dict]:
    """``{(type, summary, data)}`` already in the journal (of ``item`` when given; ``data`` is its canonical JSON or
    empty), and the receipt entry of the read."""
    argv = ["--output", "json", "events", plan, "--type", ",".join(sorted(types))]
    if item:
        argv += ["--item", item]
    if plans_root:
        argv += ["--plans-root", str(plans_root)]
    done = run_plan(argv)
    entry = {"argv": argv, "exit": done.returncode, "result": "read"}
    if done.returncode:
        entry.update(result="refused", error=(done.stderr or done.stdout).strip())
        return None, entry
    return {(e.get("type"), e.get("summary"), _data_key(e.get("data"))) for e in json.loads(done.stdout)["data"]}, entry


def execute(calls: list[list[str]], seen: set[tuple[str, str, str]], receipt: dict) -> int:
    """Run ``calls`` in order; a ``log`` already in ``seen`` is a no-op; the first refusal stops (exit 1)."""
    for argv in calls:
        if argv[0] == "log":
            given = json.loads(argv[argv.index("--data") + 1]) if "--data" in argv else None
            key = (argv[argv.index("--type") + 1], argv[argv.index("--summary") + 1], _data_key(given))
            if key in seen:
                receipt["calls"].append({"argv": argv, "exit": 0, "result": "no-op"})
                continue
            seen.add(key)
        done = run_plan(argv)
        entry = {"argv": argv, "exit": done.returncode}
        if done.returncode:
            entry.update(result="refused", error=(done.stderr or done.stdout).strip())
            receipt["calls"].append(entry)
            return 1
        head = done.stdout.splitlines()[0] if done.stdout else ""
        entry["result"] = "no-op" if " already registered (attempt " in head else "recorded"
        receipt["calls"].append(entry)
    return 0


def finish_receipt(receipt: dict, plan: str, plans_root, code: int) -> int:
    if code == 0:
        argv = ["next", plan] + (["--plans-root", str(plans_root)] if plans_root else [])
        done = run_plan(argv)
        receipt["next"] = done.stdout.strip() if done.returncode == 0 else ""
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return code


def _evidence_arg(value: str) -> tuple[str, str]:
    check_id, sep, path = value.partition("=")
    if not sep or not _CHECK_ID.fullmatch(check_id) or not path:
        raise argparse.ArgumentTypeError(f"{value!r} must be V<n>=PATH")
    return check_id, path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plan.py bridge planner-orch register",
                                description="Register an orch stage-report into the plan through plan.py.")
    p.add_argument("plan", help="plan id, PLAN<N> or path")
    p.add_argument("ref", metavar="item[/U#]")
    p.add_argument("--report", required=True, help="stage-report JSON file")
    p.add_argument("--status", choices=STATUSES, help="item outcome; a unit return takes none")
    p.add_argument("--actor", required=True, metavar="P/M[/E]", help="the registrar")
    p.add_argument("--executed-by", metavar="P/M[/E]", help="the worker that produced the report")
    p.add_argument("--attempt-id", metavar="ID", help="delivery attempt; required with open_issues")
    p.add_argument("--evidence", action="append", default=[], type=_evidence_arg, metavar="V#=PATH",
                   help="check-evidence file; its exit is the check result (repeatable)")
    p.add_argument("--owner-session", metavar="SESSION",
                   help="refuse with REGISTER_STALE_OWNER unless the item's executor session is SESSION")
    p.add_argument("--gate", choices=GATES,
                   help="evidence: acceptance results come from check-evidence files only (MISSING, RED refusals)")
    p.add_argument("--plans-root", type=Path)
    p.add_argument("--dry-run", action="store_true", help="print the argv lists as JSON and write nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    evidence = dict(args.evidence)
    if len(evidence) != len(args.evidence):
        parser().error("--evidence repeats a check id")
    args.evidence = evidence
    item, _, unit = args.ref.partition("/")
    try:
        report = load_json(args.report, "REGISTER_REPORT_INVALID", "stage-report")
        calls = plan_calls(report, args)
        check_schema(report)  # after check_report (its codes come first), before any guard reads or writes
        gate = guard(args, item, unit)
    except Refusal as refusal:
        if refusal.gate is not None:  # under the guards the refusal also says what the gate saw
            print(json.dumps({"plan": args.plan, "ref": args.ref, "calls": [], "gate": refusal.gate},
                             ensure_ascii=False, indent=2))
        print(refusal, file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps(calls, ensure_ascii=False, indent=2))
        return 0
    if unit and evidence:
        named = " ".join(f"--evidence {check_id}={path}" for check_id, path in evidence.items())
        print(f"note: the integrator records unit evidence with: unit … {unit} accept {named}", file=sys.stderr)
    receipt = {"plan": args.plan, "ref": args.ref, "calls": []}
    if gate is not None:
        receipt["gate"] = gate
    seen: set[tuple[str, str, str]] = set()
    types = {argv[argv.index("--type") + 1] for argv in calls if argv[0] == "log"}
    if types:
        seen, entry = journal(args.plan, args.plans_root, item, types)
        if seen is None:
            receipt["calls"].append(entry)
            return finish_receipt(receipt, args.plan, args.plans_root, 1)
    code = execute(calls, seen, receipt)
    last = receipt["calls"][-1] if receipt["calls"] else {}
    if code and args.owner_session and last.get("argv", [""])[0] == "finish" \
            and str(last.get("error", "")).startswith("ITEM_OWNED"):
        receipt["gate"] = {"verdict": "stale", "checks": {}}  # taken over after the guard, refused under the lock
        print(f"REGISTER_STALE_OWNER: {last['error']}", file=sys.stderr)
    return finish_receipt(receipt, args.plan, args.plans_root, code)


if __name__ == "__main__":
    sys.exit(main())
