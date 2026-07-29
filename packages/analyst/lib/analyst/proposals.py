"""analyst proposals (2026.07.02-SKM-MASTER-002 P4.3) — черновики СИСТЕМНЫХ предложений улучшений.

Мост между тем, что analyst НАБЛЮДАЕТ (digest/scan/ingest — данные о конкретном проекте/
паттерне), и тем, что улучшить стоило бы НА УРОВНЕ ЭКОСИСТЕМЫ: стек-пак (`stack-pack`),
override целевого проекта (`project-override`) или документацию (`docs`). Пишет ТОЛЬКО в
свой каталог:

    ~/.swissknifeman/analyst/proposals/<type>/<id>/
      PROPOSAL.md            — человекочитаемое тело (детерминировано, БЕЗ timestamp)
      proposal.meta.json     — провенанс-паспорт + ТЕКУЩИЙ статус (draft|accepted|rejected)
    ~/.swissknifeman/analyst/proposals/audit.ndjson
                              — append-only история смен статуса (НЕ тело — тело статус не несёт)

ИНВАРИАНТ (analyst): авто-применение ЗАПРЕЩЕНО — analyst НИКОГДА не пишет в agent-packs/
шаблоны/проекты. Промоут `accepted`-предложения в реальную правку — руками человека/
plan-design; этот модуль лишь копит черновик и печатает handoff-последовательность
«что и куда применить» (см. `handoff_lines`/`build_handoff_lines`).

Writer edit-safe как в `suggest.py` (D6): тело — детерминированная функция входа (без
timestamp — иначе seed_sha256-детект ручных правок ложно срабатывал бы на каждый ре-create).
Статус живёт ТОЛЬКО в proposal.meta.json (текущий указатель) — смена статуса НЕ переписывает
тело и не двигает файл между каталогами (в отличие от lessons.move_lesson: `<type>/<id>/`
статичен), а лишь дописывает audit-строку (история переходов, никогда не перезаписывается)."""
import hashlib
import json
import os
from pathlib import Path

from .common import (atomic_write_json, atomic_write_text, die, now_iso,
                     parse_args, read_ndjson, safe_load_json, sanitize)

PROPOSAL_SCHEMA_VERSION = 1
PROPOSAL_TYPES = ("stack-pack", "project-override", "docs")
STATUSES = ("draft", "accepted", "rejected")
TITLE_SLUG_MAX = 40

# Generic (repo-grounded) handoff-шаги по типу — куда именно (--target) решает автор
# предложения, ЧТО и КАК применять — фиксировано здесь (analyst сюда не пишет НИКОГДА).
_HANDOFF_STEPS = {
    "stack-pack": (
        "правки — ТОЛЬКО в паке harness: packages/harness/configs/claude-code/agent-packs/"
        "<pack>/ (человек, по скиллу system/agent-packs); analyst НЕ пишет в agent-packs/",
        "версия пака + запись в его CHANGELOG.md "
        "(packages/harness/configs/claude-code/agent-packs/<pack>/CHANGELOG.md)",
        "раскатка на проекты: `harness agent-packs upgrade --pack <pack> --target <project>` "
        "(user_owned-файлы проектов пак не тронет — D11 base+overlay)",
        "bash packages/harness/scripts/validate.sh",
    ),
    "project-override": (
        "правки — ТОЛЬКО в override/extension-зоне ЦЕЛЕВОГО проекта: user_owned-файлы "
        "агент-пака (base+overlay, D11); analyst НЕ пишет в проекты",
        "generated/managed-файлы пака руками НЕ редактировать — их перезатрёт следующий "
        "`harness agent-packs render`/`upgrade`",
        "сверка после правки: harness agent-packs doctor --target <project>",
        "валидация — стандартный dev-loop целевого проекта",
    ),
    "docs": (
        "правки — в целевой документации: docs/reference.md · roadmap/ (зонтик) или "
        "packages/<pkg>/docs/ (per-package, standalone-сборка); analyst НЕ пишет в docs/",
        "per-package правки — при необходимости прогнать scripts/docs-sync.sh (зонтичный агрегат)",
        "если предложение про сам пакет analyst — отметить в packages/analyst/CLAUDE.md",
    ),
}


def handoff_steps(ptype):
    """ЧИСТО: [шаг,...] для типа предложения. Неизвестный/битый type (напр. из повреждённого
    meta.json) → fallback на 'docs' (самый нейтральный маршрут), не падаем."""
    return list(_HANDOFF_STEPS.get(ptype, _HANDOFF_STEPS["docs"]))


