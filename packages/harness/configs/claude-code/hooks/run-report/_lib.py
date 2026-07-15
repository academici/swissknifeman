"""run-report · защитный парсер транскрипта Claude Code → структурированный исход прогона.

Stdlib-only, автономен в ~/.claude/hooks (импорт пакета harness в момент работы хука
недоступен — маленький дубль осознан). Разбор СТРОЧНЫЙ (по одной JSONL-записи, без слурпа
всего транскрипта в память — большие транскрипты рвут RAM) и ЗАЩИТНЫЙ: любая битая строка /
неизвестный тип события / отсутствующее поле пропускается, парсер не падает. Схема транскрипта
официально не заморожена (verified perplexity-web: стабильна к аддитивным изменениям, но не
контракт) → берём только то, что стабильно, и деградируем молча.

SCHEMA=2 (аддитивно к SCHEMA=1, старые читатели не ломаются — новые ключи просто добавлены):
токен-usage (главный транскрипт + субагенты, через вендоренный _usage.py — см.
scripts/sync-usage.sh), reads (re-read-хотспоты), error_loops (застревания на одном инструменте),
retrieval (WebFetch/WebSearch/context7/perplexity-вызовы), protected_writes (пересечение
files_changed с managed-путями skills-lock.json/agent-pack.lock.json), workflow_relaunch
(P1.2, plans/2026.07.15-TELEMETRY-OPT: ≥_WF_RELAUNCH_MIN вызовов Workflow сгруппированных по
runId — fallback на workflowName при его отсутствии — диагностический сигнал «скрипт воркфлоу
дебажился на лету», не ошибка).

Никогда не бросай наружу: вызывающий хук оборачивает всё в try/except → exit 0.
"""
import json
import re
from pathlib import Path

SCHEMA = 2

# _usage.py — вендоренная (scripts/sync-usage.sh) байт-в-байт копия core/usage.py, лежит
# рядом физически: PYTHONPATH монорепо в ~/.claude/hooks недоступен. Отсутствие/битость
# (старый хук до пересинка) не должно ронять отчёт — весь usage-блок деградирует в None,
# остальные срезы (reads/error_loops/retrieval/protected_writes) от неё не зависят.
try:
    import _usage
except Exception:
    _usage = None

# Паттерны «что гоняли» в Bash-командах — детект тест/линт-прогонов (грубо, но полезно
# для форензики). Точный pass/fail даёт is_error на tool_result, здесь — классификация.
TEST_PAT = re.compile(
    r"(?:\bpytest\b|\bphpunit\b|vendor/bin/pest|\bpest\b|\bjest\b|\bvitest\b|"
    r"go\s+test|cargo\s+test|npm\s+(?:run\s+)?test|yarn\s+test|pnpm\s+test|"
    r"\bunittest\b|validate\.sh|(?<![\w/])test\.sh)", re.I)
LINT_PAT = re.compile(
    r"(?:\bruff\b|\bflake8\b|\bpylint\b|\bmypy\b|\beslint\b|vendor/bin/pint|"
    r"\bphpstan\b|\bpsalm\b|(?<![\w/])pint\b|\bblack\b|\bisort\b|(?<![\w/])tsc\b|"
    r"\bprettier\b|py_compile)", re.I)

# Ключи «богатого» сигнала dev-loop (SLICE_RESULT_SCHEMA и агрегат воркфлоу): если результат
# воркфлоу/агента в транскрипте несёт их JSON'ом — извлекаем; иначе довольствуемся summary.
DEVLOOP_KEYS = ("tool_failures", "workarounds", "deferred", "open_questions",
                "results", "verify")

_MAX_FAILURES = 25
_MAX_FILES = 200
_MAX_WORKFLOWS = 20
_WF_RELAUNCH_MIN = 3  # D4 (plans/2026.07.15-TELEMETRY-OPT): ≥3 launches одной группы → flag
_MAX_READS = 500             # верхняя граница числа различимых путей чтения (память)
_MAX_ERROR_LOOPS = 20
_MAX_RETRIEVAL_QUERIES = 20  # окно для O(n²) similar_ratio-сравнения запросов (дёшево)
_MAX_SUBAGENTS = 50

# WebFetch/WebSearch — retrieval всегда; mcp__<server>__<tool> — retrieval, если хвост
# инструмента похож на поиск/доки, ИЛИ имя сервера явно RAG-провайдер (perplexity/context7).
_RETRIEVAL_TAIL_PAT = re.compile(r"^(search|query-docs|resolve-library-id)", re.I)


