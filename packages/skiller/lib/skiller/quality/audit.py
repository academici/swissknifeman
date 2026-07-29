"""audit — bucket-audit: размер · overlap · usage · вердикты по всему реестру скиллов
(P7.1 SKM-MASTER-002).

Зачем: решения по ~205 скиллам без метрик — гадание. Собирает в один отчёт:

  размер   — реюз `budget.skill_budget` (⊕tier0/↻tier1/⌥tier2); budget.py остаётся
             ЕДИНСТВЕННЫМ источником токен-математики, этот модуль её только потребляет,
             не расширяет.
  overlap  — Jaccard≥0.4 по description-триггерам (нормализованные слова описания) И/ИЛИ
             5-gram word-shingle≥0.3 по телам (устойчивее к переформулировкам, чем
             посимвольный diff). Свои компактные множества на stdlib, без либ.
  usage    — фан-аут по ~/.swissknifeman/projects.json → skill_usage из JSONL-транскриптов,
             как в `analyze.py` (Skill-tool вызовы), окно `--since N` дней. Транскрипты
             fail-safe (формат логов не гарантирован; см. analyze.parse_transcript) —
             недоступные/битые логи дают usage=0, а не падение аудита.
  резидент — ВТОРОЙ, независимый от транскриптов источник видимости (P2.2 SKM-MASTER-003):
             скилл в CORE_SKILLS (config.py, ярус-0 в каждом проекте) ИЛИ входит в
             активный набор (профиль/бакеты `.swissknife.json`, тот же resolve_active_set,
             что `analyze._active_skill_names`) хотя бы одного зарегистрированного проекта.
             Закрывает слепую зону transcript-скана: транскрипт-скан ловит ТОЛЬКО явные
             Skill-tool-вызовы (см. analyze.py) — резидентные/авто-триггерные скиллы (ярус-0
             description, нативный preload) молча не оставляют такого следа и ложно
             выглядят dead. Резидентность — best-effort/graceful (битый/удалённый проект →
             просто пропускается, аудит не падает).
  вердикт  — чистая функция метрик с порогами-константами: keep/thin/retrieval-only/
             merge/dead. Резидентный скилл БЕЗ явных skill-вызовов не помечается dead —
             вместо этого keep с честной пометкой (авто-триггер вне детекции обоих
             источников — см. verdict()/usage_note()).

Честность формулировки: skill с нулём загрузок в окне помечается РОВНО «не использовался
в окне N дней» — усечённые данные (короткое окно / мало просканированных проектов) НЕ
равны доказанной бесполезности. Поле `channel` в отчёте (skill-call/resident/none)
показывает, КАКОЙ из двух источников вообще видел скилл."""
import json
import re
import time
from pathlib import Path

from .analyze import agent_stats, logs_root, parse_transcript, skill_key
from ..budget import _split_frontmatter, budget_for_set, resolve_active_set, skill_budget
from ..common import die, parse_flags, parse_frontmatter
from ..config import CORE_SKILLS, load_config
from ..state import load_db

# --- пороги вердикта (константы — не магические числа по месту) ----------------
OVERLAP_DESC_JACCARD = 0.4     # схожесть description-триггеров -> кандидат merge
OVERLAP_BODY_SHINGLE = 0.3     # схожесть 5-gram теловых shingle -> кандидат merge
TIER1_MONOLITH_TOKENS = 6000   # крупное тело (↻ on-trigger) -> кандидат thin-navigator
TIER1_LARGE_TOKENS = 2000      # заметное тело + редкое использование -> retrieval-only
LOW_USAGE_MAX_LOADS = 1        # ≤1 загрузка в окне — «редко» (retrieval-only), не dead
SHINGLE_N = 5
DEFAULT_SINCE_DAYS = 30


# --- description-триггеры / body-shingles ---------------------------------------
def _words(text):
    return re.findall(r"[a-zа-яё0-9]+", (text or "").lower())


def desc_triggers(description):
    """Множество нормализованных слов description (≥3 симв) — прокси «триггеров»
    активации скилла, по которым считаем Jaccard-overlap описаний."""
    return {w for w in _words(description) if len(w) >= 3}


def body_shingles(body, n=SHINGLE_N):
    """Множество word n-gram (по умолчанию 5) тела скилла — похожесть контента,
    устойчивее к переформулировкам/перестановкам абзацев, чем посимвольный diff.
    Короче n слов → пусто (НЕ единственный «фолбэк»-шингл из всех слов): иначе
    любые два коротких тела с одинаковым числом слов (< n) молча дают
    Jaccard=1.0 и ложный overlap независимо от реального смысла."""
    words = _words(body)
    if len(words) < n:
        return set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def jaccard(a, b):
    if not a and not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


