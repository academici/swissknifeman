"""pathology — detectors workflow-pathologies by run-report (SCHEMA=2).

Login - dict run report `<project>/.claude/runs/<sid>.json`, who writes
harness-hook run-report (see packages/harness/configs/claude-code/hooks/run-report/_lib.py).
Exit `detect()` — flat list of finds:

    {code, severity: 'info'|'attention', metric, threshold, evidence, data}

'attention' — probable run pathology (is worth disassembling), 'info' — weak signal
(view during scheduled analysis). evidence — short Russian string with numbers,
data — raw values for machine processing.

CLEAN and PROTECTIVE function: without I/O and clock, same inputs → same output; exceptions
NEVER come out - a broken report section extinguishes only its detector, the rest
are being processed. Report SCHEMA=1 (without usage/reads/error_loops/retrieval/protected_writes)
degrades silently: detectors on missing slices simply do not work.

The thresholds below are HEURISTICS, selected according to common sense and the shape of the signals,
NOT field calibrated false-positive-rate (there was no real calibration;
it is only possible after accumulating field runs). Single source - change
only here, not with magic locally (pattern analyst/confidence.py).
"""

# ── detector thresholds (heuristics, NOT field calibrated FP-rate) ─────────
REREAD_MIN_TOTAL = 10          # file-reread: minimum readings so that the share is meaningful
REREAD_RATIO_MAX = 0.4         # file-reread: share of repeated reads (total−unique)/total
ERROR_LOOP_INFO_LEN = 3        # tool-error-loop: series of similar errors → info
ERROR_LOOP_ATTENTION_LEN = 5   # tool-error-loop: long series → attention (stuck)
NOOP_MIN_TOOLS = 20            # no-op-run: so many tool calls without a trace - already suspicious
CACHE_HIT_LOW = 0.4            # cache-miss: the proportion of cache reads in the input is lower - is the prefix unstable?
CACHE_MISS_MIN_TOKENS = 200_000  # cache-miss: for small volumes low hit — noise, not signal
OVERTHINKING_RATIO = 0.6       # overthinking: share thinking in the output haiku-agent
RETRIEVAL_IN_SHARE = 0.25      # retrieval-stuffing: retrieval-tokens (chars/4) as input share
RETRIEVAL_REPEATED_MIN = 2     # retrieval-stuffing: repeated requests → is no longer info, attention
STATIC_MIN_MSGS = 3            # static-context: minimum API-calls to the main agent for the middle
STATIC_WINDOW_SHARE = 0.7      # static-context: middle input as a share of the context window
STATIC_MAX_TOOLS = 15          # static-context: little work with heavy entry → context «hanging»
CONTEXT_WINDOW_TOKENS = 200_000  # max input proxy: standard window Sonnet/Opus
FANOUT_MIN_AGENTS = 8          # fanout: there are more subagents - but the output from the files is small
FANOUT_MAX_FILES = 5           # fanout: so many modified files do not justify the wide fan-out

# chars→tokens: rough estimate ~4 characters per token (for Latin; worse for Cyrillic,
# but retrieval-output is almost always in English - it is enough for the threshold heuristic).
CHARS_PER_TOKEN = 4


def _num(v):
    """Number from the report: only real ones int/float (bool — is not a number), otherwise 0 —
    debris in the field should not drop the detector's arithmetic."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _list(v):
    """List from the report; everything else (string/None/dict) → empty list."""
    return v if isinstance(v, list) else []


def _dget(d, *keys, default=None):
    """Protective access in depth dict'a: any non-dict/missing level → default."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _finding(code, severity, metric, threshold, evidence, data=None):
    """Uniform discovery form - so that consumers (maind analyze / analyst digest)
    didn't guess by the keys."""
    return {"code": code, "severity": severity, "metric": metric,
            "threshold": threshold, "evidence": evidence, "data": data or {}}


# ── detectors: each takes the entire report, returns a list of finds ───────────────

def _file_reread(r):
    """Files are read in a circle - the context is lost/is not held between steps."""
    total = _num(_dget(r, "reads", "total"))
    unique = _num(_dget(r, "reads", "unique"))
    if total < REREAD_MIN_TOTAL:
        return []
    ratio = (total - unique) / total
    if ratio <= REREAD_RATIO_MAX:
        return []
    tops = [f"{e.get('path')}×{e.get('count')}"
            for e in _list(_dget(r, "reads", "top_rereads"))[:3] if isinstance(e, dict)]
    return [_finding(
        "file-reread", "attention", ratio, REREAD_RATIO_MAX,
        f"re-reads: {int(total - unique)} from {int(total)} ({ratio:.0%});"
        f" top: {', '.join(tops) or '—'}",
        {"total": total, "unique": unique,
         "top_rereads": _list(_dget(r, "reads", "top_rereads"))[:5]})]


