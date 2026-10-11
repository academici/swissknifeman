"""analyst events — ecosystem run outcomes received from planner.* and orch.run.* events.

The subscription ``run-events`` of ``unit.json`` runs ``analyst events ingest --event -`` for every delivered
event. One line per event is appended to ``ecosystem-events.jsonl`` in the analyst state directory; the values of
``data`` are never copied, only the fields below and the digest of the canonical ``data``.

Fields read from ``data`` (checked against the producers' schemas by ``scripts/test-event-contracts.py``):

====================== ======================================= ==================================
event type             subject                                 outcome
====================== ======================================= ==================================
planner.item.finished  ``<plan_id>/<item_id>``                 ``status``
planner.phase.closed   ``<plan_id>/<phase_id>``                ``result``
planner.plan.closed    ``plan_id``                             ``status``
orch.run.finished      ``run_id``                              ``outcome``
orch.run.refused       ``run_id`` or ``submission_id``         ``null`` (``step`` is not an outcome)
====================== ======================================= ==================================

``project`` is ``data.project`` when a producer sends it, else ``null``.
"""
import datetime
import fcntl
import json
import os
import sys
from contextlib import contextmanager

from aicore.ext import events as _events
from aicore.util.cli import parse_args
from aicore.util.digest import digest_json
from aicore.util.term import die, parse_iso

JOURNAL = "ecosystem-events.jsonl"
SUBSCRIBED = (
    "planner.item.finished", "planner.phase.closed", "planner.plan.closed",
    "orch.run.finished", "orch.run.refused",
)
INVALID = "ANALYST_EVENT_INVALID"
MAX_EVENT_BYTES = 1 << 20
STATUS_DAYS = 30

_OUTCOME_KEYS = {
    "planner.item.finished": "status",
    "planner.phase.closed": "result",
    "planner.plan.closed": "status",
    "orch.run.finished": "outcome",
    "orch.run.refused": None,
}

_HELP = """analyst events ingest --event -|FILE
  Subscriber of planner.item.finished, planner.phase.closed, planner.plan.closed, orch.run.finished and
  orch.run.refused: records the outcome of one event (never the values of its data) once per event id.
  Other event types: exit 0, "skip" on stderr. Invalid event: exit 2, ANALYST_EVENT_INVALID.
analyst events list [--type T] [--since ISO] [--json]
  Recorded events and the counts per type and outcome."""


def journal_path(env):
    return os.path.join(str(env.state_dir), JOURNAL)


def _invalid(message):
    print(f"{INVALID}: {message}", file=sys.stderr)
    sys.exit(2)


def _read_document(source):
    try:
        if source == "-":
            raw = sys.stdin.buffer.read(MAX_EVENT_BYTES + 1)
        else:
            with open(source, "rb") as handle:
                raw = handle.read(MAX_EVENT_BYTES + 1)
    except OSError as exc:
        _invalid(f"the event cannot be read from {source}: {exc.strerror or exc}")
    if len(raw) > MAX_EVENT_BYTES:
        _invalid(f"the event is larger than {MAX_EVENT_BYTES} bytes")
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        _invalid("the event is not JSON")


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def build_record(event):
    """The journal line of a subscribed ``Event``; ``ANALYST_EVENT_INVALID`` (ValueError) for unusable data."""
    data = event.data
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    kind = event.type
    if kind in ("planner.item.finished", "planner.phase.closed"):
        key = "item_id" if kind == "planner.item.finished" else "phase_id"
        plan, part = _text(data.get("plan_id")), _text(data.get(key))
        if not plan or not part:
            raise ValueError(f"data.plan_id and data.{key} are required")
        subject = f"{plan}/{part}"
    elif kind == "planner.plan.closed":
        subject = _text(data.get("plan_id"))
        if not subject:
            raise ValueError("data.plan_id is required")
    else:
        subject = _text(data.get("run_id")) or _text(data.get("submission_id"))
        if not subject:
            raise ValueError("data.run_id or data.submission_id is required")
    outcome_key = _OUTCOME_KEYS[kind]
    outcome = _text(data.get(outcome_key)) if outcome_key else None
    if outcome_key and outcome is None:
        raise ValueError(f"data.{outcome_key} is required")
    return {
        "event_id": event.id, "type": kind, "occurred_at": event.time, "source": event.source,
        "project": _text(data.get("project")), "subject": subject, "outcome": outcome,
        "data_digest": digest_json(data),
    }