# --- сбор реестра ----------------------------------------------------------------
def iter_registry_skills(env):
    """Скиллы всего реестра (skills/**/SKILL.md) с описанием/телом/бюджетом.

    Возвращает [{bucket, name, key, dir, description, triggers, shingles,
    tier0, tier1, tier2}]. key = "bucket/name" (адресация в отчёте/парах overlap).
    Раскладка пути идентична registry.build_registry (bucket = parts[1]), но без
    графа/upstream — audit.py не дублирует сборку skills.json, читает SKILL.md сам
    (нужны сырые description/body для триггеров/шинглов, которых нет в skills.json)."""
    items = []
    for skill_md in sorted(env.root.glob("skills/**/SKILL.md")):
        rel = skill_md.relative_to(env.root)
        parts = rel.parts
        if len(parts) < 3:
            continue
        bucket = parts[1]
        fm = parse_frontmatter(skill_md)
        text = skill_md.read_text(encoding="utf-8-sig")
        # _split_frontmatter — реюз budget.py (не дублируем разбор тела; см. её
        # docstring про сознательное неслияние с common.parse_frontmatter).
        _, body = _split_frontmatter(text)
        b = skill_budget(skill_md.parent)
        if b is None:
            continue
        description = fm.get("description", "")
        items.append({
            "bucket": bucket, "name": b["name"], "key": f"{bucket}/{b['name']}",
            "dir": skill_md.parent, "description": description,
            "triggers": desc_triggers(description), "shingles": body_shingles(body),
            "tier0": b["tier0"], "tier1": b["tier1"], "tier2": b["tier2"],
        })
    return items


# --- overlap -----------------------------------------------------------------
def find_overlaps(items):
    """Пары скиллов над порогом Jaccard(description) ИЛИ shingle(body). O(n²) —
    реестр ~200 скиллов → ~20K пар, дёшево на stdlib-множествах. Возвращает
    [{a, b, desc_jaccard, body_shingle}] только для пар над хотя бы одним порогом."""
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            ia, ib = items[i], items[j]
            dj = jaccard(ia["triggers"], ib["triggers"])
            bs = jaccard(ia["shingles"], ib["shingles"])
            if dj >= OVERLAP_DESC_JACCARD or bs >= OVERLAP_BODY_SHINGLE:
                pairs.append({"a": ia["key"], "b": ib["key"],
                             "desc_jaccard": round(dj, 3), "body_shingle": round(bs, 3)})
    return pairs


def _overlap_map(pairs):
    """key -> [partner_key, ...] — быстрая проверка «есть overlap» при вердикте."""
    out = {}
    for p in pairs:
        out.setdefault(p["a"], []).append(p["b"])
        out.setdefault(p["b"], []).append(p["a"])
    return out


# --- usage: фан-аут по projects.json --------------------------------------------
def _sessions_since(root, since_days):
    """main-транскрипты (*.jsonl) каталога логов проекта, изменённые за since_days
    дней. root может не существовать (проект без логов) — тогда пусто."""
    if not root.is_dir():
        return []
    cutoff = time.time() - since_days * 86400
    out = []
    for p in sorted(root.glob("*.jsonl")):
        try:
            if p.stat().st_mtime >= cutoff:
                out.append(p)
        except OSError:
            continue
    return out


def collect_usage(env, since_days=DEFAULT_SINCE_DAYS):
    """Фан-аут по ~/.swissknifeman/projects.json: сколько раз каждый нормализованный
    скилл реально загружался (Skill-tool, как в analyze.agent_stats) за последние
    since_days дней across ВСЕХ зарегистрированных проектов (main-сессии + их
    сабагенты). Транскрипты fail-safe — parse_transcript/agent_stats толерантны к
    битым/отсутствующим файлам (формат логов не гарантирован между версиями CLI).

    Возвращает (loaded: {normalized_name: count}, scanned_projects: int) —
    scanned_projects=0 значит usage-данных за окно нет вообще (не «всё мёртво»)."""
    db = load_db(env)
    loaded = {}
    scanned = 0
    for proj in db.get("projects", []):
        path = proj.get("path")
        if not path:
            continue
        root = logs_root(env, Path(path))
        sessions = _sessions_since(root, since_days)
        if not sessions:
            continue
        scanned += 1
        for sess in sessions:
            st = agent_stats(parse_transcript(sess), sess.stem)
            for k, c in st["skills"].items():
                loaded[k] = loaded.get(k, 0) + c
            subs_dir = sess.parent / sess.stem / "subagents"
            if subs_dir.is_dir():
                for sp in sorted(subs_dir.glob("agent-*.jsonl")):
                    st = agent_stats(parse_transcript(sp), sp.stem)
                    for k, c in st["skills"].items():
                        loaded[k] = loaded.get(k, 0) + c
    return loaded, scanned


