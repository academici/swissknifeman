"""run-report · защитный парсер транскрипта Claude Code → структурированный исход прогона.

Stdlib-only, автономен в ~/.claude/hooks (импорт пакета harness в момент работы хука
недоступен — маленький дубль осознан). Разбор СТРОЧНЫЙ (по одной JSONL-записи, без слурпа
всего транскрипта в память — большие транскрипты рвут RAM) и ЗАЩИТНЫЙ: любая битая строка /
неизвестный тип события / отсутствующее поле пропускается, парсер не падает. Схема транскрипта
официально не заморожена (verified perplexity-web: стабильна к аддитивным изменениям, но не
контракт) → берём только то, что стабильно, и деградируем молча.

Никогда не бросай наружу: вызывающий хук оборачивает всё в try/except → exit 0.
"""
import json
import re

SCHEMA = 1

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


def parse_events(lines):
    """Разобрать итератор строк JSONL (файловый объект или список) в исход прогона.

    Единый forward-проход: tool_use раньше своего tool_result, поэтому id→имя/команда
    успевают заполниться. Возвращает dict-срезы (см. ключи в конце)."""
    counts = {}                 # имя инструмента → сколько вызовов
    tool_name = {}              # tool_use_id → имя (для сопоставления с tool_result)
    bash_cmd = {}               # tool_use_id → команда (Bash)
    files, _files_seen = [], set()
    tool_failures = []
    workflows = []
    tests, lints, bash_failed = [], [], []
    devloop = {}
    total_tools = 0
    maind = {}                  # op → {calls, results, found_total, found_max} (память/граф хаба)

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
                if name == "Bash":
                    cmd = inp.get("command") or ""
                    if cmd and tid:
                        bash_cmd[tid] = cmd
                elif name in ("Edit", "Write", "MultiEdit"):
                    add_file(inp.get("file_path"))
                elif name == "NotebookEdit":
                    add_file(inp.get("notebook_path"))
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

    return {
        "schema": SCHEMA,
        "tools": {"total": total_tools, "by_name": counts},
        "files_changed": sorted(files),
        "tool_failures": tool_failures,
        "bash": {"tests": tests, "lints": lints, "failed": bash_failed},
        "workflows": workflows,
        "devloop": devloop or None,
        "maind": maind or None,       # память/граф хаба: {op:{calls,results,found_total,found_max}}
    }


def parse_transcript(text):
    """Обёртка над parse_events для строки/теста (строчный split, без слурпа структуры)."""
    return parse_events((text or "").splitlines())
