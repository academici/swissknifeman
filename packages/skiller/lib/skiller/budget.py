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
from pathlib import Path

from core import atomic_write_text

from .common import die, parse_flags, parse_frontmatter
from .config import (CORE_SKILLS, DEFAULT_EXCLUDE, RESIDENT_BUDGET_TARGET,
                     all_buckets, core_skill_tuples, find_project_root,
                     load_config, resolve_selection, validate_config)
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
        "--check-core": "bool", "--strict": "bool",
    })
    if opts["help"]:
        print("skiller budget [--config F.json | --compare a,b | --target DIR]\n"
              "               [--profile P | --buckets a,b] [--exclude x,y]\n"
              "               [--no-core] [--json] [--write-map] [--check-core [--strict]]\n"
              "  Трёхъярусный токеновый бюджет набора скиллов (⊕ always / ↻ on-trigger\n"
              "  / ⌥ on-demand). --write-map перегенерит docs/guide/budget.md.\n"
              "  --check-core: резидентный (⊕ tier-0) бюджет CORE_SKILLS vs target (гейт\n"
              "  против тихого роста ядра И против тихого недобора — пропавший по пути\n"
              "  CORE-скилл занижает резидент, а не улучшает его); --strict — ненулевой\n"
              "  код при превышении ИЛИ недоборе (CI).")
        return
    no_core = opts.get("no_core", False)

    if opts.get("write_map"):
        write_budget_map(env)
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
    if opts.get("json"):
        print(json.dumps({"label": label, "meta": {
            "buckets": meta["buckets"], "profile": meta["profile"],
            "source": meta["source"]}, **b}, indent=2, ensure_ascii=False))
        return
    print(format_report(f"{label}  [profile: {meta['profile'] or '-'} "
                        f"via {meta['source']}]", b))


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
