"""wf_status — детерминированный парсер transcript-директории workflow-прогона Claude Code
(P2.1: ядро парсинга; discovery/рендер/CLI — P2.2-P2.4).

Формат ВНУТРЕННИЙ и НЕДОКУМЕНТИРОВАННЫЙ (может меняться между версиями CLI) — источник
истины НЕ доки Claude Code, а эмпирика на реальных прогонах:
`plans/SKM-ROADMAP-005/findings/P2-workflow-transcript-format.md` (дата сверки 2026-07-10;
при регрессии формата — пере-сверить перед правкой, доки его не несут).

Раскладка (см. findings §«Раскладка на диске»):
    <session>/workflows/scripts/<name>-wf_<id>.js         скрипт прогона (export const meta)
    <session>/subagents/workflows/wf_<id>/                 transcript-директория (run_dir)
        journal.jsonl            построчные события {"type":"started"|"result","agentId":...}
        agent-<hex>.meta.json    {"agentType":..., "spawnDepth":...} — метки/фазы НЕТ
        agent-<hex>.jsonl        0600 транскрипт агента (НЕ читаем — Scope Excluded P2.1)

D18 (owner-confirmed, см. Decision Log плана): привязка агент→фаза журналом/агент-метой НЕ
выводится — журнал её физически не несёт, эвристику намеренно НЕ изобретаем (при соблазне
«сопоставить агентов фазам» — это Scope Excluded). Отчёт несёт декларации фаз (из meta
скрипта) ОТДЕЛЬНО от общего прогресса агентов (started/done/inflight).
D19: скрипт прогона лежит в sibling-каталоге `../../workflows/scripts/`, НЕ внутри run_dir.

Парсер ЗАЩИЩЁННЫЙ: несовпадение формата / битый journal.jsonl → `degraded=True` +
честная причина в `degraded_reasons`. НИКОГДА трейсбек, НИКОГДА тихий пустой ответ.
Запрещены `eval`/`exec`/импорт `.js` и любые внешние зависимости — meta скрипта (JS-объект,
НЕ JSON) парсится регуляркой. Функции здесь ЧИСТЫЕ (path in → dict out), без печати и
других побочных эффектов — рендер и вывод живут в P2.3/P2.4. stdlib-only."""
import json
import re
from pathlib import Path

from core import safe_load_json

# Типы событий journal.jsonl, которые парсер понимает (findings §journal.jsonl). Любой
# другой type молча игнорируется (защита от будущих полей CC) — это НЕ считается поломкой
# формата, деградация журнала определяется отдельно (см. _read_journal/parse_run).
_KNOWN_EVENT_TYPES = ("started", "result")

# `export const meta = {...}` — JS-объект, НЕ JSON (ключи без кавычек, висячие запятые,
# см. findings §«export const meta»). Извлекаем регуляркой, НИКОГДА eval/exec/json.loads
# целиком (Code Guidance P2.1 — жёсткий запрет).
_NAME_RE = re.compile(r"\bname\s*:\s*(['\"])(?P<name>.*?)\1", re.DOTALL)
_DESCRIPTION_RE = re.compile(r"\bdescription\s*:\s*(['\"])(?P<description>.*?)\1", re.DOTALL)
_PHASES_BLOCK_RE = re.compile(r"\bphases\s*:\s*\[(?P<body>.*?)\]", re.DOTALL)
_PHASE_RE = re.compile(
    r"\{\s*title\s*:\s*(['\"])(?P<title>.*?)\1"
    r"(?:\s*,\s*detail\s*:\s*(['\"])(?P<detail>.*?)\3)?[^{}]*\}",
    re.DOTALL,
)


def summarize_result(result):
    """Произвольный JSON `result` из `journal.jsonl` → 1-строчная выжимка по
    УПОРЯДОЧЕННОМУ fallback (Implementation Rules): `summary` → `title` → первый ключ
    dict-а → усечённый repr. Никогда не бросает — на любой неожиданный тип возвращает
    честную заглушку, а не падает (парсер обязан быть защищённым)."""
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
    except Exception:  # noqa: BLE001 — выжимка обязана быть безотказной, не источником трейсбека
        return "(результат не распознан)"


def _truncate(s, limit=160):
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _read_journal(path):
    """`journal.jsonl` → `(events, garbage_lines, exists)`. Читает построчно (findings:
    «строки читать по одной; битую строку — continue, не падать»); не-dict записи и
    строки, не являющиеся JSON, считаются в `garbage_lines`, но не роняют разбор."""
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
    """`agent-*.meta.json` → `{agent_id: {"agent_type": ...}}`. Метки/фазы в этих файлах
    НЕТ (D18) — используются только для счёта агентов как fallback/пересечение с journal
    (findings: `agentType`/`spawnDepth`, ничего больше). Битый/нечитаемый файл — пропуск
    (fail-soft, единый паттерн с settings_audit: не роняет разбор всей директории)."""
    metas = {}
    for meta_path in sorted(Path(run_dir).glob("agent-*.meta.json")):
        data = safe_load_json(meta_path, default=None)
        if not isinstance(data, dict):
            continue
        agent_id = meta_path.name[len("agent-"):-len(".meta.json")]
        metas[agent_id] = {"agent_type": data.get("agentType")}
    return metas


def _locate_script(run_dir):
    """Sibling-скрипт прогона (D19): `run_dir` = `<session>/subagents/workflows/wf_<id>/`,
    скрипт — `<session>/workflows/scripts/*-<run_id>.js`. Раскладка иная / не найден →
    `None`, честно (не исключение)."""
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
    """Текст скрипта прогона → `{"name","description","phases":[{"title","detail"}],
    "recognized"}`. `export const meta = {...}` — JS-объект (ключи без кавычек, висячие
    запятые), парсится РЕГУЛЯРКОЙ — НЕ `eval`/`exec`/`json.loads` целиком (запрет,
    Code Guidance). Не распознан (нет `phases`/блок не найден) → `phases=[]` +
    `recognized=False` (findings: «meta не распознан → phases=[] + флаг»)."""
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
    """Одна transcript-директория `wf_<id>/` → dict-статус прогона. ЧИСТАЯ функция
    (path in → dict out), без печати/побочных эффектов — рендер в P2.3.

    Возвращает:
        run_id, run_dir, degraded, degraded_reasons (list[str]),
        agents_total, started, done, inflight,
        results (list[{"agent_id","summary"}]) — В ПОРЯДКЕ journal.jsonl,
        meta ({"name","description","phases","recognized","script_path"}).

    Несовпадение формата (нет `journal.jsonl` / журнал не распознан) → `degraded=True` +
    честная причина, НИКОГДА трейсбек. Per-agent→phase attribution НЕ выводится (D18,
    Scope Excluded) — `meta.phases` это ДЕКЛАРАЦИИ фаз из скрипта, не привязка к агентам."""
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
        # rtype вне _KNOWN_EVENT_TYPES — молча игнорируем (unknown-поля игнорировать,
        # Implementation Rules); НЕ считается поломкой формата.

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
