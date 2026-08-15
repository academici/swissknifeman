"""Internal documentation."""
import json
import os
import re
import time
from pathlib import Path

from core import safe_load_json

from .common import die, parse_flags




_KNOWN_EVENT_TYPES = ("started", "result")




_NAME_RE = re.compile(r"\bname\s*:\s*(['\"])(?P<name>.*?)\1", re.DOTALL)
_DESCRIPTION_RE = re.compile(r"\bdescription\s*:\s*(['\"])(?P<description>.*?)\1", re.DOTALL)
_PHASES_BLOCK_RE = re.compile(r"\bphases\s*:\s*\[(?P<body>.*?)\]", re.DOTALL)
_PHASE_RE = re.compile(
    r"\{\s*title\s*:\s*(['\"])(?P<title>.*?)\1"
    r"(?:\s*,\s*detail\s*:\s*(['\"])(?P<detail>.*?)\3)?[^{}]*\}",
    re.DOTALL,
)


def summarize_result(result):
    """Internal documentation."""
    try:
        if isinstance(result, dict):
            for key in ("summary", "title"):
                val = result.get(key)
                if isinstance(val, str) and val.strip():
                    return _truncate(val.strip())
            for key, val in result.items():
                return _truncate(f"{key}={val!r}")
            return "{}"
        if isinstance(result, str):
            return _truncate(result.strip()) if result.strip() else "(пустая строка)"
        return _truncate(repr(result))
    except Exception:
        return "(результат не распознан)"


def _truncate(s, limit=160):
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _read_journal(path):
    """Internal documentation."""
    path = Path(path)
    if not path.is_file():
        return [], 0, False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], 0, True
    events, garbage = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            garbage += 1
            continue
        if isinstance(rec, dict):
            events.append(rec)
        else:
            garbage += 1
    return events, garbage, True


def _read_agent_metas(run_dir):
    """Internal documentation."""
    metas = {}
    for meta_path in sorted(Path(run_dir).glob("agent-*.meta.json")):
        data = safe_load_json(meta_path, default=None)
        if not isinstance(data, dict):
            continue
        agent_id = meta_path.name[len("agent-"):-len(".meta.json")]
        metas[agent_id] = {"agent_type": data.get("agentType")}
    return metas


def _locate_script(run_dir):
    """Internal documentation."""
    run_dir = Path(run_dir)
    run_id = run_dir.name
    try:
        session_dir = run_dir.parents[2]
    except IndexError:
        return None
    scripts_dir = session_dir / "workflows" / "scripts"
    if not scripts_dir.is_dir():
        return None
    matches = sorted(scripts_dir.glob(f"*-{run_id}.js"))
    return matches[0] if matches else None


def _read_script_text(script_path):
    try:
        return Path(script_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def parse_script_meta(text):
    """Internal documentation."""
    if not isinstance(text, str) or "phases" not in text:
        return {"name": None, "description": None, "phases": [], "recognized": False}
    name_m = _NAME_RE.search(text)
    descr_m = _DESCRIPTION_RE.search(text)
    block_m = _PHASES_BLOCK_RE.search(text)
    phases = []
    if block_m:
        for m in _PHASE_RE.finditer(block_m.group("body")):
            phases.append({
                "title": m.group("title").strip(),
                "detail": (m.group("detail") or "").strip(),
            })
    return {
        "name": name_m.group("name") if name_m else None,
        "description": descr_m.group("description") if descr_m else None,
        "phases": phases,
        "recognized": bool(block_m),
    }


def parse_run(run_dir):
    """Internal documentation."""
    run_dir = Path(run_dir)
    run_id = run_dir.name
    reasons = []
    degraded = False

    events, garbage, journal_exists = _read_journal(run_dir / "journal.jsonl")
    if not journal_exists:
        degraded = True
        reasons.append(f"journal.jsonl не найден: {run_dir / 'journal.jsonl'}")
    elif not events and garbage > 0:
        degraded = True
        reasons.append(
            f"journal.jsonl не распознан ({garbage} строк(и) не JSON-объект — версия CC?)"
        )

    started_ids, done_ids, results = set(), set(), []
    for rec in events:
        rtype = rec.get("type")
        agent_id = rec.get("agentId")
        if rtype == "started":
            if agent_id is not None:
                started_ids.add(agent_id)
        elif rtype == "result":
            if agent_id is not None:
                done_ids.add(agent_id)
            results.append({
                "agent_id": agent_id,
                "summary": summarize_result(rec.get("result")),
            })



    agent_metas = _read_agent_metas(run_dir)
    agents_total = len(started_ids | set(agent_metas))
    done = len(done_ids)
    inflight = max(len(started_ids) - done, 0)

    script_path = _locate_script(run_dir)
    script_text = _read_script_text(script_path) if script_path is not None else None
    meta = parse_script_meta(script_text) if script_text is not None else {
        "name": None, "description": None, "phases": [], "recognized": False,
    }
    meta["script_path"] = str(script_path) if script_path is not None else None

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "degraded": degraded,
        "degraded_reasons": reasons,
        "agents_total": agents_total,
        "started": len(started_ids),
        "done": done,
        "inflight": inflight,
        "results": results,
        "meta": meta,
    }


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------



