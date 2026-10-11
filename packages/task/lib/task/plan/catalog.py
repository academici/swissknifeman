"""Parser-derived API catalog with explicit data contracts, side effects and refusal codes."""
from __future__ import annotations

import argparse
import copy

from . import schema

# None means the legacy data payload is polymorphic or has no dedicated plan/v1 schema.
# schema's read-catalog applies to --verbs/default; <kind> returns the schema document itself.
VERB_DATA = {
    "new": None, "show": None, "get": "read-get", "list": "read-list", "events": "read-events",
    "artifact": "read-artifact", "links": "read-links", "neighborhood": "read-neighborhood",
    "schema": "read-catalog", "set": None, "apply": None, "export": "snapshot", "import": None,
    "add-document": None, "link": None, "unlink": None, "add-artifact": None, "push": None, "add-phase": None, "add-item": None, "add-decision": None,
    "batches": None, "check": None, "render": None, "next": None, "start": None, "context": None,
    "bridge": None, "finish": None, "unit": None, "stats": None, "log": None, "decide": None,
    "supersede": None, "grant": None, "design-done": None, "reopen": None, "reconcile": None, "archive": None, "commit": None, "commits": "read-commits",
}

# Mode describes the default invocation's writes; mixed verbs are conservative (unit is write; bridge verbs may write).
VERB_MODES = {
    "new": "write", "show": "read", "get": "read", "list": "read", "events": "read",
    "artifact": "read", "links": "read", "neighborhood": "read", "schema": "read",
    "set": "write", "apply": "write", "export": "read", "import": "write", "add-document": "write",
    "link": "write", "unlink": "write", "add-artifact": "write", "push": "write", "add-phase": "write", "add-item": "write", "add-decision": "write", "batches": "write",
    "check": "read", "render": "write", "next": "read", "start": "write", "context": "write",
    "bridge": "write", "finish": "write", "unit": "write", "stats": "read", "log": "write",
    "decide": "write", "supersede": "write", "grant": "write", "design-done": "write", "reopen": "write",
    "reconcile": "write",
    "archive": "write", "commit": "write", "commits": "read",
}

# Maintained refusal registry. Tests compare it with PlanError literals across lib/task/plan.
ERROR_CODES = frozenset("""
ACCEPT_REQUIRED ACTOR_REQUIRED AGENT_REQUIRED ALREADY_ARCHIVED ARCHIVE_EXISTS ATTEMPT_CONFLICT
ATTEMPT_ID_INVALID BRIDGE_INVALID BRIDGE_UNKNOWN BRIDGE_VERB_UNKNOWN BY_INVALID CHECKS_MISSING CHECKS_RED CHECK_UNKNOWN CONTENT_INVALID
DECISION_NOT_ACCEPTED DECISION_NOT_OPEN DECISION_REQUIRED DECISION_SELF_SUPERSEDE DECISION_SUPERSEDED
DEPENDENCY_NOT_READY DEPTH_INVALID DESIGN_INCOMPLETE DEVIATION_REQUIRED DIRECTION_INVALID
ESCALATION_REQUIRED EVIDENCE_CONFLICT EXTENSION_UNAVAILABLE EVIDENCE_INVALID EVIDENCE_REQUIRED EVIDENCE_SUBJECT EXTERNAL_GATE
FIELD_NOT_ARRAY FIELD_OWNED FIELD_UNKNOWN GATE_INVALID GATE_NOT_GRANTED GATE_UNKNOWN HUMAN_VIEW
GIT_UNAVAILABLE GIT_BUSY GIT_CONFLICT GIT_FAILED OUTSIDE_SCOPE NOTHING_TO_COMMIT
ID_DUPLICATE ITEMS_DUPLICATE ITEMS_REQUIRED ITEMS_SPAN_PHASES ITEM_NOT_IN_PROGRESS ITEM_NOT_STARTABLE
KIND_UNKNOWN LIMIT_INVALID LINK_INVALID LOG_INVALID LOG_TYPE_INVALID MESSAGE_REQUIRED MINUTES_INVALID NOTES_REQUIRED
NOTE_REQUIRED NOT_STARTED NOT_TERMINAL OPTION_UNKNOWN PARALLEL_LIMIT PATCH_INVALID
PATH_INVALID PHASE_NOT_DETAILED PLAN_AMBIGUOUS PLAN_CODENAME_INVALID PLAN_DATE_INVALID PLAN_EXISTS
PLAN_INVALID PLAN_LOCKED PLAN_NOT_DONE PLAN_NOT_FOUND RATIONALE_REQUIRED READ_MISSING REASON_REQUIRED
REF_INVALID REF_QUALIFIED REF_UNKNOWN REPO_UNKNOWN ROUTE_MISMATCH ROUTE_UNDERSHOOT
ROUTING_UNAVAILABLE SCHEMA_INVALID SECTION_UNKNOWN SINCE_INVALID STATUS_INVALID UNITS_OPEN
UNIT_DEPENDENCY UNIT_INVALID UNIT_SELF UNIT_STATE IO_ERROR USAGE VERB_FAILED
""".split())

