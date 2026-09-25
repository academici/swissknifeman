"""budget — токеновый бюджет набора скиллов (трёхъярусная модель раскрытия).

Зачем: набор скиллов раздувается молча. Видно это только если различать, ЧТО
грузится всегда, а что условно:

  ярус-0 ⊕ always     — name+description каждого активного скилла. Резидентны в
                        КАЖДОМ запросе (по ним агент решает, применять ли скилл).
                        Это и есть постоянный «налог» — главная метрика.
  ярус-1 ↻ on-trigger — тело SKILL.md. Грузится, только когда скилл срабатывает.
  ярус-2 ⌥ on-demand  — сниппеты и references. Грузятся по ссылке из тела,
                        опционально (references — тела монолитов после
                        thin-navigator-волны, см. P2.1 SKM-MASTER-003).

Оценка токенов — ГРУБАЯ и языко-зависимая (кириллица плотнее латиницы у
токенайзера Claude), stdlib-only, без сторонних токенайзеров. Именно поэтому
EN-канон дешевле RU при равном объёме — это виден выигрыш перевода. Число
пригодно для СРАВНЕНИЯ наборов и относительного веса, не для точного учёта. Источник математики ОДИН (этот модуль) — им пользуются CLI
(`skiller budget`), генератор карты (docs/guide/budget.md) и строка в
`skiller status`."""
import json
import math
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import atomic_write_text

from .common import die, parse_flags, parse_frontmatter
from .config import (CORE_SKILLS, DEFAULT_EXCLUDE, RESIDENT_BUDGET_TARGET,
                     ProjectConfig, all_buckets, core_skill_tuples,
                     find_project_root, load_config, resolve_selection,
                     validate_config)
from .plugins import plugins_summary
from .native_codex import native_inventory
from .vendor import build_requires_index, collect_skills, resolve_requires

# Символов на токен — РАЗНЫЕ для кириллицы и латиницы/кода: кириллица у токенайзера
# Claude плотнее, латиница/код/пунктуация — реже. Поэтому EN-канон дешевле RU при
# ТОМ ЖЕ объёме текста — это и есть выигрыш перевода. Грубо, для сравнения наборов,
# не точный учёт (оракул — /v1/messages/count_tokens).
#
# Калибровка (RAG, verified 2026-07-02, perplexity — 3 источника: codeusagecalc,
# frontiersin 2025, basicfreetools; аудит B-1): кириллица-проза ~2.8–3.2 chars/tok,
# латиница-проза ~3.5–4.0, код ~2.5–3.0. Прежние 2.2/4.0 занижали RU chars/tok
# (=завышали RU-токены, искусственно раздувая «выигрыш перевода») и завышали LAT
# chars/tok (=занижали токены code-heavy тел). CYR — середина диапазона (2.9). LAT —
# компромисс EN-прозы и кода одной константой (модель не различает код-блоки внутри
# тела): тела скиллов технические (команды/сниппеты/таблицы) → ближе к коду, чем к
# чистой прозе (3.4).
CHARS_PER_TOKEN_CYR = 2.9
CHARS_PER_TOKEN_LAT = 3.4
CONTEXT_LIMIT = 200_000
TOP_N = 10


# --- оценка токенов -----------------------------------------------------------
def estimate_tokens(text):
    """Языко-зависимая оценка токенов: кириллица ~2.9 chars/tok, остальное ~3.4
    (см. калибровку выше). 0 для пустого. EN тем самым дешевле RU при равном
    объёме (выигрыш перевода)."""
    if not text:
        return 0
    # U+0400–04FF (Cyrillic) — RU/UK и большинство славянских языков; U+0500–052F
    # (Cyrillic Supplement) — доп. буквы (коми-пермяцкий и др.), B-3: раньше не
    # учитывались (недо-подсчёт токенов для текста с этими буквами).
    cyr = sum(1 for c in text if "Ѐ" <= c <= "ӿ" or "Ԁ" <= c <= "ԯ")
    return math.ceil(cyr / CHARS_PER_TOKEN_CYR + (len(text) - cyr) / CHARS_PER_TOKEN_LAT)