# --- резидент: второй источник видимости (P2.2 SKM-MASTER-003) -------------------
def _core_skill_names():
    """Нормализованные имена CORE_SKILLS (последний сегмент "bucket/name" —
    та же нормализация, что skill_key/collect_usage) — грузятся ярусом-0
    (name+description) в КАЖДОМ проекте по умолчанию, см. config.py."""
    return {skill_key(p) for p in CORE_SKILLS}


def resident_skill_names(env):
    """Множество нормализованных имён «резидентных» скиллов — второй,
    НЕЗАВИСИМЫЙ от транскриптов источник видимости:

      1) CORE_SKILLS (config.py) — резидентны ярусом-0 в каждом проекте.
      2) активный набор (профиль/бакеты `.swissknife.json`, тот же
         `budget.resolve_active_set`, что использует `analyze._active_skill_names`)
         хотя бы ОДНОГО зарегистрированного проекта (~/.swissknifeman/projects.json).

    Резидентный скилл может не оставить ни одного явного Skill-tool-вызова в
    транскрипте (авто-триггер description/нативный preload вне детекции transcript-
    скана, см. docstring analyze.py) — это НЕ значит, что он мёртв.

    Best-effort/graceful по каждому проекту: битый/отсутствующий `.swissknife.json`,
    неизвестный бакет (die изнутри resolve_active_set) или удалённый путь проекта —
    просто пропускаем проект, аудит целиком не падает (тот же принцип, что
    collect_usage про битые транскрипты)."""
    names = _core_skill_names()
    db = load_db(env)
    for proj in db.get("projects", []):
        path = proj.get("path")
        if not path:
            continue
        target = Path(path)
        try:
            config = load_config(env, target)
            skills, meta = resolve_active_set(env, target, config)
            b = budget_for_set(skills, meta.get("pulled"))
            names |= {skill_key(i["name"]) for i in b["items"]}
        except SystemExit:
            continue  # неизвестный бакет/битый конфиг -> пропуск проекта
        except Exception:
            continue  # любая другая деградация (ФС/JSON) -> пропуск проекта
    return names


# --- вердикт ---------------------------------------------------------------------
def verdict(item, *, overlap_partners, loaded_count, scanned_projects, resident=False):
    """Чистая функция метрик → вердикт (keep/thin/retrieval-only/merge/dead).

    Порядок проверки = приоритет сигнала (первое совпадение побеждает). Структурные
    факты (overlap/размер тела — считаются из САМОГО контента, полная уверенность)
    идут ПЕРЕД usage-выводом (dead — по неполным логам одной машины/окна, см.
    analyze.py про частичный детект «только явный Skill-tool»): иначе крупный
    известный монолит, просто не пойманный usage-детектом в окне, тонет под «dead»
    вместо «thin» — теряется ровно тот сигнал, ради которого и нужен размер:
      1) merge           — overlap с другим скиллом над порогом Jaccard/shingle.
      2) thin            — тело-монолит (tier1 >= TIER1_MONOLITH_TOKENS).
      3) dead            — usage-данные ЕСТЬ (scanned_projects>0) И 0 загрузок в окне
                            И скилл НЕ резидентный (см. resident_skill_names) — иначе
                            keep (2026.07.02-SKM-MASTER-003 P2.2: резидент без skill-вызовов ≠ мёртв, это второй
                            источник видимости, транскрипт-скан его просто не ловит).
      4) retrieval-only  — заметное тело (>= TIER1_LARGE_TOKENS) при редком
                            использовании (<= LOW_USAGE_MAX_LOADS, включая «нет данных»).
      5) keep            — иначе (включая dead-кандидатов, спасённых резидентностью).

    scanned_projects==0 → usage неинформативен: dead НЕ ставим (усечённые данные ≠
    бесполезность), но structural-вердикты (merge/thin) и retrieval-only по размеру
    всё ещё применимы. usage_note() — независимый от вердикта текст, «не использовался
    в окне N дней» виден в отчёте даже когда вердикт «thin»/«merge»."""
    if overlap_partners:
        return "merge"
    if item["tier1"] >= TIER1_MONOLITH_TOKENS:
        return "thin"
    if scanned_projects > 0 and loaded_count == 0:
        return "keep" if resident else "dead"
    if item["tier1"] >= TIER1_LARGE_TOKENS and loaded_count <= LOW_USAGE_MAX_LOADS:
        return "retrieval-only"
    return "keep"


def usage_note(loaded_count, scanned_projects, since_days, resident=False):
    """РОВНО «не использовался в окне N дней» при нуле загрузок — не «мёртв»/
    «бесполезен» (усечённые данные ≠ доказанная бесполезность). Резидентный скилл
    (см. resident_skill_names) без загрузок получает отдельную честную пометку —
    он виден вторым источником (CORE/активный набор), а не «не использовался»."""
    if scanned_projects == 0:
        return f"usage: нет данных за окно {since_days} дней (0 просканированных проектов)"
    if loaded_count == 0:
        if resident:
            return "резидентный, прямых вызовов не видно (авто-триггер вне детекции)"
        return f"не использовался в окне {since_days} дней"
    return f"{loaded_count}× за {since_days} дней"


