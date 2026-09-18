"""Internal documentation."""
import json
import re
from pathlib import Path

SCHEMA = 2





try:
    import _usage
except Exception:
    _usage = None



TEST_PAT = re.compile(
    r"(?:\bpytest\b|\bphpunit\b|vendor/bin/pest|\bpest\b|\bjest\b|\bvitest\b|"
    r"go\s+test|cargo\s+test|npm\s+(?:run\s+)?test|yarn\s+test|pnpm\s+test|"
    r"\bunittest\b|validate\.sh|(?<![\w/])test\.sh)", re.I)
LINT_PAT = re.compile(
    r"(?:\bruff\b|\bflake8\b|\bpylint\b|\bmypy\b|\beslint\b|vendor/bin/pint|"
    r"\bphpstan\b|\bpsalm\b|(?<![\w/])pint\b|\bblack\b|\bisort\b|(?<![\w/])tsc\b|"
    r"\bprettier\b|py_compile)", re.I)



DEVLOOP_KEYS = ("tool_failures", "workarounds", "deferred", "open_questions",
                "results", "verify")

_MAX_FAILURES = 25
_MAX_FILES = 200
_MAX_WORKFLOWS = 20
_WF_RELAUNCH_MIN = 3
_MAX_READS = 500
_MAX_ERROR_LOOPS = 20
_MAX_RETRIEVAL_QUERIES = 20
_MAX_SUBAGENTS = 50



_RETRIEVAL_TAIL_PAT = re.compile(r"^(search|query-docs|resolve-library-id)", re.I)


def similar_ratio(a, b):
    """Internal documentation."""
    if _usage is not None:
        return _usage.similar_ratio(a, b)

    def toks(s):
        return {w for w in str(s or "").lower().split() if len(w) >= 2}

    ta, tb = toks(a), toks(b)
    union = ta | tb
    return (len(ta & tb) / len(union)) if union else 0.0


def _retrieval_tool(name):
    """Internal documentation."""
    if not isinstance(name, str):
        return None
    if name in ("WebFetch", "WebSearch"):
        return name
    if not name.startswith("mcp__"):
        return None
    tail = name.rsplit("__", 1)[-1]
    server = name[len("mcp__"):-(len(tail) + 2)]
    if _RETRIEVAL_TAIL_PAT.match(tail) or "perplexity" in server.lower() or "context7" in server.lower():
        return name
    return None


def _retrieval_query(inp):
    """Internal documentation."""
    if not isinstance(inp, dict):
        return None
    for k in ("query", "q", "url", "libraryName", "topic", "prompt"):
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _sidecar_dir(transcript_path):
    """Internal documentation."""
    if not transcript_path:
        return None
    try:
        p = Path(transcript_path)
    except Exception:
        return None
    return p.parent / p.stem / "subagents"


def _collect_usage(main_acc, transcript_path):
    """Internal documentation."""
    if _usage is None or main_acc is None:
        return None
    agents = [_usage.finish(main_acc, label="main")]
    parsed = skipped = 0
    sdir = _sidecar_dir(transcript_path)
    files = []
    if sdir is not None:
        try:
            if sdir.is_dir():
                files = sorted(sdir.glob("agent-*.jsonl"))[:_MAX_SUBAGENTS]
        except Exception:
            files = []
    for f in files:
        try:
            acc = _usage.new_acc()
            for ev in _usage.iter_jsonl(f):
                _usage.feed_event(acc, ev)
            agents.append(_usage.finish(acc, label=f.stem))
            parsed += 1
        except Exception:
            skipped += 1
    summary = _usage.merge(agents)
    main = agents[0]
    return {
        "totals": summary["totals"],
        "by_model": summary["by_model"],
        "cache_hit": summary["cache_hit"],
        "agents": agents,
        "subagents_parsed": parsed,
        "subagents_skipped": skipped,


        "first_turn_overhead": main.get("first_turn_overhead"),
        "turns": main.get("msgs"),
    }


