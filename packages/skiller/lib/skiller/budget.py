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
from pathlib import Path

from core import atomic_write_text

from .common import die, parse_flags, parse_frontmatter
from .config import (CORE_SKILLS, DEFAULT_EXCLUDE, RESIDENT_BUDGET_TARGET,
                     all_buckets, core_skill_tuples, find_project_root,
                     load_config, resolve_selection, validate_config)
from .plugins import plugins_summary
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
    flag_buckets = flag_buckets or []
    flag_exclude = flag_exclude or []
    buckets, profile_name, _profile_source, source, _include_meta = \
        resolve_selection(env, target, config, profile, flag_buckets)
    known = all_buckets(env)
    for b in buckets:
        if b not in known:
            die(f"unknown bucket: {b}")
    exclude = set(flag_exclude) | set(config.get("exclude", []))
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
    pulled = resolve_requires(skills, index, exclude)
    meta = {"buckets": list(buckets), "profile": profile_name, "source": source,
            "exclude": sorted(exclude), "pulled": pulled, "core_added": core_added}
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
# против baseline флота — plans/2026.07.31-SKM-LEAN/findings/P1-fleet-baseline.md,
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
# .mcp.json — FALLBACK_MCP_TOOLS (flat-оценка, не 0 и не завышение).
KNOWN_MCP_TOOLS = {
    "maind": 11, "perplexity-web": 4, "context7": 2, "sequential-thinking": 1,
    "fetch": 1, "memory": 9, "filesystem": 11, "github": 20, "playwright": 21,
    "serena": 20, "laravel-boost": 15,
}
FALLBACK_MCP_TOOLS = 5
TOKENS_PER_MCP_TOOL = 150

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

