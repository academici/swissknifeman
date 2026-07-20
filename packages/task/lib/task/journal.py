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
import hashlib
import json
import re
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
EXCEPTIONS_FILENAME = "journal-exceptions.jsonl"
EXCEPTION_REQUIRED_FIELDS = (
    "ts", "plan_id", "target_line", "target_sha256", "invalid_fields",
    "owner_decision", "actor", "reason",
)
HISTORICAL_EXCEPTION_FIELDS = ("friction",)

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


def entry_error_map(entry):
    """Возвращает ошибки P1.1, сгруппированные по полям.

    Карта — единый источник для обычной валидации и sealed sidecar: исключение может
    сопоставить только точный набор ошибочных полей, не повторяя enum-проверки.
    """
    if not isinstance(entry, dict):
        return {"<entry>": ["запись обязана быть dict"]}

    errors = {}

    def add(name, message):
        errors.setdefault(name, []).append(message)

    for field in REQUIRED_FIELDS:
        if field not in entry:
            add(field, f"нет обязательного поля «{field}»")
    if errors:
        return errors

    def check_str(name, *, allow_none=False, allow_empty=False):
        value = entry[name]
        if value is None and allow_none:
            return
        if not isinstance(value, str) or (not allow_empty and not value):
            add(name, f"{name}: обязано быть {'str|null' if allow_none else 'непустой str'}")

    def check_number(name):
        value = entry[name]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            add(name, f"{name}: обязано быть number|null")

    check_str("ts")
    check_str("plan_id")
    check_str("item_id")
    check_str("session_id", allow_none=True)
    check_str("run_id", allow_none=True)
    check_str("actor")
    check_str("note", allow_none=True)

    if entry["command"] not in COMMANDS:
        add("command", f"command: «{entry['command']}» не входит в {COMMANDS}")
    if entry["result"] not in RESULT_VALUES:
        add("result", f"result: «{entry['result']}» не входит в {RESULT_VALUES}")

    attempt = entry["attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        add("attempt", "attempt: обязано быть int ≥1")

    friction = entry["friction"]
    if not isinstance(friction, list) or any(value not in FRICTION_VALUES for value in friction):
        add("friction", f"friction: обязан быть массивом значений из {FRICTION_VALUES}")

    for name in ("cost_usd", "num_turns", "duration_ms"):
        check_number(name)
    return errors


def validate_entry(entry):
    """Сверяет запись со схемой P1.1 (§2). Копит ВСЕ нарушения разом (не первое
    найденное) — исполнитель чинит одним проходом, не итерацией по одной ошибке.
    Бросает `JournalValidationError`, если нарушения есть."""
    errors = entry_error_map(entry)
    if errors:
        raise JournalValidationError("; ".join(
            message for messages in errors.values() for message in messages))


def _decision_exists(plan_dir, decision):
    plan_md = Path(plan_dir) / "plan.md"
    try:
        return re.search(rf"^\|\s*{re.escape(decision)}\s*\|", plan_md.read_text(
            encoding="utf-8"), re.MULTILINE) is not None
    except OSError:
        return False


def _exception_errors(record, plan_dir, plan_id, journal_lines, seen_targets):
    errors = []
    if not isinstance(record, dict):
        return ["sidecar record обязан быть JSON object"]
    keys = set(record)
    expected = set(EXCEPTION_REQUIRED_FIELDS)
    if keys != expected:
        errors.append("sidecar record обязан содержать только exact required fields")
        return errors
    for name in ("ts", "plan_id", "target_sha256", "owner_decision", "actor", "reason"):
        if not isinstance(record[name], str) or not record[name]:
            errors.append(f"{name}: обязано быть непустой str")
    if record["plan_id"] != plan_id:
        errors.append("plan_id не совпадает с canonical plan ID")
    if (not isinstance(record["target_line"], int) or isinstance(record["target_line"], bool)
            or record["target_line"] < 1 or record["target_line"] > len(journal_lines)
            or not journal_lines[record["target_line"] - 1].strip()):
        errors.append("target_line не указывает на physical non-empty journal line")
        return errors
    target_line = record["target_line"]
    if target_line in seen_targets:
        errors.append("duplicate exception target_line")
    raw = journal_lines[target_line - 1]
    if record["target_sha256"] != hashlib.sha256(raw.encode("utf-8")).hexdigest():
        errors.append("target_sha256 не совпадает с raw SHA-256 target line")
    if record["invalid_fields"] != list(HISTORICAL_EXCEPTION_FIELDS):
        errors.append("invalid_fields обязан быть exact [\"friction\"]")
    owner_decision = record["owner_decision"]
    if isinstance(owner_decision, str) and (
            not re.fullmatch(r"D\d+", owner_decision)
            or not _decision_exists(plan_dir, owner_decision)):
        errors.append(f"owner_decision {owner_decision!r} отсутствует в plan.md")
    try:
        entry = json.loads(raw)
    except json.JSONDecodeError:
        errors.append("target journal line не JSON")
        return errors
    if not isinstance(entry, dict) or entry.get("plan_id") != plan_id:
        errors.append("target event не принадлежит canonical plan ID")
        return errors
    actual_fields = set(entry_error_map(entry))
    if not actual_fields:
        errors.append("target event уже валидна")
    elif actual_fields != set(HISTORICAL_EXCEPTION_FIELDS):
        errors.append("invalid_fields не совпадает с exact target schema error set")
    return errors


def validate_exceptions(plan_dir, plan_id):
    """Проверяет optional D51 sidecar и возвращает safe line→record map/error list.

    Любая ошибка делает map пустой: malformed exception никогда не ослабляет журнал.
    """
    plan_dir = Path(plan_dir)
    sidecar = plan_dir / EXCEPTIONS_FILENAME
    if not sidecar.exists():
        return {}, []
    try:
        journal_lines = (plan_dir / FILENAME).read_text(encoding="utf-8").splitlines()
        sidecar_lines = sidecar.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return {}, [f"{EXCEPTIONS_FILENAME} не читается: {exc}"]
    records, errors, seen_targets = {}, [], set()
    for number, raw in enumerate(sidecar_lines, 1):
        if not raw.strip():
            errors.append(f"{EXCEPTIONS_FILENAME}:{number}: пустая строка запрещена")
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"{EXCEPTIONS_FILENAME}:{number}: не JSON: {exc}")
            continue
        record_errors = _exception_errors(record, plan_dir, plan_id, journal_lines, seen_targets)
        if record_errors:
            errors.extend(f"{EXCEPTIONS_FILENAME}:{number}: {error}" for error in record_errors)
            continue
        seen_targets.add(record["target_line"])
        records[record["target_line"]] = record
    return ({}, errors) if errors else (records, [])