@contextmanager
def _locked(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def read_records(path):
    """Journal records in file order; a line that is not a JSON object is skipped."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except FileNotFoundError:
        return []
    found = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and isinstance(item.get("event_id"), str):
            found.append(item)
    return found


def ingest(env, document):
    """Record one event document; returns ``"recorded"``, ``"duplicate"`` or ``"skipped"``."""
    if not isinstance(document, dict):
        _invalid("the event is not a JSON object")
    problems = _events.validate_document(document)
    if problems:
        _invalid(f"the event is not a valid event/v1 document: {problems[0]}")
    event = _events.Event.from_json(document)
    if event.type not in SUBSCRIBED:
        print(f"analyst events: skip {event.type}", file=sys.stderr)
        return "skipped"
    try:
        record = build_record(event)
    except (ValueError, TypeError) as exc:  # TypeError: data the canonical digest cannot hold (floats)
        _invalid(str(exc))
    path = journal_path(env)
    with _locked(path):
        if any(item["event_id"] == record["event_id"] for item in read_records(path)):
            return "duplicate"
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return "recorded"


def summarize(records):
    """``{"events": [...], "counts": {type: {outcome: n}}}``; a missing outcome counts as ``none``."""
    counts = {}
    for item in records:
        per_type = counts.setdefault(item.get("type", ""), {})
        outcome = item.get("outcome") or "none"
        per_type[outcome] = per_type.get(outcome, 0) + 1
    return {"events": records, "counts": counts}


def select(records, kind=None, since=None):
    found = []
    for item in records:
        if kind and item.get("type") != kind:
            continue
        if since is not None:
            moment = parse_iso(item.get("occurred_at") or "")
            if moment is None or moment < since:
                continue
        found.append(item)
    return found


def status_summary(env, now=None):
    """The block ``ecosystem_events`` of ``analyst status``: events of the last 30 days and counts per type."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    recent = select(read_records(journal_path(env)), since=now - datetime.timedelta(days=STATUS_DAYS))
    return {"total": len(recent), "days": STATUS_DAYS,
            "by_type": {kind: sum(per.values()) for kind, per in summarize(recent)["counts"].items()}}


def cmd_events(env, argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_HELP)
        return
    sub, rest = argv[0], argv[1:]
    if sub == "ingest":
        opts, _ = parse_args(rest, {"--event": "str"})
        if opts["help"]:
            print(_HELP)
            return
        if not opts["event"]:
            die("analyst events ingest requires --event -|FILE", 2)
        outcome = ingest(env, _read_document(opts["event"]))
        # Subscriber protocol: one JSON object whose ``status`` is ok or skipped.
        print(json.dumps({"status": "skipped" if outcome == "skipped" else "ok", "result": outcome}))
    elif sub == "list":
        opts, _ = parse_args(rest, {"--type": "str", "--since": "str", "--json": "bool"})
        if opts["help"]:
            print(_HELP)
            return
        since = None
        if opts["since"]:
            since = parse_iso(opts["since"])
            if since is None:
                die(f"--since is not an ISO timestamp: {opts['since']}", 2)
        result = summarize(select(read_records(journal_path(env)), opts["type"] or None, since))
        if opts["json"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        for item in result["events"]:
            print(f"{item['occurred_at']}  {item['type']}  {item.get('subject')}  {item.get('outcome') or '-'}")
        print(f"{len(result['events'])} event(s)")
    else:
        die(f"unknown events command: {sub}", 2)
