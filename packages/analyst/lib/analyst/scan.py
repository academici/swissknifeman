"""analyst scan — cross-project агрегатор (P2): паттерны уроков across проектов.

Пакет САМ обнаруживает проекты через существующий реестр config.json (в корне монорепо):
projects[].{local_path, namespaces, enabled}. Читает per-project уроки (.claude/analyst/lessons/),
кластеризует по Jaccard (stdlib) и детектит паттерны, повторяющиеся в ≥N проектах → пишет
draft-ПРЕДЛОЖЕНИЯ (не скиллы!) в ~/.swissknifeman/analyst/suggestions/ + индекс by_pattern/.

Namespace-изоляция (наследуется от maind): уроки кластеризуются ТОЛЬКО среди проектов, делящих
namespace — паттерн из ns:axioma не течёт в чужой namespace. Проект без namespace изолирован
(кластер из него никогда не станет межпроектным). Кластеризация — greedy single-link (детерминизм:
входные уроки сортируются по id перед проходом). Демона/сети нет; всё stdlib, read-only по проектам."""
import json
import os
from pathlib import Path

from . import lessons
from .common import atomic_write_json, atomic_write_text, now_iso, safe_load_json, sanitize

# Уроки, участвующие в детекте паттернов (deprecated исключён — демоутнутое не тиражируем).
SCAN_STATES = ("curated", "candidate", "ephemeral")
DEFAULT_MIN_PROJECTS = 3     # межпроектный паттерн — только при ≥N проектах (DoD P2)
DEFAULT_THRESHOLD = 0.5      # Jaccard-порог «тот же паттерн»


# ── реестр проектов (config.json, читаем сами) ───────────────────────────────
def load_projects(config_path):
    """[{id, local_path, namespaces, enabled}] из config.json. [] если файла/ключа нет.
    Читаем реестр напрямую (stdlib) — analyst не зависит от lib maind."""
    data = safe_load_json(Path(config_path), None)
    if not isinstance(data, dict):
        return []
    out = []
    for pr in (data.get("projects") or []):
        if not isinstance(pr, dict) or not pr.get("id"):
            continue
        out.append({
            "id": pr["id"],
            "local_path": pr.get("local_path") or "",
            "namespaces": list(pr.get("namespaces") or []),
            "enabled": bool(pr.get("enabled", True)),
        })
    return out


def enabled_projects(projects, namespace=None):
    """enabled-проекты с непустым local_path; namespace фильтрует по членству."""
    out = []
    for pr in projects:
        if not pr["enabled"] or not pr["local_path"]:
            continue
        if namespace and namespace not in pr["namespaces"]:
            continue
        out.append(pr)
    return out


# ── сбор уроков по namespace (изоляция) ──────────────────────────────────────
def _lesson_text(lesson):
    return f"{lesson.get('trigger', '')} {lesson.get('action', '')}"


def gather_by_namespace(projects, *, states=SCAN_STATES):
    """{namespace: [{project, lesson, text}]} — уроки проекта попадают в КАЖДЫЙ его namespace.
    Проект без namespace не попадает никуда (изолирован — межпроектным стать не может)."""
    buckets = {}
    for pr in projects:
        ppath = os.path.expanduser(pr["local_path"])
        items = []
        for st in states:
            for lesson in [L for L, _s in lessons.list_lessons(ppath, st)]:
                items.append({"project": pr["id"], "lesson": lesson, "text": _lesson_text(lesson)})
        if not items:
            continue
        for ns in pr["namespaces"]:
            buckets.setdefault(ns, []).extend(items)
    return buckets


# ── кластеризация (greedy single-link, детерминированная) ─────────────────────
def cluster(items, threshold=DEFAULT_THRESHOLD):
    """[[item,...], ...] greedy single-link по Jaccard(text). Вход сортируется по
    (lesson.id) → детерминизм независимо от порядка чтения каталогов."""
    ordered = sorted(items, key=lambda it: it["lesson"].get("id", ""))
    clusters = []
    for it in ordered:
        placed = False
        for cl in clusters:
            if any(lessons.jaccard(it["text"], m["text"]) >= threshold for m in cl):
                cl.append(it)
                placed = True
                break
        if not placed:
            clusters.append([it])
    return clusters


