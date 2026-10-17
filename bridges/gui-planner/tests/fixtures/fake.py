"""Fake `swissknifeman planner ...`: canned answers of one demo plan by argv; every call is logged to $HOME/umbrella.log.

Scenarios (the wrappers umbrella-*): ok, empty (no plans), broken (a plan with an unreadable plan.json in the list),
fail (exit 4 with ANSI noise), garbage (exit 0, not JSON), missing (every plan is PLAN_NOT_FOUND).
"""
import hashlib
import json
import os
import sys

DIR_ID = "2026.10.16-№1-DEMO"
ITEMS = {
    "P1.1": {"title": "Skeleton", "status": "done", "depends_on": [],
             "result": {"finished_at": "2026-10-16T10:00:00Z", "notes": "All good.", "deviations": ["moved a file"],
                        "pending": ["follow_up(docs): wording"],
                        "checks": [{"id": "V1", "exit": 0, "evidence": "@plan/artifacts/P1.1/V1.json"}],
                        "evidence": ["@plan/artifacts/P1.1/V1.json"]},
             "artifacts": [{"path": "out/report.json", "role": "output", "id": "report"}]},
    "P1.2": {"title": "Contracts", "status": "skipped", "depends_on": ["P1.1"]},
    "P2.1": {"title": "Form \x1b[31mred\x1b[0m <script>alert(1)</script>", "status": "todo", "depends_on": []},
    "P2.2": {"title": "Query", "status": "in_progress", "depends_on": ["P1.1", "P2.1"],
             "summary": "Reads the **plan**.", "why": "Because.", "route": {"class": "implementation", "effort": "medium"},
             "review": {"mode": "requested", "reviewer": {"class": "frontier", "provider": "codex", "model": "gpt-x",
                                                          "effort": "high"}},
             "authority": {"kind": "routine"}},
    "P2.3": {"title": "Command", "status": "blocked", "depends_on": ["P2.2", "P9.9"],
             "related": [{"ref": "P2.1", "relation": "informs"}, {"ref": "D1", "relation": "informs"},
                         {"ref": "P7.7", "relation": "informs"}]},
    "P2.4": {"title": "Odd", "status": "weird", "depends_on": []},
    "P2.5": {"title": "Docs", "status": "done_with_deviations", "depends_on": ["P2.4"]},
}
DECISIONS = {"D1": {"title": "Stack", "status": "accepted", "date": "2026-10-16"},
             "D2": {"title": "Open question", "status": "open"}}
EVENTS = [
    {"v": 1, "ts": "2026-10-16T09:00:00Z", "type": "start", "item": "P1.1", "phase": "P1",
     "actor": {"provider": "orch", "model": "conductor"}, "summary": "P1.1 started", "data": {}},
    {"v": 1, "ts": "2026-10-16T10:00:00Z", "type": "finish", "item": "P1.1", "phase": "P1",
     "actor": {"provider": "orch", "model": "conductor"}, "summary": "P1.1 done", "data": {}},
    {"v": 1, "ts": "2026-10-16T11:00:00Z", "type": "Odd Type!", "summary": "plan level \x1b[1mnote\x1b[0m", "data": {}},
    {"v": 1, "ts": "not a time", "type": "note", "summary": "dropped", "data": {}},
]


def item_doc(ref):
    item = ITEMS[ref]
    return {"$schema": "urn:swissknifeman:task:plan:item:v1", "id": ref, **item}


def plan_row(scenario):
    done = sum(1 for i in ITEMS.values() if i["status"] in ("done", "done_with_deviations", "skipped"))
    return {"id": DIR_ID, "short_id": "PLAN1", "title": "Demo plan", "status": "active", "updated_at": "2026-10-16T12:00:00Z",
            "progress": {"phases": 2, "phases_closed": 1, "items": len(ITEMS), "items_done": done}}


def show():
    def phase(pid, closed):
        return {"id": pid, "title": f"Phase {pid}", "design": "detailed", "closed": closed,
                "items": [{"id": k, "title": v["title"], "status": v["status"]} for k, v in ITEMS.items()
                          if k.split(".")[0] == pid]}
    return {"id": DIR_ID, "short_id": "PLAN1", "title": "Demo plan", "status": "active",
            "phases": [phase("P1", {"at": "2026-10-16T10:00:00Z", "result": "done", "summary": "2 item(s)"}),
                       phase("P2", None)],
            "decisions": [{"id": k, "title": v["title"], "status": v["status"]} for k, v in DECISIONS.items()],
            "next": "run-items: P2.1"}


def get(ref):
    if ref == "plan":
        return {"kind": "plan", "doc": {"goal": "Ship the demo.\n\n```evil```", "context": "Some context <b>x</b>.",
                                        "rules": ["Rule one", "Rule two"]}}
    if ref == "brief":
        return {"kind": "brief", "doc": {"messages": []}}
    if ref in ITEMS:
        return {"kind": "item", "doc": item_doc(ref)}
    if ref in DECISIONS:
        return {"kind": "decision", "doc": {"id": ref, **DECISIONS[ref]}}
    if ref in ("P1", "P2"):
        return {"kind": "phase", "doc": {"title": f"Phase {ref}", "design": "detailed"}}
    return None


def _state_path():
    return os.path.join(os.environ.get("HOME", "/tmp"), "umbrella-state.json")