def _tool_error_loop(r):
    """Series of similar errors from one tool - retry without changing the approach."""
    out = []
    for loop in _list(r.get("error_loops")):
        if not isinstance(loop, dict):
            continue
        n = _num(loop.get("len"))
        if n < ERROR_LOOP_INFO_LEN:
            continue
        attention = n >= ERROR_LOOP_ATTENTION_LEN
        out.append(_finding(
            "tool-error-loop", "attention" if attention else "info",
            n, ERROR_LOOP_ATTENTION_LEN if attention else ERROR_LOOP_INFO_LEN,
            f"tool {loop.get('tool') or '?'}: {int(n)} errors of the same type in a row"
            f" — {str(loop.get('snippet') or '')[:80]}",
            {"tool": loop.get("tool"), "len": n, "snippet": loop.get("snippet")}))
    return out


def _no_op_run(r):
    """Many tool calls, but no trace: no files, no tests, no retrieval —
    run was spinning idle (or purely read-only reconnaissance - because only info)."""
    tools = _num(_dget(r, "tools", "total"))
    if (tools >= NOOP_MIN_TOOLS
            and not _list(r.get("files_changed"))
            and not _list(_dget(r, "bash", "tests"))
            and _num(_dget(r, "retrieval", "calls")) == 0):
        return [_finding(
            "no-op-run", "info", tools, NOOP_MIN_TOOLS,
            f"{int(tools)} tool calls without a trace: no files, no tests, no retrieval",
            {"tools_total": tools})]
    return []


def _no_verify(r):
    """Edits without verification: files have been changed, but there are no test runs; separately -
    dev-loop reported, but without keys verify/results (result slice lost)."""
    out = []
    changed = _list(r.get("files_changed"))
    tests = _list(_dget(r, "bash", "tests"))
    if changed and not tests:
        out.append(_finding(
            "no-verify", "attention", len(changed), 0,
            f"files modified: {len(changed)}, test runs: 0 - edits not checked",
            {"files_changed": len(changed)}))
    devloop = r.get("devloop")
    # we check the keys protectively: devloop maybe None/not-dict (SCHEMA=1 and degradation)
    if isinstance(devloop, dict) and devloop \
            and not devloop.get("verify") and not devloop.get("results"):
        out.append(_finding(
            "no-verify-devloop", "info", 0, 0,
            "dev-loop-there is a signal, but without verify/results — slice result not recorded",
            {"devloop_keys": sorted(devloop.keys())}))
    return out


def _cache_miss(r):
    """Low cache read ratio with large input - looks like an unstable prefix
    (jumping system prompt/context breaks prompt-cache and inflates the bill)."""
    hit = _dget(r, "usage", "cache_hit")
    if not isinstance(hit, (int, float)) or isinstance(hit, bool):
        return []
    t = _dget(r, "usage", "totals", default={})
    volume = _num(_dget(t, "in")) + _num(_dget(t, "cache_read")) + _num(_dget(t, "cache_creation"))
    if hit < CACHE_HIT_LOW and volume > CACHE_MISS_MIN_TOKENS:
        return [_finding(
            "cache-miss", "info", hit, CACHE_HIT_LOW,
            f"cache_hit {hit:.2f} at login {int(volume)} current - unstable prefix?",
            {"cache_hit": hit, "input_volume": volume})]
    return []


def _overthinking(r):
    """haiku-agents who have thinking dominates the text: cheap model
    forced «think» — probably the task is not for her range (routing models)."""
    hits = []
    for a in _list(_dget(r, "usage", "agents")):
        if not isinstance(a, dict):
            continue
        model = a.get("model")
        if not isinstance(model, str) or "haiku" not in model.lower():
            continue
        th, tx = _num(a.get("thinking_chars")), _num(a.get("text_chars"))
        if th + tx <= 0:
            continue
        ratio = th / (th + tx)
        if ratio > OVERTHINKING_RATIO:
            hits.append({"label": a.get("label"), "model": model, "ratio": round(ratio, 3)})
    if not hits:
        return []
    worst = max(h["ratio"] for h in hits)
    names = ", ".join(f"{h['label'] or '?'} {h['ratio']:.0%}" for h in hits[:3])
    return [_finding(
        "overthinking", "info", worst, OVERTHINKING_RATIO,
        f"haiku-agents with thinking>{OVERTHINKING_RATIO:.0%}: {len(hits)} ({names})",
        {"agents": hits})]


