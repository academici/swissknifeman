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
  вердикт  — чистая функция метрик с порогами-константами: keep/thin/retrieval-only/
             merge/dead.

Честность формулировки: skill с нулём загрузок в окне помечается РОВНО «не использовался
в окне N дней» — усечённые данные (короткое окно / мало просканированных проектов) НЕ
равны доказанной бесполезности."""
import json
import re
import time
from pathlib import Path

from .analyze import agent_stats, logs_root, parse_transcript
from .budget import _split_frontmatter, skill_budget
from .common import die, parse_flags, parse_frontmatter
from .state import load_db

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


# --- вердикт ---------------------------------------------------------------------
def verdict(item, *, overlap_partners, loaded_count, scanned_projects):
    """Чистая функция метрик → вердикт (keep/thin/retrieval-only/merge/dead).

    Порядок проверки = приоритет сигнала (первое совпадение побеждает). Структурные
    факты (overlap/размер тела — считаются из САМОГО контента, полная уверенность)
    идут ПЕРЕД usage-выводом (dead — по неполным логам одной машины/окна, см.
    analyze.py про частичный детект «только явный Skill-tool»): иначе крупный
    известный монолит, просто не пойманный usage-детектом в окне, тонет под «dead»
    вместо «thin» — теряется ровно тот сигнал, ради которого и нужен размер:
      1) merge           — overlap с другим скиллом над порогом Jaccard/shingle.
      2) thin            — тело-монолит (tier1 >= TIER1_MONOLITH_TOKENS).
      3) dead            — usage-данные ЕСТЬ (scanned_projects>0) И 0 загрузок в окне.
      4) retrieval-only  — заметное тело (>= TIER1_LARGE_TOKENS) при редком
                            использовании (<= LOW_USAGE_MAX_LOADS, включая «нет данных»).
      5) keep            — иначе.

    scanned_projects==0 → usage неинформативен: dead НЕ ставим (усечённые данные ≠
    бесполезность), но structural-вердикты (merge/thin) и retrieval-only по размеру
    всё ещё применимы. usage_note() — независимый от вердикта текст, «не использовался
    в окне N дней» виден в отчёте даже когда вердикт «thin»/«merge»."""
    if overlap_partners:
        return "merge"
    if item["tier1"] >= TIER1_MONOLITH_TOKENS:
        return "thin"
    if scanned_projects > 0 and loaded_count == 0:
        return "dead"
    if item["tier1"] >= TIER1_LARGE_TOKENS and loaded_count <= LOW_USAGE_MAX_LOADS:
        return "retrieval-only"
    return "keep"


def usage_note(loaded_count, scanned_projects, since_days):
    """РОВНО «не использовался в окне N дней» при нуле загрузок — не «мёртв»/
    «бесполезен» (усечённые данные ≠ доказанная бесполезность)."""
    if scanned_projects == 0:
        return f"usage: нет данных за окно {since_days} дней (0 просканированных проектов)"
    if loaded_count == 0:
        return f"не использовался в окне {since_days} дней"
    return f"{loaded_count}× за {since_days} дней"


# --- сборка отчёта ----------------------------------------------------------------
def build_audit(env, since_days=DEFAULT_SINCE_DAYS):
    items = iter_registry_skills(env)
    pairs = find_overlaps(items)
    ov_map = _overlap_map(pairs)
    loaded, scanned = collect_usage(env, since_days)

    rows = []
    for it in items:
        partners = ov_map.get(it["key"], [])
        loaded_count = loaded.get(it["name"], 0)
        v = verdict(it, overlap_partners=partners, loaded_count=loaded_count,
                    scanned_projects=scanned)
        rows.append({
            "bucket": it["bucket"], "name": it["name"], "key": it["key"],
            "tier0": it["tier0"], "tier1": it["tier1"], "tier2": it["tier2"],
            "overlap_with": sorted(partners), "loaded_count": loaded_count,
            "usage_note": usage_note(loaded_count, scanned, since_days),
            "verdict": v,
        })
    return {
        "since_days": since_days, "scanned_projects": scanned,
        "skills": len(rows), "overlap_pairs": pairs, "items": rows,
    }


# --- рендер ------------------------------------------------------------------
def render_audit(report):
    out = []
    out.append("")
    out.append("━━━ BUCKET-AUDIT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    out.append(f"Скиллов: {report['skills']}   usage-окно: {report['since_days']} дней   "
               f"просканировано проектов: {report['scanned_projects']}")
    counts = {}
    for r in report["items"]:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    if counts:
        out.append("Вердикты: " + " · ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    items = report["items"]
    width = max((len(r["key"]) for r in items), default=10)
    out.append("")
    out.append(f"  {'скилл'.ljust(width)}  ⊕tier0  ↻tier1  вердикт           usage")
    for r in sorted(items, key=lambda r: (r["verdict"], -r["tier1"])):
        out.append(f"  {r['key'].ljust(width)}  {r['tier0']:>6}  {r['tier1']:>6}  "
                   f"{r['verdict']:<17} {r['usage_note']}")

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
              "  5-gram shingle≥0.3) · usage (фан-аут по ~/.swissknifeman/projects.json,\n"
              "  окно --since N дней, по умолчанию 30) · вердикты keep/thin/\n"
              "  retrieval-only/merge/dead (чистая функция метрик).")
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