def similar_ratio(a, b):
    """Похожесть двух текстов (Жаккар по словам lower len>=2) — та же формула, что в
    core.usage.similar_ratio, переиспользуем при наличии вендоренного _usage.py; локальный
    фолбэк на случай его отсутствия (error_loops/retrieval не должны терять сигнал только
    из-за не довезённого/устаревшего вендора — в отличие от usage-блока, это не опционально)."""
    if _usage is not None:
        return _usage.similar_ratio(a, b)

    def toks(s):
        return {w for w in str(s or "").lower().split() if len(w) >= 2}

    ta, tb = toks(a), toks(b)
    union = ta | tb
    return (len(ta & tb) / len(union)) if union else 0.0


def _retrieval_tool(name):
    """Имя инструмента → само имя, если это retrieval-вызов (WebFetch/WebSearch/
    mcp__server__search-ишный/context7/perplexity), иначе None."""
    if not isinstance(name, str):
        return None
    if name in ("WebFetch", "WebSearch"):
        return name
    if not name.startswith("mcp__"):
        return None
    tail = name.rsplit("__", 1)[-1]
    server = name[len("mcp__"):-(len(tail) + 2)]  # часть между 'mcp__' и последним '__'
    if _RETRIEVAL_TAIL_PAT.match(tail) or "perplexity" in server.lower() or "context7" in server.lower():
        return name
    return None


def _retrieval_query(inp):
    """Текст запроса из input tool_use retrieval-вызова — best-effort по частым ключам."""
    if not isinstance(inp, dict):
        return None
    for k in ("query", "q", "url", "libraryName", "topic", "prompt"):
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _sidecar_dir(transcript_path):
    """Каталог сайдкар-логов субагентов рядом с главным транскриптом:
    <dir>/<session-id>/subagents/ — session-id тут ИМЯ ФАЙЛА транскрипта без расширения
    (как их кладёт сама Claude Code), не санитайзированный session_id хука."""
    if not transcript_path:
        return None
    try:
        p = Path(transcript_path)
    except Exception:
        return None
    return p.parent / p.stem / "subagents"


def _collect_usage(main_acc, transcript_path):
    """usage-блок отчёта: главный транскрипт (main_acc уже накоплен общим проходом
    parse_events) + субагенты (сайдкар-файлы, читаются отдельно — вне основного потока
    строк). None целиком, если _usage.py не довезли (старый хук до scripts/sync-usage.sh) —
    деградация тихая, остальной отчёт как раньше."""
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
    main = agents[0]   # finish(main_acc, label="main") — всегда первый (см. выше)
    return {
        "totals": summary["totals"],
        "by_model": summary["by_model"],
        "cache_hit": summary["cache_hit"],
        "agents": agents,
        "subagents_parsed": parsed,
        "subagents_skipped": skipped,
        # first_turn_overhead/turns — ГЛАВНОГО транскрипта (не мёрж с субагентами):
        # это про стартовый оверхед самой сессии (P5.3, ТЗ), не про сумму всех агентов.
        "first_turn_overhead": main.get("first_turn_overhead"),
        "turns": main.get("msgs"),
    }


def _protected_sets(cwd):
    """Managed-пути проекта, вторжение в которые стоит подсветить в отчёте:
    - `<cwd>/skills-lock.json` (skiller vendor-канал) — managed=true записи несут каталог
      скилла (`installed_path`), любая правка ВНУТРИ него — protected;
    - `<cwd>/.claude/agent-pack.lock.json` (harness agent-packs) — конкретные файлы
      (`files[].target`), КРОМЕ `user_owned` (те отданы пользователю навсегда).
    Оба читаются защитно: нет файла / битый JSON / нет cwd → пустые множества, без исключений."""
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
    """Однострочный срез значения (str или JSON-сериализуемое) до n символов."""
    try:
        s = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
    except Exception:
        s = str(val)
    return " ".join(s.split())[:n]


def _blocks(event):
    """content-блоки сообщения (assistant tool_use / user tool_result), защитно."""
    msg = event.get("message")
    if isinstance(msg, dict):
        c = msg.get("content")
        if isinstance(c, list):
            return c
    return []


def _result_text(content):
    """Текст из tool_result.content (строка ИЛИ список блоков {type:text,text})."""
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
    """MCP-имя инструмента хаба → 'memory_<op>' / 'graph_<op>' / None. Матчим по ХВОСТУ после
    последнего '__' — переживает и `mcp__maind__…`, и `mcp__plugin_core_maind__…` (лейбл сервера
    меняется, имя инструмента — нет)."""
    if not isinstance(name, str):
        return None
    tail = name.rsplit("__", 1)[-1]
    if tail.startswith("maind_memory_"):
        return "memory_" + tail[len("maind_memory_"):]
    if tail.startswith("maind_graph_"):
        return "graph_" + tail[len("maind_graph_"):]
    return None