def _protected_sets(cwd):
    """Internal documentation."""
    dirs, files = set(), set()
    if not cwd:
        return dirs, files
    base = Path(cwd)
    try:
        lock = json.loads((base / "skills-lock.json").read_text(encoding="utf-8"))
        skills = lock.get("skills") if isinstance(lock, dict) else None
        if isinstance(skills, dict):
            for entry in skills.values():
                if isinstance(entry, dict) and entry.get("managed") and entry.get("installed_path"):
                    dirs.add(str(base / entry["installed_path"]))
    except Exception:
        pass
    try:
        lock = json.loads((base / ".claude" / "agent-pack.lock.json").read_text(encoding="utf-8"))
        packs = lock.get("packs") if isinstance(lock, dict) else None
        if isinstance(packs, dict):
            for pack in packs.values():
                if not isinstance(pack, dict):
                    continue
                for f in pack.get("files") or []:
                    if isinstance(f, dict) and f.get("target") and not f.get("user_owned"):
                        files.add(str(base / f["target"]))
    except Exception:
        pass
    return dirs, files


def _is_protected(fp, dirs, files):
    if fp in files:
        return True
    return any(fp == d or fp.startswith(d + "/") for d in dirs)


def _snippet(val, n=240):
    """Internal documentation."""
    try:
        s = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
    except Exception:
        s = str(val)
    return " ".join(s.split())[:n]


def _blocks(event):
    """Internal documentation."""
    msg = event.get("message")
    if isinstance(msg, dict):
        c = msg.get("content")
        if isinstance(c, list):
            return c
    return []