def _retrieval_stuffing(r):
    """Retrieval-output occupies a noticeable share of the input: raw materials are poured into the context instead
    synthesis; with repeated requests - they keep repeating the same thing in circles."""
    tin = _num(_dget(r, "usage", "totals", "in"))
    if tin <= 0:
        return []
    retr_tokens = _num(_dget(r, "retrieval", "result_chars")) / CHARS_PER_TOKEN
    share = retr_tokens / tin
    if share <= RETRIEVAL_IN_SHARE:
        return []
    repeated = len(_list(_dget(r, "retrieval", "repeated_queries")))
    attention = repeated >= RETRIEVAL_REPEATED_MIN
    tail = f", repeated requests: {repeated}" if attention else ""
    return [_finding(
        "retrieval-stuffing", "attention" if attention else "info",
        share, RETRIEVAL_IN_SHARE,
        f"retrieval ≈ {int(retr_tokens)} current = {share:.0%} login ({int(tin)}){tail}",
        {"retrieval_tokens": retr_tokens, "in": tin, "repeated_queries": repeated})]


def _protected_write(r):
    """Edits in managed-paths (vendor-skills/agent-pack) — they will be overwritten by the next one
    sync; always attention, regardless of volume."""
    pw = _list(r.get("protected_writes"))
    if not pw:
        return []
    shown = ", ".join(str(p) for p in pw[:3])
    return [_finding(
        "protected-write", "attention", len(pw), 0,
        f"edits managed-paths: {len(pw)} ({shown}) — will overwrite the next one sync",
        {"protected_writes": pw})]


def _static_context(r):
    """Resident context dominates: middle input of one API-calling the main agent
    is close to the context window, and useful work (tool calls) little - context «hanging»
    ballast (fat skill buckets/MCP-output).

    Proxy, not the exact formula: they appear in the spec totals, but totals mix input
    subagents with msgs chief agent - we consider it more honest (in+cache_read)/msgs HIMSELF
    main agent, and «maximum» take as a standard window CONTEXT_WINDOW_TOKENS."""
    agents = _list(_dget(r, "usage", "agents"))
    main = next((a for a in agents if isinstance(a, dict) and a.get("label") == "main"), None)
    if main is None:
        main = agents[0] if agents and isinstance(agents[0], dict) else None
    if main is None:
        return []
    msgs = _num(main.get("msgs"))
    if msgs < STATIC_MIN_MSGS:
        return []
    avg_in = (_num(main.get("in")) + _num(main.get("cache_read"))) / msgs
    share = avg_in / CONTEXT_WINDOW_TOKENS
    tools = _num(_dget(r, "tools", "total"))
    if share > STATIC_WINDOW_SHARE and tools < STATIC_MAX_TOOLS:
        return [_finding(
            "static-context", "info", share, STATIC_WINDOW_SHARE,
            f"middle input {int(avg_in)} current/call ≈ {share:.0%} windows when {int(tools)}"
            f" tool calls - resident context dominates; audit of buckets/MCP: skiller budget",
            {"avg_in": avg_in, "msgs": msgs, "tools_total": tools,
             "window": CONTEXT_WINDOW_TOKENS})]
    return []


def _fanout(r):
    """Wide fan-out subagents with modest output from files - orchestration
    more expensive than the result (each subagent pays for his entry again)."""
    n_agents = len(_list(_dget(r, "usage", "agents")))
    n_files = len(_list(r.get("files_changed")))
    if n_agents > FANOUT_MIN_AGENTS and n_files < FANOUT_MAX_FILES:
        return [_finding(
            "fanout", "info", n_agents, FANOUT_MIN_AGENTS,
            f"agents: {n_agents} when {n_files} modified files - fan-out more expensive than exhaust",
            {"agents": n_agents, "files_changed": n_files})]
    return []


_DETECTORS = (_file_reread, _tool_error_loop, _no_op_run, _no_verify, _cache_miss,
              _overthinking, _retrieval_stuffing, _protected_write, _static_context,
              _fanout)


def detect(run_report):
    """Run all detectors by run-report → list of finds (may be empty).

    Never throws: non-dict input → []; exception inside detector (broken slice)
    is extinguished and only HIS finds are dropped - the rest of the detectors are processed."""
    if not isinstance(run_report, dict):
        return []
    findings = []
    for det in _DETECTORS:
        try:
            findings.extend(det(run_report))
        except Exception:
            continue  # protective contract: see docstring
    return findings
