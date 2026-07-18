"""journal — append-only писатель пер-планового журнала исполнения
`plans/<PLAN-ID>/journal.jsonl` (схема P1.1 sealed v1,
`root/contracts/plan-journal-schema.md`).

Одна запись = одна строка валидного JSON (NDJSON, D20). Запись только ДОПИСЫВАЕТСЯ —
существующие строки никогда не переписываются/не удаляются (§1 контракта); поэтому
`append()` открывает файл в режиме `"a"` и делает РОВНО один `write()` на запись —
конкурентные сессии дописывают свою строку без чужого построчного разрыва (git-merge
разрешается конкатенацией строк, контракт §1).

Вызывается close-протоколом команд `/task:plan-*` (P1.3) — старт-запись
(`result="in-progress"`) в начале исполнения item'а, финал-запись (терминальный
`result` + запечённые cost/turns/duration) при закрытии (контракт §2, «пара записей»).

stdlib-only (json/argparse/pathlib) — конвенция пакета task."""
import argparse
import json
import sys
from pathlib import Path

try:
    # core.term.now_iso — тот же формат, что схема §2 (`2026-07-18T18:42:07Z`).
    # core/ опционален (standalone-раскладка пакета без монорепо-родителя, как
    # у task.plan_lint) — фолбэк ниже даёт байт-в-байт тот же формат.
    from core.term import now_iso as _now_iso
except ImportError:  # pragma: no cover - standalone-фолбэк
    from datetime import datetime, timezone

    def _now_iso():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

FILENAME = "journal.jsonl"

# --- канон схемы P1.1 (root/contracts/plan-journal-schema.md §2, §2.1, §2.2) -----
COMMANDS = ("plan-exec", "plan-run", "plan-close", "plan-audit", "plan-design")
FRICTION_VALUES = (
    "escalation", "routing-blocked", "red-audit", "deviation", "retry", "no-op",
)
RESULT_VALUES = (
    "in-progress", "closed-green", "closed-deviations", "blocked",
    "escalated", "no-op", "audit-green", "audit-red",
)
REQUIRED_FIELDS = (
    "ts", "plan_id", "item_id", "command", "session_id", "run_id", "attempt",
    "actor", "friction", "result", "cost_usd", "num_turns", "duration_ms", "note",
)


class JournalValidationError(ValueError):
    """Запись не прошла schema-валидацию P1.1 — `append()` не пишет строку."""


def validate_entry(entry):
    """Сверяет запись со схемой P1.1 (§2). Копит ВСЕ нарушения разом (не первое
    найденное) — исполнитель чинит одним проходом, не итерацией по одной ошибке.
    Бросает `JournalValidationError`, если нарушения есть."""
    if not isinstance(entry, dict):
        raise JournalValidationError("запись обязана быть dict")

    errors = [f"нет обязательного поля «{f}»" for f in REQUIRED_FIELDS if f not in entry]
    if errors:
        raise JournalValidationError("; ".join(errors))

    def _check_str(name, *, allow_none=False, allow_empty=False):
        v = entry[name]
        if v is None and allow_none:
            return
        if not isinstance(v, str) or (not allow_empty and not v):
            errors.append(f"{name}: обязано быть {'str|null' if allow_none else 'непустой str'}")

    def _check_number(name):
        v = entry[name]
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            errors.append(f"{name}: обязано быть number|null")

    _check_str("ts")
    _check_str("plan_id")
    _check_str("item_id")  # P1.1 — всегда set (сужение P0.6 str|null, §5)
    _check_str("session_id", allow_none=True)
    _check_str("run_id", allow_none=True)
    _check_str("actor")
    _check_str("note", allow_none=True)

    if entry["command"] not in COMMANDS:
        errors.append(f"command: «{entry['command']}» не входит в {COMMANDS}")
    if entry["result"] not in RESULT_VALUES:
        errors.append(f"result: «{entry['result']}» не входит в {RESULT_VALUES}")

    attempt = entry["attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        errors.append("attempt: обязано быть int ≥1")

    friction = entry["friction"]
    if not isinstance(friction, list) or any(v not in FRICTION_VALUES for v in friction):
        errors.append(f"friction: обязан быть массивом значений из {FRICTION_VALUES}")

    for name in ("cost_usd", "num_turns", "duration_ms"):
        _check_number(name)

    if errors:
        raise JournalValidationError("; ".join(errors))


def new_entry(*, plan_id, item_id, command, actor, result, session_id=None, run_id=None,
              attempt=1, friction=(), cost_usd=None, num_turns=None, duration_ms=None,
              note=None, ts=None):
    """Собирает запись по схеме P1.1 с дефолтами контракта (§2) — единая точка сборки,
    чтобы close-протокол команд не собирал dict вручную по месту россыпью полей."""
    return {
        "ts": ts or _now_iso(),
        "plan_id": plan_id,
        "item_id": item_id,
        "command": command,
        "session_id": session_id,
        "run_id": run_id,
        "attempt": attempt,
        "actor": actor,
        "friction": list(friction),
        "result": result,
        "cost_usd": cost_usd,
        "num_turns": num_turns,
        "duration_ms": duration_ms,
        "note": note,
    }


def append(plan_dir, entry):
    """Дописывает ОДНУ запись в `plans/<ID>/journal.jsonl`. Валидирует ДО записи
    (§2) — битая запись не попадает в durable-историю плана (§1). Возвращает путь
    файла. Файла нет — создаётся (append-режим сам создаёт)."""
    validate_entry(entry)
    path = Path(plan_dir) / FILENAME
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path


# --- CLI: `python3 -m task.journal append --plan … --item … …` (вызов из команд) --

def _parse_friction(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _build_arg_parser():
    p = argparse.ArgumentParser(
        prog="task.journal", description="Append-only журнал исполнения плана (P1.1)")
    sub = p.add_subparsers(dest="cmd", required=True)
    ap = sub.add_parser("append", help="дописать запись в plans/<ID>/journal.jsonl")
    ap.add_argument("--plan-dir", required=True, help="каталог плана plans/<PLAN-ID>")
    ap.add_argument("--plan", required=True, dest="plan_id")
    ap.add_argument("--item", required=True, dest="item_id")
    ap.add_argument("--command", required=True, choices=COMMANDS)
    ap.add_argument("--result", required=True, choices=RESULT_VALUES)
    ap.add_argument("--actor", required=True, help="`<model>/<effort>` или `owner`")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--friction", default="", help="через запятую, из закрытого списка")
    ap.add_argument("--cost-usd", type=float, default=None)
    ap.add_argument("--num-turns", type=int, default=None)
    ap.add_argument("--duration-ms", type=float, default=None)
    ap.add_argument("--note", default=None)
    return p


def main(argv=None):
    args = _build_arg_parser().parse_args(argv)
    if args.cmd != "append":  # pragma: no cover - argparse уже гейтит choices
        return 1
    entry = new_entry(
        plan_id=args.plan_id, item_id=args.item_id, command=args.command,
        actor=args.actor, result=args.result, session_id=args.session_id,
        run_id=args.run_id, attempt=args.attempt,
        friction=_parse_friction(args.friction), cost_usd=args.cost_usd,
        num_turns=args.num_turns, duration_ms=args.duration_ms, note=args.note,
    )
    try:
        path = append(args.plan_dir, entry)
    except JournalValidationError as e:
        print(f"ERROR: запись журнала не прошла валидацию: {e}", file=sys.stderr)
        return 1
    print(f"journal: append → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