def _split_frontmatter(text):
    """(frontmatter_text, body_text). Без frontmatter → ("", text).

    B-4 (аудит): похоже на дубль common.parse_frontmatter/core.text.parse_frontmatter,
    но решает ДРУГУЮ задачу — тем нужен разобранный YAML-словарь (без тела), этой
    функции нужно ИМЕННО тело (frontmatter_text здесь не парсится как YAML, только
    отрезается). Слить значило бы менять сигнатуру core.parse_frontmatter (общую для
    skiller/harness/maind — риск шире одного пакета) ради 8-строчной находилки границы
    `---`...`---`. Оставлено раздельно осознанно, не по недосмотру."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return "", text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return "", text


def skill_budget(skill_dir):
    """Трёхъярусный бюджет одного скилла (каталог с SKILL.md).
    → {name, tier0, tier1, tier2, snippets, references}; None, если SKILL.md
    отсутствует. tier2 (⌥ on-demand) — сумма snippets/ И references/: оба
    грузятся ПО ССЫЛКЕ из тела (навигатор), не резидентно — та же семантика,
    один glob-паттерн (P2.1 SKM-MASTER-003, T1: после thin-navigator-волны
    P7 SKM-MASTER-002 тела монолитов лежат в references/full.md — без учёта
    здесь ярус-2 занижен, «единый источник токен-математики» врёт)."""
    skill_dir = Path(skill_dir)
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return None
    text = md.read_text(encoding="utf-8-sig")
    fm = parse_frontmatter(md)
    name = fm.get("name", "") or skill_dir.name
    desc = fm.get("description", "")
    _, body = _split_frontmatter(text)

    def _on_demand_files(subdir):
        d = skill_dir / subdir
        return [p for p in sorted(d.glob("*"))
                if p.is_file() and p.name != "index.json"] if d.is_dir() else []

    snippets = _on_demand_files("snippets")
    references = _on_demand_files("references")
    tier2 = sum(estimate_tokens(p.read_text(encoding="utf-8", errors="ignore"))
                for p in (*snippets, *references))
    return {
        "name": name,
        "tier0": estimate_tokens(name + " " + desc),
        "tier1": estimate_tokens(body),
        "tier2": tier2,
        "snippets": len(snippets),
        "references": len(references),
    }


# --- активный набор (как собрал бы vendor, без установки) ----------------------
def resolve_active_set(env, target, config, *, profile="", flag_buckets=None,
                       flag_exclude=None, no_core=False):
    """Активный набор скиллов проекта, без записи на диск. Переиспользует
    resolve_selection / collect_skills / core_skill_tuples / resolve_requires —
    та же выборка, что у `skiller vendor`. Возвращает (skills, meta), где
    skills — [(bucket, rel, dir, fm_name)], meta['pulled'] — транзитивные deps."""
    config = ProjectConfig.coerce(config)  # исторические вызовы передают dict
    flag_buckets = flag_buckets or []
    flag_exclude = flag_exclude or []
    buckets, profile_name, _profile_source, source, _include_meta = \
        resolve_selection(env, target, config, profile, flag_buckets)
    known = all_buckets(env)
    for b in buckets:
        if b not in known and b not in {"core", "task"}:
            die(f"unknown bucket: {b}")
    buckets = [b for b in buckets if b in known]
    exclude = set(flag_exclude) | set(config.exclude)
    if not no_core:
        exclude |= set(DEFAULT_EXCLUDE)
    skills, _ = collect_skills(env, buckets, exclude)
    core_added = []
    if not no_core:
        have = {f"{b}/{r}" for b, r, _, _ in skills}
        for tup in core_skill_tuples(env, exclude):
            if f"{tup[0]}/{tup[1]}" not in have:
                skills.append(tup)
                core_added.append(f"{tup[0]}/{tup[1]}")
    index = build_requires_index(env)
    dependency_diagnostics = []
    pulled = resolve_requires(
        skills, index, exclude, diagnostics=dependency_diagnostics)
    meta = {"buckets": list(buckets), "profile": profile_name, "source": source,
            "exclude": sorted(exclude), "pulled": pulled, "core_added": core_added,
            "dependency_diagnostics": dependency_diagnostics}
    return skills, meta


def budget_for_set(skills, pulled=None):
    """Агрегировать трёхъярусный бюджет по списку скиллов [(bucket, rel, dir,
    fm_name)]. Возвращает dict с суммами, разбивкой по бакетам и items."""
    pulled = pulled or {}
    items, by_bucket = [], {}
    for bucket, _rel, d, fm_name in skills:
        b = skill_budget(d)
        if b is None:
            continue
        key = fm_name or Path(d).name
        rec = {"bucket": bucket, "name": b["name"], "tier0": b["tier0"],
               "tier1": b["tier1"], "tier2": b["tier2"], "snippets": b["snippets"],
               "references": b["references"], "transitive": key in pulled}
        items.append(rec)
        agg = by_bucket.setdefault(
            bucket, {"tier0": 0, "tier1": 0, "tier2": 0, "count": 0})
        for k in ("tier0", "tier1", "tier2"):
            agg[k] += b[k]
        agg["count"] += 1
    tier0 = sum(i["tier0"] for i in items)
    tier1 = sum(i["tier1"] for i in items)
    tier2 = sum(i["tier2"] for i in items)
    return {
        "count": len(items),
        "transitive": sum(1 for i in items if i["transitive"]),
        "tier0": tier0, "tier1": tier1, "tier2": tier2,
        "if_all_triggered": tier0 + tier1,
        "by_bucket": by_bucket,
        "items": items,
    }


# --- first-turn footprint (2026.07.12-CONTEXT-ECONOMY P5.1) --------------------
# Невидимый always-on бюджет — первопричина инцидента (findings/P0-rag-context-economy.md,
# RAG:✅ 2026-07-12). Пять источников always-on нагрузки первого хода проекта:
# skills meta (⊕ tier-0), .claude/agents description, CLAUDE.md + path-less rules,
# живой прогон SessionStart-хуков, MCP tool-defs.
#
# Пороги пере-изданы 2026-07-31 (2026.07.31-SKM-LEAN D83, решение владельца по OQ-1)
# против baseline флота — plans/archive/2026.07.31-SKM-LEAN/findings/P1-fleet-baseline.md,
# n=22, якорь 3003d352. Прежняя пара 7 000/10 000 калибровалась на величине, которая
# НЕ считала marketplace-плагины (считать их было нечем до P1.1), и потому давала
# WARN у 95 % флота: гейт, красный у всех, нормы от аварии не отличает. Медиана
# плагинной суммы по флоту — 8 741 ток, поэтому тот же по смыслу порог на
# плагин-инклюзивной величине равен 7 000 + 8 741 ≈ 16 000, а полоса сохраняет
# прежнее отношение warn/target 1,43 → 23 000. Распределение флота на новой паре
# (session_total): OK 23 % · ELEVATED 32 % · WARN 45 %.
FIRST_TURN_TARGET_MAX = 16_000
FIRST_TURN_WARN = 23_000
HOOK_TIMEOUT = 10

# Известные MCP-серверы → число tool-схем, резидентных в system prompt (грубо;
# maind точный — packages/maind/lib/maind/mcp.py::TOOLS). Неизвестный сервер из
# .mcp.json — FALLBACK_MCP_TOOLS (flat-оценка, не 0 и не завышение). `boost` —
# алиас `laravel-boost`, замечен у vintera/cms (одна раздача, два имени сервера
# во флоте — P2.3 Scope Included).
KNOWN_MCP_TOOLS = {
    "maind": 11, "perplexity-web": 4, "context7": 2, "sequential-thinking": 1,
    "fetch": 1, "memory": 9, "filesystem": 11, "github": 20, "playwright": 21,
    "serena": 20, "laravel-boost": 15, "boost": 15,
}
FALLBACK_MCP_TOOLS = 5
TOKENS_PER_MCP_TOOL = 150

# --- режим-зависимая модель стоимости MCP (P2.3, D19/D22) ---------------------
# RAG:✅ 2026-07-31 <https://code.claude.com/docs/en/mcp> §«Scale with MCP tool
# search» + <https://code.claude.com/docs/en/context-window> §«MCP tools
# (deferred)» + <https://code.claude.com/docs/en/features-overview> §«Context
# cost by feature»: tool search включён ПО УМОЛЧАНИЮ (deferred) — на старте
# сессии резидентны только ИМЕНА инструментов + инструкции сервера, полные
# схемы подгружаются по запросу; `ENABLE_TOOL_SEARCH=auto` — пороговый режим
# (грузит схемы вперёд, если укладываются в 10% контекстного окна модели);
# `ENABLE_TOOL_SEARCH=false` — старая модель, все схемы вперёд (TOKENS_PER_MCP_TOOL
# выше — эта ветка). Переменная НЕ выставляется нигде в репозитории (D22) —
# измеритель её только ЧИТАЕТ.
ENABLE_TOOL_SEARCH_ENV = "ENABLE_TOOL_SEARCH"
MCP_MODE_DEFERRED = "deferred"
MCP_MODE_AUTO = "auto"
MCP_MODE_OFF = "off"
MCP_MODE_SOURCE_DEFAULT = "default"

# Резидентное имя инструмента в deferred-режиме — НИЖНЯЯ граница, не измерение:
# `context-economy/SKILL.md:89` уже несёт цифру «lazy tool-search cuts schemas
# ~84%» (тот же факт, что прозой знает `mcp-advisor/SKILL.md:113-117`) —
# 150 ток/схема × (1 − 0.84) ≈ 24 ток/имя. Точность — не наша (репозиторий не
# видит `/context` изнутри агента, RAG:— repo-grounded `findings/…probe §9`).
TOKENS_PER_MCP_TOOL_NAME = 24
# Инструкции сервера, когда их текст НЕ доступен локально (внешний бинарник/
# пакет, напр. perplexity-web/serena) — грубый фолбэк на короткий блок
# инструкций одного сервера (симметрично FALLBACK_MCP_TOOLS у эйджер-модели):
# не 0 и не завышение.
FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS = 40


def _maind_server_instructions_tokens():
    """`maind` — единственный известный сервер, чей исходник лежит в этом
    монорепо (`packages/maind/lib/maind/mcp.py`): ответ `initialize` не несёт
    поля `instructions` (`mcp.py` — `_result(req_id, {"protocolVersion": …,
    "capabilities": …, "serverInfo": …})`) — резидентный текст инструкций
    равен 0 ФАКТИЧЕСКИ, это не фолбэк."""
    return 0


# Серверы, чей текст инструкций проверен по локальному исходнику (Implementation
# Rules P2.3 §4) — ключ отсутствует ⇒ фолбэк FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS.
_LOCAL_MCP_SERVER_INSTRUCTIONS = {"maind": _maind_server_instructions_tokens}


def _tool_search_mode(target):
    """Эффективный режим tool search: окружение процесса → `env` в
    `.claude/settings.local.json` → `env` в `.claude/settings.json` → дефолт
    «включён» (D22, Implementation Rules P2.3 §2). Возвращает (mode, source);
    source печатается в отчёте — число без происхождения не публикуется."""
    val = os.environ.get(ENABLE_TOOL_SEARCH_ENV)
    source = "env" if val is not None else None
    if val is None:
        target = Path(target)
        for fname in ("settings.local.json", "settings.json"):
            f = target / ".claude" / fname
            if not f.is_file():
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            v = data.get("env", {}).get(ENABLE_TOOL_SEARCH_ENV)
            if v is not None:
                val, source = v, fname
                break
    if val is None:
        return MCP_MODE_DEFERRED, MCP_MODE_SOURCE_DEFAULT
    val_norm = str(val).strip().lower()
    if val_norm == "auto":
        return MCP_MODE_AUTO, source
    if val_norm in ("false", "0", "off"):
        return MCP_MODE_OFF, source
    return MCP_MODE_DEFERRED, source

# --- модель листингового бюджета Claude Code (P3.4, RAG:✅ /docs/en/skills) ----
# «The listing always contains every skill name … Claude Code shortens
# descriptions to fit the listing's character budget … drops descriptions
# starting with the skills you invoke least.» Клиент режет каждую запись ДО
# 1 536 симв (description+when_to_use; name — всегда полностью) и держит сумму
# листинга под потолком budget = context_window * fraction (дефолт 1%,
# настраивается `skillListingBudgetFraction`/`SLASH_COMMAND_TOOL_CHAR_BUDGET` —
# оба параметризуемы здесь, а не зашиты, см. Implementation Rules P3.4).
# Порядок «дропа» зависит от истории вызовов проекта, которой у нас нет —
# `_measure_skills` МОДЕЛИРУЕТ потолок (после-бюджета = min(сумма, потолок)),
# не порядок дропа конкретных записей; это Scope Included P3.4, не полная
# симуляция клиента.
SKILL_LISTING_MAX_ENTRY_CHARS = 1_536
SKILL_LISTING_BUDGET_FRACTION = 0.01
SKILL_LISTING_CONTEXT_WINDOW = 1_000_000

# --- модель листингового бюджета Codex (P3.4, RAG:✅ learn.chatgpt.com/docs/build-skills,
# 2026-07-29) --------------------------------------------------------------------------
# «The skills list uses at most 2% of the model's context window, or 8,000 characters when
# the context window is unknown.» / «If many skills are installed, Codex shortens skill
# descriptions first. For large skill sets, Codex may omit some skills from the initial list
# and show a warning.» ЕДИНИЦА — СИМВОЛЫ напрямую (не токены, не переводится ×3, как у
# Claude Code выше) — единицы двух моделей НЕ смешиваются (D52). Реальное контекстное окно,
# которое Codex CLI считает «известным» для текущей модели, не измерено (round-trip вне
# скоупа, D3) — поэтому расчёт всегда ведётся по ХУДШЕМУ случаю: фолбэк-бюджету, а не по
# `CODEX_LISTING_BUDGET_FRACTION * окно` (зависимость от реального окна — [UNVERIFIED],
# см. artifacts/P3-skill-listing-budget.md). Per-entry cap на запись Codex первоисточник не
# называет (в отличие от `SKILL_LISTING_MAX_ENTRY_CHARS` у Claude) — измеряется сырая сумма.
CODEX_LISTING_FALLBACK_CHARS = 8_000
CODEX_LISTING_BUDGET_FRACTION = 0.02

LISTING_PROVIDERS = ("claude-code", "codex", "cursor")
DEFAULT_LISTING_PROVIDER = "claude-code"

MEASUREMENT_SURFACES = frozenset({"listing", "loaded-body", "runtime"})
MEASUREMENT_CLASSES = frozenset({
    "exact", "estimate", "lower-bound", "upper-bound", "unknown",
})
MEASUREMENT_STATUSES = frozenset({"pass", "over-budget", "stale", "unknown"})
MEASUREMENT_TTL = timedelta(days=30)

# --- какие записи в резидентный листинг НЕ входят (P3.2, D95/D96) --------------
# Пере-издание модели по НАБЛЮДЕНИЮ стенда P3.1/P3.6 на живой 2.1.220, а не по
# доку (`plan.md` §2 «Правило внешних фактов»). Оба поля сняли запись целиком,
# дельта воспроизведена байт-в-байт в обоих прогонах:
#   • `disable-model-invocation: true` — ось A −88
#     (`plans/archive/2026.07.31-SKM-LEAN/findings/P3-native-fields-smoke.md` §3.2), это же
#     говорит first-party док: «Description **not** in context»
#     (<https://code.claude.com/docs/en/skills> §«Control who invokes a skill»);
#   • `paths:` — ось A −88, ТА ЖЕ величина (там же §3.1/§4). Доку это
#     противоречит («The listing always contains every skill name»), поэтому
#     основание — наблюдение. Дозамер P3.6 назвал механизм: (C) условная
#     загрузка с условием «сессия ПРОЧЛА совпавший файл», а НЕ «файл лежит в
#     дереве» (`findings/P3-paths-mechanism.md` §2). Условие по ДЕРЕВУ в модель
#     не вносится: плечо A1 дозамера («совпавший файл лежит») дало
#     «неразличимо» в обоих прогонах — запись не возвращается (там же §3), а
#     недоказанное занижение хуже известного завышения (Implementation Rules
#     P3.2 §2). На ПЕРВОМ ходу прочитанных файлов нет по построению, поэтому для
#     first-turn-модели исключение безусловно.
# Поля НЕ измерены для Codex (стенд гонял только Claude Code — версия клиента
# первой строкой файла-вердикта), поэтому исключение применяется ТОЛЬКО к
# provider `claude-code`; codex-ветка сознательно продолжает завышать.
LISTING_EXCLUDED_BY_FIELDS = ("disable-model-invocation", "paths")
LISTING_EXCLUSION_PROVIDERS = ("claude-code",)


def _listing_exclusion(skill_dir):
    """Поле frontmatter, по которому запись скилла НЕ входит в резидентный
    листинг Claude Code, либо None. Порядок проверки = порядок
    `LISTING_EXCLUDED_BY_FIELDS`; первое совпадение и есть причина (запись
    снимается один раз, двух причин у одной записи не бывает)."""
    md = Path(skill_dir) / "SKILL.md"
    if not md.is_file():
        return None
    try:
        fm = parse_frontmatter(md)
    except Exception:
        return None
    if str(fm.get("disable-model-invocation", "")).strip().lower() == "true":
        return "disable-model-invocation"
    if fm.get("paths"):
        return "paths"
    return None


def _split_listing_entries(dirs, provider=DEFAULT_LISTING_PROVIDER):
    """(включённые в листинг каталоги, {поле-причина: [каталоги]}) для провайдера.
    Провайдер вне `LISTING_EXCLUSION_PROVIDERS` — исключений нет вовсе (поля для
    него не измерены)."""
    if provider not in LISTING_EXCLUSION_PROVIDERS:
        return list(dirs), {}
    included, excluded = [], {}
    for d in dirs:
        field = _listing_exclusion(d)
        if field is None:
            included.append(d)
        else:
            excluded.setdefault(field, []).append(d)
    return included, excluded


def format_listing_exclusions(excluded_by):
    """Каноническая строка отчёта об исключённых записях (`{поле: N}`) —
    ОДНА форма для first-turn и для `--provider`-отчёта, чтобы число исключений
    не разошлось между двумя печатями."""
    if not excluded_by:
        return "исключено записей: 0"
    total = sum(excluded_by.values())
    by = ", ".join(f"{f}: {n}" for f, n in sorted(excluded_by.items()))
    return f"исключено записей: {total} (по полю {by})"


def _listing_entry_tokens(skill_dir):
    """⊕ tier-0 ОДНОЙ записи листинга, как считает клиент: `name` без обрезки +
    `description`(+`when_to_use`, если фронтматтер несёт поле), капнутые до
    SKILL_LISTING_MAX_ENTRY_CHARS символов. Отдельно от `skill_budget.tier0`
    (используется `budget_for_set`/`--check-core`/картой бюджета — та математика
    вне Scope P3.4, Files item'а её не трогает)."""
    skill_dir = Path(skill_dir)
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return 0
    fm = parse_frontmatter(md)
    name = fm.get("name", "") or skill_dir.name
    desc_text = (fm.get("description", "") + " " + fm.get("when_to_use", "")).strip()
    return estimate_tokens(name) + estimate_tokens(
        desc_text[:SKILL_LISTING_MAX_ENTRY_CHARS])


def _listing_entry_chars(skill_dir):
    """Запись листинга Codex в СЫРЫХ СИМВОЛАХ: `name` + `description`(+`when_to_use`),
    БЕЗ капа — первоисточник не называет числа для Codex (в отличие от 1 536 у Claude
    Code), поэтому честный замер — сырая сумма, не угаданный потолок."""
    skill_dir = Path(skill_dir)
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return 0
    fm = parse_frontmatter(md)
    name = fm.get("name", "") or skill_dir.name
    desc_text = (fm.get("description", "") + " " + fm.get("when_to_use", "")).strip()
    return len(name) + len(desc_text)


def measure_listing_budget(skills, provider=DEFAULT_LISTING_PROVIDER):
    """Provider-aware бюджет обнаружения (листинга) для активного набора скиллов
    `[(bucket, rel, dir, fm_name)]` (P3.4). Две модели, две единицы — НЕ смешиваются
    (D52): Claude Code — 1% контекстного окна в ТОКЕНАХ (см. `_listing_entry_tokens`);
    Codex — фолбэк 8 000 СИМВОЛОВ (худший случай — реальное окно [UNVERIFIED], D3).
    Записи, снятые с листинга нативным полем (`LISTING_EXCLUDED_BY_FIELDS`,
    P3.2/D95/D96), в `raw` не входят; их число и цена приезжают АДДИТИВНЫМИ
    ключами `excluded`/`excluded_by`/`excluded_raw` (D16 — смысл прежних ключей
    не меняется).
    → {provider, unit, raw, budget, over, degradation, excluded, excluded_by,
       excluded_raw}."""
    if provider not in LISTING_PROVIDERS:
        die(f"неизвестный --provider: {provider} (ожидается: "
            f"{', '.join(LISTING_PROVIDERS)})")
    all_dirs = [d for _bucket, _rel, d, _fm in skills]
    dirs, excluded = _split_listing_entries(all_dirs, provider)
    entry = _listing_entry_chars if provider in ("codex", "cursor") else _listing_entry_tokens
    if provider in ("codex", "cursor"):
        budget = CODEX_LISTING_FALLBACK_CHARS
        unit = "симв"
        degradation = "скилл может быть выброшен из листинга целиком"
    else:
        budget = int(SKILL_LISTING_CONTEXT_WINDOW * SKILL_LISTING_BUDGET_FRACTION)
        unit = "ток"
        degradation = "описание усекается, имя остаётся"
    raw = sum(entry(d) for d in dirs)
    excluded_raw = sum(entry(d) for ds in excluded.values() for d in ds)
    return {"provider": provider, "unit": unit, "raw": raw, "budget": budget,
            "over": raw > budget, "degradation": degradation,
            "excluded": sum(len(ds) for ds in excluded.values()),
            "excluded_by": {f: len(ds) for f, ds in sorted(excluded.items())},
            "excluded_raw": excluded_raw}


def _measurement_timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("SKILL_MEASUREMENT_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("SKILL_MEASUREMENT_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError("SKILL_MEASUREMENT_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def _measurement_number(value, *, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("SKILL_MEASUREMENT_VALUE_INVALID")
    if not math.isfinite(value):
        raise ValueError("SKILL_MEASUREMENT_VALUE_INVALID")


def make_measurement(*, provider, surface, value, unit, method, uncertainty,
                     measurement_class, observed_at, expires_at, source_id,
                     threshold, evaluated_at=None, model=None, model_family=None):
    """Build one closed provider-qualified measurement row.

    The row carries exactly one model identity and keeps its own unit/class and
    provider/surface threshold.  No cross-row arithmetic is performed here.
    ``unknown`` is the sole class permitted to use a null value.
    """
    for label, item in {
            "provider": provider, "unit": unit, "method": method,
            "uncertainty": uncertainty, "source_id": source_id}.items():
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"SKILL_MEASUREMENT_{label.upper()}_INVALID")
    if surface not in MEASUREMENT_SURFACES:
        raise ValueError("SKILL_MEASUREMENT_SURFACE_INVALID")
    if measurement_class not in MEASUREMENT_CLASSES:
        raise ValueError("SKILL_MEASUREMENT_CLASS_INVALID")
    identities = [item for item in (model, model_family) if item is not None]
    if len(identities) != 1 or not isinstance(identities[0], str) or not identities[0].strip():
        raise ValueError("SKILL_MEASUREMENT_MODEL_IDENTITY_INVALID")
    _measurement_number(value, nullable=measurement_class == "unknown")
    if (measurement_class == "unknown") != (value is None):
        raise ValueError("SKILL_MEASUREMENT_CLASS_VALUE_MISMATCH")
    _measurement_number(threshold)
    observed = _measurement_timestamp(observed_at)
    expires = _measurement_timestamp(expires_at)
    if expires <= observed:
        raise ValueError("SKILL_MEASUREMENT_FRESHNESS_INVALID")
    evaluated = _measurement_timestamp(evaluated_at or observed_at)
    if evaluated >= expires:
        status = "stale"
    elif measurement_class == "unknown":
        status = "unknown"
    elif value > threshold:
        status = "over-budget"
    else:
        status = "pass"
    row = {
        "provider": provider,
        "surface": surface,
        "value": value,
        "unit": unit,
        "method": method,
        "uncertainty": uncertainty,
        "measurement_class": measurement_class,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "source_id": source_id,
        "status": status,
        "threshold": threshold,
    }
    row["model" if model is not None else "model_family"] = identities[0]
    return row


def aggregate_measurements(rows):
    """Validate and deterministically order independent measurement rows.

    Aggregation never sums rows.  A provider/model/surface may carry bounds as
    separate observations, but exact and estimated values (or differing units)
    cannot coexist under one identity because that would invite a mixed scalar.
    Provider IDs are open: a third provider needs rows, not a schema change.
    """
    accepted = []
    by_identity = {}
    thresholds = {}
    expected_base = {
        "provider", "surface", "value", "unit", "method", "uncertainty",
        "measurement_class", "observed_at", "expires_at", "source_id",
        "status", "threshold",
    }
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("SKILL_MEASUREMENT_ROW_INVALID")
        model_keys = {key for key in ("model", "model_family") if key in row}
        if len(model_keys) != 1 or set(row) != expected_base | model_keys:
            raise ValueError("SKILL_MEASUREMENT_SCHEMA_INVALID")
        rebuilt = make_measurement(
            provider=row["provider"], surface=row["surface"], value=row["value"],
            unit=row["unit"], method=row["method"], uncertainty=row["uncertainty"],
            measurement_class=row["measurement_class"], observed_at=row["observed_at"],
            expires_at=row["expires_at"], source_id=row["source_id"],
            threshold=row["threshold"], evaluated_at=(
                row["expires_at"] if row["status"] == "stale" else row["observed_at"]),
            **{key: row[key] for key in model_keys},
        )
        if rebuilt["status"] != row["status"] or row["status"] not in MEASUREMENT_STATUSES:
            raise ValueError("SKILL_MEASUREMENT_STATUS_INVALID")
        model_key = next(iter(model_keys))
        identity = (row["provider"], model_key, row[model_key], row["surface"])
        threshold_key = (row["provider"], row["surface"], row["unit"])
        if (threshold_key in thresholds
                and thresholds[threshold_key] != row["threshold"]):
            raise ValueError("SKILL_MEASUREMENT_THRESHOLD_CONFLICT")
        thresholds[threshold_key] = row["threshold"]
        peers = by_identity.setdefault(identity, [])
        if any(peer["measurement_class"] == row["measurement_class"] for peer in peers):
            raise ValueError("SKILL_MEASUREMENT_DUPLICATE")
        classes = {peer["measurement_class"] for peer in peers} | {row["measurement_class"]}
        if {"exact", "estimate"} <= classes:
            raise ValueError("SKILL_MEASUREMENT_CLASS_MIXED")
        if any(peer["unit"] != row["unit"] for peer in peers):
            raise ValueError("SKILL_MEASUREMENT_UNIT_MIXED")
        peers.append(row)
        accepted.append(dict(row))
    ordered = sorted(accepted, key=lambda row: (
        row["provider"], "model" not in row,
        row.get("model", row.get("model_family", "")), row["surface"],
        row["measurement_class"], row["source_id"],
    ))
    return {
        "status": "green" if ordered and all(
            row["status"] == "pass" for row in ordered) else "non-green",
        "rows": ordered,
    }


def listing_measurements(skills, *, observed_at=None, evaluated_at=None):
    """Current Claude/Codex listing estimates as typed independent rows."""
    observed = (_measurement_timestamp(observed_at).strftime("%Y-%m-%dT%H:%M:%SZ")
                if observed_at else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    expires = (_measurement_timestamp(observed) + MEASUREMENT_TTL).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for provider in LISTING_PROVIDERS:
        legacy = measure_listing_budget(skills, provider)
        rows.append(make_measurement(
            provider=provider,
            model_family="unknown",
            surface="listing",
            value=legacy["raw"],
            unit="characters" if provider in ("codex", "cursor") else "estimated_tokens",
            method=("skiller:listing-characters-v1" if provider in ("codex", "cursor")
                    else "skiller:listing-token-estimate-v1"),
            uncertainty=("exact source characters; provider loading is estimated"
                         if provider in ("codex", "cursor") else "heuristic token estimate"),
            measurement_class="estimate",
            observed_at=observed,
            expires_at=expires,
            source_id="skiller.budget.listing",
            threshold=legacy["budget"],
            evaluated_at=evaluated_at or observed,
        ))
    return aggregate_measurements(rows)


def format_listing_report(report):
    """Человекочитаемая строка `measure_listing_budget` для CLI (--profile + --provider)."""
    status = "ПЕРЕБОР" if report["over"] else "ок"
    ratio = (f" (×{report['raw'] / report['budget']:.1f})"
             if report["over"] and report["budget"] else "")
    lines = [
        "", f"─── Бюджет обнаружения (листинг), provider: {report['provider']} ───",
        f"Листинг: {report['raw']} {report['unit']}  vs  бюджет {report['budget']} "
        f"{report['unit']}  — {status}{ratio}"]
    if report.get("excluded"):
        lines.append(f"{format_listing_exclusions(report['excluded_by'])} — "
                     f"{report['excluded_raw']} {report['unit']} вне листинга")
    lines += [f"Режим деградации: {report['degradation']}", ""]
    return "\n".join(lines)


def profiles_listing_report(env):
    """Бюджет обнаружения КАЖДОГО поставляемого профиля (`profiles/*.json`) против ОБОИХ
    провайдеров — режим замера `--profiles` (P3.4 Scope Included). Тот же производственный
    путь, что раздача connect-канала (`resolve_active_set` + курируемый `core@`)."""
    rows = []
    for name in sorted(p.stem for p in (env.root / "profiles").glob("*.json")):
        skills, _meta = resolve_active_set(env, env.root, {}, profile=name)
        rows.append({
            "profile": name, "count": len(skills),
            "codex": measure_listing_budget(skills, "codex"),
            "claude-code": measure_listing_budget(skills, "claude-code"),
        })
    return rows


def format_profiles_listing_report(rows):
    out = ["", "━━━ БЮДЖЕТ ОБНАРУЖЕНИЯ ПО ПРОФИЛЯМ (provider-aware, P3.4) ━━━━━━━━━━━━━━━",
          "", "| Профиль | Скиллов | Codex (симв) | vs фолбэк 8000 | Claude Code (ток) "
          "| vs бюджет 1% @1M |", "|:--|--:|--:|:--|--:|:--|"]
    for r in rows:
        c, k = r["codex"], r["claude-code"]
        out.append(f"| {r['profile']} | {r['count']} | {c['raw']} | "
                   f"{'ПЕРЕБОР' if c['over'] else 'ок'} | {k['raw']} | "
                   f"{'ПЕРЕБОР' if k['over'] else 'ок'} |")
    out.append("")
    return "\n".join(out)


def _managed_skill_measurement(env, target, provider, *,
                               listing_fraction=SKILL_LISTING_BUDGET_FRACTION,
                               listing_context_window=SKILL_LISTING_CONTEXT_WINDOW):
    """Резидент листинга активного набора скиллов проекта — модель бюджета
    выше (cap на запись + потолок = context_window*fraction), не сумма всех
    описаний (тот переучёт был причиной D22/[POSSIBLE-DEFECT] в разведке P3.4).
    n/a на любой сбой (незнакомый бакет в чужом .swissknife.json и т.п.) — не
    должно ронять весь отчёт."""
    try:
        config = load_config(env, target)
        skills, meta = resolve_active_set(env, target, config)
        all_dirs = [d for _bucket, _rel, d, _fm in skills]
        dirs, excluded = _split_listing_entries(all_dirs, provider)
        raw = sum(_listing_entry_tokens(d) for d in dirs)
        budget = int(listing_context_window * listing_fraction)
        resident = min(raw, budget)
        detail = f"{len(skills)} скиллов"
        if excluded:
            detail += f", в листинге {len(dirs)}"
        if raw > budget:
            detail += (f", листинг {raw} > бюджет {budget} ток → резидент "
                      f"{resident} (клиент дропает редко вызываемые описания)")
        return {"tokens": resident, "raw_tokens": raw, "listing_budget": budget,
                "desired_plugins": list(config.plugins),
                "excluded": sum(len(ds) for ds in excluded.values()),
                "excluded_by": {f: len(ds) for f, ds in sorted(excluded.items())},
                "excluded_raw": sum(_listing_entry_tokens(d)
                                    for ds in excluded.values() for d in ds),
                "detail": detail}
    except (Exception, SystemExit) as e:
        return {"tokens": None, "detail": f"n/a ({e})"}


def _measure_skills(env, target, *, provider=DEFAULT_LISTING_PROVIDER,
                    listing_fraction=SKILL_LISTING_BUDGET_FRACTION,
                    listing_context_window=SKILL_LISTING_CONTEXT_WINDOW):
    """Use provider-observed skill inventory when the provider exposes it."""
    managed = _managed_skill_measurement(
        env, target, provider,
        listing_fraction=listing_fraction,
        listing_context_window=listing_context_window)
    if provider != "codex":
        managed["measurement"] = "managed-estimate"
        return managed

    observed = native_inventory(env, target)
    managed_fields = {
        "managed_tokens": managed.get("tokens"),
        "managed_raw_tokens": managed.get("raw_tokens"),
        "managed_detail": managed.get("detail"),
        "desired_plugins": managed.get("desired_plugins", []),
    }
    if not observed["ok"]:
        return {
            **managed_fields,
            "tokens": None,
            "detail": "; ".join(observed["notes"]),
            "measurement": "provider-unavailable",
            "observed_count": None,
            "enabled_plugins": observed.get("enabled", []),
            "duplicates": [],
        }

    entries = []
    for name, paths in sorted(observed["paths"].items()):
        for raw_path in paths:
            path = Path(raw_path)
            tokens = None
            try:
                fm = parse_frontmatter(path)
                tokens = estimate_tokens(
                    f"{fm.get('name', name) or name} {fm.get('description', '')}")
            except (OSError, ValueError, TypeError):
                pass
            entries.append({"name": name, "path": raw_path, "tokens": tokens})
    missing = [entry for entry in entries if entry["tokens"] is None]
    duplicates = [
        {"name": name, "paths": list(paths)}
        for name, paths in sorted(observed["paths"].items()) if len(paths) > 1
    ]
    total = None if missing else sum(entry["tokens"] for entry in entries)
    desired = set(managed.get("desired_plugins", []))
    outside_policy = sorted(set(observed["enabled"]) - desired) if desired else []
    not_effective = sorted(desired - set(observed["enabled"]))
    return {
        **managed_fields,
        "tokens": total,
        "raw_tokens": total,
        "detail": (f"Codex observed: {len(entries)} entries / "
                   f"{len(observed['names'])} unique names; managed: "
                   f"{managed.get('detail', 'n/a')}")
                  + (f"; {len(missing)} unreadable" if missing else ""),
        "measurement": "provider-observed" if total is not None else "provider-partial",
        "observed_count": len(entries),
        "observed_unique_names": len(observed["names"]),
        "enabled_plugins": observed["enabled"],
        "enabled_outside_project_policy": outside_policy,
        "desired_plugins_not_effective": not_effective,
        "duplicates": duplicates,
    }


def _measure_agents(target, provider=DEFAULT_LISTING_PROVIDER):
    """name+description каждого .claude/agents/*.md (frontmatter) — тот же
    always-on «налог», что у скиллов, но для субагентов проекта."""
    if provider == "codex":
        return {"tokens": 0,
                "detail": "Codex repo agents are provider-managed, not .claude/agents"}
    d = Path(target) / ".claude" / "agents"
    if not d.is_dir():
        return {"tokens": 0, "detail": "нет .claude/agents"}
    total, count = 0, 0
    for p in sorted(d.glob("*.md")):
        try:
            fm = parse_frontmatter(p)
        except Exception:
            continue
        total += estimate_tokens(f"{fm.get('name', p.stem)} {fm.get('description', '')}")
        count += 1
    return {"tokens": total, "detail": f"{count} агентов"}


def _measure_claude_md(target):
    """CLAUDE.md проекта + .claude/rules/**/*.md БЕЗ `paths:` (path-scoped rules
    не always-on — грузятся только на затронутый файл, см. skill-authoring/
    context-economy канон). `**` — подкаталоги `.claude/rules/` тоже always-on
    источник (апстрим: «subdirectories … are discovered automatically»,
    RAG:✅ `findings/…probe §6`) — плоский `*.md` их пропускал (P2.3 находка)."""
    target = Path(target)
    total, parts, n_rules = 0, [], 0
    claude_md = target / "CLAUDE.md"
    if claude_md.is_file():
        try:
            t = estimate_tokens(claude_md.read_text(encoding="utf-8", errors="ignore"))
            total += t
            parts.append(f"CLAUDE.md={t}")
        except Exception:
            parts.append("CLAUDE.md=n/a")
    rules_dir = target / ".claude" / "rules"
    if rules_dir.is_dir():
        for p in sorted(rules_dir.glob("**/*.md")):
            try:
                fm = parse_frontmatter(p)
            except Exception:
                continue
            if fm.get("paths"):
                continue
            total += estimate_tokens(p.read_text(encoding="utf-8", errors="ignore"))
            n_rules += 1
    detail = " + ".join(parts) if parts else "нет CLAUDE.md"
    if n_rules:
        detail += f" + {n_rules} rules без paths"
    return {"tokens": total, "detail": detail}


def _measure_instructions(target, provider=DEFAULT_LISTING_PROVIDER):
    if provider == "claude-code":
        value = _measure_claude_md(target)
        value["surface"] = "CLAUDE.md + .claude/rules"
        return value
    target = Path(target)
    agents_md = target / "AGENTS.md"
    if not agents_md.is_file():
        return {"tokens": 0, "detail": "нет AGENTS.md", "surface": "AGENTS.md"}
    try:
        tokens = estimate_tokens(agents_md.read_text(encoding="utf-8", errors="ignore"))
    except OSError as error:
        return {"tokens": None, "detail": f"n/a ({error})", "surface": "AGENTS.md"}
    return {"tokens": tokens, "detail": f"AGENTS.md={tokens}", "surface": "AGENTS.md"}


def _settings_hook_commands(target, event="SessionStart"):
    """Команды хука `event` из .claude/settings.json + settings.local.json
    (merge, оба читаются — local может добавлять хуки поверх settings.json)."""
    target = Path(target)
    cmds = []
    for fname in ("settings.json", "settings.local.json"):
        f = target / ".claude" / fname
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for block in data.get("hooks", {}).get(event, []):
            for h in block.get("hooks", []):
                cmd = h.get("command")
                if cmd:
                    cmds.append(cmd)
    return cmds


def _run_hook(cmd, target, timeout=HOOK_TIMEOUT):
    """Живой прогон одного SessionStart-хука: пустой stdin, timeout, fail-soft.
    additionalContext из hookSpecificOutput JSON, иначе сырой stdout (тот же
    контракт, что читает сам Claude Code). Возвращает (tokens, ok); ok=False на
    любой сбой/таймаут/ненулевой exit — это ДАННЫЕ отчёта (хук чужого проекта
    может быть сломан), не повод падать самой команде."""
    run_env = dict(os.environ)
    run_env["CLAUDE_PROJECT_DIR"] = str(target)
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=str(target), env=run_env, input="",
            capture_output=True, text=True, timeout=timeout, check=False)
    except Exception:
        return None, False
    if result.returncode != 0:
        return None, False
    out = result.stdout.strip()
    if not out:
        return 0, True
    ctx = out
    try:
        data = json.loads(out)
        ctx = data.get("hookSpecificOutput", {}).get("additionalContext", out)
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return estimate_tokens(ctx), True


def _measure_hooks(target, timeout=HOOK_TIMEOUT, provider=DEFAULT_LISTING_PROVIDER):
    if provider != "claude-code":
        return {"tokens": 0,
                "detail": f"нет измеряемого SessionStart-контракта для {provider}"}
    cmds = _settings_hook_commands(target, "SessionStart")
    if not cmds:
        return {"tokens": 0, "detail": "нет SessionStart-хуков"}
    total, ok_n, fail_n = 0, 0, 0
    for cmd in cmds:
        tokens, ok = _run_hook(cmd, target, timeout=timeout)
        if ok:
            total += tokens
            ok_n += 1
        else:
            fail_n += 1
    if ok_n == 0:
        return {"tokens": None, "detail": f"n/a ({fail_n} хук(ов) сбоили)"}
    detail = f"{ok_n} хук(ов)" + (f", {fail_n} n/a" if fail_n else "")
    return {"tokens": total, "detail": detail}


def _measure_mcp(target):
    """Режим-зависимая оценка резидентной цены MCP-серверов проекта (.mcp.json,
    P2.3/D19/D22): `mode`/`mode_source` — НОВЫЕ ключи (аддитивность D16), не
    меняют `tokens`/`detail` по форме. Три ветки:
      off      — старая эйджер-модель (KNOWN_MCP_TOOLS × TOKENS_PER_MCP_TOOL),
                 честна только при ENABLE_TOOL_SEARCH=false;
      auto     — допущение «в пределах 10% контекстного окна» НЕ проверено
                 живым /context (агенту недоступен) → берём тот же эйджер-
                 потолок как явно названную верхнюю границу (Implementation
                 Rules P2.3 §3, Scope Included «auto — с явно названным
                 допущением»);
      deferred — дефолт клиента: имена инструментов (TOKENS_PER_MCP_TOOL_NAME)
                 + инструкции сервера (измерены фактически для серверов с
                 локальным исходником, иначе FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS)
                 — нижняя граница.
    Не парсим реальные схемы (сервер может быть недоступен из этого окружения)
    — это оценка, как и весь budget.py."""
    f = Path(target) / ".mcp.json"
    if not f.is_file():
        return {"tokens": 0, "detail": "нет .mcp.json", "mode": None,
                "mode_source": None, "estimate_class": None}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"tokens": None, "detail": "n/a (.mcp.json invalid JSON)",
                "mode": None, "mode_source": None, "estimate_class": None}
    servers = sorted(data.get("mcpServers", {}))
    mode, source = _tool_search_mode(target)
    if not servers:
        return {"tokens": 0, "detail": "нет серверов", "mode": mode,
                "mode_source": source, "estimate_class": None}
    if mode == MCP_MODE_OFF:
        total = sum(KNOWN_MCP_TOOLS.get(n, FALLBACK_MCP_TOOLS) * TOKENS_PER_MCP_TOOL
                   for n in servers)
        est_class = "точная модель полных схем (ENABLE_TOOL_SEARCH=false)"
    elif mode == MCP_MODE_AUTO:
        total = sum(KNOWN_MCP_TOOLS.get(n, FALLBACK_MCP_TOOLS) * TOKENS_PER_MCP_TOOL
                   for n in servers)
        est_class = ("верхняя граница (auto: допущение «в пределах 10% окна» "
                     "не проверено живым /context)")
    else:
        total = 0
        for n in servers:
            n_tools = KNOWN_MCP_TOOLS.get(n, FALLBACK_MCP_TOOLS)
            total += n_tools * TOKENS_PER_MCP_TOOL_NAME
            if n in _LOCAL_MCP_SERVER_INSTRUCTIONS:
                total += _LOCAL_MCP_SERVER_INSTRUCTIONS[n]()
            else:
                total += FALLBACK_MCP_SERVER_INSTRUCTIONS_TOKENS
        est_class = "нижняя граница (deferred: имена инструментов + инструкции сервера)"
    return {"tokens": total, "detail": f"{len(servers)} сервер(ов): " + ", ".join(servers),
           "mode": mode, "mode_source": source, "estimate_class": est_class}


_FIRST_TURN_SOURCE_LABELS = (
    ("skills", "skills meta (⊕ always)"),
    ("agents", ".claude/agents"),
    ("claude_md", "CLAUDE.md + rules"),
    ("hooks", "SessionStart-хуки (живой прогон)"),
    ("mcp", "MCP tool-defs"),
)


def _first_turn_verdict(total):
    """Трёхветочный вердикт OK/ELEVATED/WARN по порогам FIRST_TURN_TARGET_MAX/
    FIRST_TURN_WARN — единственный носитель лестницы (используется и для
    проектного `total`, и для плагин-инклюзивного `session_total`, D16)."""
    if total <= FIRST_TURN_TARGET_MAX:
        return "OK"
    elif total <= FIRST_TURN_WARN:
        return "ELEVATED"
    return "WARN"


def first_turn_report(env, target, *, provider=DEFAULT_LISTING_PROVIDER,
                      timeout=HOOK_TIMEOUT,
                      listing_fraction=SKILL_LISTING_BUDGET_FRACTION,
                      listing_context_window=SKILL_LISTING_CONTEXT_WINDOW):
    """Сумма always-on футпринта первого хода проекта по пяти источникам.
    n/a-источники (fail-soft) не участвуют в сумме — total считает только то,
    что реально измерено. Вердикт: OK ≤16K · ELEVATED ≤23K · WARN >23K
    (пороги — FIRST_TURN_TARGET_MAX/FIRST_TURN_WARN, обоснование там же:
    baseline флота plans/archive/2026.07.31-SKM-LEAN/findings/P1-fleet-baseline.md,
    D83). `listing_fraction`/
    `listing_context_window` — доля бюджета листинга скиллов и контекстное окно
    целевой модели; параметры, а не константы (P3.4 Implementation Rules —
    захардкоженный дефолт протухнет при смене `skillListingBudgetFraction`)."""
    target = Path(target).resolve()
    sources = {
        "skills": _measure_skills(env, target, provider=provider,
                                  listing_fraction=listing_fraction,
                                  listing_context_window=listing_context_window),
        "agents": _measure_agents(target, provider=provider),
        "claude_md": _measure_instructions(target, provider=provider),
        "hooks": _measure_hooks(target, timeout=timeout, provider=provider),
        "mcp": _measure_mcp(target),
    }
    total = sum(s["tokens"] for s in sources.values() if s["tokens"] is not None)
    complete = all(source["tokens"] is not None for source in sources.values())
    report = {"target": str(target), "sources": sources, "total": total,
              "verdict": _first_turn_verdict(total) if complete else "INCOMPLETE"}
    if provider != DEFAULT_LISTING_PROVIDER:
        report["provider"] = provider
        report["measurement_status"] = "complete" if complete else "incomplete"
        report["scope"] = "managed-first-turn"
        report["platform_overhead"] = "excluded"
    return report


def _format_plugins_block(plugins):
    """Блок сводки always-on marketplace-плагинов (--with-plugins, D16 —
    вызывается ТОЛЬКО когда ключ `plugins` уже в отчёте, иначе вывод не
    меняется вовсе)."""
    out = ["  Marketplace-плагины (always-on)"]
    if plugins["status"] != "ok":
        out.append(f"    n/a — {'; '.join(plugins['warnings']) or 'листинг недоступен'}")
        return out
    if not plugins["entries"]:
        out.append("    нет enabled-плагинов")
    for e in plugins["entries"]:
        tok_str = "   n/a" if e["tokens"] is None else f"{e['tokens']:>6}"
        out.append(f"    {e['id']} ({e['scope']})".ljust(30) + f" {tok_str} ток")
    if plugins["broken"]:
        broken_str = "; ".join(f"{b['id']} ({b['reason']})" for b in plugins["broken"])
        out.append(f"    broken: {broken_str}")
    if plugins["unparsed"]:
        out.append(f"    unparsed: {'; '.join(plugins['unparsed'])}")
    if plugins["warnings"]:
        out.append(f"    warnings: {'; '.join(plugins['warnings'])}")
    out.append(f"    Итого плагины: {'n/a' if plugins['total'] is None else plugins['total']} ток"
               + ("  (partial)" if plugins["partial"] else ""))
    return out


def format_first_turn_report(report):
    out = ["", "━━━ FIRST-TURN БЮДЖЕТ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
          f"Проект: {report['target']}",
          f"Provider: {report.get('provider', 'claude-code')}", ""]
    for key, label in _FIRST_TURN_SOURCE_LABELS:
        s = report["sources"].get(key, {})
        if key == "claude_md":
            label = s.get("surface", label)
        elif key == "agents" and report.get("provider") == "codex":
            label = "provider agents"
        tok = s.get("tokens")
        tok_str = "   n/a" if tok is None else f"{tok:>6}"
        out.append(f"  {label:<28} {tok_str} ток  ({s.get('detail', '')})")
        raw = s.get("raw_tokens")
        if raw is not None and raw != tok:
            out.append(f"  {'  (сумма описаний до бюджета)':<28} {raw:>6} ток")
        if key == "skills" and s.get("excluded"):
            # P3.2: запись, снятая нативным полем, в резидент не входит — число
            # публикуется отдельной строкой (эффект ПРИБОРА, не диеты реестра).
            out.append(f"  {'  ' + format_listing_exclusions(s['excluded_by']):<28} "
                       f"{-s['excluded_raw']:>6} ток вне листинга")
        if key == "skills" and s.get("managed_tokens") is not None:
            out.append(f"  {'  managed estimate':<28} {s['managed_tokens']:>6} ток")
        if key == "skills" and s.get("duplicates"):
            names = ", ".join(row["name"] for row in s["duplicates"])
            out.append(f"  {'  duplicate names':<28} {names}")
        if key == "skills" and s.get("enabled_outside_project_policy"):
            names = ", ".join(s["enabled_outside_project_policy"])
            out.append(f"  {'  plugins outside policy':<28} {names}")
        if key == "mcp" and s.get("mode"):
            out.append(f"  {'  tool search':<28} {s['mode']} "
                       f"(источник: {s['mode_source']}) — {s['estimate_class']}")
    if "plugins" in report:
        out.append("")
        out.extend(_format_plugins_block(report["plugins"]))
    out.append("")
    out.append(f"Итого: {report['total']:>6} ток — {report['verdict']}  "
               f"(target ≤{FIRST_TURN_TARGET_MAX} · warn >{FIRST_TURN_WARN})")
    if "session_total" in report:
        out.append(f"Итого с плагинами: {report['session_total']:>6} ток — "
                   f"{report['session_verdict']}")
    out.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append("")
    return "\n".join(out)


# --- текстовый отчёт ----------------------------------------------------------
def _bar(value, scale):
    return "█" * min(40, round(value / scale)) if scale else ""


def format_report(label, b):
    """Человекочитаемый трёхъярусный отчёт по результату budget_for_set."""
    out = []
    pct = b["if_all_triggered"] / CONTEXT_LIMIT * 100
    out.append("")
    out.append("━━━ ТОКЕНОВЫЙ БЮДЖЕТ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append(f"Набор:        {label}")
    out.append(f"Скиллов:      {b['count']}  "
               f"(транзитивных via requires: {b['transitive']})")
    out.append(f"⊕ always:     {b['tier0']:>6} ток  — резидентно КАЖДЫЙ запрос "
               f"(name+description)")
    out.append(f"↻ on-trigger: {b['tier1']:>6} ток  — тела, если ВСЕ сработают")
    out.append(f"⌥ on-demand:  {b['tier2']:>6} ток  — сниппеты/references, по требованию")
    out.append(f"Σ если всё:   {b['if_all_triggered']:>6} ток  "
               f"(~{pct:.1f}% от {CONTEXT_LIMIT // 1000}K)")

    by_b = b["by_bucket"]
    if by_b:
        out.append("")
        out.append("─── По бакетам (⊕ always / ↻ bodies / скиллов) ─────────")
        for bucket in sorted(by_b, key=lambda k: by_b[k]["tier0"], reverse=True):
            a = by_b[bucket]
            out.append(f"  {bucket:<22} ⊕{a['tier0']:>5}  ↻{a['tier1']:>6}  "
                       f"({a['count']})")

    top0 = sorted(b["items"], key=lambda i: i["tier0"], reverse=True)[:TOP_N]
    if top0:
        scale = max(i["tier0"] for i in top0) / 20 or 1
        width = max(len(f"{i['bucket']}/{i['name']}") for i in top0)
        out.append("")
        out.append("─── Топ-описания (⊕ always — постоянный налог) ─────────")
        for i in top0:
            tag = " [transitive]" if i["transitive"] else ""
            label = f"{i['bucket']}/{i['name']}".ljust(width)
            out.append(f"  {label} {i['tier0']:>5} ток  "
                       f"{_bar(i['tier0'], scale)}{tag}")

    top1 = sorted(b["items"], key=lambda i: i["tier1"], reverse=True)[:TOP_N]
    if top1:
        width = max(len(f"{i['bucket']}/{i['name']}") for i in top1)
        out.append("")
        out.append("─── Топ-тела (↻ on-trigger — цена срабатывания) ────────")
        for i in top1:
            label = f"{i['bucket']}/{i['name']}".ljust(width)
            out.append(f"  {label} {i['tier1']:>5} ток")
    out.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append("")
    return "\n".join(out)


# --- разрешение конфигов для CLI ----------------------------------------------
def _load_config_file(env, path):
    p = Path(os.path.expanduser(path))
    if not p.is_file():
        die(f"конфиг не найден: {p}")
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{p}: invalid JSON: {e}")
    validate_config(env, cfg, str(p))
    return cfg, p.resolve().parent


def _config_by_name(env, name):
    """Имя из --compare → budget-configs/<name>.json (или путь, если он есть)."""
    cand = Path(os.path.expanduser(name))
    if cand.suffix == ".json" and cand.is_file():
        return _load_config_file(env, str(cand))
    return _load_config_file(env, str(env.root / "budget-configs" / f"{name}.json"))


def _budget_from_config(env, config, target, no_core):
    skills, meta = resolve_active_set(env, target, config, no_core=no_core)
    return budget_for_set(skills, meta["pulled"])


# --- CLI ----------------------------------------------------------------------
def cmd_budget(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--config": "str", "--compare": "str",
        "--profile": "str", "--buckets": "str", "--exclude": "str",
        "--json": "bool", "--no-core": "bool", "--write-map": "bool",
        "--check-core": "bool", "--strict": "bool", "--first-turn": "bool",
        "--provider": "str", "--profiles": "bool", "--with-plugins": "bool",
    })
    if opts["help"]:
        print("skiller budget [--config F.json | --compare a,b | --target DIR]\n"
              "               [--profile P | --buckets a,b] [--exclude x,y]\n"
              "               [--provider claude-code|codex|cursor] [--profiles]\n"
              "               [--no-core] [--json] [--write-map] [--check-core [--strict]]\n"
              "               [--first-turn [--provider claude-code|codex|cursor] "
              "[--json] [--strict]]\n"
              "  Трёхъярусный токеновый бюджет набора скиллов (⊕ always / ↻ on-trigger\n"
              "  / ⌥ on-demand). --write-map перегенерит docs/guide/budget.md.\n"
              "  --check-core: резидентный (⊕ tier-0) бюджет CORE_SKILLS vs target (гейт\n"
              "  против тихого роста ядра И против тихого недобора — пропавший по пути\n"
              "  CORE-скилл занижает резидент, а не улучшает его); --strict — ненулевой\n"
              "  код при превышении ИЛИ недоборе (CI).\n"
              "  --first-turn: provider-aware always-on футпринт первого хода проекта.\n"
              "  Claude измеряет CLAUDE.md/rules, agents и SessionStart; Codex — AGENTS.md\n"
              "  и фактический native prompt inventory с duplicate/policy diagnostics;\n"
              "  target ≤16K / warn >23K ток; --strict — exit 1 при WARN (CI).\n"
              "  --with-plugins (только вместе с --first-turn): добавляет always-on цену\n"
              "  установленных marketplace-плагинов проекта (`claude plugin list/details`)\n"
              "  аддитивными ключами `plugins`/`session_total`/`session_verdict` — без\n"
              "  флага вывод не меняется.\n"
              "  --provider claude-code|codex|cursor (с --profile/--config/--target): добавляет к\n"
              "  отчёту provider-aware бюджет обнаружения (листинга) и режим деградации;\n"
              "  без флага поведение не меняется (дефолт — claude-code).\n"
              "  --profiles: бюджет обнаружения КАЖДОГО поставляемого профиля против ОБОИХ\n"
              "  провайдеров (P3.4).")
        return
    no_core = opts.get("no_core", False)
    if opts.get("with_plugins") and not opts.get("first_turn"):
        die("--with-plugins требует --first-turn")

    if opts.get("write_map"):
        write_budget_map(env)
        return

    if opts.get("profiles"):
        rows = profiles_listing_report(env)
        if opts.get("json"):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print(format_profiles_listing_report(rows))
        return

    if opts.get("first_turn"):
        if opts.get("target"):
            target = Path(os.path.expanduser(opts["target"])).resolve()
        else:
            target, _via = find_project_root(env)
            if target is None:
                die("корень проекта не найден выше CWD — укажи --target")
        provider = opts.get("provider") or DEFAULT_LISTING_PROVIDER
        if provider not in ("claude-code", "codex", "cursor"):
            die("--provider: ожидался claude-code|codex|cursor")
        report = first_turn_report(env, target, provider=provider)
        if opts.get("with_plugins"):
            if provider != "claude-code":
                die("--with-plugins пока измеряет только Claude Code; для Codex используй "
                    "provider-observed inventory без этого флага")
            plugins = plugins_summary(target)
            report["plugins"] = plugins
            session_total = (report["total"] if plugins["total"] is None
                            else report["total"] + plugins["total"])
            report["session_total"] = session_total
            report["session_verdict"] = _first_turn_verdict(session_total)
        if opts.get("json"):
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_first_turn_report(report))
        if opts.get("strict") and report["verdict"] in {"WARN", "INCOMPLETE"}:
            die(f"first-turn бюджет {report['total']} ток > warn-порог "
                f"{FIRST_TURN_WARN} либо измерение неполно ({target}) — см. таблицу выше")
        return

    if opts.get("check_core"):
        tuples = core_skill_tuples(env, set())
        cards = [skill_budget(d) for (_b, _rel, d, _n) in tuples]
        cards = [c for c in cards if c]
        # core_skill_tuples/skill_budget молча пропускают CORE_SKILLS-путь без SKILL.md
        # (переезд/опечатка) — раньше пропавший скилл просто уменьшал resident и делал
        # гейт «зеленее» (аудит B-2). Недобор — отдельная ошибка, не «повезло с бюджетом».
        missing = len(CORE_SKILLS) - len(cards)
        resident = sum(c["tier0"] for c in cards)
        over = resident > RESIDENT_BUDGET_TARGET
        status = "MISSING" if missing else ("OVER" if over else "OK")
        if opts.get("json"):
            print(json.dumps({"resident_core_tier0": resident,
                              "target": RESIDENT_BUDGET_TARGET,
                              "skills": len(cards), "expected_skills": len(CORE_SKILLS),
                              "missing": missing, "status": status},
                             ensure_ascii=False))
        else:
            print(f"CORE резидент (⊕ tier-0): {resident} ток / target "
                  f"{RESIDENT_BUDGET_TARGET} — {status} "
                  f"({len(cards)}/{len(CORE_SKILLS)} скиллов)")
        if missing and opts.get("strict"):
            die(f"CORE недобор: {missing} из {len(CORE_SKILLS)} CORE_SKILLS не найдены "
                f"на диске (переезд/опечатка пути в config.py/core-policy.json) — "
                f"резидент занижен, а не улучшен")
        if over and opts.get("strict"):
            die(f"CORE резидентный бюджет {resident} > target "
                f"{RESIDENT_BUDGET_TARGET}: ужми description или пересмотри состав CORE")
        return

    if opts.get("compare"):
        names = [n for n in opts["compare"].split(",") if n]
        if len(names) < 2:
            die("--compare ждёт ≥2 конфига через запятую: --compare a,b")
        results = []
        for name in names:
            cfg, tdir = _config_by_name(env, name)
            results.append((name, _budget_from_config(env, cfg, tdir, no_core)))
        if opts.get("json"):
            print(json.dumps({n: b for n, b in results}, indent=2,
                             ensure_ascii=False))
            return
        print("\n━━━ СРАВНЕНИЕ НАБОРОВ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for name, b in results:
            print(f"  {name:<26} ⊕{b['tier0']:>5}  ↻{b['tier1']:>6}  "
                  f"Σ{b['if_all_triggered']:>6}  ({b['count']} скиллов)")
        worst = max(results, key=lambda r: r[1]["if_all_triggered"])
        print(f"  Тяжелее всего: {worst[0]}\n")
        for name, b in results:
            print(format_report(name, b))
        return

    # одиночный набор: --config | .swissknife.json из --target/CWD
    flag_buckets = [b for b in opts.get("buckets", "").split(",") if b]
    flag_exclude = [e for e in opts.get("exclude", "").split(",") if e]
    if opts.get("config"):
        config, target = _load_config_file(env, opts["config"])
        label = opts["config"]
    else:
        if opts.get("target"):
            target = Path(os.path.expanduser(opts["target"])).resolve()
        else:
            target, _via = find_project_root(env)
            if target is None:
                die("корень проекта не найден выше CWD — укажи --config или --target")
        config = load_config(env, target)
        label = str(target)
    skills, meta = resolve_active_set(
        env, target, config, profile=opts.get("profile", ""),
        flag_buckets=flag_buckets, flag_exclude=flag_exclude, no_core=no_core)
    b = budget_for_set(skills, meta["pulled"])
    listing = (measure_listing_budget(skills, opts["provider"])
              if opts.get("provider") else None)
    if opts.get("json"):
        out = {"label": label, "meta": {
            "buckets": meta["buckets"], "profile": meta["profile"],
            "source": meta["source"]}, **b}
        if listing is not None:
            out["listing"] = listing
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    print(format_report(f"{label}  [profile: {meta['profile'] or '-'} "
                        f"via {meta['source']}]", b))
    if listing is not None:
        print(format_listing_report(listing))


# --- генератор карты docs/guide/budget.md -------------------------------------
def _docs_root(p):
    """Ближайший вверх каталог с docs/guide (сам пакет; fallback — p)."""
    for cand in (p, *p.parents):
        if (cand / "docs" / "guide").is_dir():
            return cand
    return p


def _node_id(name):
    return name.replace("-", "_").replace("/", "_")


def _quantile(values, frac):
    if not values:
        return 0
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * frac))]