LISTING_PROVIDERS = ("claude-code", "codex")
DEFAULT_LISTING_PROVIDER = "claude-code"


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
    → {provider, unit, raw, budget, over, degradation}."""
    if provider not in LISTING_PROVIDERS:
        die(f"неизвестный --provider: {provider} (ожидается: "
            f"{', '.join(LISTING_PROVIDERS)})")
    dirs = [d for _bucket, _rel, d, _fm in skills]
    if provider == "codex":
        raw = sum(_listing_entry_chars(d) for d in dirs)
        budget = CODEX_LISTING_FALLBACK_CHARS
        unit = "симв"
        degradation = "скилл может быть выброшен из листинга целиком"
    else:
        raw = sum(_listing_entry_tokens(d) for d in dirs)
        budget = int(SKILL_LISTING_CONTEXT_WINDOW * SKILL_LISTING_BUDGET_FRACTION)
        unit = "ток"
        degradation = "описание усекается, имя остаётся"
    return {"provider": provider, "unit": unit, "raw": raw, "budget": budget,
            "over": raw > budget, "degradation": degradation}


def format_listing_report(report):
    """Человекочитаемая строка `measure_listing_budget` для CLI (--profile + --provider)."""
    status = "ПЕРЕБОР" if report["over"] else "ок"
    ratio = (f" (×{report['raw'] / report['budget']:.1f})"
             if report["over"] and report["budget"] else "")
    return "\n".join([
        "", f"─── Бюджет обнаружения (листинг), provider: {report['provider']} ───",
        f"Листинг: {report['raw']} {report['unit']}  vs  бюджет {report['budget']} "
        f"{report['unit']}  — {status}{ratio}",
        f"Режим деградации: {report['degradation']}", ""])


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


def _measure_skills(env, target, *, listing_fraction=SKILL_LISTING_BUDGET_FRACTION,
                    listing_context_window=SKILL_LISTING_CONTEXT_WINDOW):
    """Резидент листинга активного набора скиллов проекта — модель бюджета
    выше (cap на запись + потолок = context_window*fraction), не сумма всех
    описаний (тот переучёт был причиной D22/[POSSIBLE-DEFECT] в разведке P3.4).
    n/a на любой сбой (незнакомый бакет в чужом .swissknife.json и т.п.) — не
    должно ронять весь отчёт."""
    try:
        config = load_config(env, target)
        skills, meta = resolve_active_set(env, target, config)
        raw = sum(_listing_entry_tokens(d) for _bucket, _rel, d, _fm in skills)
        budget = int(listing_context_window * listing_fraction)
        resident = min(raw, budget)
        detail = f"{len(skills)} скиллов"
        if raw > budget:
            detail += (f", листинг {raw} > бюджет {budget} ток → резидент "
                      f"{resident} (клиент дропает редко вызываемые описания)")
        return {"tokens": resident, "raw_tokens": raw, "listing_budget": budget,
                "detail": detail}
    except (Exception, SystemExit) as e:
        return {"tokens": None, "detail": f"n/a ({e})"}


def _measure_agents(target):
    """name+description каждого .claude/agents/*.md (frontmatter) — тот же
    always-on «налог», что у скиллов, но для субагентов проекта."""
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
    """CLAUDE.md проекта + .claude/rules/*.md БЕЗ `paths:` (path-scoped rules
    не always-on — грузятся только на затронутый файл, см. skill-authoring/
    context-economy канон)."""
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
        for p in sorted(rules_dir.glob("*.md")):
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


def _measure_hooks(target, timeout=HOOK_TIMEOUT):
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
    """Статичная оценка tool-defs подключённых MCP-серверов проекта (.mcp.json):
    известные серверы — по числу tool-схем (KNOWN_MCP_TOOLS), неизвестные —
    flat FALLBACK_MCP_TOOLS. Не парсим реальные схемы (сервер может быть недоступен
    из этого окружения) — это оценка, как и весь budget.py."""
    f = Path(target) / ".mcp.json"
    if not f.is_file():
        return {"tokens": 0, "detail": "нет .mcp.json"}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"tokens": None, "detail": "n/a (.mcp.json invalid JSON)"}
    servers = sorted(data.get("mcpServers", {}))
    if not servers:
        return {"tokens": 0, "detail": "нет серверов"}
    total = sum(KNOWN_MCP_TOOLS.get(n, FALLBACK_MCP_TOOLS) * TOKENS_PER_MCP_TOOL
               for n in servers)
    return {"tokens": total, "detail": f"{len(servers)} сервер(ов): " + ", ".join(servers)}


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


def first_turn_report(env, target, *, timeout=HOOK_TIMEOUT,
                      listing_fraction=SKILL_LISTING_BUDGET_FRACTION,
                      listing_context_window=SKILL_LISTING_CONTEXT_WINDOW):
    """Сумма always-on футпринта первого хода проекта по пяти источникам.
    n/a-источники (fail-soft) не участвуют в сумме — total считает только то,
    что реально измерено. Вердикт: OK ≤16K · ELEVATED ≤23K · WARN >23K
    (пороги — FIRST_TURN_TARGET_MAX/FIRST_TURN_WARN, обоснование там же:
    baseline флота plans/2026.07.31-SKM-LEAN/findings/P1-fleet-baseline.md,
    D83). `listing_fraction`/
    `listing_context_window` — доля бюджета листинга скиллов и контекстное окно
    целевой модели; параметры, а не константы (P3.4 Implementation Rules —
    захардкоженный дефолт протухнет при смене `skillListingBudgetFraction`)."""
    target = Path(target).resolve()
    sources = {
        "skills": _measure_skills(env, target, listing_fraction=listing_fraction,
                                  listing_context_window=listing_context_window),
        "agents": _measure_agents(target),
        "claude_md": _measure_claude_md(target),
        "hooks": _measure_hooks(target, timeout=timeout),
        "mcp": _measure_mcp(target),
    }
    total = sum(s["tokens"] for s in sources.values() if s["tokens"] is not None)
    return {"target": str(target), "sources": sources, "total": total,
           "verdict": _first_turn_verdict(total)}


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
          f"Проект: {report['target']}", ""]
    for key, label in _FIRST_TURN_SOURCE_LABELS:
        s = report["sources"].get(key, {})
        tok = s.get("tokens")
        tok_str = "   n/a" if tok is None else f"{tok:>6}"
        out.append(f"  {label:<28} {tok_str} ток  ({s.get('detail', '')})")
        raw = s.get("raw_tokens")
        if raw is not None and raw != tok:
            out.append(f"  {'  (сумма описаний до бюджета)':<28} {raw:>6} ток")
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
              "               [--provider claude-code|codex] [--profiles]\n"
              "               [--no-core] [--json] [--write-map] [--check-core [--strict]]\n"
              "               [--first-turn [--json] [--strict]]\n"
              "  Трёхъярусный токеновый бюджет набора скиллов (⊕ always / ↻ on-trigger\n"
              "  / ⌥ on-demand). --write-map перегенерит docs/guide/budget.md.\n"
              "  --check-core: резидентный (⊕ tier-0) бюджет CORE_SKILLS vs target (гейт\n"
              "  против тихого роста ядра И против тихого недобора — пропавший по пути\n"
              "  CORE-скилл занижает резидент, а не улучшает его); --strict — ненулевой\n"
              "  код при превышении ИЛИ недоборе (CI).\n"
              "  --first-turn: always-on футпринт первого хода проекта (skills meta +\n"
              "  agents + CLAUDE.md/rules + живой прогон SessionStart-хуков + MCP) —\n"
              "  target ≤16K / warn >23K ток; --strict — exit 1 при WARN (CI).\n"
              "  --with-plugins (только вместе с --first-turn): добавляет always-on цену\n"
              "  установленных marketplace-плагинов проекта (`claude plugin list/details`)\n"
              "  аддитивными ключами `plugins`/`session_total`/`session_verdict` — без\n"
              "  флага вывод не меняется.\n"
              "  --provider claude-code|codex (с --profile/--config/--target): добавляет к\n"
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
        report = first_turn_report(env, target)
        if opts.get("with_plugins"):
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
        if opts.get("strict") and report["verdict"] == "WARN":
            die(f"first-turn бюджет {report['total']} ток > warn-порог "
                f"{FIRST_TURN_WARN} ({target}) — см. таблицу выше")
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