# --- сборка отчёта ----------------------------------------------------------------
def build_audit(env, since_days=DEFAULT_SINCE_DAYS):
    items = iter_registry_skills(env)
    pairs = find_overlaps(items)
    ov_map = _overlap_map(pairs)
    loaded, scanned = collect_usage(env, since_days)
    resident = resident_skill_names(env)

    rows = []
    for it in items:
        partners = ov_map.get(it["key"], [])
        loaded_count = loaded.get(it["name"], 0)
        is_resident = it["name"] in resident
        # channel: какой из двух независимых источников видел скилл — явный
        # skill-call (сильнее, транскрипт) перевешивает резидентность (косвенный
        # сигнал: CORE/активный набор), при отсутствии обоих — none.
        channel = "skill-call" if loaded_count > 0 else ("resident" if is_resident else "none")
        v = verdict(it, overlap_partners=partners, loaded_count=loaded_count,
                    scanned_projects=scanned, resident=is_resident)
        rows.append({
            "bucket": it["bucket"], "name": it["name"], "key": it["key"],
            "tier0": it["tier0"], "tier1": it["tier1"], "tier2": it["tier2"],
            "overlap_with": sorted(partners), "loaded_count": loaded_count,
            "channel": channel,
            "usage_note": usage_note(loaded_count, scanned, since_days, resident=is_resident),
            "verdict": v,
        })
    return {
        "since_days": since_days, "scanned_projects": scanned,
        "resident_skills": len(resident),
        "skills": len(rows), "overlap_pairs": pairs, "items": rows,
    }


# --- рендер ------------------------------------------------------------------
def render_audit(report):
    out = []
    out.append("")
    out.append("━━━ BUCKET-AUDIT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append(f"Скиллов: {report['skills']}   usage-окно: {report['since_days']} дней   "
               f"просканировано проектов: {report['scanned_projects']}   "
               f"резидентных (CORE/активный набор): {report.get('resident_skills', 0)}")
    counts = {}
    for r in report["items"]:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    if counts:
        out.append("Вердикты: " + " · ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    items = report["items"]
    width = max((len(r["key"]) for r in items), default=10)
    out.append("")
    out.append(f"  {'скилл'.ljust(width)}  ⊕tier0  ↻tier1  вердикт           канал       usage")
    for r in sorted(items, key=lambda r: (r["verdict"], -r["tier1"])):
        out.append(f"  {r['key'].ljust(width)}  {r['tier0']:>6}  {r['tier1']:>6}  "
                   f"{r['verdict']:<17} {r.get('channel', 'none'):<11} {r['usage_note']}")

    if report["overlap_pairs"]:
        out.append("")
        out.append("─── Overlap-пары (desc-триггеры Jaccard≥0.4 / тело shingle≥0.3) ─")
        for p in report["overlap_pairs"]:
            out.append(f"  {p['a']} × {p['b']}   desc={p['desc_jaccard']}  "
                       f"body={p['body_shingle']}")
    out.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append("")
    return "\n".join(out)


# --- CLI -----------------------------------------------------------------------
def cmd_bucket_audit(env, argv):
    opts = parse_flags(argv, {"--since": "str", "--json": "bool"})
    if opts["help"]:
        print("skiller bucket-audit [--since N] [--json]")
        print("  Метрики по всему реестру скиллов: размер (⊕tier0/↻tier1/⌥tier2, реюз\n"
              "  budget.skill_budget) · overlap (description-триггеры Jaccard≥0.4 / тело\n"
              "  5-gram shingle≥0.3) · usage — ДВА независимых источника видимости:\n"
              "  явные skill-call (фан-аут по ~/.swissknifeman/projects.json, окно\n"
              "  --since N дней, по умолчанию 30) И резидентность (CORE_SKILLS/активный\n"
              "  набор проекта, поле channel: skill-call|resident|none) · вердикты\n"
              "  keep/thin/retrieval-only/merge/dead (резидентный скилл без\n"
              "  skill-call НЕ помечается dead — чистая функция метрик).")
        return
    since_raw = opts.get("since") or str(DEFAULT_SINCE_DAYS)
    try:
        since_days = int(since_raw)
    except ValueError:
        die(f"--since ждёт целое число дней, получено: {since_raw}")
    if since_days <= 0:
        die(f"--since ждёт положительное число дней, получено: {since_days}")
    report = build_audit(env, since_days)
    if opts.get("json"):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(render_audit(report))