def _pattern_id(namespace, rep_text):
    slug = sanitize(rep_text)[:40] or "pattern"
    import hashlib
    h = hashlib.sha1(f"{namespace}\x00{rep_text}".encode("utf-8")).hexdigest()[:8]
    return f"{sanitize(namespace) or 'ns'}-{slug}-{h}"


def detect_patterns(buckets, *, min_projects=DEFAULT_MIN_PROJECTS, threshold=DEFAULT_THRESHOLD):
    """Межпроектные паттерны по namespace. Паттерн — кластер, охватывающий ≥min_projects
    РАЗНЫХ проектов. Возвращает [pattern] отсортированно по весу (число проектов) убыв."""
    patterns = []
    for ns in sorted(buckets):
        for cl in cluster(buckets[ns], threshold):
            projs = sorted({it["project"] for it in cl})
            if len(projs) < min_projects:
                continue
            rep = min(cl, key=lambda it: it["lesson"].get("id", ""))   # детерминированный представитель
            patterns.append({
                "pattern_id": _pattern_id(ns, rep["text"]),
                "namespace": ns,
                "projects": projs,
                "weight": len(projs),
                "lessons": len(cl),
                "representative": {
                    "trigger": rep["lesson"].get("trigger", ""),
                    "action": rep["lesson"].get("action", ""),
                    "kind": rep["lesson"].get("kind", ""),
                },
                "members": [{"project": it["project"], "id": it["lesson"].get("id"),
                             "trigger": it["lesson"].get("trigger", "")} for it in cl],
            })
    patterns.sort(key=lambda p: (p["weight"], p["lessons"]), reverse=True)
    return patterns


# ── запись артефактов (cross-project слой ~/.swissknifeman/analyst) ───────────
def _suggestion_md(pattern):
    rep = pattern["representative"]
    lines = [
        f"# Предложение (draft) — паттерн `{pattern['pattern_id']}`",
        "",
        f"> **Не скилл.** Черновик на промоушен: паттерн повторился в **{pattern['weight']} проектах** "
        f"namespace `{pattern['namespace']}`. Черновик скилла — `analyst suggest {pattern['pattern_id']}`; "
        f"промоут в бакет — человек.",
        "",
        f"- **kind:** {rep.get('kind') or '—'}",
        f"- **trigger:** {rep.get('trigger') or '—'}",
        f"- **action:** {rep.get('action') or '—'}",
        f"- **проекты ({pattern['weight']}):** {', '.join(pattern['projects'])}",
        f"- **уроков в кластере:** {pattern['lessons']}",
        "",
        "## Экземпляры по проектам",
    ]
    for m in pattern["members"]:
        lines.append(f"- `{m['project']}` · {m['id']} — {m['trigger']}")
    lines.append("")
    return "\n".join(lines)


def write_artifacts(env, patterns):
    """Записать index/by_pattern/<id>.json + suggestions/<id>.md. Возвращает пути.
    Атомарно; каталоги создаются. Только для найденных паттернов (пустой список — no-op)."""
    idx_dir = env.state_dir / "index" / "by_pattern"
    sug_dir = env.state_dir / "suggestions"
    written = []
    for p in patterns:
        atomic_write_json(idx_dir / f"{p['pattern_id']}.json",
                          {**p, "generated_at": now_iso()})
        atomic_write_text(sug_dir / f"{p['pattern_id']}.md", _suggestion_md(p))
        written.append(p["pattern_id"])
    return written