def _maind_result_count(result_text):
    """Число «полезных» единиц в результате maind-вызова (найденные факты / соседи / узлы / длина
    пути). best-effort JSON: список → len; dict с `count` → count; `neighbors`/`nodes` → len;
    `path` → len|0. Непарсибельно / нет числа → None (тогда пишем только счётчик вызова, без found)."""
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
    """Первый {...}-фрагмент в text, парсящийся как dict с ≥1 ключом из keys. Best-effort:
    сканирует кандидатов по позициям '{' с балансировкой скобок. None если не нашли."""
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
                        break  # невалидно — к следующему '{'
                    if isinstance(obj, dict) and any(k in obj for k in keys):
                        return obj
                    break
        # к следующему '{'
    return None


def _merge_devloop(dst, obj):
    """Слить извлечённый dev-loop-словарь в аккумулятор (списки — конкатенация, дедуп прост)."""
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
    """Разобрать итератор строк JSONL (файловый объект или список) в исход прогона.

    Единый forward-проход: tool_use раньше своего tool_result, поэтому id→имя/команда
    успевают заполниться. `transcript_path`/`cwd` опциональны (SCHEMA=2, только для
    usage-субагентов и protected_writes) — без них парсер работает как раньше, просто
    эти срезы деградируют (usage без субагентов/без transcript_path, protected_writes=[]
    без cwd). Возвращает dict-срезы (см. ключи в конце)."""
    counts = {}                 # имя инструмента → сколько вызовов
    tool_name = {}              # tool_use_id → имя (для сопоставления с tool_result)
    tool_input = {}             # tool_use_id → снимок input (для similar_ratio в error_loops)
    bash_cmd = {}               # tool_use_id → команда (Bash)
    files, _files_seen = [], set()
    tool_failures = []
    workflows = []
    wf_relaunch = {}            # runId (fallback: workflowName) → {"name","count","statuses"}
    tests, lints, bash_failed = [], [], []
    devloop = {}
    total_tools = 0
    maind = {}                  # op → {calls, results, found_total, found_max} (память/граф хаба)
    reads = {}                  # file_path/path (Read/Grep/Glob) → сколько раз
    error_loops = []            # серии ≥3 подряд ошибок ОДНОГО инструмента с похожим input
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

    def maind_rec(op):          # запись метрики op (фикс. размер: 4 счётчика, не растёт с вызовами)
        r = maind.get(op)
        if r is None:
            r = maind[op] = {"calls": 0, "results": 0, "found_total": 0, "found_max": 0}
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
            _usage.feed_event(main_acc, ev)      # тот же forward-проход — второго чтения файла нет

        for b in _blocks(ev):
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "tool_use":
                name = b.get("name") or "?"
                counts[name] = counts.get(name, 0) + 1
                total_tools += 1
                op = _maind_tool(name)          # память/граф хаба — агрегируем отдельно (для analyze)
                if op:
                    maind_rec(op)["calls"] += 1
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
                rtool = _retrieval_tool(name)   # WebFetch/WebSearch/context7/perplexity — RAG-срез
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
                mop = _maind_tool(name)         # результат maind-вызова: сколько нашёл/соседей
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
                # error_loops: серия ≥3 подряд ошибок ОДНОГО инструмента с похожим input —
                # застревание (retry без изменения подхода). Любой не-error tool_result рвёт серию.
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
                # dev-loop-сигнал может прийти текстом результата воркфлоу/агента
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
                # workflow_relaunch (P1.2, findings/P1-workflow-rootcause.md): группировка ПО
                # runId (resume того же рана — dterema-кейс, 11× resumeFromRunId), не по имени —
                # один workflowName у двух разных runId не должен схлопываться в одну группу.
                # runId отсутствует (старые транскрипты/фикстуры) → деградация на workflowName.
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
            # MultiEdit toolUseResult может нести несколько правок
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
        "maind": maind or None,       # память/граф хаба: {op:{calls,results,found_total,found_max}}
        "usage": _collect_usage(main_acc, transcript_path),   # None без _usage.py (SCHEMA=2)
        "reads": {"total": sum(reads.values()), "unique": len(reads), "top_rereads": top_rereads},
        "error_loops": error_loops,
        "retrieval": {"calls": retr_calls, "by_tool": retr_by_tool, "result_chars": retr_result_chars,
                      "queries": retr_queries, "repeated_queries": retr_repeated},
        "protected_writes": protected_writes,
    }


def parse_transcript(text, transcript_path=None, cwd=None):
    """Обёртка над parse_events для строки/теста (строчный split, без слурпа структуры)."""
    return parse_events((text or "").splitlines(), transcript_path=transcript_path, cwd=cwd)
