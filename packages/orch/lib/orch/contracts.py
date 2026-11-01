"""exec/v1 schema registry, semantic validation and document digests."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Callable, NamedTuple

import aicore
from aicore.util import digest as canonical, timefmt

from orch import CONTRACT_VERSION
from orch import schema

URN_PREFIX = "urn:swissknifeman:orch:exec:"
KINDS = (
    "execution-input", "run-policy", "role-manifest", "capability-record", "run-event",
    "stage-result", "effect-receipt", "check-evidence", "launch-plan",
)
# aicore contracts that exec/v1 schemas reference (transitively); they join the registry for $ref resolution.
AICORE_CONTRACTS = ("error", "artifact-ref", "digest", "common", "permissions", "capability-support")
# Identity keys, one per level of the idempotency hierarchy; values of different levels never coincide.
KEY_FIELDS = ("submission_id", "run_id", "attempt_id", "call_id", "event_id")
# The required part of an execution input; a condensed brief pins it by digest.
REQUIRED_PART = ("goal", "scope", "acceptance", "constraints", "decisions", "route", "result_contract", "escalation")
# Plan bridges add their own stricter phrases.
LIFECYCLE_PHRASES = ("report_api", "report API")


class Issue(NamedTuple):
    path: str
    code: str
    message: str
    level: str = "error"


SEMANTIC: dict[str, Callable[[object], list[Issue]]] = {}


def load_registry() -> schema.Registry:
    """Load the cached registry from this package, independent of the current cwd."""
    directory = Path(__file__).resolve().parents[2] / "schemas" / "exec" / "v1"
    foundation = Path(aicore.__file__).resolve().parents[2] / "schemas"
    extras = tuple(foundation / name / "v1" for name in AICORE_CONTRACTS)
    return schema.load_registry(directory, urn_prefix=URN_PREFIX, kinds=KINDS, extra_dirs=extras)


def semantic_checks(doc: object, kind: str) -> list[Issue]:
    if kind not in KINDS:
        raise schema.SchemaProfileError(f"unknown schema kind: {kind!r}")
    issues = []
    if isinstance(doc, dict) and doc.get("contract_version") != CONTRACT_VERSION:
        issues.append(Issue("/contract_version", "CONTRACT_VERSION",
                            f"contract_version must equal {CONTRACT_VERSION!r}"))
    check = SEMANTIC.get(kind)
    if check is not None:
        issues.extend(check(doc))
    if isinstance(doc, dict):
        issues.extend(_key_reuse(doc))
    return issues


def validate(doc: object, kind: str, registry: schema.Registry | None = None) -> list[Issue]:
    """Reject incompatible versions, then collect schema and semantic issues."""
    semantic = semantic_checks(doc, kind)
    # A different contract version cannot be interpreted using exec/v1 schemas.
    if any(issue.code == "CONTRACT_VERSION" for issue in semantic):
        return semantic
    reg = registry if registry is not None else load_registry()
    return [Issue(*issue) for issue in schema.validate(doc, kind, reg)] + semantic


def canonical_digest(doc: dict) -> str:
    """Bare sha256 hex of the canonical JSON without digest or the derived suffix of input_id."""
    payload = {key: value for key, value in doc.items() if key != "digest"}
    if isinstance(payload.get("input_id"), str):
        payload["input_id"] = payload["input_id"].rsplit("@", 1)[0]
    return canonical.sha256_hex(canonical.canonical_json_bytes(payload))


def _walk(value: object, path: str = ""):
    """Yield values with escaped JSON pointers, including nested JSON content."""
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from _walk(child, f"{path}/{escaped}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}/{index}")


def _execution_input(doc: object) -> list[Issue]:
    if not isinstance(doc, dict):
        return []
    issues = []
    digest, input_id = doc.get("digest"), doc.get("input_id")
    if isinstance(digest, str):
        try:
            matches = digest == canonical_digest(doc)
        except (TypeError, ValueError):  # not canonical JSON (floats, lone surrogates): the schema check reports it
            issues.append(Issue("/digest", "DIGEST_MISMATCH", "digest cannot be computed: document is not canonical JSON"))
        else:
            if not matches:
                issues.append(Issue("/digest", "DIGEST_MISMATCH", "digest does not match canonical JSON"))
    if isinstance(input_id, str) and isinstance(digest, str) and not input_id.endswith("@" + digest[:12]):
        issues.append(Issue("/input_id", "INPUT_ID", "input_id must end with @digest[:12]"))
    scope, result_contract = doc.get("scope"), doc.get("result_contract")
    if isinstance(scope, dict) and scope.get("read_only") is True \
            and isinstance(result_contract, dict) and result_contract.get("write_authority") != "none":
        issues.append(Issue("/result_contract/write_authority", "INPUT_AUTHORITY",
                            "read-only input requires write_authority none"))
    for path, value in _walk(doc):
        if not isinstance(value, str) or not any(phrase in value for phrase in LIFECYCLE_PHRASES):
            continue
        if path == "/provenance/generated_by/tool":
            continue
        level = "error"
        parts = path.split("/")
        if len(parts) == 4 and parts[1] == "constraints" and parts[2].isdigit() and parts[3] == "text":
            constraints = doc.get("constraints")
            if isinstance(constraints, list):
                constraint = constraints[int(parts[2])]
                if isinstance(constraint, dict) and isinstance(constraint.get("source"), str) \
                        and constraint["source"].startswith("plan.rules"):
                    level = "warning"
        issues.append(Issue(path, "LIFECYCLE_LEAK", "lifecycle instruction is present in execution input", level))
    acceptance = doc.get("acceptance")
    for index, entry in enumerate(doc.get("reads") or []):
        if not isinstance(entry, dict) or entry.get("delivery") != "on-demand":
            continue
        path = entry.get("path")
        if (not isinstance(path, str) or path.startswith(("@plan/", "/", "~")) or not path.endswith(".json")
                or ".." in re.split(r"[\\/]", path)
                or "section" in entry or "content" in entry or "included" in entry or entry.get("error")
                or (entry.get("exists") is True and not entry.get("sha256"))
                or (entry.get("required") is True and entry.get("exists") is not True)):
            issues.append(Issue(f"/reads/{index}", "READ_DELIVERY_INVALID",
                                "on-demand needs a whole repository JSON path and identity, without inline content"))
    for index, entry in enumerate(doc.get("context_refs") or []):
        if isinstance(entry, dict) and entry.get("delivery") == "supplement" and "content" not in entry:
            issues.append(Issue(f"/context_refs/{index}/content", "CONTEXT_MISSING",
                                "supplement delivery requires inline content"))
    checks = acceptance.get("checks") if isinstance(acceptance, dict) else None
    if isinstance(checks, list):
        for index, check in enumerate(checks):
            if isinstance(check, dict) and ("cmd" in check) == ("procedure" in check):
                issues.append(Issue(f"/acceptance/checks/{index}", "CHECK_CARRIER",
                                    "check must contain exactly one of cmd or procedure"))
    return issues


def _run_policy(doc: object) -> list[Issue]:
    if not isinstance(doc, dict):
        return []
    issues = []
    for path, value in _walk(doc):
        if isinstance(value, int) and not isinstance(value, bool) and value < 0:
            issues.append(Issue(path, "POLICY_NEGATIVE", "policy integers must be non-negative"))
    if "commit" in doc and doc.get("git_action") == "none":
        issues.append(Issue("/commit", "COMMIT_POLICY_CONFLICT",
                            "commit policy requires git_action commit"))
    isolation = doc.get("isolation")
    if isinstance(isolation, dict) and isolation.get("mode") == "worktree" and doc.get("git_action") == "none":
        issues.append(Issue("/isolation", "ISOLATION_POLICY_CONFLICT",
                            "worktree isolation needs git_action commit to integrate"))
    stages = doc.get("stages")
    if not isinstance(stages, list):
        return issues
    primary = sum(isinstance(stage, dict) and stage.get("kind") == "primary" for stage in stages)
    if primary != 1:
        issues.append(Issue("/stages", "POLICY_PRIMARY", "policy must have exactly one primary stage"))
    graph = {}
    previous = None
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue
        if stage.get("required") is True and stage.get("on_unavailable") != "refuse":
            issues.append(Issue(f"/stages/{index}/on_unavailable", "POLICY_REQUIRED_REFUSE",
                                "required stages must refuse when unavailable"))
        stage_id = stage.get("id")
        if not isinstance(stage_id, str):
            continue
        if stage_id in graph:
            issues.append(Issue(f"/stages/{index}/id", "POLICY_DEPENDS", "stage id is duplicated"))
        depends = stage.get("depends_on", [previous] if previous is not None else [])
        graph[stage_id] = [d for d in depends if isinstance(d, str)] if isinstance(depends, list) else []
        previous = stage_id
    unknown = any(dep not in graph for deps in graph.values() for dep in deps)
    if unknown:
        issues.append(Issue("/stages", "POLICY_DEPENDS", "dependency refers to an unknown stage"))
    # Remove satisfied nodes iteratively; this also avoids recursion limits for long pipelines.
    remaining = {name: set(deps) & graph.keys() for name, deps in graph.items()}
    while remaining:
        ready = {name for name, deps in remaining.items() if not deps}
        if not ready:
            issues.append(Issue("/stages", "POLICY_DEPENDS", "stage dependencies contain a cycle"))
            break
        remaining = {name: deps - ready for name, deps in remaining.items() if name not in ready}
    review = doc.get("review")
    if isinstance(review, dict):
        for field, limit in (("max_rounds", 2), ("max_corrections", 1)):
            value = review.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value > limit:
                issues.append(Issue(f"/review/{field}", "POLICY_REVIEW_LIMIT", f"{field} must not exceed {limit}"))
        has_review = any(isinstance(s, dict) and s.get("kind") == "review" for s in stages)
        if isinstance(review.get("enabled"), bool) and review["enabled"] != has_review:
            issues.append(Issue("/review/enabled", "POLICY_REVIEW_STAGE",
                                "review.enabled must match the presence of a review stage"))
    return issues


def _role_manifest(doc: object) -> list[Issue]:
    if not isinstance(doc, dict) or not isinstance(doc.get("tools"), dict):
        return []
    authority, tools = doc.get("write_authority"), doc["tools"]
    if (authority == "plan") != (tools.get("plan_api") == "write") \
            or (authority == "none" and tools.get("filesystem") == "write"):
        return [Issue("/write_authority", "ROLE_AUTHORITY", "write authority conflicts with tool permissions")]
    return []


def _capability_record(doc: object) -> list[Issue]:
    if not isinstance(doc, dict) or doc.get("status") != "declared":
        return []
    evidence = doc.get("evidence")
    if isinstance(evidence, list) and any(isinstance(e, dict) and e.get("kind") in ("doc", "code")
                                          for e in evidence):
        return []
    fields = ("model", "effort", "stream", "attach", "cancel", "resume", "usage",
              "restrictions", "skill_delivery", "plan_write_prevention")
    for field in fields:
        value = doc.get(field)
        values = value.items() if isinstance(value, dict) else (("", value),)
        for name, support in values:
            if name in ("notes", "mode", "prompt_only"):
                continue
            if support == "supported":
                return [Issue("/evidence", "CAPABILITY_EVIDENCE",
                              "declared supported capabilities require doc or code evidence")]
    return []


SEMANTIC.update({
    "execution-input": _execution_input,
    "run-policy": _run_policy,
    "role-manifest": _role_manifest,
    "capability-record": _capability_record,
})


def required_digest(doc: dict) -> str:
    """Bare sha256 hex of the canonical JSON of the required part of an execution input."""
    part = {key: doc[key] for key in REQUIRED_PART if key in doc}
    return canonical.sha256_hex(canonical.canonical_json_bytes(part))


_TS = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?Z", re.ASCII)


def _parse_ts(value: object) -> tuple[datetime, str] | None:
    """Whole seconds and the fraction digits of a ``ts`` value (the schema allows any number of digits)."""
    match = _TS.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    whole = timefmt.parse_rfc3339(match.group(1))
    if whole is None:  # a pattern-valid value that is not a calendar time; the schema check cannot tell
        return None
    return whole, match.group(2) or ""


def _ts_before(first: tuple[datetime, str], second: tuple[datetime, str]) -> bool:
    width = max(len(first[1]), len(second[1]))
    return (first[0], first[1].ljust(width, "0")) < (second[0], second[1].ljust(width, "0"))


def _condensed(doc: dict) -> list[Issue]:
    condensed = doc.get("condensed")
    if not isinstance(condensed, dict) or not isinstance(condensed.get("required_digest"), str):
        return []
    try:
        matches = condensed["required_digest"] == required_digest(doc)
    except (TypeError, ValueError):  # not canonical JSON (floats, lone surrogates): the schema check reports it
        return [Issue("/condensed/required_digest", "CONDENSED_REQUIRED_DRIFT",
                      "required_digest cannot be computed: the required part is not canonical JSON")]
    if matches:
        return []
    return [Issue("/condensed/required_digest", "CONDENSED_REQUIRED_DRIFT",
                  "required_digest does not match the canonical JSON of the required part")]


def _capability_freshness(doc: dict) -> list[Issue]:
    issues = []
    observed, fresh = _parse_ts(doc.get("observed_at")), _parse_ts(doc.get("fresh_until"))
    if observed is not None and fresh is not None and _ts_before(fresh, observed):
        issues.append(Issue("/fresh_until", "CAPABILITY_FRESHNESS", "fresh_until is earlier than observed_at"))
    source, status = doc.get("source"), doc.get("status")
    if isinstance(source, str) and isinstance(status, str):
        # declared and probed records keep their own source; an inferred source only backs a declared record.
        consistent = status == "declared" if source == "inferred" else source == status
        if not consistent:
            issues.append(Issue("/source", "CAPABILITY_FRESHNESS", f"source {source} contradicts status {status}"))
    return issues


def _fallback_declared(doc: dict) -> list[Issue]:
    on_error = doc.get("on_error")
    if not isinstance(on_error, dict) or doc.get("fallback_routes"):
        return []
    return [Issue(f"/on_error/{name}/action", "FALLBACK_UNDECLARED",
                  "action fallback_route requires a non-empty fallback_routes")
            for name, rule in on_error.items()
            if isinstance(rule, dict) and rule.get("action") == "fallback_route"]


def _key_reuse(doc: dict) -> list[Issue]:
    """Report identity keys of different levels that carry the same value."""
    issues = []
    seen: dict[str, str] = {}
    for name in KEY_FIELDS:
        value = doc.get(name)
        if not isinstance(value, str):
            continue
        if value in seen:
            issues.append(Issue(f"/{name}", "KEY_REUSED", f"{name} repeats the value of {seen[value]}"))
        else:
            seen[value] = name
    return issues


def _owner_epoch(doc: dict) -> list[Issue]:
    value = doc.get("owner_epoch")
    if isinstance(value, int) and not isinstance(value, bool) and value < 1:
        return [Issue("/owner_epoch", "EPOCH_INVALID", "owner_epoch must be at least 1")]
    return []


def _attempt_range(doc: dict, *, event: bool = False) -> list[Issue]:
    issues = []
    for name, minimum in (("attempt", 1), ("seq", 0)) if event else (("attempt", 1),):
        value = doc.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value < minimum:
            issues.append(Issue(f"/{name}", "ATTEMPT_RANGE", f"{name} must be at least {minimum}"))
    return issues


def _run_event(doc: object) -> list[Issue]:
    return _attempt_range(doc, event=True) + _owner_epoch(doc) if isinstance(doc, dict) else []


def _stage_result(doc: object) -> list[Issue]:
    if not isinstance(doc, dict):
        return []
    issues = _attempt_range(doc) + _owner_epoch(doc)
    commits = doc.get("commits")
    if isinstance(commits, list):
        seen = set()
        for index, commit in enumerate(commits):
            commit_sha = commit.get("sha") if isinstance(commit, dict) else None
            if not isinstance(commit_sha, str):
                continue
            if commit_sha in seen:
                issues.append(Issue(f"/commits/{index}/sha", "COMMIT_SHA_DUPLICATE",
                                    "commit hashes must be unique"))
            seen.add(commit_sha)
    usage = doc.get("usage")
    if isinstance(usage, dict):
        if usage.get("status") == "unknown" and any(
                name in usage for name in ("input_tokens", "output_tokens", "cost_usd")):
            issues.append(Issue("/usage", "USAGE_UNKNOWN_NUMERIC",
                                "unknown usage must not include token counts or cost"))
        cost = usage.get("cost_usd")
        if isinstance(cost, str) and re.fullmatch(r"\d+(\.\d+)?", cost, re.ASCII) is None:
            issues.append(Issue("/usage/cost_usd", "COST_FORMAT", "cost_usd must be a decimal string"))
    errors = doc.get("errors")
    if doc.get("status") == "completed" and isinstance(errors, list):
        for index, error in enumerate(errors):
            if isinstance(error, dict) and error.get("class") == "parse":
                issues.append(Issue(f"/errors/{index}", "COMPLETED_PARSE_ERROR",
                                    "completed stage cannot contain a parse error"))
    return issues


def _effect_receipt(doc: object) -> list[Issue]:
    if not isinstance(doc, dict):
        return []
    issues = _owner_epoch(doc)
    reconcile = doc.get("reconcile")
    if doc.get("outcome") == "unknown" and isinstance(reconcile, dict) and reconcile.get("method") == "none":
        issues.append(Issue("/reconcile/method", "RECEIPT_RECONCILE",
                            "unknown effect outcome requires a reconciliation method"))
    precondition = doc.get("precondition")
    if isinstance(precondition, dict) and precondition.get("matched") is False and doc.get("outcome") != "failed":
        issues.append(Issue("/precondition/matched", "PRECONDITION_MISMATCH",
                            "a precondition that did not match requires outcome failed"))
    return issues


def _check_evidence(doc: object) -> list[Issue]:
    if not isinstance(doc, dict) or not isinstance(doc.get("procedure"), dict):
        return []
    procedure = doc["procedure"]
    command, manual = "cmd" in procedure, "procedure" in procedure
    if command == manual:
        return [Issue("/procedure", "EVIDENCE_CARRIER", "exactly one of cmd or procedure is required")]
    if command and ("exit" not in doc or "verdict" in doc):
        return [Issue("/procedure", "EVIDENCE_CARRIER", "command evidence requires exit without verdict")]
    if manual and ("verdict" not in doc or "observation" not in doc or "exit" in doc):
        return [Issue("/procedure", "EVIDENCE_CARRIER",
                      "manual evidence requires verdict and observation without exit")]
    return []


def _launch_plan(doc: object) -> list[Issue]:
    if not isinstance(doc, dict) or not isinstance(doc.get("stages"), list):
        return []
    issues = []
    for index, stage in enumerate(doc["stages"]):
        if not isinstance(stage, dict) or not isinstance(stage.get("env"), dict):
            continue
        for name, value in stage["env"].items():
            if not isinstance(value, str):
                escaped = name.replace("~", "~0").replace("/", "~1")
                issues.append(Issue(f"/stages/{index}/env/{escaped}", "type",
                                    "environment variable value must be a string"))
    return issues


SEMANTIC.update({
    "run-event": _run_event,
    "stage-result": _stage_result,
    "effect-receipt": _effect_receipt,
    "check-evidence": _check_evidence,
    "launch-plan": _launch_plan,
})


def _with(base: Callable[[object], list[Issue]], *extra: Callable[[dict], list[Issue]]):
    """Extend the checks of a kind with checks that only look at documents shaped as objects."""
    def check(doc: object) -> list[Issue]:
        issues = base(doc)
        if isinstance(doc, dict):
            for more in extra:
                issues.extend(more(doc))
        return issues
    return check


SEMANTIC["execution-input"] = _with(SEMANTIC["execution-input"], _condensed)
SEMANTIC["run-policy"] = _with(SEMANTIC["run-policy"], _fallback_declared)
SEMANTIC["capability-record"] = _with(SEMANTIC["capability-record"], _capability_freshness)