def _result_text(content):
    """Internal documentation."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                parts.append(b.get("text") or b.get("content") or "")
            elif isinstance(b, str):
                parts.append(b)
        return " ".join(p for p in parts if p)
    if isinstance(content, dict):
        return content.get("text") or ""
    return ""


def _maind_tool(name):
    """Internal documentation."""
    if not isinstance(name, str):
        return None
    tail = name.rsplit("__", 1)[-1]
    if tail.startswith("maind_memory_"):
        return "memory_" + tail[len("maind_memory_"):]
    if tail.startswith("maind_graph_"):
        return "graph_" + tail[len("maind_graph_"):]
    return None


_SYMBOL_TOOLS = frozenset({
    "find_symbol", "find_referencing_symbols", "get_symbols_overview",
    "find_implementations", "find_declaration", "replace_symbol_body",
    "insert_after_symbol", "insert_before_symbol", "rename_symbol",
    "safe_delete_symbol", "replace_content", "replace_in_files",
    "get_diagnostics_for_file",
})
_CODEGRAPH_SERVERS = (
    "codegraph", "serena", "plugin_core_codegraph", "plugin-core-codegraph",
    "laravel-boost", "laravel_boost",
)


def _codegraph_server_match(server):
    norm = server.lower().replace("-", "_")
    return any(marker.replace("-", "_") in norm for marker in _CODEGRAPH_SERVERS)


def _codegraph_tool(name):
    """Symbol-tool op id for codegraph/Serena/laravel-boost MCP names."""
    if not isinstance(name, str) or not name:
        return None
    if name in _SYMBOL_TOOLS:
        return name
    low = name.lower()
    if low in _SYMBOL_TOOLS:
        return low
    if low.startswith("mcp:"):
        parts = name.split(":", 2)
        if len(parts) >= 3 and _codegraph_server_match(parts[1]):
            return parts[2]
        return None
    if not name.startswith("mcp__"):
        return None
    tail = name.rsplit("__", 1)[-1]
    server = name[len("mcp__"):-(len(tail) + 2)]
    if _codegraph_server_match(server):
        return tail
    return None


def _maind_result_count(result_text):
    """Internal documentation."""
    text = (result_text or "").strip()
    if not text or ("{" not in text and "[" not in text):
        return None
    try:
        obj = json.loads(text)
    except Exception:
        return None
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        if isinstance(obj.get("count"), int):
            return obj["count"]
        for k in ("neighbors", "nodes"):
            if isinstance(obj.get(k), list):
                return len(obj[k])
        if "path" in obj:
            p = obj.get("path")
            return len(p) if isinstance(p, list) else 0
    return None


def _find_json_with_keys(text, keys):
    """Internal documentation."""
    if not isinstance(text, str) or "{" not in text:
        return None
    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except Exception:
                        break
                    if isinstance(obj, dict) and any(k in obj for k in keys):
                        return obj
                    break

    return None


def _merge_devloop(dst, obj):
    """Internal documentation."""
    for k in DEVLOOP_KEYS:
        v = obj.get(k)
        if v is None:
            continue
        if isinstance(v, list):
            cur = dst.setdefault(k, [])
            for item in v:
                if item not in cur:
                    cur.append(item)
        else:
            dst.setdefault(k, v)


def parse_events(lines, transcript_path=None, cwd=None):
    """Internal documentation."""
    counts = {}
    tool_name = {}
    tool_input = {}
    bash_cmd = {}
    files, _files_seen = [], set()
    tool_failures = []
    workflows = []
    wf_relaunch = {}            # runId (fallback: workflowName) → {"name","count","statuses"}
    tests, lints, bash_failed = [], [], []
    devloop = {}
    total_tools = 0
    maind = {}
    codegraph = {}
    reads = {}
    error_loops = []
    err_streak = {"tool": None, "input": None, "len": 0, "snippet": None, "entry": None}
    retr_calls = 0
    retr_by_tool = {}
    retr_result_chars = 0
    retr_queries = []
    retr_repeated = []
    retrieval_tids = set()
    main_acc = _usage.new_acc() if _usage is not None else None

    def add_file(fp):
        if fp and fp not in _files_seen and len(files) < _MAX_FILES:
            _files_seen.add(fp)
            files.append(fp)

    def maind_rec(op):
        r = maind.get(op)
        if r is None:
            r = maind[op] = {"calls": 0, "results": 0, "found_total": 0, "found_max": 0}
        return r

    def codegraph_rec(op):
        r = codegraph.get(op)
        if r is None:
            r = codegraph[op] = {"calls": 0}
        return r

    for line in lines:
        line = line.strip() if isinstance(line, str) else ""
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if not isinstance(ev, dict):
            continue

        if main_acc is not None:
            _usage.feed_event(main_acc, ev)

        for b in _blocks(ev):
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "tool_use":
                name = b.get("name") or "?"
                counts[name] = counts.get(name, 0) + 1
                total_tools += 1
                op = _maind_tool(name)
                if op:
                    maind_rec(op)["calls"] += 1
                cg = _codegraph_tool(name)
                if cg:
                    codegraph_rec(cg)["calls"] += 1
                tid = b.get("id")
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                if tid:
                    tool_name[tid] = name
                    tool_input[tid] = _snippet(inp, 160)
                if name == "Bash":
                    cmd = inp.get("command") or ""
                    if cmd and tid:
                        bash_cmd[tid] = cmd
                elif name in ("Edit", "Write", "MultiEdit"):
                    add_file(inp.get("file_path"))
                elif name == "NotebookEdit":
                    add_file(inp.get("notebook_path"))
                elif name in ("Read", "Grep", "Glob"):
                    fp = inp.get("file_path") or inp.get("path")
                    if isinstance(fp, str) and fp and len(reads) < _MAX_READS:
                        reads[fp] = reads.get(fp, 0) + 1
                rtool = _retrieval_tool(name)
                if rtool:
                    retr_calls += 1
                    retr_by_tool[name] = retr_by_tool.get(name, 0) + 1
                    if tid:
                        retrieval_tids.add(tid)
                    q = _retrieval_query(inp)
                    if q and len(retr_queries) < _MAX_RETRIEVAL_QUERIES:
                        if (any(similar_ratio(q, prev) >= 0.7 for prev in retr_queries)
                                and len(retr_repeated) < 5):
                            retr_repeated.append(_snippet(q, 120))
                        retr_queries.append(q)
            elif bt == "tool_result":
                tid = b.get("tool_use_id")
                name = tool_name.get(tid, "?")
                is_err = bool(b.get("is_error"))
                mop = _maind_tool(name)
                if mop and not is_err:
                    cnt = _maind_result_count(_result_text(b.get("content")))
                    if cnt is not None:
                        rec = maind_rec(mop)
                        rec["results"] += 1
                        rec["found_total"] += cnt
                        if cnt > rec["found_max"]:
                            rec["found_max"] = cnt
                cmd = bash_cmd.get(tid)
                if cmd is not None:
                    entry = {"command": _snippet(cmd, 160), "ok": not is_err}
                    if TEST_PAT.search(cmd):
                        tests.append(entry)
                    if LINT_PAT.search(cmd):
                        lints.append(entry)
                    if is_err:
                        bash_failed.append(_snippet(cmd, 160))
                if is_err and len(tool_failures) < _MAX_FAILURES:
                    tool_failures.append({"tool": name,
                                          "snippet": _snippet(_result_text(b.get("content")))})


                if is_err:
                    ir = tool_input.get(tid, "")
                    if err_streak["tool"] == name and similar_ratio(err_streak["input"], ir) >= 0.6:
                        err_streak["len"] += 1
                    else:
                        err_streak = {"tool": name, "input": ir, "len": 1,
                                      "snippet": _snippet(_result_text(b.get("content")), 120),
                                      "entry": None}
                    if err_streak["len"] >= 3 and len(error_loops) < _MAX_ERROR_LOOPS:
                        if err_streak["entry"] is None:
                            err_streak["entry"] = {"tool": name, "len": err_streak["len"],
                                                    "snippet": err_streak["snippet"]}
                            error_loops.append(err_streak["entry"])
                        else:
                            err_streak["entry"]["len"] = err_streak["len"]
                else:
                    err_streak = {"tool": None, "input": None, "len": 0,
                                  "snippet": None, "entry": None}
                if tid in retrieval_tids:
                    retr_result_chars += len(_result_text(b.get("content")))

                if name in ("Task", "Workflow", "?"):
                    obj = _find_json_with_keys(_result_text(b.get("content")), DEVLOOP_KEYS)
                    if obj:
                        _merge_devloop(devloop, obj)

        tur = ev.get("toolUseResult")
        if isinstance(tur, dict):
            if any(k in tur for k in ("workflowName", "runId", "scriptPath")):
                if len(workflows) < _MAX_WORKFLOWS:
                    workflows.append({
                        "name": tur.get("workflowName") or "?",
                        "status": tur.get("status") or "?",
                        "summary": _snippet(tur.get("summary") or "", 300),
                    })




                wf_name = tur.get("workflowName") or "?"
                wf_status = tur.get("status") or "?"
                wf_key = tur.get("runId") or wf_name
                g = wf_relaunch.get(wf_key)
                if g is None and len(wf_relaunch) < _MAX_WORKFLOWS:
                    g = wf_relaunch[wf_key] = {"name": wf_name, "count": 0, "statuses": {}}
                if g is not None:
                    g["count"] += 1
                    g["statuses"][wf_status] = g["statuses"].get(wf_status, 0) + 1
                obj = _find_json_with_keys(tur.get("summary") or "", DEVLOOP_KEYS)
                if obj:
                    _merge_devloop(devloop, obj)
                for k in DEVLOOP_KEYS:
                    if k in tur:
                        _merge_devloop(devloop, tur)
                        break
            add_file(tur.get("filePath"))

            for edit in (tur.get("edits") or []):
                if isinstance(edit, dict):
                    add_file(edit.get("file_path"))

    files_sorted = sorted(files)
    top_rereads = sorted(
        ({"path": p, "count": c} for p, c in reads.items() if c > 1),
        key=lambda e: (-e["count"], e["path"]))[:5]
    protected_dirs, protected_files = _protected_sets(cwd)
    protected_writes = [fp for fp in files_sorted if _is_protected(fp, protected_dirs, protected_files)]
    workflow_relaunch = [
        {"name": g["name"], "count": g["count"], "statuses": g["statuses"]}
        for g in wf_relaunch.values() if g["count"] >= _WF_RELAUNCH_MIN
    ]

    return {
        "schema": SCHEMA,
        "tools": {"total": total_tools, "by_name": counts},
        "files_changed": files_sorted,
        "tool_failures": tool_failures,
        "bash": {"tests": tests, "lints": lints, "failed": bash_failed},
        "workflows": workflows,
        "workflow_relaunch": workflow_relaunch,
        "devloop": devloop or None,
        "maind": maind or None,
        "codegraph": codegraph or None,
        "usage": _collect_usage(main_acc, transcript_path),
        "reads": {"total": sum(reads.values()), "unique": len(reads), "top_rereads": top_rereads},
        "error_loops": error_loops,
        "retrieval": {"calls": retr_calls, "by_tool": retr_by_tool, "result_chars": retr_result_chars,
                      "queries": retr_queries, "repeated_queries": retr_repeated},
        "protected_writes": protected_writes,
    }


def parse_transcript(text, transcript_path=None, cwd=None):
    """Internal documentation."""
    return parse_events((text or "").splitlines(), transcript_path=transcript_path, cwd=cwd)
