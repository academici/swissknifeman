"""analyst suggest (P4) — cross-project паттерн → ЧЕРНОВИК скилла (draft SKILL.ru.md).

Детерминированный (stdlib, on-demand — без демона) мост между `scan` и переиспользуемым
скиллом. Читает ТОЛЬКО индекс паттернов (`~/.swissknifeman/analyst/index/by_pattern/<id>.json`,
пишет его `scan`) и генерит staged-черновик в `~/.swissknifeman/analyst/drafts/<pattern_id>/`:

    drafts/<pattern_id>/
      SKILL.ru.md      — RU-источник-ЗАГОТОВКА (правит человек) с frontmatter-скелетом
      draft.meta.json  — провенанс-паспорт черновика + seed_sha256 (детект ручных правок)

ИНВАРИАНТ (analyst): авто-запись в скиллы ЗАПРЕЩЕНА — suggest НЕ пишет в skills/, НЕ генерит
EN-канон (это человек промтом skiller после доработки), НЕ регистрирует, НЕ раскрывает raw/секреты.
Промоут черновика в бакет — руками человека (см. handoff в выводе). Приватность СТРУКТУРНА:
индекс by_pattern/ — уже абстрагированная проекция (trigger/action/kind), сырья в нём нет.

Модель кода (как digest/scan): ЧИСТЫЕ генераторы (pattern→текст) + writer с I/O в cmd_suggest.

Замечание по детерминизму: провенанс-штамп в SKILL.ru.md НЕ несёт timestamp (он живёт только в
draft.meta.json) — иначе тело было бы недетерминированным и seed_sha256-детект ручных правок (D6)
ложно срабатывал бы на каждый ре-suggest.
"""
import hashlib
import re

from .common import (atomic_write_json, atomic_write_text, die, now_iso,
                     parse_args, safe_load_json, warn)

DRAFT_SCHEMA_VERSION = 1
RESERVED_NAME_WORDS = ("claude", "anthropic")   # офиц. запрет в name скиллов Claude Code
NAME_MAX = 64                                    # офиц. лимит name (lowercase/цифры/дефисы)
DESC_SOFT_MAX = 150                              # мягкий таргет резидентного description


# ── чистые генераторы (без I/O/часов) ────────────────────────────────────────
def _slug_name(representative):
    """kebab-name-кандидат из representative (trigger→action fallback): lowercase, только
    [a-z0-9-], без ведущих/хвостовых дефисов, без reserved (claude/anthropic), ≤64. Человек
    финализирует так, чтобы name == имя финального каталога скилла."""
    base = (representative.get("trigger") or representative.get("action") or "skill").lower()
    parts = [p for p in re.sub(r"[^a-z0-9]+", "-", base).split("-")
             if p and p not in RESERVED_NAME_WORDS]
    slug = "-".join(parts)[:NAME_MAX].strip("-")
    return slug or "skill"


def _draft_description(representative):
    """RU-заготовка description (≤~150 симв, мягкий таргет; правит человек). Экранируем `\\` и `"`
    — description кладётся в YAML double-quoted скаляр (напр. `App\\Domain` иначе битый YAML)."""
    action = (representative.get("action") or "").strip()
    trigger = (representative.get("trigger") or "").strip()
    body = " — ".join(x for x in (action, trigger) if x) or "переиспользуемый урок"
    if len(body) > DESC_SOFT_MAX:
        body = body[:DESC_SOFT_MAX - 1].rstrip() + "…"
    return body.replace("\\", "\\\\").replace('"', '\\"')


def _provenance_stamp(pattern):
    """Инертный HTML-штамп провенанса в тело SKILL.ru.md (БЕЗ timestamp — детерминизм).
    Переносится с файлом; человек снимает перед промоутом. SSOT провенанса — draft.meta.json."""
    projs = ", ".join(pattern.get("projects") or [])
    return (f"<!-- analyst-provenance: сгенерировано `analyst suggest` из pattern "
            f"{pattern['pattern_id']} · ns {pattern['namespace']} · "
            f"{pattern.get('weight', 0)} проект(ов) ({projs}) · {pattern.get('lessons', 0)} урок(ов). "
            f"Источник: index/by_pattern/{pattern['pattern_id']}.json. "
            f"УДАЛИ этот блок перед промоутом. -->")


