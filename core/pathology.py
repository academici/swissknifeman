"""pathology — детекторы workflow-патологий по run-report (SCHEMA=2).

Вход — dict отчёта прогона `<project>/.claude/runs/<sid>.json`, который пишет
harness-хук run-report (см. packages/harness/configs/claude-code/hooks/run-report/_lib.py).
Выход `detect()` — плоский список находок:

    {code, severity: 'info'|'attention', metric, threshold, evidence, data}

'attention' — вероятная патология прогона (стоит разобрать), 'info' — слабый сигнал
(посмотреть при плановом разборе). evidence — короткая русская строка с числами,
data — сырые величины для машинной обработки.

Функция ЧИСТАЯ и ЗАЩИТНАЯ: без I/O и часов, те же входы → тот же выход; исключения
наружу не выходят НИКОГДА — битый срез отчёта гасит только свой детектор, остальные
отрабатывают. Отчёт SCHEMA=1 (без usage/reads/error_loops/retrieval/protected_writes)
деградирует молча: детекторы на отсутствующих срезах просто не срабатывают.

Пороги ниже — ЭВРИСТИКИ, подобранные по здравому смыслу и форме сигналов,
НЕ откалиброванные по полевому false-positive-rate (реальной калибровки не было;
она возможна только после накопления полевых прогонов). Единый источник — меняются
только здесь, не магией по месту (паттерн analyst/confidence.py).
"""

# ── пороги детекторов (эвристики, НЕ откалиброваны по полевому FP-rate) ─────────
REREAD_MIN_TOTAL = 10          # file-reread: минимум чтений, чтобы доля была осмысленной
REREAD_RATIO_MAX = 0.4         # file-reread: доля повторных чтений (total−unique)/total
ERROR_LOOP_INFO_LEN = 3        # tool-error-loop: серия однотипных ошибок → info
ERROR_LOOP_ATTENTION_LEN = 5   # tool-error-loop: длинная серия → attention (застрял)
NOOP_MIN_TOOLS = 20            # no-op-run: столько тул-вызовов без следа — уже подозрительно
CACHE_HIT_LOW = 0.4            # cache-miss: доля кэш-чтений во входе ниже — префикс нестабилен?
CACHE_MISS_MIN_TOKENS = 200_000  # cache-miss: на малых объёмах низкий hit — шум, не сигнал
OVERTHINKING_RATIO = 0.6       # overthinking: доля thinking в выводе haiku-агента
RETRIEVAL_IN_SHARE = 0.25      # retrieval-stuffing: retrieval-токены (chars/4) как доля входа
RETRIEVAL_REPEATED_MIN = 2     # retrieval-stuffing: повторные запросы → уже не info, attention
STATIC_MIN_MSGS = 3            # static-context: минимум API-вызовов главного агента для среднего
STATIC_WINDOW_SHARE = 0.7      # static-context: средний вход как доля контекст-окна
STATIC_MAX_TOOLS = 15          # static-context: мало работы при тяжёлом входе → контекст «висит»
CONTEXT_WINDOW_TOKENS = 200_000  # прокси максимума входа: стандартное окно Sonnet/Opus
FANOUT_MIN_AGENTS = 8          # fanout: субагентов больше — а выхлоп по файлам мал
FANOUT_MAX_FILES = 5           # fanout: столько изменённых файлов не оправдывают широкий fan-out

# chars→tokens: грубая оценка ~4 символа на токен (для латиницы; хуже для кириллицы,
# но retrieval-выдача почти всегда англоязычная — для порога-эвристики достаточно).
CHARS_PER_TOKEN = 4


def _num(v):
    """Число из отчёта: только настоящие int/float (bool — не число), иначе 0 —
    мусор в поле не должен ронять арифметику детектора."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _list(v):
    """Список из отчёта; всё остальное (строка/None/dict) → пустой список."""
    return v if isinstance(v, list) else []


def _dget(d, *keys, default=None):
    """Защитный доступ вглубь dict'а: любой не-dict/отсутствующий уровень → default."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _finding(code, severity, metric, threshold, evidence, data=None):
    """Единая форма находки — чтобы потребители (maind analyze / analyst digest)
    не гадали по ключам."""
    return {"code": code, "severity": severity, "metric": metric,
            "threshold": threshold, "evidence": evidence, "data": data or {}}