_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"


def _config_base_dir():
    """Internal documentation."""
    override = os.environ.get(_CONFIG_DIR_ENV)
    if override:
        return Path(override)
    return Path(os.path.expanduser("~/.claude"))


def project_slug(path):
    """Internal documentation."""
    abs_path = os.path.abspath(os.path.expanduser(str(path)))
    return abs_path.replace("/", "-")


def _run_mtime(run_dir):
    """Internal documentation."""
    try:
        return (run_dir / "journal.jsonl").stat().st_mtime
    except OSError:
        try:
            return run_dir.stat().st_mtime
        except OSError:
            return 0.0


def discover_runs(base_dir=None, run=None, project=None, limit=1):
    """Internal documentation."""
    base_dir = Path(base_dir) if base_dir is not None else _config_base_dir()
    projects_dir = base_dir / "projects"
    if not projects_dir.is_dir():
        return []

    slug = project_slug(project) if project else None
    candidates = []

    try:
        proj_entries = sorted(projects_dir.iterdir())
    except OSError:
        return []

    for proj_dir in proj_entries:
        if proj_dir.is_symlink() or not proj_dir.is_dir():
            continue
        if slug is not None and proj_dir.name != slug:
            continue
        try:
            session_entries = sorted(proj_dir.iterdir())
        except OSError:
            continue
        for session_dir in session_entries:
            if session_dir.is_symlink() or not session_dir.is_dir():
                continue
            wf_root = session_dir / "subagents" / "workflows"
            if wf_root.is_symlink() or not wf_root.is_dir():
                continue
            try:
                run_entries = sorted(wf_root.glob("wf_*"))
            except OSError:
                continue
            for run_dir in run_entries:
                if run_dir.is_symlink() or not run_dir.is_dir():
                    continue
                run_id = run_dir.name
                if run is not None and run_id != run:
                    continue
                candidates.append({
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "project_slug": proj_dir.name,
                    "mtime": _run_mtime(run_dir),
                })

    candidates.sort(key=lambda c: (-c["mtime"], c["run_id"]))
    if limit is not None:
        return candidates[:limit]
    return candidates


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
#