def build_skill_ru(pattern, bucket):
    """ЧИСТО: полный текст заготовки SKILL.ru.md (frontmatter-скелет + провенанс + тело).
    Детерминирован от (pattern, bucket) — timestamp сюда НЕ попадает (см. модульный docstring).
    Тело абстрагировано: только representative + members-триггеры из индекса (raw в индексе нет)."""
    rep = pattern.get("representative") or {}
    name = _slug_name(rep)
    projs = pattern.get("projects") or []
    fm = [
        "---",
        f"name: {name}",
        f"bucket: {bucket}",
        "version: 0.1.0",
        f'description: "{_draft_description(rep)} (черновик; ≤150 симв, правит человек)"',
        "risk: read                     # TODO: уточни (read|draft|write|external)",
        'persona: ""',
        "tags: []",
        "requires: []",
        "produces_for: []",
        "outputs: []",
        "---",
    ]
    heading = rep.get("trigger") or rep.get("action") or pattern["pattern_id"]
    body = [
        _provenance_stamp(pattern),
        "",
        f"# {heading} (черновик)",
        "",
        "## Контекст (когда применять)",
        f"Паттерн повторился в **{pattern.get('weight', len(projs))} проектах** "
        f"namespace `{pattern['namespace']}`: {', '.join(projs)}.",
        f"- **trigger:** {rep.get('trigger') or '—'}",
        f"- **action:**  {rep.get('action') or '—'}",
        f"- **kind:**    {rep.get('kind') or '—'}",
        "",
        "## Наблюдённые экземпляры (абстрагировано)",
    ]
    for m in pattern.get("members") or []:
        body.append(f"- `{m.get('project', '—')}` — {m.get('trigger') or '—'}")
    body += [
        "",
        "## Алгоритм",
        "TODO — оформи action в переиспользуемые шаги.",
        "",
        "## Чеклист",
        "TODO",
        "",
    ]
    return "\n".join(fm + [""] + body)