# ── детекторы: каждый берёт весь отчёт, возвращает список находок ───────────────

def _file_reread(r):
    """Файлы читаются по кругу — контекст теряется/не удерживается между шагами."""
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
        f"повторные чтения: {int(total - unique)} из {int(total)} ({ratio:.0%});"
        f" топ: {', '.join(tops) or '—'}",
        {"total": total, "unique": unique,
         "top_rereads": _list(_dget(r, "reads", "top_rereads"))[:5]})]


def _tool_error_loop(r):
    """Серии однотипных ошибок одного инструмента — retry без смены подхода."""
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
            f"инструмент {loop.get('tool') or '?'}: {int(n)} однотипных ошибок подряд"
            f" — {str(loop.get('snippet') or '')[:80]}",
            {"tool": loop.get("tool"), "len": n, "snippet": loop.get("snippet")}))
    return out


def _no_op_run(r):
    """Много тул-вызовов, а следа нет: ни файлов, ни тестов, ни retrieval —
    прогон крутился вхолостую (или чисто read-only разведка — потому лишь info)."""
    tools = _num(_dget(r, "tools", "total"))
    if (tools >= NOOP_MIN_TOOLS
            and not _list(r.get("files_changed"))
            and not _list(_dget(r, "bash", "tests"))
            and _num(_dget(r, "retrieval", "calls")) == 0):
        return [_finding(
            "no-op-run", "info", tools, NOOP_MIN_TOOLS,
            f"{int(tools)} тул-вызовов без следа: ни файлов, ни тестов, ни retrieval",
            {"tools_total": tools})]
    return []


def _no_verify(r):
    """Правки без верификации: файлы изменены, а тест-прогонов нет; отдельно —
    dev-loop отчитался, но без ключей verify/results (срез результата потерян)."""
    out = []
    changed = _list(r.get("files_changed"))
    tests = _list(_dget(r, "bash", "tests"))
    if changed and not tests:
        out.append(_finding(
            "no-verify", "attention", len(changed), 0,
            f"изменено файлов: {len(changed)}, тест-прогонов: 0 — правки не проверены",
            {"files_changed": len(changed)}))
    devloop = r.get("devloop")
    # ключи проверяем защитно: devloop может быть None/не-dict (SCHEMA=1 и деградации)
    if isinstance(devloop, dict) and devloop \
            and not devloop.get("verify") and not devloop.get("results"):
        out.append(_finding(
            "no-verify-devloop", "info", 0, 0,
            "dev-loop-сигнал есть, но без verify/results — итог среза не зафиксирован",
            {"devloop_keys": sorted(devloop.keys())}))
    return out


def _cache_miss(r):
    """Низкая доля кэш-чтений при большом входе — похоже на нестабильный префикс
    (скачущий системный промпт/контекст рвёт prompt-cache и раздувает счёт)."""
    hit = _dget(r, "usage", "cache_hit")
    if not isinstance(hit, (int, float)) or isinstance(hit, bool):
        return []
    t = _dget(r, "usage", "totals", default={})
    volume = _num(_dget(t, "in")) + _num(_dget(t, "cache_read")) + _num(_dget(t, "cache_creation"))
    if hit < CACHE_HIT_LOW and volume > CACHE_MISS_MIN_TOKENS:
        return [_finding(
            "cache-miss", "info", hit, CACHE_HIT_LOW,
            f"cache_hit {hit:.2f} при входе {int(volume)} ток — нестабильный префикс?",
            {"cache_hit": hit, "input_volume": volume})]
    return []


def _overthinking(r):
    """haiku-агенты, у которых thinking доминирует над текстом: дешёвую модель
    заставили «думать» — вероятно, задача не под её тир (роутинг моделей)."""
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
        f"haiku-агентов с thinking>{OVERTHINKING_RATIO:.0%}: {len(hits)} ({names})",
        {"agents": hits})]