def render_text(status):
    """Internal documentation."""
    meta = status.get("meta") or {}
    lines = []
    lines.append(f"run: {status.get('run_id')}")
    lines.append(f"имя: {meta.get('name') or '(без имени)'}")

    if status.get("degraded"):
        state = "degraded"
    elif status.get("inflight", 0) > 0:
        state = "running"
    else:
        state = "done"
    lines.append(f"статус: {state}")

    if status.get("degraded"):
        lines.append("формат не распознан (версия CC?):")
        for reason in status.get("degraded_reasons") or []:
            lines.append(f"  — {reason}")

    lines.append("фазы (декларация скрипта; привязка агентов недоступна — D18):")
    phases = meta.get("phases") or []
    if not phases:
        lines.append("  (фазы не распознаны)")
    else:
        for phase in phases:
            title = phase.get("title") or "(без названия)"
            detail = (phase.get("detail") or "").strip()
            lines.append(f"  - {title}: {detail}" if detail else f"  - {title}")

    started = status.get("started", 0)
    done = status.get("done", 0)
    inflight = status.get("inflight", 0)
    total = status.get("agents_total", 0)
    pct = round(done / started * 100) if started > 0 else 0
    lines.append(
        f"агенты: всего={total} started={started} done={done} inflight={inflight}")
    lines.append(f"% готово (грубо, done/started): {pct}%")

    results = status.get("results") or []
    lines.append(f"последние результаты ({len(results)}):")
    if not results:
        lines.append("  (пока нет)")
    else:
        for r in results:
            agent_id = r.get("agent_id") or "?"
            lines.append(f"  [{agent_id}] {r.get('summary') or ''}")

    return "\n".join(lines)


def render_json(status):
    """Internal documentation."""
    return json.dumps(status, ensure_ascii=False)


def watch_loop(run_dir, interval=2.0, out=None, sleep_fn=time.sleep, max_iterations=None):
    """Internal documentation."""
    if out is None:
        import sys as _sys
        out = _sys.stdout
    iterations = 0
    try:
        while True:
            status = parse_run(run_dir)
            print(render_text(status), file=out)
            iterations += 1
            if status.get("inflight", 0) == 0:
                break
            if max_iterations is not None and iterations >= max_iterations:
                break
            sleep_fn(interval)
    except KeyboardInterrupt:
        pass
    return 0


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
#




_WF_USAGE = (
    "harness wf status [--run WF_ID] [--project PATH] [--json] [--last N]\n"
    "                   [--watch] [--interval SEC]\n"
    "  --run WF_ID     точный id прогона (имя каталога wf_<id>)\n"
    "  --project PATH  сузить discovery до прогонов этого проекта (CC-слаг пути)\n"
    "  --last N        сколько самых свежих прогонов показать (дефолт 1, игнорируется с --run)\n"
    "  --json          та же структура, valid JSON (ensure_ascii=False)\n"
    "  --watch         перепечатка кадром до Ctrl-C / пока прогон не завершится\n"
    "  --interval SEC  интервал --watch в секундах (дефолт 2)\n"
    "exit-code: 0 — всегда (включая «нет прогонов»/degraded — это info, не ошибка);\n"
    "ненулевой — ТОЛЬКО ошибка использования флагов."
)


def _cmd_wf_status(argv):
    """Internal documentation."""
    opts = parse_flags(argv, {
        "--run": "str", "--project": "str", "--json": "bool",
        "--watch": "bool", "--interval": "str", "--last": "str",
    })
    if opts["help"]:
        print(_WF_USAGE)
        return
    run_id = opts["run"] or None
    project = opts["project"] or None
    last_raw = opts["last"] or "1"
    try:
        last = int(last_raw)
    except ValueError:
        die(f"--last ожидает целое число, получено: {last_raw!r}")
        return
    try:
        interval = float(opts["interval"]) if opts["interval"] else 2.0
    except ValueError:
        die(f"--interval ожидает число секунд, получено: {opts['interval']!r}")
        return

    limit = None if run_id else last
    candidates = discover_runs(run=run_id, project=project, limit=limit)
    if not candidates:
        print("прогонов не найдено"
              f"{f' (run={run_id})' if run_id else ''}"
              f"{f' (project={project})' if project else ''}")
        return

    if opts["watch"]:

        watch_loop(Path(candidates[0]["run_dir"]), interval=interval)
        return

    for cand in candidates:
        status = parse_run(Path(cand["run_dir"]))
        print(render_json(status) if opts["json"] else render_text(status))


def cmd_wf(env, argv):


    """Internal documentation."""
    if not argv or argv[0] in ("-h", "--help"):
        print(_WF_USAGE)
        return
    sub, rest = argv[0], argv[1:]
    if sub != "status":
        die(f"неизвестная подкоманда wf: {sub} (ожидается: status)")
        return
    _cmd_wf_status(rest)