def append_exception(plan_dir, *, target_line, invalid_fields, owner_decision, actor, reason,
                     ts=None):
    """Append-only writer for one owner-gated historical schema exception."""
    plan_dir = Path(plan_dir)
    try:
        journal_lines = (plan_dir / FILENAME).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise JournalValidationError(f"journal.jsonl не читается: {exc}") from exc
    if not isinstance(target_line, int) or target_line < 1 or target_line > len(journal_lines):
        raise JournalValidationError("target_line не указывает на journal.jsonl")
    record = {
        "ts": ts or _now_iso(), "plan_id": plan_dir.name, "target_line": target_line,
        "target_sha256": hashlib.sha256(journal_lines[target_line - 1].encode("utf-8")).hexdigest(),
        "invalid_fields": list(invalid_fields), "owner_decision": owner_decision,
        "actor": actor, "reason": reason,
    }
    existing, errors = validate_exceptions(plan_dir, plan_dir.name)
    if errors:
        raise JournalValidationError("; ".join(errors))
    errors = _exception_errors(record, plan_dir, plan_dir.name, journal_lines, set(existing))
    if errors:
        raise JournalValidationError("; ".join(errors))
    path = plan_dir / EXCEPTIONS_FILENAME
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


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
    ep = sub.add_parser("exception", help="дописать owner-gated historical schema exception")
    ep.add_argument("--plan-dir", required=True, help="каталог plans/<PLAN-ID>")
    ep.add_argument("--target-line", required=True, type=int)
    ep.add_argument("--invalid-fields", required=True, help="только friction")
    ep.add_argument("--owner-decision", required=True)
    ep.add_argument("--actor", required=True)
    ep.add_argument("--reason", required=True)
    return p


def main(argv=None):
    args = _build_arg_parser().parse_args(argv)
    if args.cmd == "exception":
        try:
            path = append_exception(
                args.plan_dir, target_line=args.target_line,
                invalid_fields=_parse_friction(args.invalid_fields),
                owner_decision=args.owner_decision, actor=args.actor, reason=args.reason)
        except JournalValidationError as e:
            print(f"ERROR: exception sidecar не прошёл валидацию: {e}", file=sys.stderr)
            return 1
        print(f"journal: exception append → {path}")
        return 0
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