# ── reconcile: прун осиротевших артефактов (строго в scope прогона) ───────────
def list_existing_patterns(env):
    """Существующие артефакты паттернов на диске: [{pattern_id, namespace, index_path,
    suggestion_path}]. namespace берётся из ПОЛЯ 'namespace' индекса (имя файла не реверсим).
    Битый/непрочитанный индекс либо без pattern_id/namespace → SKIP (не удаляем
    неклассифицированное). Отсортировано по pattern_id — детерминизм."""
    idx_dir = env.state_dir / "index" / "by_pattern"
    sug_dir = env.state_dir / "suggestions"
    out = []
    if not idx_dir.is_dir():
        return out
    for idx_path in sorted(idx_dir.glob("*.json")):
        data = safe_load_json(idx_path, None)
        if not isinstance(data, dict):
            continue                       # битый JSON → SKIP
        pid = data.get("pattern_id")
        ns = data.get("namespace")
        if not pid or not ns:
            continue                       # без классифицирующих полей → SKIP
        out.append({
            "pattern_id": pid,
            "namespace": ns,
            "index_path": idx_path,
            "suggestion_path": sug_dir / f"{pid}.md",
        })
    return out


def stale_pattern_ids(existing, written_ids, scanned_namespaces):
    """ЧИСТАЯ (без I/O): id артефактов-сирот к снятию. Сирота = существующий паттерн, чей
    namespace ВХОДИТ в отсканированный этим прогоном scope, но которого НЕТ среди written
    (регенерённых). namespace ВНЕ scope → НЕ трогаем: чужой ns не рескан → его отсутствие
    в written ≠ 'устарело'. Так scoped-прогон (scan --namespace X) прунит только ns X."""
    written = set(written_ids)
    scoped = set(scanned_namespaces)
    return {e["pattern_id"] for e in existing
            if e["namespace"] in scoped and e["pattern_id"] not in written}