def _retrieval_stuffing(r):
    """Retrieval-выдача занимает заметную долю входа: сырьё льют в контекст вместо
    синтеза; с повторными запросами — ещё и одно и то же гоняют по кругу."""
    tin = _num(_dget(r, "usage", "totals", "in"))
    if tin <= 0:
        return []
    retr_tokens = _num(_dget(r, "retrieval", "result_chars")) / CHARS_PER_TOKEN
    share = retr_tokens / tin
    if share <= RETRIEVAL_IN_SHARE:
        return []
    repeated = len(_list(_dget(r, "retrieval", "repeated_queries")))
    attention = repeated >= RETRIEVAL_REPEATED_MIN
    tail = f", повторных запросов: {repeated}" if attention else ""
    return [_finding(
        "retrieval-stuffing", "attention" if attention else "info",
        share, RETRIEVAL_IN_SHARE,
        f"retrieval ≈ {int(retr_tokens)} ток = {share:.0%} входа ({int(tin)}){tail}",
        {"retrieval_tokens": retr_tokens, "in": tin, "repeated_queries": repeated})]


def _protected_write(r):
    """Правки в managed-путях (vendor-скиллы/agent-pack) — их перезатрёт следующий
    sync; всегда attention, независимо от объёма."""
    pw = _list(r.get("protected_writes"))
    if not pw:
        return []
    shown = ", ".join(str(p) for p in pw[:3])
    return [_finding(
        "protected-write", "attention", len(pw), 0,
        f"правки managed-путей: {len(pw)} ({shown}) — перезатрёт следующий sync",
        {"protected_writes": pw})]


def _static_context(r):
    """Резидентный контекст доминирует: средний вход одного API-вызова главного агента
    близок к контекст-окну, а полезной работы (тул-вызовов) мало — контекст «висит»
    балластом (жирные бакеты скиллов/MCP-выдача).

    Прокси, а не точная формула: в спеке фигурируют totals, но totals смешивают вход
    субагентов с msgs главного агента — считаем честнее по (in+cache_read)/msgs САМОГО
    главного агента, а «максимум» берём как стандартное окно CONTEXT_WINDOW_TOKENS."""
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
            f"средний вход {int(avg_in)} ток/вызов ≈ {share:.0%} окна при {int(tools)}"
            f" тул-вызовах — резидентный контекст доминирует; ревизия бакетов/MCP: skiller budget",
            {"avg_in": avg_in, "msgs": msgs, "tools_total": tools,
             "window": CONTEXT_WINDOW_TOKENS})]
    return []


def _fanout(r):
    """Широкий fan-out субагентов при скромном выхлопе по файлам — оркестрация
    дороже результата (каждый субагент оплачивает свой вход заново)."""
    n_agents = len(_list(_dget(r, "usage", "agents")))
    n_files = len(_list(r.get("files_changed")))
    if n_agents > FANOUT_MIN_AGENTS and n_files < FANOUT_MAX_FILES:
        return [_finding(
            "fanout", "info", n_agents, FANOUT_MIN_AGENTS,
            f"агентов: {n_agents} при {n_files} изменённых файлах — fan-out дороже выхлопа",
            {"agents": n_agents, "files_changed": n_files})]
    return []


_DETECTORS = (_file_reread, _tool_error_loop, _no_op_run, _no_verify, _cache_miss,
              _overthinking, _retrieval_stuffing, _protected_write, _static_context,
              _fanout)


def detect(run_report):
    """Прогнать все детекторы по run-report → список находок (может быть пустым).

    Никогда не бросает: не-dict вход → []; исключение внутри детектора (битый срез)
    гасится и роняет только ЕГО находки — остальные детекторы отрабатывают."""
    if not isinstance(run_report, dict):
        return []
    findings = []
    for det in _DETECTORS:
        try:
            findings.extend(det(run_report))
        except Exception:
            continue  # защитный контракт: см. docstring
    return findings