def build_handoff_lines(ptype):
    """ЧИСТО: пронумерованные строки handoff для теле PROPOSAL.md/печати CLI."""
    return [f"{i}. {s}" for i, s in enumerate(handoff_steps(ptype), 1)]


# ── id (детерминированный слаг от типа+содержимого) ──────────────────────────
def make_proposal_id(ptype, title):
    """Детерминированный id: slug(title) + короткий хэш(type|title). Тот же (type, title)
    → тот же id (идемпотентный create/update-цикл, как pattern_id в scan.py); смена title
    заводит НОВОЕ предложение (это осознанно — title = identity, summary/body — содержимое,
    эволюционирующее через edit-safe writer)."""
    slug = sanitize(title)[:TITLE_SLUG_MAX] or ptype
    h = hashlib.sha1(f"{ptype}\x00{title}".encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{h}"


# ── чистые генераторы (без I/O/часов) ────────────────────────────────────────
def build_proposal_md(ptype, pid, title, summary, body, target):
    """ЧИСТО: полный текст PROPOSAL.md. Детерминирован от входа — timestamp НЕ попадает
    в тело (см. модульный docstring). Статус тоже НЕ в теле: SSOT статуса — meta.json,
    смена статуса не должна триггерить перезапись/переиздание тела."""
    lines = [
        f"# Предложение (draft) — {title}",
        "",
        "> **Не применяется автоматически.** analyst НИКОГДА не пишет в agent-packs/шаблоны/"
        "проекты — черновик ждёт ревью человека/plan-design. Статус меняет "
        "`analyst proposals status <id> accepted|rejected`.",
        "",
        f"- **type:** {ptype}",
        f"- **id:** {pid}",
        f"- **target:** {target or '—'}",
        "",
        "## Резюме",
        summary or "TODO — кратко, что предлагается.",
        "",
        "## Обоснование / контекст",
        body or "TODO — почему это нужно, что наблюдалось.",
        "",
        "## Handoff — что и куда применить",
    ]
    lines += build_handoff_lines(ptype)
    lines.append("")
    return "\n".join(lines)


def _seed_hash(text):
    """sha256-хэш тела — маркер «сгенерённого» состояния для детекта ручных правок (D6)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_meta(ptype, pid, title, target, seed_sha256, status, created_at, updated_at):
    """ЧИСТО: провенанс-паспорт proposal.meta.json (SSOT текущего статуса)."""
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "generated_by": "analyst proposals",
        "id": pid,
        "type": ptype,
        "title": title,
        "target": target,
        "status": status,
        "seed_sha256": seed_sha256,
        "created_at": created_at,
        "updated_at": updated_at,
    }


# ── пути (cross-project слой ~/.swissknifeman/analyst) ───────────────────────
def _proposals_root(env):
    return env.state_dir / "proposals"


def _proposal_dir(env, ptype, pid):
    return _proposals_root(env) / ptype / pid


def _audit_path(env):
    return _proposals_root(env) / "audit.ndjson"


# ── чтение ───────────────────────────────────────────────────────────────────
def load_proposal(env, ptype, pid):
    """meta dict одного предложения или None (нет/битый meta.json)."""
    meta = safe_load_json(_proposal_dir(env, ptype, pid) / "proposal.meta.json", None)
    return meta if isinstance(meta, dict) else None


def find_proposal(env, pid, ptype=None):
    """(meta, ptype) первого совпадения по id; ptype сужает поиск (иначе перебор
    PROPOSAL_TYPES). (None, None), если не найдено."""
    for t in (ptype,) if ptype else PROPOSAL_TYPES:
        meta = load_proposal(env, t, pid)
        if meta is not None:
            return meta, t
    return None, None


def list_proposals(env, *, ptype=None, status=None):
    """[(meta, ptype)] отсортировано по (type, id). Битый/бездиректорный вход — SKIP."""
    out = []
    for t in (ptype,) if ptype else PROPOSAL_TYPES:
        tdir = _proposals_root(env) / t
        if not tdir.is_dir():
            continue
        for d in sorted(tdir.iterdir()):
            if not d.is_dir():
                continue
            meta = load_proposal(env, t, d.name)
            if meta is None:
                continue
            if status and meta.get("status") != status:
                continue
            out.append((meta, t))
    return out


def read_audit(env):
    """Список записей proposals/audit.ndjson (пропускает битые строки). [] если нет файла."""
    return read_ndjson(_audit_path(env))


# ── аудит (append-only, тот же идиом что lessons.audit_append/read_audit) ────
def audit_append(env, record):
    """Дописать одну запись в proposals/audit.ndjson (append-only, никогда не перезаписываем).
    Добавляет ts, если его нет. Создаёт каталог."""
    rec = dict(record)
    rec.setdefault("ts", now_iso())
    path = _audit_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# ── writer с edit-safety (I/O, как suggest.write_draft) ──────────────────────
def write_proposal(env, ptype, title, *, summary="", body="", target="", force=False):
    """Записать/обновить черновик предложения в proposals/<type>/<id>/. Edit-safe (D6):
    - каталога/файла нет            → создать (status="created", meta.status="draft");
    - тело совпадает с генерённым    → нечего менять (status="unchanged");
    - тело == прошлый seed (не правили) либо --force → перегенерить (status="updated"/"forced");
      ТЕКУЩИЙ статус (draft/accepted/rejected) и created_at СОХРАНЯЮТСЯ — content-update не
      откатывает ревью-прогресс;
    - тело != прошлый seed (правили руками) → тело НЕ трогаем, обновляем лишь провенанс meta
      (status="skipped-edited").
    Возвращает (status, pid, proposal_dir). Атомарно; каталоги создаются."""
    if ptype not in PROPOSAL_TYPES:
        raise ValueError(f"неизвестный type предложения: {ptype}")
    pid = make_proposal_id(ptype, title)
    prop_dir = _proposal_dir(env, ptype, pid)
    md_path = prop_dir / "PROPOSAL.md"
    meta_path = prop_dir / "proposal.meta.json"
    md_text = build_proposal_md(ptype, pid, title, summary, body, target)
    new_seed = _seed_hash(md_text)

    def _persist(seed, status, created_at):
        atomic_write_text(md_path, md_text)
        atomic_write_json(meta_path,
                          build_meta(ptype, pid, title, target, seed, status,
                                     created_at, now_iso()))

    if not md_path.exists():
        _persist(new_seed, "draft", now_iso())
        return "created", pid, prop_dir

    current = md_path.read_text(encoding="utf-8")
    prev_meta = safe_load_json(meta_path, {}) or {}
    status = prev_meta.get("status") or "draft"
    created_at = prev_meta.get("created_at") or now_iso()

    if current == md_text:
        return "unchanged", pid, prop_dir

    prev_seed = prev_meta.get("seed_sha256")
    if force or _seed_hash(current) == prev_seed:
        _persist(new_seed, status, created_at)
        return ("forced" if force and _seed_hash(current) != prev_seed
                else "updated"), pid, prop_dir

    # правили руками → тело не перезаписываем; освежаем только провенанс-паспорт (seed = прошлый,
    # чтобы детект правок продолжал работать против последнего СГЕНЕРЁННОГО состояния).
    atomic_write_json(meta_path,
                      build_meta(ptype, pid, title, target, prev_seed, status,
                                 created_at, now_iso()))
    return "skipped-edited", pid, prop_dir


# ── смена статуса (отдельная audit-строка, не перезапись истории) ────────────
def set_status(env, pid, new_status, *, ptype=None, note=""):
    """Перевести предложение в new_status: meta.json — ТЕКУЩИЙ указатель (перезаписывается),
    audit.ndjson — ИСТОРИЯ (только дозапись). Тот же статус → no-op (без audit-дубля).
    Возвращает (meta, old_status, new_status) либо (None, None, None), если не найдено."""
    if new_status not in STATUSES:
        raise ValueError(f"неизвестный статус: {new_status}")
    meta, t = find_proposal(env, pid, ptype)
    if meta is None:
        return None, None, None
    old_status = meta.get("status") or "draft"
    if old_status == new_status:
        return meta, old_status, new_status
    new_meta = dict(meta, status=new_status, updated_at=now_iso())
    atomic_write_json(_proposal_dir(env, t, pid) / "proposal.meta.json", new_meta)
    audit_append(env, {"action": "status-change", "id": pid, "type": t,
                       "from": old_status, "to": new_status, "note": note})
    return new_meta, old_status, new_status


def handoff_lines(meta):
    """Человекочитаемая handoff-последовательность для CLI (заголовок предложения + шаги
    по типу). analyst НИКОГДА сюда не пишет — печать/документирование маршрута человеку."""
    target = meta.get("target") or "<укажи --target: пак/проект/файл-доку>"
    header = [f"  Предложение: {meta.get('title')}  [{meta.get('status')}] · "
             f"id={meta.get('id')} · type={meta.get('type')} · target={target}",
             "  Промоут — ТОЛЬКО человек/plan-design (analyst НЕ пишет в agent-packs/шаблоны/проекты):"]
    return header + [f"    {s}" for s in build_handoff_lines(meta.get("type"))]


# ── CLI ──────────────────────────────────────────────────────────────────────
def _cmd_create(env, argv):
    """analyst proposals create --type T --title TITLE [--summary S] [--body-file F]
    [--target T] [--dry-run] [--json] [--force]"""
    opts, _ = parse_args(argv, {"--type": "str", "--title": "str", "--summary": "str",
                                "--body-file": "str", "--target": "str",
                                "--dry-run": "bool", "--json": "bool", "--force": "bool"})
    if opts["help"]:
        print("analyst proposals create --type stack-pack|project-override|docs --title T\n"
              "  [--summary S] [--body-file F] [--target T] [--dry-run] [--json] [--force]\n"
              "  Черновик предложения (edit-safe: seed_sha256, БЕЗ timestamp в теле).\n"
              "  Пишет ТОЛЬКО в ~/.swissknifeman/analyst/proposals/<type>/<id>/.")
        return
    ptype = opts["type"]
    if ptype not in PROPOSAL_TYPES:
        die(f"--type обязателен, один из: {', '.join(PROPOSAL_TYPES)} (получено: {ptype!r})")
    title = (opts["title"] or "").strip()
    if not title:
        die("--title обязателен: analyst proposals create --type T --title 'заголовок'")

    body = ""
    if opts["body_file"]:
        body_path = Path(os.path.expanduser(opts["body_file"]))
        if not body_path.is_file():
            die(f"--body-file не найден: {body_path}")
        body = body_path.read_text(encoding="utf-8")
    summary = (opts["summary"] or "").strip()
    target = (opts["target"] or "").strip()

    if opts["dry_run"]:
        pid = make_proposal_id(ptype, title)
        text = build_proposal_md(ptype, pid, title, summary, body, target)
        if opts["json"]:
            print(json.dumps({"id": pid, "type": ptype, "status": "dry-run",
                              "path": str(_proposal_dir(env, ptype, pid))},
                             ensure_ascii=False, indent=2))
        else:
            print(f"\nanalyst proposals create (dry-run) — id={pid} · type={ptype}\n")
            print(text)
        return

    status, pid, prop_dir = write_proposal(env, ptype, title, summary=summary, body=body,
                                           target=target, force=opts["force"])
    meta = load_proposal(env, ptype, pid)

    if opts["json"]:
        print(json.dumps({"id": pid, "type": ptype, "write_status": status,
                          "status": meta.get("status"), "path": str(prop_dir)},
                         ensure_ascii=False, indent=2))
        return

    print(f"\nanalyst proposals create — id={pid} · type={ptype} · {status}\n  {prop_dir}\n")
    for line in handoff_lines(meta):
        print(line)
    print()


def _cmd_list(env, argv):
    """analyst proposals list [--type T] [--status draft|accepted|rejected] [--json]"""
    opts, _ = parse_args(argv, {"--type": "str", "--status": "str", "--json": "bool"})
    if opts["help"]:
        print("analyst proposals list [--type T] [--status draft|accepted|rejected] [--json]")
        return
    ptype = opts["type"] or None
    if ptype and ptype not in PROPOSAL_TYPES:
        die(f"--type ждёт один из: {', '.join(PROPOSAL_TYPES)}")
    status = opts["status"] or None
    if status and status not in STATUSES:
        die(f"--status ждёт один из: {', '.join(STATUSES)}")

    items = list_proposals(env, ptype=ptype, status=status)
    if opts["json"]:
        print(json.dumps({"proposals": [
            {"id": m.get("id"), "type": t, "title": m.get("title"),
             "status": m.get("status"), "target": m.get("target")}
            for m, t in items]}, ensure_ascii=False, indent=2))
        return
    if not items:
        print("\nanalyst proposals — пусто (см. analyst proposals create)\n")
        return
    print(f"\nanalyst proposals — {len(items)}\n")
    for m, t in items:
        tail = f" (target: {m['target']})" if m.get("target") else ""
        print(f"  [{m.get('status')}] {t}/{m.get('id')} — {m.get('title')}{tail}")
    print()


def _cmd_show(env, argv):
    """analyst proposals show <id> [--type T] [--json]"""
    opts, pos = parse_args(argv, {"--type": "str", "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print("analyst proposals show <id> [--type T] [--json]")
        return
    meta, t = find_proposal(env, pos[0], opts["type"] or None)
    if meta is None:
        die(f"предложение не найдено: {pos[0]}")
    md_text = (_proposal_dir(env, t, pos[0]) / "PROPOSAL.md").read_text(encoding="utf-8")
    if opts["json"]:
        print(json.dumps({"meta": meta, "body": md_text}, ensure_ascii=False, indent=2))
        return
    print(md_text)


def _cmd_status(env, argv):
    """analyst proposals status <id> draft|accepted|rejected [--type T] [--note N] [--json]"""
    opts, pos = parse_args(argv, {"--type": "str", "--note": "str", "--json": "bool"}, max_pos=2)
    if opts["help"] or len(pos) < 2:
        print("analyst proposals status <id> draft|accepted|rejected [--type T] [--note N] [--json]\n"
              "  Смена статуса — ОТДЕЛЬНАЯ audit-строка в proposals/audit.ndjson (история не\n"
              "  перезаписывается). НЕ применяет предложение — только меняет метку.")
        return
    pid, new_status = pos[0], pos[1]
    if new_status not in STATUSES:
        die(f"статус должен быть одним из: {', '.join(STATUSES)} (получено: {new_status!r})")
    meta, old, new = set_status(env, pid, new_status, ptype=opts["type"] or None,
                                note=opts["note"] or "")
    if meta is None:
        die(f"предложение не найдено: {pid}")

    if opts["json"]:
        print(json.dumps({"id": pid, "from": old, "to": new}, ensure_ascii=False, indent=2))
        return
    if old == new:
        print(f"\nanalyst proposals status — {pid} уже в статусе {new} (без изменений)\n")
        return
    print(f"\nanalyst proposals status — {pid}: {old} → {new} (audit-запись добавлена)\n")
    if new == "accepted":
        for line in handoff_lines(meta):
            print(line)
        print()


def _cmd_handoff(env, argv):
    """analyst proposals handoff <id> [--type T] [--json]"""
    opts, pos = parse_args(argv, {"--type": "str", "--json": "bool"}, max_pos=1)
    if opts["help"] or not pos:
        print("analyst proposals handoff <id> [--type T] [--json]\n"
              "  Печать handoff-последовательности «что и куда применить» (человеку/plan-design).\n"
              "  analyst НИКОГДА не пишет в agent-packs/шаблоны/проекты — только печатает маршрут.")
        return
    meta, t = find_proposal(env, pos[0], opts["type"] or None)
    if meta is None:
        die(f"предложение не найдено: {pos[0]}")
    lines = handoff_lines(meta)
    if opts["json"]:
        print(json.dumps({"id": pos[0], "type": t, "status": meta.get("status"),
                          "handoff": lines}, ensure_ascii=False, indent=2))
        return
    print()
    for line in lines:
        print(line)
    print()


_SUBCOMMANDS = {
    "create": _cmd_create,
    "list": _cmd_list,
    "show": _cmd_show,
    "status": _cmd_status,
    "handoff": _cmd_handoff,
}


def cmd_proposals(env, argv):
    """analyst proposals <create|list|show|status|handoff> [...]
    — черновики системных предложений (stack-pack/project-override/docs) в
    ~/.swissknifeman/analyst/proposals/. analyst НИКОГДА не пишет в agent-packs/шаблоны/
    проекты — только копит черновик и печатает handoff-последовательность человеку."""
    if not argv or argv[0] in ("-h", "--help"):
        print("analyst proposals <create|list|show|status|handoff> [...]\n"
              "  create --type stack-pack|project-override|docs --title T [--summary S]\n"
              "         [--body-file F] [--target T] [--dry-run] [--json] [--force]\n"
              "  list   [--type T] [--status draft|accepted|rejected] [--json]\n"
              "  show   <id> [--type T] [--json]\n"
              "  status <id> draft|accepted|rejected [--type T] [--note N] [--json]\n"
              "  handoff <id> [--type T] [--json]\n"
              "  Черновики НЕ применяются автоматически — промоут accepted делает человек/\n"
              "  plan-design руками (см. handoff). Каталог: ~/.swissknifeman/analyst/proposals/.")
        return
    sub, rest = argv[0], argv[1:]
    handler = _SUBCOMMANDS.get(sub)
    if handler is None:
        die(f"неизвестная подкоманда proposals: {sub} (см. analyst proposals --help)")
    handler(env, rest)