_PLAN = {"PLAN_NOT_FOUND", "PLAN_AMBIGUOUS"}
_TARGET = {"REF_INVALID", "REF_UNKNOWN", "REF_QUALIFIED"}
_WRITE = {"PLAN_LOCKED", "SCHEMA_INVALID", "EXTENSION_UNAVAILABLE"}
_ROUTE = {"ROUTE_MISMATCH", "ROUTE_UNDERSHOOT", "ROUTING_UNAVAILABLE"}
_EVIDENCE = {"ATTEMPT_ID_INVALID", "ATTEMPT_CONFLICT", "CHECK_UNKNOWN", "EVIDENCE_INVALID", "EVIDENCE_SUBJECT",
             "EVIDENCE_REQUIRED", "EVIDENCE_CONFLICT"}
_LINK = {"LINK_INVALID", "KIND_UNKNOWN", "FIELD_NOT_ARRAY"}
_QUERY = _TARGET | {"SECTION_UNKNOWN", "REPO_UNKNOWN"}

# Conservative per-verb refusal sets; IO_ERROR and USAGE are shared CLI errors.
VERB_ERRORS = {
    "new": {"MESSAGE_REQUIRED", "PLAN_DATE_INVALID", "PLAN_CODENAME_INVALID", "PLAN_EXISTS"} | _WRITE,
    "show": _PLAN | _QUERY | {"LOG_INVALID"},
    "get": _PLAN | _QUERY | {"FIELD_UNKNOWN"},
    "list": _PLAN | _QUERY | {"KIND_UNKNOWN"},
    "events": _PLAN | _TARGET | {"LOG_INVALID", "SINCE_INVALID", "LIMIT_INVALID", "SCHEMA_INVALID"},
    "artifact": _PLAN | _QUERY | {"PATH_INVALID", "HUMAN_VIEW", "CONTENT_INVALID"},
    "links": _PLAN | _TARGET | {"SECTION_UNKNOWN", "DIRECTION_INVALID", "DEPTH_INVALID", "KIND_UNKNOWN"},
    "neighborhood": _PLAN | _TARGET | {"SECTION_UNKNOWN"},
    "schema": set(),
    "set": _PLAN | _TARGET | _WRITE | {"FIELD_OWNED", "PATCH_INVALID", "PLAN_INVALID"},
    "apply": _PLAN | _TARGET | _WRITE | {"FIELD_OWNED", "PATCH_INVALID", "PLAN_INVALID"},
    "export": _PLAN | {"LOG_INVALID"},
    "import": _PLAN | _WRITE | {"ID_DUPLICATE", "PLAN_INVALID", "PLAN_EXISTS", "LOG_INVALID"},
    "add-document": _PLAN | _WRITE | {"FIELD_OWNED", "PATCH_INVALID", "ID_DUPLICATE"},
    "link": _PLAN | _TARGET | _WRITE | _LINK | {"PLAN_INVALID"},
    "unlink": _PLAN | _TARGET | _WRITE | _LINK | {"PLAN_INVALID"},
    "add-artifact": _PLAN | _TARGET | _WRITE | {"LINK_INVALID", "FIELD_NOT_ARRAY", "PLAN_INVALID"},
    "push": _PLAN | _TARGET | _WRITE | {"FIELD_OWNED", "FIELD_NOT_ARRAY", "PLAN_INVALID"},
    "add-phase": _PLAN | _WRITE | {"FIELD_OWNED"},
    "add-item": _PLAN | _WRITE | {"REF_UNKNOWN", "FIELD_OWNED"},
    "add-decision": _PLAN | _WRITE | {"FIELD_OWNED"},
    "batches": _PLAN | _WRITE | {"REF_UNKNOWN"},
    "check": _PLAN | {"VERB_FAILED"},
    "render": _PLAN | {"VERB_FAILED"},
    "next": _PLAN | {"LIMIT_INVALID"},
    "start": _PLAN | _WRITE | _ROUTE | {"REF_UNKNOWN", "ACTOR_REQUIRED", "ITEMS_REQUIRED", "ITEMS_DUPLICATE",
        "ITEMS_SPAN_PHASES", "ITEM_NOT_STARTABLE", "PHASE_NOT_DETAILED", "DEPENDENCY_NOT_READY", "READ_MISSING",
        "HUMAN_VIEW", "EXTERNAL_GATE", "GATE_UNKNOWN", "GATE_NOT_GRANTED", "GATE_INVALID", "NOTE_REQUIRED"},
    "context": _PLAN | _TARGET | {"LOG_INVALID", "HUMAN_VIEW"},
    "bridge": {"BRIDGE_INVALID", "BRIDGE_UNKNOWN", "BRIDGE_VERB_UNKNOWN"},
    "finish": _PLAN | _WRITE | _ROUTE | _EVIDENCE | {"REF_UNKNOWN", "STATUS_INVALID", "NOT_STARTED",
        "CHECKS_MISSING", "CHECKS_RED", "DEVIATION_REQUIRED", "ESCALATION_REQUIRED", "DECISION_REQUIRED", "UNITS_OPEN"},
    "unit": _PLAN | _WRITE | _ROUTE | _EVIDENCE | {"REF_UNKNOWN", "FIELD_OWNED", "UNIT_INVALID", "AGENT_REQUIRED",
        "ITEM_NOT_IN_PROGRESS", "UNIT_SELF", "UNIT_STATE", "UNIT_DEPENDENCY", "PARALLEL_LIMIT", "NOTES_REQUIRED",
        "MINUTES_INVALID", "CHECKS_RED", "LOG_INVALID", "HUMAN_VIEW"},
    "stats": _PLAN,
    "log": _PLAN | _WRITE | {"REF_UNKNOWN", "REF_INVALID", "LOG_TYPE_INVALID"},
    "decide": _PLAN | _WRITE | {"REF_UNKNOWN", "DECISION_NOT_OPEN", "ACCEPT_REQUIRED", "OPTION_UNKNOWN",
        "RATIONALE_REQUIRED", "BY_INVALID"},
    "supersede": _PLAN | _WRITE | {"REF_UNKNOWN", "DECISION_NOT_ACCEPTED", "DECISION_SELF_SUPERSEDE", "DECISION_SUPERSEDED"},
    "grant": _PLAN | _WRITE | {"GATE_INVALID", "GATE_UNKNOWN", "NOTE_REQUIRED"},
    "design-done": _PLAN | _WRITE | {"REF_UNKNOWN", "DESIGN_INCOMPLETE"},
    "reopen": _PLAN | _WRITE | {"REF_UNKNOWN", "NOT_TERMINAL", "REASON_REQUIRED"},
    "reconcile": _PLAN | _WRITE,
    "archive": _PLAN | _WRITE | {"ALREADY_ARCHIVED", "ARCHIVE_EXISTS", "PLAN_NOT_DONE", "REASON_REQUIRED"},
    "commits": _PLAN | _TARGET | {"CONTENT_INVALID", "GIT_UNAVAILABLE", "GIT_FAILED", "SCHEMA_INVALID"},
    "commit": _PLAN | {"REF_INVALID", "REF_UNKNOWN", "PATH_INVALID", "PLAN_LOCKED", "CONTENT_INVALID",
                       "GIT_UNAVAILABLE", "GIT_BUSY", "GIT_CONFLICT", "GIT_FAILED", "OUTSIDE_SCOPE", "NOTHING_TO_COMMIT"},
}