def render_budget_map(root, registry):
    """Текст docs/guide/budget.md (без записи) из registry-dict — mermaid-карта
    трёхъярусного бюджета + таблицы по бакетам/топам. Читает тела SKILL.md по
    registry-путям относительно root. Вынесено из write_budget_map, чтобы
    registry.check_drift мог сверить актуальность без побочной записи (R-2:
    раньше только write-путь существовал, drift-гейт этот артефакт не видел).
    Возвращает (text, n_skills, total0, total1)."""
    rows = []
    for e in registry["skills"]:
        b = skill_budget((root / e["path"]).parent)
        if b is None:
            continue
        rows.append({"name": e["name"], "bucket": e["bucket"],
                     "tier0": b["tier0"], "tier1": b["tier1"],
                     "tier2": b["tier2"], "snippets": b["snippets"],
                     "references": b["references"],
                     "requires": e.get("requires", [])})

    by_name = {r["name"]: r for r in rows}
    # heat по распределению ⊕ always (квантили — устойчиво к выбору CHARS_PER_TOKEN)
    t0_vals = [r["tier0"] for r in rows]
    q_hot, q_warm, q_mild = (_quantile(t0_vals, 0.85), _quantile(t0_vals, 0.6),
                             _quantile(t0_vals, 0.3))

    def heat(t0):
        if t0 >= q_hot:
            return "hot"
        if t0 >= q_warm:
            return "warm"
        if t0 >= q_mild:
            return "mild"
        return "cool"

    by_bucket = {}
    for r in rows:
        by_bucket.setdefault(r["bucket"], []).append(r)

    total0 = sum(r["tier0"] for r in rows)
    total1 = sum(r["tier1"] for r in rows)
    total2 = sum(r["tier2"] for r in rows)

    lines = [
        "# Карта токенового бюджета",
        "",
        "> Сгенерировано `lib/skiller/budget.py` (`skiller budget --write-map`) "
        "из `skills.json` и тел `SKILL.md` — не редактировать вручную.",
        "> Пересборка: `skiller registry`.",
        "",
        "Трёхъярусная модель раскрытия контекста — что грузит нейросеть и когда:",
        "",
        "- **⊕ always** — `name`+`description`: резидентны в КАЖДОМ запросе "
        "(по ним агент решает, применять ли скилл). Постоянный «налог».",
        "- **↻ on-trigger** — тело `SKILL.md`: грузится, только когда скилл сработал.",
        "- **⌥ on-demand** — сниппеты и references: по ссылке из тела, опционально.",
        "",
        "Цвет узла — heat по **⊕ always** (краснее = дороже постоянный налог "
        "описания). Метка `name<br/>⊕always ↻body`. Сплошная стрелка `requires` "
        "показывает транзитивный налог: ставишь скилл — тянешь always-цену "
        "зависимости. Оценка токенов грубая и языко-зависимая (кириллица "
        f"~{CHARS_PER_TOKEN_CYR:g} chars/tok, латиница/код ~{CHARS_PER_TOKEN_LAT:g}) "
        "— для сравнения наборов, не точного учёта.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for bucket in sorted(by_bucket):
        lines.append(f"  subgraph {_node_id(bucket)}[\"{bucket}\"]")
        for r in sorted(by_bucket[bucket], key=lambda x: x["name"]):
            label = f"{r['name']}<br/>⊕{r['tier0']} ↻{r['tier1']}"
            lines.append(f"    {_node_id(r['name'])}[\"{label}\"]:::{heat(r['tier0'])}")
        lines.append("  end")
    # рёбра requires — только когда оба конца на карте
    edges = sorted({(r["name"], dep) for r in rows for dep in r["requires"]
                    if dep in by_name})
    for src, dst in edges:
        lines.append(f"  {_node_id(src)} -->|requires| {_node_id(dst)}")
    lines += [
        "  classDef hot fill:#c0392b,color:#fff,stroke:#7b241c;",
        "  classDef warm fill:#e67e22,color:#fff,stroke:#a04000;",
        "  classDef mild fill:#f1c40f,color:#222,stroke:#b7950b;",
        "  classDef cool fill:#27ae60,color:#fff,stroke:#1e8449;",
        "```",
        "",
        f"**Итого:** {len(rows)} скиллов · ⊕ always **{total0}** ток "
        f"(резидентно всегда, если включить весь реестр) · ↻ bodies {total1} ток "
        f"· ⌥ on-demand {total2} ток (сниппеты + references).",
        "",
        "## По бакетам",
        "",
        "| Бакет | Скиллов | ⊕ always | ↻ bodies | ⌥ on-demand |",
        "|---|--:|--:|--:|--:|",
    ]
    for bucket in sorted(by_bucket, key=lambda k: sum(
            r["tier0"] for r in by_bucket[k]), reverse=True):
        rs = by_bucket[bucket]
        lines.append(f"| `{bucket}` | {len(rs)} | {sum(r['tier0'] for r in rs)} "
                     f"| {sum(r['tier1'] for r in rs)} "
                     f"| {sum(r['tier2'] for r in rs)} |")

    def _top_table(title, key, note):
        out = ["", f"## {title}", "", note, "",
               "| Скилл | Бакет | ток |", "|---|---|--:|"]
        for r in sorted(rows, key=lambda x: x[key], reverse=True)[:TOP_N]:
            out.append(f"| `{r['name']}` | {r['bucket']} | {r[key]} |")
        return out

    lines += _top_table("Топ ⊕ always (постоянный налог)", "tier0",
                        "Самые дорогие описания — резидентны в каждом запросе.")
    lines += _top_table("Топ ↻ on-trigger (цена срабатывания)", "tier1",
                        "Самые тяжёлые тела — грузятся при применении скилла.")
    lines.append("")
    return "\n".join(lines), len(rows), total0, total1


def write_budget_map(env):
    """Сгенерировать docs/guide/budget.md (атомарно) из skills.json на диске."""
    root = env.root
    reg_file = root / "skills.json"
    if not reg_file.is_file():
        die("skills.json не найден — сначала прогони `skiller registry`")
    registry = json.loads(reg_file.read_text(encoding="utf-8"))
    text, n_skills, total0, total1 = render_budget_map(root, registry)
    out = _docs_root(root) / "docs" / "guide" / "budget.md"
    atomic_write_text(out, text)
    print(f"Updated {out.relative_to(_docs_root(root))}: {n_skills} skills, "
          f"⊕{total0} ↻{total1} ток")
