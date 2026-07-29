#!/usr/bin/env python3
"""run_live_bank.py — sole executable owner of the P3.9 live-dispatch harness
(plans/2026.07.24-AGENT-RELIABILITY).

It is a MEASURING INSTRUMENT, and an instrument that cannot show "not measured" is
useless and dangerous (Code Guidance). Three modes, one map:

  --measure-observability   pure function of (cases.json, event-mapping-v1.json):
                            for every assertion of every case decide whether its
                            event type / outcome path HAS a source in the closed
                            D83 list. A case with at least one sourceless assertion
                            is `unmappable` and is NOT graded at all — in particular
                            its `event_absent` / `outcome_list_excludes` assertions
                            are never counted (D83: 20 of the bank's 88 assertions
                            are negative and pass trivially wherever the instrument
                            sees nothing).
  --dispatch                one live headless dispatch inside an already-created
                            disposable worktree, routed axes pinned by FLAG (D46);
                            writes the sanitized raw fixture BEFORE any normalization.
  --replay                  normalize a recorded raw fixture into a typed transcript
                            + outcome record; byte-identical to the live path over
                            the same raw, because normalization reads only the raw
                            and the map.

`event-mapping-v1.json` is the SOLE carrier of "bank event type -> observation
source"; no pair is hard-coded here. A type the map does not cover is `unmappable`,
never guessed (D83, P3.9 Code Guidance).

stdlib-only, plan-scoped. Imports of packages are one-way and lazy (`analyst.trace`
only in --dispatch, to read what a dispatch produced); nothing imports this file.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCHEMA_DECLARED_SET = "p3.9-declared-case-set/v1"
SCHEMA_RAW = "p3.9-sanitized-raw/v1"
SCHEMA_NORM = "p3.9-normalized-transcript/v1"

WT_TOKEN = "<WT>"
HOST_BOUND_TOKEN = "<host-bound-erased>"
PATH_KEYS = ("file_path", "path", "notebook_path", "pattern")
DISPATCH_TIMEOUT_S = 900

# The three verdict-derived events, emitted in this fixed order per observed
# `pre_mutation` verdict (`event-mapping-v1.json::normalization.emit_order`).
VERDICT_EVENT_ORDER = ("contract_compiled", "pre_mutation_check", "portability_check")


# --------------------------------------------------------------------------- #
# small io helpers
# --------------------------------------------------------------------------- #
def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json_text(data):
    """Canonical byte-stable serialization — the only writer used for every
    artifact this script produces, so "run it twice" is a real determinism test."""
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(dump_json_text(data), encoding="utf-8")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def die(message):
    print(f"run_live_bank: {message}", file=sys.stderr)
    return 2


# --------------------------------------------------------------------------- #
# the map, indexed
# --------------------------------------------------------------------------- #
class Mapping:
    """Indexed view over `event-mapping-v1.json`. Every lookup that misses returns
    an `unmappable` verdict with a reason — never a default, never a guess."""

    def __init__(self, doc):
        self.doc = doc
        self.version = doc["mapping_version"]
        self.events = {e["type"]: e for e in doc["events"]}
        self.outcome = {o["path"]: o for o in doc["outcome_fields"]}
        self.declared_codes = tuple(doc["reason_code_channel"]["declared_codes"])
        self.predicate_verdicts = tuple(doc["reason_code_channel"]["predicate_verdicts"])

    def _domain(self, ref):
        if ref == "reason_code_channel.declared_codes":
            return self.declared_codes
        raise ValueError(f"unknown value_domain reference {ref!r}")

    def event_spec(self, event_type):
        return self.events.get(event_type)

    def check_event(self, event_type, where):
        """→ (mappable: bool, reason: str|None) for one asserted event reference."""
        spec = self.events.get(event_type)
        if spec is None:
            return False, f"event type {event_type!r} is not covered by the map"
        if spec["status"] != "mappable":
            return False, spec.get("reason", "declared unmappable by the map")
        observable = set(spec.get("observable_fields") or ())
        for key, value in (where or {}).items():
            if key not in observable:
                return False, (f"field {event_type}.{key!r} has no source "
                               f"(observable: {sorted(observable) or 'none'})")
            domain_ref = (spec.get("value_domain") or {}).get(key)
            if domain_ref is not None and value not in self._domain(domain_ref):
                return False, (f"{event_type}.{key} = {value!r} is outside "
                               f"{domain_ref} — no artifact can carry a code that "
                               f"exists in no module")
        return True, None

    def check_outcome(self, path, value=None, has_value=False):
        spec = self.outcome.get(path)
        if spec is None:
            return False, f"outcome path {path!r} is not covered by the map"
        if spec["status"] != "mappable":
            return False, spec.get("reason", "declared unmappable by the map")
        if has_value and spec.get("unmappable_value_domain") and isinstance(value, str) \
                and value.startswith("/"):
            return False, (f"outcome.{path} literal {value!r} is an absolute host-bound "
                           f"path — erased by the F8 privacy sanitizer before recording, "
                           f"so it can never be observed")
        return True, None


# --------------------------------------------------------------------------- #
# mode 1 — observability measurement (pure over cases + map)
# --------------------------------------------------------------------------- #
GRADER_OPERATORS = {
    "G-EVENT-PRESENT": "event_present",
    "G-EVENT-ABSENT": "event_absent",
    "G-EVENT-ORDER": "event_order",
    "G-EVENT-COUNT-MAX": "event_count_max",
    "G-EVENT-COUNT-MIN": "event_count_min",
    "G-OUTCOME-FIELD": "outcome_field_equals",
    "G-OUTCOME-CONTAINS": "outcome_list_contains",
    "G-OUTCOME-EXCLUDES": "outcome_list_excludes",
}


def assertion_mappability(assertion, mapping, graders_by_id=None):
    """→ (operator, mappable, reason). The operator is resolved from the grader id
    through the bank's own graders document when supplied, and through the frozen
    id→operator table above otherwise — never re-invented per assertion."""
    gid = assertion.get("grader")
    if graders_by_id and gid in graders_by_id:
        operator = graders_by_id[gid]["operator"]
    else:
        operator = GRADER_OPERATORS.get(gid)
    args = assertion.get("args") or {}
    if operator is None:
        return None, False, f"unknown grader {gid!r}"
    if operator == "event_order":
        for side in ("before", "after"):
            spec = args.get(side) or {}
            ok, reason = mapping.check_event(spec.get("type"), spec.get("where"))
            if not ok:
                return operator, False, f"{side}: {reason}"
        return operator, True, None
    if operator.startswith("event_"):
        ok, reason = mapping.check_event(args.get("type"), args.get("where"))
        return operator, ok, reason
    if operator.startswith("outcome_"):
        ok, reason = mapping.check_outcome(args.get("path"), args.get("value"),
                                           has_value="value" in args)
        return operator, ok, reason
    return operator, False, f"operator {operator!r} is outside the frozen eight"


def measure_observability(cases_doc, mapping, graders_doc=None):
    graders_by_id = {g["id"]: g for g in (graders_doc or {}).get("graders", [])}
    cases_out, mappable_ids = [], []
    total_assertions = mappable_assertions = 0
    for case in cases_doc["cases"]:
        rows = []
        for assertion in case.get("assertions") or []:
            operator, ok, reason = assertion_mappability(assertion, mapping, graders_by_id)
            total_assertions += 1
            mappable_assertions += 1 if ok else 0
            rows.append({"id": assertion.get("id"), "grader": assertion.get("grader"),
                         "operator": operator, "mappable": ok,
                         "reason": None if ok else reason})
        case_mappable = bool(rows) and all(r["mappable"] for r in rows)
        if case_mappable:
            mappable_ids.append(case["case_id"])
        cases_out.append({
            "case_id": case["case_id"], "kind": case["kind"], "family": case["family"],
            "mappable": case_mappable,
            "unmappable_assertions": [r["id"] for r in rows if not r["mappable"]],
            "reasons": sorted({r["reason"] for r in rows if r["reason"]}),
            "assertions": rows,
        })
    cases = cases_doc["cases"]
    return {
        "schema_version": SCHEMA_DECLARED_SET,
        "owner": "plans/2026.07.24-AGENT-RELIABILITY P3.9",
        "note": ("The DECLARED case set for layer-2 (D51): declared as a literal BEFORE any "
                 "live paired run, so P3.10 cannot pick a denominator after the fact. A case "
                 "is included only if EVERY one of its assertions has a source in the closed "
                 "D83 list; a case with one sourceless assertion is excluded WHOLE — its "
                 "negative assertions are never counted (D83)."),
        "mapping_version": mapping.version,
        "bank_version": cases_doc.get("bank_version"),
        "counts": {
            "cases": len(cases),
            "critical": sum(1 for c in cases if c["kind"] == "critical"),
            "control": sum(1 for c in cases if c["kind"] == "control"),
            "mappable": len(mappable_ids),
            "unmappable": len(cases) - len(mappable_ids),
            "assertions": total_assertions,
            "mappable_assertions": mappable_assertions,
            "mappable_critical": sum(1 for c in cases_out
                                     if c["mappable"] and c["kind"] == "critical"),
            "mappable_control": sum(1 for c in cases_out
                                    if c["mappable"] and c["kind"] == "control"),
        },
        "declared_case_set": sorted(mappable_ids),
        "excluded_case_set": sorted(c["case_id"] for c in cases_out if not c["mappable"]),
        "cases": cases_out,
    }


def cmd_measure(args):
    cases_doc = load_json(args.cases)
    mapping = Mapping(load_json(args.mapping))
    graders_doc = load_json(args.graders) if args.graders else None
    report = measure_observability(cases_doc, mapping, graders_doc)
    report["inputs"] = {
        "cases": {"path": str(args.cases), "sha256": sha256_file(args.cases)},
        "mapping": {"path": str(args.mapping), "sha256": sha256_file(args.mapping)},
    }
    if args.graders:
        report["inputs"]["graders"] = {"path": str(args.graders),
                                       "sha256": sha256_file(args.graders)}
    write_json(args.out, report)
    counts = report["counts"]
    print(f"{counts['mappable']}/{counts['cases']} mappable "
          f"({counts['mappable_critical']} critical + {counts['mappable_control']} control); "
          f"assertions {counts['mappable_assertions']}/{counts['assertions']}")
    print("declared_case_set:")
    for cid in report["declared_case_set"]:
        print(f"  + {cid}")
    print("unmappable:")
    for case in report["cases"]:
        if case["mappable"]:
            continue
        print(f"  - {case['case_id']} [{', '.join(case['unmappable_assertions'])}]: "
              f"{case['reasons'][0] if case['reasons'] else 'no reason recorded'}")
    return 0


# --------------------------------------------------------------------------- #
# sanitizer — privacy/minimization, runs BEFORE normalization
# --------------------------------------------------------------------------- #
def sanitize_path(value, worktree):
    """Worktree-relative or erased. A path outside the dispatch worktree cannot be
    made worktree-relative, so it is ERASED rather than committed (lesson F8) — the
    map records this as the reason an assertion naming an absolute literal has no
    source."""
    if not isinstance(value, str):
        return value
    root = str(worktree)
    if value == root:
        return "."
    if value.startswith(root + "/"):
        return value[len(root) + 1:]
    if value.startswith("/"):
        return HOST_BOUND_TOKEN
    return value


def scan_literals(text, mapping):
    """The closed reason-code channel: the ONLY thing kept from a tool_result."""
    codes = sorted({c for c in mapping.declared_codes if c in text})
    verdicts = []
    for name in mapping.predicate_verdicts:
        for quote in ("'", '"'):
            marker = f"{quote}{name}{quote}"
            start = 0
            while True:
                idx = text.find(marker, start)
                if idx < 0:
                    break
                start = idx + len(marker)
                tail = text[start:start + 80]
                value = None
                for candidate in ("allow", "n/a"):
                    if f"{quote}{candidate}{quote}" in tail.split(",")[0]:
                        value = candidate
                for code in mapping.declared_codes:
                    if f"block:{code}" in tail:
                        value = f"block:{code}"
                if value is not None:
                    verdicts.append({"name": name, "value": value})
    # deterministic, de-duplicated
    seen, out = set(), []
    for v in verdicts:
        key = (v["name"], v["value"])
        if key not in seen:
            seen.add(key)
            out.append(v)
    return codes, out


def _block_text(block):
    """Concatenate the textual payload of one content block WITHOUT storing it —
    used only to feed `scan_literals`, never written anywhere."""
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        return "\n".join(_block_text(v) for v in block.values())
    if isinstance(block, list):
        return "\n".join(_block_text(v) for v in block)
    return ""


def sanitize_stream(lines, worktree, mapping):
    """Provider stream -> sanitized raw events. Model prose (`text`/`thinking`) is
    dropped ENTIRELY, which makes "grep the final text" structurally impossible
    rather than merely forbidden (map § forbidden_sources)."""
    events, index = [], 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            events.append({"i": index, "kind": "unparsable_line"})
            index += 1
            continue
        kind = obj.get("type")
        if kind == "system" and obj.get("subtype") == "init":
            events.append({"i": index, "kind": "system_init",
                           "model": obj.get("model"),
                           "permission_mode": obj.get("permissionMode"),
                           "tools_count": len(obj.get("tools") or []),
                           "mcp_servers_count": len(obj.get("mcp_servers") or [])})
            index += 1
        elif kind in ("assistant", "user"):
            for block in (obj.get("message") or {}).get("content") or []:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    raw_input = block.get("input") or {}
                    paths = [sanitize_path(raw_input[k], worktree)
                             for k in PATH_KEYS if isinstance(raw_input.get(k), str)]
                    events.append({"i": index, "kind": "tool_use",
                                   "name": block.get("name"),
                                   "input_paths": paths,
                                   "input_keys": sorted(raw_input)})
                    index += 1
                elif btype == "tool_result":
                    text = _block_text(block.get("content"))
                    codes, verdicts = scan_literals(text, mapping)
                    events.append({"i": index, "kind": "tool_result",
                                   "is_error": bool(block.get("is_error")),
                                   "reason_codes": codes,
                                   "predicate_verdicts": verdicts})
                    index += 1
                # `text` / `thinking` blocks: dropped, never recorded
        elif kind == "result":
            usage = obj.get("usage") or {}
            events.append({"i": index, "kind": "result",
                           "subtype": obj.get("subtype"),
                           "is_error": bool(obj.get("is_error")),
                           "num_turns": obj.get("num_turns"),
                           "session_id": obj.get("session_id"),
                           "permission_denials": len(obj.get("permission_denials") or []),
                           "total_cost_usd": obj.get("total_cost_usd"),
                           "usage": {k: usage.get(k) for k in
                                     ("input_tokens", "cache_creation_input_tokens",
                                      "cache_read_input_tokens", "output_tokens")}})
            index += 1
    return events


def assert_no_host_paths(payload):
    text = dump_json_text(payload)
    if "/home/" in text or "/Users/" in text:
        raise RuntimeError("sanitizer failed: a host-bound absolute path survived into "
                           "the fixture (lesson F8) — refusing to write")


# --------------------------------------------------------------------------- #
# mode 2 — live dispatch (fixture producer only, <= 3 per this item)
# --------------------------------------------------------------------------- #
def git(repo, *cmd, check=True):
    result = subprocess.run(["git", "-C", str(repo), *cmd], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(cmd)} failed: {result.stderr.strip()}")
    return result.stdout


def read_lines(path):
    p = Path(path)
    return p.read_text(encoding="utf-8").splitlines() if p.is_file() else []


def cmd_dispatch(args):
    if not args.model or not args.effort:
        return die("--model and --effort are REQUIRED: a routed axis that cannot be "
                   "pinned by flag makes the dispatch fail-closed (D46), never a run "
                   "on the session default")
    worktree = Path(args.repo).resolve()
    mapping = Mapping(load_json(args.mapping))
    base_sha = git(worktree, "rev-parse", "HEAD").strip()
    if git(worktree, "status", "--porcelain").strip():
        return die(f"dispatch worktree is not clean at {base_sha}")

    journal_path = worktree / args.journal if args.journal else None
    journal_before = len(read_lines(journal_path)) if journal_path else 0

    cmd = ["claude", "-p", args.prompt, "--model", args.model, "--effort", args.effort,
           "--output-format", "stream-json", "--verbose",
           "--permission-mode", "bypassPermissions"]
    try:
        proc = subprocess.run(cmd, cwd=str(worktree), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=DISPATCH_TIMEOUT_S)
        stdout, returncode = proc.stdout, proc.returncode
        stderr_class = "none" if not proc.stderr.strip() else "non-empty"
    except subprocess.TimeoutExpired:
        stdout, returncode, stderr_class = "", -1, "timeout"

    events = sanitize_stream(stdout.splitlines(), worktree, mapping)

    tracked = [p for p in git(worktree, "diff", "--name-only", base_sha).splitlines() if p]
    untracked = [p for p in git(worktree, "ls-files", "--others",
                                "--exclude-standard").splitlines() if p]
    changed = sorted(set(tracked) | set(untracked))

    journal_delta = []
    if journal_path:
        for line in read_lines(journal_path)[journal_before:]:
            try:
                journal_delta.append(json.loads(line))
            except json.JSONDecodeError:
                journal_delta.append({"unparsable": True})

    traces = []
    if args.traces:
        traces_path = worktree / args.traces
        if traces_path.is_file():
            payload = load_json(traces_path)
            traces = payload if isinstance(payload, list) else payload.get("records") or []

    out_dir = Path(args.out_dir)
    fixture = {
        "stream.json": {"schema_version": SCHEMA_RAW, "stage": "sanitized-raw",
                        "worktree_token": WT_TOKEN, "events": events},
        "git.json": {"schema_version": SCHEMA_RAW, "base_sha": base_sha,
                     "changed_paths": changed},
        "journal-delta.json": {"schema_version": SCHEMA_RAW, "entries": journal_delta},
        "traces.json": {"schema_version": SCHEMA_RAW, "records": traces},
        "meta.json": {"schema_version": SCHEMA_RAW,
                      "provider": "claude-code",
                      "route": {"model_class": args.model_class, "effort": args.effort,
                                "model": args.model, "source": "cli-flag"},
                      "cli_flags": ["--model", args.model, "--effort", args.effort,
                                    "--output-format", "stream-json", "--verbose",
                                    "--permission-mode", "bypassPermissions"],
                      "returncode": returncode, "stderr_class": stderr_class,
                      "base_sha": base_sha, "prompt_sha256":
                          hashlib.sha256(args.prompt.encode("utf-8")).hexdigest()},
    }
    for payload in fixture.values():
        assert_no_host_paths(payload)
    for name, payload in fixture.items():
        write_json(out_dir / name, payload)
    print(json.dumps({"returncode": returncode, "events": len(events),
                      "changed_paths": len(changed), "journal_delta": len(journal_delta),
                      "traces": len(traces)}))
    return 0


# --------------------------------------------------------------------------- #
# mode 3 — normalization / replay
# --------------------------------------------------------------------------- #
def _tool_names(mapping, event_type):
    spec = mapping.event_spec(event_type) or {}
    return tuple((spec.get("rule") or {}).get("tools") or ())


def _enabled(mapping, event_type):
    spec = mapping.event_spec(event_type)
    return bool(spec) and spec["status"] == "mappable"


def normalize(fixture_dir, mapping):
    """Recorded raw + map -> typed transcript + outcome. Pure: no clock, no host
    paths, no randomness — the byte-for-byte property `--replay` is validated on."""
    fixture_dir = Path(fixture_dir)
    stream = load_json(fixture_dir / "stream.json")
    git_state = load_json(fixture_dir / "git.json")
    journal = load_json(fixture_dir / "journal-delta.json")
    traces = load_json(fixture_dir / "traces.json")

    transcript, reads = [], []
    read_tools = _tool_names(mapping, "read")
    result_event = None
    saw_block = False

    # (1) stream-derived, in stream order
    for event in stream["events"]:
        if event["kind"] == "tool_use" and _enabled(mapping, "read"):
            if event.get("name") in read_tools:
                for path in event.get("input_paths") or []:
                    transcript.append({"type": "read", "target": path,
                                       "source": "stream-json"})
                    reads.append(path)
        elif event["kind"] == "tool_result":
            # One `block` per DISTINCT code per tool_result: a `block:<CODE>` verdict
            # always repeats a literal the code scan already found, so emitting both
            # would double-count the same observation.
            codes = list(event.get("reason_codes") or [])
            for verdict in event.get("predicate_verdicts") or []:
                value = verdict.get("value") or ""
                if value.startswith("block:"):
                    code = value[len("block:"):]
                    if code not in codes:
                        codes.append(code)
            if _enabled(mapping, "block"):
                for code in codes:
                    transcript.append({"type": "block", "reason_code": code,
                                       "source": "reason-code"})
                    saw_block = True
            for verdict in event.get("predicate_verdicts") or []:
                if verdict["name"] != "pre_mutation":
                    continue
                for etype in VERDICT_EVENT_ORDER:
                    if _enabled(mapping, etype):
                        transcript.append({"type": etype, "source": "reason-code"})
        elif event["kind"] == "result":
            result_event = event

    # (2) git-state-derived, sorted by path
    for path in sorted(git_state.get("changed_paths") or []):
        if _enabled(mapping, "mutation"):
            transcript.append({"type": "mutation", "target": path, "source": "git-state"})
        if _enabled(mapping, "handoff_emitted") and Path(path).name == "handoff.md":
            transcript.append({"type": "handoff_emitted", "source": "git-state"})

    # (3) journal-delta-derived, in file order
    if _enabled(mapping, "route_declared"):
        undershoot = any(e.get("type") == "block" and e.get("reason_code") == "ROUTE_UNDERSHOOT"
                         for e in transcript)
        for entry in journal.get("entries") or []:
            if entry.get("actor"):
                transcript.append({"type": "route_declared", "actor": entry["actor"],
                                   "undershoot": undershoot, "source": "journal-delta"})

    # (4) trace-derived, sorted by trace_id
    if _enabled(mapping, "trace_emitted"):
        for record in sorted(traces.get("records") or [],
                             key=lambda r: r.get("trace_id") or ""):
            missing = ((record.get("quality") or {}).get("missing")) or []
            transcript.append({"type": "trace_emitted",
                               "required_fields_complete": missing == [],
                               "completeness": (record.get("quality") or {}).get("completeness"),
                               "source": "trace-record"})

    # (5) final_response, always last
    if result_event is not None and _enabled(mapping, "final_response"):
        transcript.append({"type": "final_response", "source": "stream-json"})

    for seq, event in enumerate(transcript, start=1):
        event["seq"] = seq

    outcome, provenance = {}, {}
    if mapping.check_outcome("declared_status")[0]:
        if result_event is None:
            status = "failed"
            detail = "no terminal result object in the recorded stream"
        elif result_event.get("is_error"):
            status, detail = "failed", "result.is_error"
        elif saw_block:
            status, detail = "blocked", "a block event was observed"
        else:
            status, detail = "success", "result.is_error == false and no block observed"
        outcome["declared_status"] = status
        provenance["declared_status"] = {"source": "stream-json", "derivation": detail}
    if mapping.check_outcome("execution_inputs")[0]:
        outcome["execution_inputs"] = sorted(set(reads))
        provenance["execution_inputs"] = {"source": "stream-json",
                                          "derivation": "sorted unique `read` targets"}

    unobserved = {}
    for path, spec in sorted(mapping.outcome.items()):
        if path in outcome:
            continue
        unobserved[path] = {"value": None,
                            "reason": spec.get("reason", "declared unmappable by the map")}

    return {
        "schema_version": SCHEMA_NORM,
        "mapping_version": mapping.version,
        "fixture": fixture_dir.name,
        "base_sha": git_state.get("base_sha"),
        "transcript": transcript,
        "outcome": outcome,
        "outcome_provenance": provenance,
        "outcome_unobserved": unobserved,
        "observed_event_types": sorted({e["type"] for e in transcript}),
    }


def cmd_replay(args):
    mapping = Mapping(load_json(args.mapping))
    normalized = normalize(args.replay, mapping)
    write_json(args.out, normalized)
    observed = set(normalized["observed_event_types"])
    print(json.dumps({"events": len(normalized["transcript"]),
                      "observed_event_types": sorted(observed)}))
    failures = []
    for expected in args.expect_present or []:
        if expected not in observed:
            failures.append(f"expected present but ABSENT: {expected}")
    for expected in args.expect_absent or []:
        if expected in observed:
            failures.append(f"expected absent but PRESENT: {expected}")
    for failure in failures:
        print(f"run_live_bank: {failure}", file=sys.stderr)
    return 1 if failures else 0


# --------------------------------------------------------------------------- #
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure-observability", action="store_true")
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--replay")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--out")
    parser.add_argument("--cases")
    parser.add_argument("--graders")
    parser.add_argument("--repo")
    parser.add_argument("--prompt")
    parser.add_argument("--out-dir")
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--model-class", default="frontier")
    parser.add_argument("--journal")
    parser.add_argument("--traces")
    parser.add_argument("--expect-present", action="append")
    parser.add_argument("--expect-absent", action="append")
    args = parser.parse_args(argv)

    modes = [bool(args.measure_observability), bool(args.dispatch), bool(args.replay)]
    if sum(modes) != 1:
        return die("exactly one of --measure-observability / --dispatch / --replay")
    if args.measure_observability:
        if not (args.cases and args.out):
            return die("--measure-observability requires --cases and --out")
        return cmd_measure(args)
    if args.dispatch:
        if not (args.repo and args.prompt and args.out_dir):
            return die("--dispatch requires --repo, --prompt and --out-dir")
        return cmd_dispatch(args)
    if not args.out:
        return die("--replay requires --out")
    return cmd_replay(args)


if __name__ == "__main__":
    sys.exit(main())