def _arguments(parser: argparse.ArgumentParser, scope: str) -> list[dict]:
    rows = []
    for action in parser._actions:
        if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)) or action.help == argparse.SUPPRESS:
            continue
        name = action.option_strings[0] if action.option_strings else action.dest
        row = {"name": name, "required": action.required, "help": action.help or "", "scope": scope,
               "nargs": action.nargs if action.nargs is not None else 1}
        if len(action.option_strings) > 1:
            row["aliases"] = list(action.option_strings[1:])
        if action.choices is not None:
            row["choices"] = list(action.choices)
        for group in parser._mutually_exclusive_groups:
            if action in group._group_actions:
                row["exclusive_with"] = [other.option_strings[0] if other.option_strings else other.dest
                                         for other in group._group_actions if other is not action]
                row["required_group"] = group.required
        rows.append(row)
    return rows


def verbs(parser: argparse.ArgumentParser) -> dict:
    """Describe every parser verb without invoking handlers or opening a plan."""
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    names = set(sub.choices)
    if any(set(table) != names for table in (VERB_DATA, VERB_MODES, VERB_ERRORS)):
        raise ValueError("catalog metadata must match the parser's verbs exactly")
    global_args = _arguments(parser, "global")
    rows = []
    for name, command in sorted(sub.choices.items()):
        if not command.description:
            raise ValueError(f"catalog summary is missing for {name}")
        errors = VERB_ERRORS[name] | {"IO_ERROR", "USAGE", "SCHEMA_INVALID"}
        if not errors <= ERROR_CODES:
            raise ValueError(f"unregistered catalog refusal for {name}")
        row = {"name": name, "summary": command.description, "mode": VERB_MODES[name],
               "args": copy.deepcopy(global_args) + _arguments(command, "verb"), "errors": sorted(errors)}
        kind = VERB_DATA[name]
        if kind is not None:
            schema.load_registry().for_kind(kind)
            row["data_kind"] = kind
        rows.append(row)
    return {"verbs": rows}