def _writes():
    try:
        with open(_state_path(), encoding="utf-8") as handle:
            return json.load(handle)
    except OSError:
        return {}


def revision(ref):
    """The revision of a document: it changes with every accepted `set` of that ref."""
    return "sha256:" + hashlib.sha256(f"{ref}:{_writes().get(ref, 0)}".encode()).hexdigest()


def main(scenario):
    args = sys.argv[1:]
    home = os.environ.get("HOME", "/tmp")
    with open(os.path.join(home, "umbrella.log"), "a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": args, "cwd": os.getcwd()}) + "\n")
    if scenario == "fail":
        print("first line", file=sys.stderr)
        print("planner: broken \x1b[31mbadly\x1b[0m", file=sys.stderr)
        return 4
    if scenario == "garbage":
        print("this is not json")
        return 0
    if args == ["units", "list", "--json"]:
        try:
            with open(os.path.join(home, "aicore-root"), encoding="utf-8") as handle:
                root = handle.read().strip()
        except OSError:
            root = "/nonexistent"
        print(json.dumps({"hub_root": "", "units": [{"id": "aicore", "root": root}]}))
        return 0
    if args[:1] != ["planner"]:
        print(f"unknown command {args}", file=sys.stderr)
        return 2
    args = args[1:]
    envelope = args[:2] == ["--output", "json"]
    if envelope:
        args = args[2:]

    def ok(data):
        print(json.dumps({"ok": True, "data": data}, ensure_ascii=False))
        return 0

    def refuse(code, message):
        if envelope:
            print(json.dumps({"ok": False, "error": {"code": code, "message": message}}))
        else:
            print(f"{code}: {message}", file=sys.stderr)
        return 1

    if args == ["plans"]:
        rows = {"empty": [], "broken": [{"id": "2026.10.01-№1-DEMO", "error": "PLAN_INVALID"}, plan_row(scenario)]}
        return ok({"plans": rows.get(scenario, [plan_row(scenario)])})
    plan = args[1] if len(args) > 1 else None
    if scenario == "missing" or plan not in ("PLAN1", DIR_ID):
        return refuse("PLAN_NOT_FOUND", f"no plan {plan}")
    if args[0] == "show" and args[2:] == ["--json"]:
        print(json.dumps(show(), ensure_ascii=False))
        return 0
    if args[0] == "get" and len(args) == 3:
        found = get(args[2])
        return ok({"ref": args[2], "kind": found["kind"], "doc": found["doc"], "revision": revision(args[2])}) \
            if found else refuse("REF_UNKNOWN", f"unknown {args[2]}")
    if args[0] == "get" and args[3:4] == ["--fields"]:
        found = get(args[2])
        if not found:
            return refuse("REF_UNKNOWN", f"unknown {args[2]}")
        fields = args[4].split(",")
        return ok({"ref": args[2], "kind": found["kind"], "doc": {k: found["doc"][k] for k in fields if k in found["doc"]},
                   "revision": revision(args[2])})
    if args[0] == "set":
        ref, body = args[2], json.loads(args[4])
        expected = args[5].split("=", 1)[1] if len(args) > 5 and args[5].startswith("--expected-revision=") else None
        if get(ref) is None:
            return refuse("REF_UNKNOWN", f"unknown {ref}")
        if set(body) & {"status", "result", "id", "updated_at"}:
            return refuse("FIELD_OWNED", "identity or lifecycle-owned")
        if expected != revision(ref):
            return refuse("PLAN_REVISION_CONFLICT", f"the document changed since revision {expected}")
        writes = _writes()
        writes[ref] = writes.get(ref, 0) + 1
        with open(_state_path(), "w", encoding="utf-8") as handle:
            json.dump(writes, handle)
        return ok({"message": f"updated {ref}"}) if envelope else 0
    if args[0] == "check":
        broken = _writes().get("P2.4")
        if broken:
            if envelope:
                print(json.dumps({"ok": False, "error": {"code": "VERB_FAILED", "message": "check exited 1", "issues": [
                    {"level": "error", "code": "x", "where": "P2.4", "message": "bad"},
                    {"level": "error", "code": "y", "where": "P2.4", "message": "worse"},
                    {"level": "warning", "code": "z", "where": "plan", "message": "meh"}]}}))
            return 1
        return ok({"ok": True, "errors": 0, "warnings": 1, "issues": [{"level": "warning", "code": "z", "where": "plan",
                                                                         "message": "meh"}]})
    if args[0] == "grant" and args[2] == "NOGATE":
        return refuse("GATE_UNKNOWN", "no item declares owner gate 'NOGATE'")
    if args[0] in ("decide", "reopen", "grant", "log"):
        return ok({"message": f"{args[0]} done"})
    if args[0] == "list" and args[2] == "item":
        phase = args[args.index("--phase") + 1] if "--phase" in args else None
        return ok([{"ref": k, "title": v["title"], "status": v["status"]} for k, v in ITEMS.items()
                   if phase in (None, k.split(".")[0])])
    if args[0] == "list" and args[2] == "decision":
        return ok([{"ref": k, "title": v["title"], "status": v["status"]} for k, v in DECISIONS.items()])
    if args[0] == "events":
        only = args[args.index("--item") + 1] if "--item" in args else None
        return ok([e for e in EVENTS if only in (None, e.get("item"))])
    print(f"unknown command {args}", file=sys.stderr)
    return 2