def prune_artifacts(env, stale_ids):
    """Снять index+suggestion файлы для stale_ids — ОБА вместе (missing_ok, синхронно).
    Возвращает removed[] — отсортированный список снятых pattern_id. Детерминированно."""
    idx_dir = env.state_dir / "index" / "by_pattern"
    sug_dir = env.state_dir / "suggestions"
    removed = []
    for pid in sorted(stale_ids):
        (idx_dir / f"{pid}.json").unlink(missing_ok=True)
        (sug_dir / f"{pid}.md").unlink(missing_ok=True)
        removed.append(pid)
    return removed


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_scan(env, argv):
    """analyst scan [--min-projects N] [--namespace NS] [--threshold T] [--no-prune] [--dry-run] [--json]
    — межпроектные паттерны уроков (config.json) → suggestions/ (namespace-изолированно)."""
    from .common import die, parse_args, warn
    opts, _ = parse_args(argv, {"--min-projects": "str", "--namespace": "str",
                                "--threshold": "str", "--no-prune": "bool",
                                "--dry-run": "bool", "--json": "bool"})
    if opts["help"]:
        print("analyst scan [--min-projects N] [--namespace NS] [--threshold T] [--no-prune] [--dry-run] [--json]\n"
              "  Обход config.json:projects[] → per-project уроки → Jaccard-кластеры → паттерны в ≥N\n"
              "  проектах (namespace-изолированно) → draft-предложения в ~/.swissknifeman/analyst/.\n"
              "  Реконсиляция: осиротевшие index+suggestion файлы (исчезнувшие паттерны) снимаются\n"
              "  СТРОГО в scope прогона (--no-prune выключает; --dry-run ничего не пишет и\n"
              "  показывает would-prune ОТНОСИТЕЛЬНО would-be-written паттернов этого прогона).")
        return

    try:
        min_projects = int(opts["min_projects"]) if opts["min_projects"] else DEFAULT_MIN_PROJECTS
    except ValueError:
        die(f"--min-projects ждёт число, получено: {opts['min_projects']}")
    try:
        threshold = float(opts["threshold"]) if opts["threshold"] else DEFAULT_THRESHOLD
    except ValueError:
        die(f"--threshold ждёт число, получено: {opts['threshold']}")

    cfg = env.default_config
    if not Path(cfg).is_file():
        die(f"реестр проектов не найден: {cfg} — cross-project scan нужен config.json "
            "(корень монорепо экосистемы)")
    projects = enabled_projects(load_projects(cfg), opts["namespace"] or None)
    if not projects:
        warn("нет enabled-проектов в реестре"
             + (f" для namespace {opts['namespace']}" if opts["namespace"] else ""))

    buckets = gather_by_namespace(projects)
    patterns = detect_patterns(buckets, min_projects=min_projects, threshold=threshold)
    current_ids = {p["pattern_id"] for p in patterns}   # что ДОЛЖНО существовать в scope прогона

    written = [] if opts["dry_run"] else write_artifacts(env, patterns)

    # ── reconcile: снять осиротевшие артефакты СТРОГО в scope этого прогона ──
    # scope: {namespace} при --namespace X (регенерён только он), ИНАЧЕ union ns всех
    # enabled-проектов (полный обход). Чужой ns не рескан → его файлы не трогаем.
    scanned_namespaces = ({opts["namespace"]} if opts["namespace"]
                          else {ns for pr in projects for ns in pr["namespaces"]})
    prune_enabled = not opts["no_prune"]
    params_default = (min_projects == DEFAULT_MIN_PROJECTS and threshold == DEFAULT_THRESHOLD)
    pruned = []
    if prune_enabled and not params_default:
        # [POSSIBLE-DEFECT] нестандартные параметры делают written строже → авто-прун снял бы
        # то, что дефолтный scan оставит (churn: удалил сейчас — пересоздал следующим дефолтом).
        # Осознанно ограничиваем авто-прун дефолтными параметрами (данные важнее авточистки).
        warn("[POSSIBLE-DEFECT] нестандартные --min-projects/--threshold — авто-прун сирот пропущен "
             "(риск churn). Прогоните scan с дефолтными параметрами для чистки сирот.")
    elif prune_enabled:
        # list_existing_patterns — ПОСЛЕ write_artifacts: актуальные попадут в current_ids
        # (не стухнут), сироты — нет. В dry-run write не было → показываем would-prune.
        stale = stale_pattern_ids(list_existing_patterns(env), current_ids, scanned_namespaces)
        pruned = sorted(stale) if opts["dry_run"] else prune_artifacts(env, stale)

    if opts["json"]:
        print(json.dumps({"projects_scanned": len(projects),
                          "namespaces": sorted(buckets),
                          "min_projects": min_projects,
                          "patterns": patterns,
                          "written": written,
                          "pruned": pruned,
                          "dry_run": bool(opts["dry_run"])}, ensure_ascii=False, indent=2))
        return

    ns_count = len(buckets)
    print(f"\nanalyst scan — проектов: {len(projects)} · namespace с уроками: {ns_count} · "
          f"порог ≥{min_projects} проектов\n")
    if not patterns:
        print("  ✓ GREEN — межпроектных паттернов не найдено "
              "(мало уроков / не повторяются в ≥N проектах). Собери больше: analyst digest по проектам.")
    else:
        for p in patterns:
            print(f"  ⚑ [{p['namespace']}] {p['pattern_id']}  · {p['weight']} проект(ов), "
                  f"{p['lessons']} урок(ов)")
            print(f"      {p['representative']['trigger']}")
            print(f"      проекты: {', '.join(p['projects'])}")
        dest = env.state_dir / "suggestions"
        print(f"\n  {len(patterns)} паттерн(ов) → {'(dry-run, не записано)' if opts['dry_run'] else dest}")
        print("  Черновик скилла: analyst suggest <pattern_id> (P4). Промоут в бакет — человек, не авто-запись.")
    if pruned:
        label = "сирот к снятию (dry-run)" if opts["dry_run"] else "снято сирот"
        print(f"  {label}: {len(pruned)}")
    print()

