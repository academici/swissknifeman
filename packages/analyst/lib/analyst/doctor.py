"""analyst doctor — package environment diagnostics as check-result/v1 documents (read-only).

Checks: the Python floor and the state directory, the optional partners (`maind`, `planner`; found by
`aicore.util.partners`, none is imported) and the readability of the event journal. Nothing is written."""
import json
import os
import sys
from pathlib import Path

from aicore import MIN_PYTHON
from aicore.util.cli import parse_args
from aicore.util.partners import partner_command

RESULT_SCHEMA = "urn:swissknifeman:aicore:check-result:v1"


def _result(check_id, status, observed, *, category, evidence=None, remediation=None):
    doc = {"$schema": RESULT_SCHEMA, "check_id": check_id, "status": status,
           "category": category, "observed": observed}
    if evidence:
        doc["evidence"] = evidence
    if remediation:
        doc["remediation"] = remediation
    return doc


def _environment_check(env):
    floor = ".".join(str(part) for part in MIN_PYTHON)
    state = Path(env.state_dir)
    if sys.version_info < tuple(MIN_PYTHON):
        return _result("analyst.environment", "fail", f"python3 {sys.version.split()[0]} is older than {floor}",
                       category="environment", remediation=f"Install python3 >= {floor}.")
    # The state directory may not exist yet; writability is judged from the nearest existing parent.
    probe = state
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    evidence = [f"python3 {sys.version.split()[0]}", f"state_dir: {state}"]
    if not os.access(str(probe), os.W_OK):
        return _result("analyst.environment", "fail", f"the state directory {state} cannot be created or written",
                       category="environment", evidence=evidence, remediation=f"Make {probe} writable.")
    return _result("analyst.environment", "ok", f"python3 >= {floor}, state directory {state} is writable",
                   category="environment", evidence=evidence)


def _partners_check():
    found = {name: partner_command(name, legacy_env=("MAIND_BIN",) if name == "maind" else ())
             for name in ("maind", "planner")}
    missing = [name for name, cmd in found.items() if not cmd]
    evidence = [f"{name}: {found[name][0]}" for name in found if found[name]]
    if len(missing) == len(found):
        return _result("analyst.partners", "skip", "neither maind nor planner was found (both are optional)",
                       category="integration",
                       remediation="Set SKM_<PARTNER>_ROOT or put the partner on PATH to enable surfacing and plan links.")
    if missing:
        return _result("analyst.partners", "warn", f"optional partner not found: {', '.join(missing)}",
                       category="integration", evidence=evidence,
                       remediation="Set SKM_<PARTNER>_ROOT or put the partner on PATH.")
    return _result("analyst.partners", "ok", "maind and planner were found", category="integration", evidence=evidence)


def _events_check(project):
    from .events import events_path, read_events
    path = events_path(project)
    if not path.is_file():
        return _result("analyst.events", "skip", f"no event journal in {project}", category="state")
    try:
        total = sum(1 for _ in open(path, encoding="utf-8", errors="replace") if _.strip())
    except OSError as error:
        return _result("analyst.events", "fail", f"the event journal {path} cannot be read: {error.strerror}",
                       category="state", remediation="Check the file permissions.")
    readable = len(read_events(project))
    if readable < total:
        return _result("analyst.events", "warn", f"{total - readable} of {total} journal lines are not valid events",
                       category="state", evidence=[f"path: {path}"],
                       remediation="Inspect the journal; unreadable lines are skipped by readers.")
    return _result("analyst.events", "ok", f"the event journal holds {total} events", category="state",
                   evidence=[f"path: {path}"])


def run_checks(env, project=None):
    """The doctor checks as ``check-result/v1`` documents."""
    return [_environment_check(env), _partners_check(), _events_check(project or os.getcwd())]


def cmd_doctor(env, argv):
    """analyst doctor — environment diagnostics (python/state/partners/events)."""
    opts, _ = parse_args(argv, {"--json": "bool"})
    if opts["help"]:
        print("analyst doctor [--json] — diagnostics of the package environment; --json prints "
              "a list of check-result/v1 documents.")
        return
    results = run_checks(env)
    if opts["json"]:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for doc in results:
            print(f"{doc['status']} {doc['check_id']}: {doc['observed']}")
            if doc.get("remediation"):
                print(f"  remediation: {doc['remediation']}")
    if any(doc["status"] == "fail" for doc in results):
        raise SystemExit(1)