def _seed_hash(text):
    """sha256-хэш заготовки — маркер «сгенерённого» состояния для детекта ручных правок."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_meta(pattern, bucket, seed_sha256, generated_at):
    """ЧИСТО: провенанс-паспорт draft.meta.json (SSOT провенанса черновика)."""
    return {
        "schema_version": DRAFT_SCHEMA_VERSION,
        "generated_by": "analyst suggest",
        "pattern_id": pattern["pattern_id"],
        "namespace": pattern["namespace"],
        "projects": list(pattern.get("projects") or []),
        "weight": pattern.get("weight", 0),
        "lessons": pattern.get("lessons", 0),
        "bucket": bucket,
        "source_index": f"index/by_pattern/{pattern['pattern_id']}.json",
        "seed_sha256": seed_sha256,
        "generated_at": generated_at,
    }


def filter_by_weight(patterns, min_weight):
    """ЧИСТО: паттерны с weight ≥ min_weight (None → без фильтра). Порядок сохраняется."""
    if min_weight is None:
        return list(patterns)
    return [p for p in patterns if p.get("weight", 0) >= min_weight]


# ── чтение индекса паттернов (I/O, read-only) ────────────────────────────────
def _index_dir(env):
    return env.state_dir / "index" / "by_pattern"


def load_patterns(env):
    """Полные dict'ы паттернов из index/by_pattern/*.json, отсортированы по pattern_id
    (детерминизм). Битый JSON / без pattern_id|namespace → SKIP (как list_existing_patterns)."""
    idx_dir = _index_dir(env)
    out = []
    if not idx_dir.is_dir():
        return out
    for path in sorted(idx_dir.glob("*.json")):
        data = safe_load_json(path, None)
        if isinstance(data, dict) and data.get("pattern_id") and data.get("namespace"):
            out.append(data)
    return out


def load_pattern(env, pattern_id):
    """Один паттерн по id или None."""
    data = safe_load_json(_index_dir(env) / f"{pattern_id}.json", None)
    if isinstance(data, dict) and data.get("pattern_id") and data.get("namespace"):
        return data
    return None


def list_draft_ids(env):
    """pattern_id существующих черновиков (drafts/<id>/ с draft.meta.json), отсортировано."""
    drafts = env.state_dir / "drafts"
    if not drafts.is_dir():
        return []
    return sorted(d.name for d in drafts.iterdir()
                  if d.is_dir() and (d / "draft.meta.json").is_file())


def orphan_draft_ids(env, current_ids):
    """Черновики, чей паттерн исчез из индекса (current_ids). Для WARN — НЕ удаляем (D6:
    черновик человеко-редактируем, авто-delete = потеря труда; ≠ scan-prune)."""
    return [d for d in list_draft_ids(env) if d not in set(current_ids)]


# ── writer с edit-safety (I/O) ───────────────────────────────────────────────
def write_draft(env, pattern, bucket, *, force=False):
    """Записать/обновить черновик паттерна в drafts/<id>/. Edit-safe (D6):
    - каталога/файла нет           → создать (status="created");
    - тело совпадает с генерённым   → нечего менять (status="unchanged");
    - тело == прошлый seed (не правили) либо --force → перегенерить (status="updated"/"forced");
    - тело != прошлый seed (правили руками) → тело НЕ трогаем, обновляем лишь провенанс meta
      (status="skipped-edited").
    Возвращает (status, ru_path). Атомарно; каталоги создаются."""
    pid = pattern["pattern_id"]
    draft_dir = env.state_dir / "drafts" / pid
    ru_path = draft_dir / "SKILL.ru.md"
    meta_path = draft_dir / "draft.meta.json"
    ru_text = build_skill_ru(pattern, bucket)
    new_seed = _seed_hash(ru_text)

    def _persist(seed):
        atomic_write_text(ru_path, ru_text)
        atomic_write_json(meta_path, build_meta(pattern, bucket, seed, now_iso()))

    if not ru_path.exists():
        _persist(new_seed)
        return "created", ru_path

    current = ru_path.read_text(encoding="utf-8")
    if current == ru_text:
        return "unchanged", ru_path

    prev_seed = (safe_load_json(meta_path, {}) or {}).get("seed_sha256")
    if force or _seed_hash(current) == prev_seed:
        _persist(new_seed)
        return ("forced" if force and _seed_hash(current) != prev_seed else "updated"), ru_path

    # правили руками → тело не перезаписываем; освежаем только провенанс-паспорт (seed = прошлый,
    # чтобы детект правок продолжал работать против последнего СГЕНЕРЁННОГО состояния).
    atomic_write_json(meta_path, build_meta(pattern, bucket, prev_seed, now_iso()))
    return "skipped-edited", ru_path


# ── CLI ──────────────────────────────────────────────────────────────────────
def _resolve_bucket(env, opts):
    """bucket из --bucket или плейсхолдер TODO. namespace→bucket авто-маппинга НЕТ
    (namespace — изоляция, bucket — тема). Возвращает (bucket, hint[]): hint — доступные
    бакеты из реестра skiller (best-effort, если достижим), для подсказки человеку."""
    if opts["bucket"]:
        return opts["bucket"], []
    hint = []
    buckets_json = env.monorepo_root / "packages" / "skiller" / "buckets.json"
    data = safe_load_json(buckets_json, None)
    if isinstance(data, dict):
        hint = sorted(data.keys())
    return "TODO", hint


def _handoff_lines(env, pid, bucket, name):
    """Точная (repo-grounded) последовательность промоута черновика в скилл — печатается
    человеку. НЕ `skiller integrate` (тот вшивает скиллы В проект, не регистрирует новый)."""
    b = bucket if bucket != "TODO" else "<bucket>"
    return [
        f"  Черновик: {env.state_dir / 'drafts' / pid / 'SKILL.ru.md'}",
        "  Промоут в скилл — человек (analyst НЕ пишет в skills/, НЕ генерит EN, НЕ регистрирует):",
        f"    1. mkdir -p <skiller>/skills/{b}/{name}/  и перенеси туда SKILL.ru.md (name == каталог)",
        "    2. сгенерируй EN-канон: промт packages/skiller/prompts/generate/claude-canon-from-ru.md → SKILL.md",
        "    3. bash packages/skiller/scripts/check-translations.sh --stamp",
        "    4. bash packages/skiller/scripts/validate.sh",
        "    5. skiller registry",
    ]


def cmd_suggest(env, argv):
    """analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]
    — cross-project паттерн (index/by_pattern/) → ЧЕРНОВИК SKILL.ru.md в ~/.swissknifeman/analyst/drafts/."""
    import json
    opts, pos = parse_args(argv, {"--all": "bool", "--bucket": "str", "--min-weight": "str",
                                  "--dry-run": "bool", "--json": "bool", "--force": "bool"},
                           max_pos=1)
    if opts["help"] or (not pos and not opts["all"]):
        print("analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] "
              "[--dry-run] [--json] [--force]\n"
              "  Cross-project паттерн → ЧЕРНОВИК SKILL.ru.md в ~/.swissknifeman/analyst/drafts/.\n"
              "  НЕ пишет в skills/, НЕ генерит EN, НЕ регистрирует. Промоут — человек.\n"
              "  --all по всем паттернам; --min-weight N — только weight≥N; --force — перезаписать\n"
              "  черновик, правленный вручную; --dry-run/--json — без записи.")
        return
    if pos and opts["all"]:
        die("укажи <pattern_id> ЛИБО --all, не оба")

    min_weight = None
    if opts["min_weight"]:
        try:
            min_weight = int(opts["min_weight"])
        except ValueError:
            die(f"--min-weight ждёт число, получено: {opts['min_weight']}")

    if opts["all"]:
        patterns = filter_by_weight(load_patterns(env), min_weight)
    else:
        p = load_pattern(env, pos[0])
        if p is None:
            die(f"паттерн не найден: {pos[0]} (см. analyst scan — index/by_pattern/)")
        patterns = filter_by_weight([p], min_weight)

    bucket, bucket_hint = _resolve_bucket(env, opts)

    # сироты (черновик есть, паттерн исчез) — только при полном обзоре (--all); WARN, не delete.
    orphans = orphan_draft_ids(env, [p["pattern_id"] for p in load_patterns(env)]) if opts["all"] else []

    results = []
    for p in patterns:
        name = _slug_name(p.get("representative") or {})
        if opts["dry_run"]:            # только dry-run подавляет запись; --json пишет (как scan)
            status = "dry-run"
        else:
            status, _ = write_draft(env, p, bucket, force=opts["force"])
        results.append({"pattern_id": p["pattern_id"], "namespace": p["namespace"],
                        "weight": p.get("weight", 0), "name": name, "bucket": bucket,
                        "status": status})

    if opts["json"]:
        print(json.dumps({"drafts_dir": str(env.state_dir / "drafts"),
                          "min_weight": min_weight,
                          "results": results,
                          "orphans": orphans,
                          "dry_run": bool(opts["dry_run"])}, ensure_ascii=False, indent=2))
        return

    if not patterns:
        print("\nanalyst suggest — подходящих паттернов нет "
              + (f"(weight≥{min_weight})" if min_weight is not None else "(index/by_pattern/ пуст — запусти analyst scan)")
              + "\n")
        return

    verb = "черновиков к записи (dry-run)" if opts["dry_run"] else "черновик(ов)"
    print(f"\nanalyst suggest — {len(results)} {verb}"
          + (f" · bucket={bucket}" if bucket != "TODO" else "") + "\n")
    for r in results:
        print(f"  ⚑ [{r['namespace']}] {r['pattern_id']}  · weight {r['weight']} · "
              f"name-кандидат: {r['name']}  ({r['status']})")
    if bucket == "TODO":
        tip = (", ".join(bucket_hint[:12]) + ", …") if bucket_hint else "см. skiller buckets.json"
        print(f"\n  bucket не задан — выбери человеком (--bucket B). Доступные: {tip}")
    # handoff — по первому черновику как образец (для --all детали идентичны, каталоги свои).
    print()
    for line in _handoff_lines(env, results[0]["pattern_id"], bucket, results[0]["name"]):
        print(line)
    if orphans:
        warn(f"осиротевшие черновики (паттерн исчез, НЕ удалены — правь/чисти вручную): {', '.join(orphans)}")
    if opts["dry_run"]:
        print("\n  (dry-run — ничего не записано)")
    print()
