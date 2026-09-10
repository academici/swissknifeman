"""journal — append-only писатель пер-планового журнала исполнения
`plans/<PLAN-ID>/journal.jsonl` (схема 2026.07.18-FOREMAN P1.1 sealed v1,
`root/contracts/plan-journal-schema.md`) и optional append-only sidecar
`journal-exceptions.jsonl` для owner-gated historical schema exceptions.

Одна запись = одна строка валидного JSON (NDJSON, D20). Запись только ДОПИСЫВАЕТСЯ —
существующие строки никогда не переписываются/не удаляются (§1 контракта); поэтому
`append()` открывает файл в режиме `"a"` и делает РОВНО один `write()` на запись —
конкурентные сессии дописывают свою строку без чужого построчного разрыва (git-merge
разрешается конкатенацией строк, контракт §1).

Вызывается close-протоколом команд `/task:plan-*` (2026.07.18-FOREMAN P1.3) — старт-запись
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
NOTE_MAX_CHARS = 300
UPDATE_LOG_WHAT_MAX_CHARS = 300

# --- канон схемы 2026.07.18-FOREMAN P1.1 (root/contracts/plan-journal-schema.md §2, §2.1, §2.2) -----
COMMANDS = ("plan-exec", "plan-run", "plan-close", "plan-audit", "plan-design")
FRICTION_VALUES = (
    "escalation", "routing-blocked", "route-deviation", "red-audit", "deviation", "retry", "no-op",
    "local-repair", "block-review", "external-evidence",
)
RESULT_VALUES = (
    "in-progress", "closed-green", "closed-deviations", "blocked",
    "escalated", "no-op", "audit-green", "audit-attention", "audit-red",
    "routing-rejected", "decision-pending", "local-repair", "rag-pending", "block-candidate",
)
TERMINAL_CLOSE_RESULTS = ("closed-green", "closed-deviations", "blocked", "escalated")
REQUIRED_FIELDS = (
    "ts", "plan_id", "item_id", "command", "session_id", "run_id", "attempt",
    "actor", "friction", "result", "cost_usd", "num_turns", "duration_ms", "note",
)
EXCEPTION_REQUIRED_FIELDS = (
    "ts", "plan_id", "target_line", "target_sha256", "invalid_fields",
    "owner_decision", "actor", "reason",
)
# v1 намеренно узок: exception не превращается в общий механизм отмены schema.
EXEMPTABLE_FIELDS = ("friction",)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DECISION_RE = re.compile(r"^D[1-9][0-9]*$")


class JournalValidationError(ValueError):
    """Запись не прошла schema-валидацию 2026.07.18-FOREMAN P1.1 — `append()` не пишет строку."""


def entry_validation_errors(entry):
    """Возвращает schema-нарушения как пары ``(поле, сообщение)``.

    Поле нужно linter'у для точного сопоставления с owner-gated historical exception;
    обычный writer по-прежнему использует :func:`validate_entry` и fail-closed."""
    if not isinstance(entry, dict):
        return [("$", "запись обязана быть dict")]

    errors = [(f, f"нет обязательного поля «{f}»")
              for f in REQUIRED_FIELDS if f not in entry]
    if errors:
        return errors

    def _check_str(name, *, allow_none=False, allow_empty=False):
        v = entry[name]
        if v is None and allow_none:
            return
        if not isinstance(v, str) or (not allow_empty and not v):
            errors.append((
                name,
                f"{name}: обязано быть {'str|null' if allow_none else 'непустой str'}",
            ))

    def _check_number(name):
        v = entry[name]
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            errors.append((name, f"{name}: обязано быть number|null"))

    _check_str("ts")
    _check_str("plan_id")
    _check_str("item_id")  # 2026.07.18-FOREMAN P1.1 — всегда set (сужение 2026.07.18-FOREMAN P0.6 str|null, §5)
    _check_str("session_id", allow_none=True)
    _check_str("run_id", allow_none=True)
    _check_str("actor")
    _check_str("note", allow_none=True)

    if entry["command"] not in COMMANDS:
        errors.append(("command", f"command: «{entry['command']}» не входит в {COMMANDS}"))
    if entry["result"] not in RESULT_VALUES:
        errors.append(("result", f"result: «{entry['result']}» не входит в {RESULT_VALUES}"))

    attempt = entry["attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        errors.append(("attempt", "attempt: обязано быть int ≥1"))

    friction = entry["friction"]
    if not isinstance(friction, list) or any(v not in FRICTION_VALUES for v in friction):
        errors.append((
            "friction",
            f"friction: обязан быть массивом значений из {FRICTION_VALUES}",
        ))

    for name in ("cost_usd", "num_turns", "duration_ms"):
        _check_number(name)

    fingerprint = entry.get("fingerprint")
    if fingerprint is not None and (
            not isinstance(fingerprint, str) or not _SHA256_RE.fullmatch(fingerprint)):
        errors.append(("fingerprint", "fingerprint: обязан быть lowercase SHA-256|null"))
    decision = entry.get("decision")
    if decision is not None:
        required = {"signal_class", "scope_class", "action", "recovered", "terminal"}
        if not isinstance(decision, dict) or not required <= set(decision):
            errors.append(("decision", "decision: отсутствуют обязательные поля evidence"))
    if "batch_receipt" in entry:
        try:
            from task.task_contract import validate_batch_receipt
            validate_batch_receipt(entry["batch_receipt"])
        except (ImportError, ValueError) as exc:
            errors.append(("batch_receipt", f"batch_receipt: {exc}"))
    if "repair_decision" in entry:
        try:
            from task import plan_repair
            plan_repair.validate(entry["repair_decision"])
            outcome = plan_repair.evaluate(entry["repair_decision"])
            if entry.get("repair_digest") != outcome["repair_digest"]:
                raise ValueError("repair_digest не совпадает с record")
            if entry.get("repair_action") != outcome["action"]:
                raise ValueError("repair_action не совпадает с reducer result")
            if (outcome["action"] == "repair-in-current-attempt"
                    and entry.get("result") in TERMINAL_CLOSE_RESULTS):
                raise ValueError("qualified repair не может записать terminal result")
            if (entry.get("command") == "plan-design"
                    and outcome["action"] != "design-required"):
                raise ValueError("plan-design требует repair action design-required")
        except (ImportError, ValueError) as exc:
            errors.append(("repair_decision", f"repair_decision: {exc}"))
    if "candidate_snapshot" in entry:
        snapshot = entry["candidate_snapshot"]
        required_snapshot = {"phase_id", "terminal_item_heads", "declared_files", "product_tree_sha256"}
        if (entry.get("command") != "plan-audit" or not isinstance(snapshot, dict)
                or not required_snapshot <= set(snapshot)):
            errors.append(("candidate_snapshot", "candidate_snapshot допустим только как полный audit candidate"))

    return errors


def validate_entry(entry):
    """Сверяет event-запись со схемой 2026.07.18-FOREMAN P1.1 (§2), копя все нарушения разом."""
    errors = entry_validation_errors(entry)
    if errors:
        raise JournalValidationError("; ".join(message for _, message in errors))


def validate_append_policy(entry, *, plan_dir=None):
    """Validate forward-only writer policy outside the sealed event schema.

    Historical rows with longer notes remain schema-valid and readable.  Only a
    new append is rejected, before any bytes are written.
    """
    note = entry.get("note") if isinstance(entry, dict) else None
    if isinstance(note, str) and len(note) > NOTE_MAX_CHARS:
        raise JournalValidationError(
            f"note: {len(note)} символов > {NOTE_MAX_CHARS}; "
            "детали вынесите в Completion Notes/findings")
    if (isinstance(entry, dict) and entry.get("command") == "plan-audit"
            and entry.get("result") in {"audit-green", "audit-attention", "audit-red"}):
        from task import review_policy
        if review_policy.phase_audit_subject(entry.get("item_id")) is not None:
            try:
                review_policy.phase_audit_terminal_policy(entry)
            except review_policy.ReviewPolicyError as exc:
                raise JournalValidationError(str(exc)) from exc
    if isinstance(entry, dict):
        from task import terminal_policy
        try:
            terminal_policy.validate_entry(
                entry, plan_dir=Path(plan_dir) if plan_dir is not None else None)
        except terminal_policy.TerminalPolicyError as exc:
            raise JournalValidationError(str(exc)) from exc


def project_update_log_what(entry, line_number):
    """Return the bounded owner-facing ``Что`` cell for one journal row.

    The immutable journal remains the full source.  A projection that would
    exceed the owner-view limit is replaced by a deterministic line pointer.
    """
    note = str(entry.get("note") or "—")
    command = str(entry.get("command") or "—")
    result = str(entry.get("result") or "—")
    what = " · ".join((command, result, note))
    if len(what) <= UPDATE_LOG_WHAT_MAX_CHARS:
        return what
    return f"{command} · {result} · note сокращена; полный текст: {FILENAME}:{line_number}"


def validate_exception(exception):
    """Валидирует одну запись sidecar-схемы historical schema exception v1."""
    if not isinstance(exception, dict):
        raise JournalValidationError("schema exception обязано быть dict")
    errors = [f"нет обязательного поля «{f}»"
              for f in EXCEPTION_REQUIRED_FIELDS if f not in exception]
    unknown = sorted(set(exception) - set(EXCEPTION_REQUIRED_FIELDS))
    if unknown:
        errors.append(f"неизвестные поля schema exception: {unknown}")
    if errors:
        raise JournalValidationError("; ".join(errors))

    for name in ("ts", "plan_id", "actor", "reason"):
        value = exception[name]
        if not isinstance(value, str) or not value:
            errors.append(f"{name}: обязано быть непустой str")

    target_line = exception["target_line"]
    if isinstance(target_line, bool) or not isinstance(target_line, int) or target_line < 1:
        errors.append("target_line: обязано быть int ≥1")
    target_sha256 = exception["target_sha256"]
    if not isinstance(target_sha256, str) or not _SHA256_RE.fullmatch(target_sha256):
        errors.append("target_sha256: обязан быть lowercase SHA-256")
    invalid_fields = exception["invalid_fields"]
    if (not isinstance(invalid_fields, list) or not invalid_fields
            or len(invalid_fields) != len(set(invalid_fields))
            or any(v not in EXEMPTABLE_FIELDS for v in invalid_fields)):
        errors.append(
            f"invalid_fields: непустой unique-массив значений из {EXEMPTABLE_FIELDS}")
    owner_decision = exception["owner_decision"]
    if not isinstance(owner_decision, str) or not _DECISION_RE.fullmatch(owner_decision):
        errors.append("owner_decision: обязан быть D#")

    if errors:
        raise JournalValidationError("; ".join(errors))


def line_sha256(raw_line):
    """SHA-256 точных UTF-8 bytes строки journal без завершающего newline."""
    return hashlib.sha256(raw_line.encode("utf-8")).hexdigest()


def derive_run_id(*, plan_id, item_id, attempt, session_id):
    """Return one deterministic identity for a start/terminal execution pair."""
    if (not all(isinstance(value, str) and value for value in (plan_id, item_id, session_id))
            or isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1):
        raise JournalValidationError(
            "run_id: plan_id/item_id/session_id и attempt ≥1 обязательны")
    value = "\0".join((plan_id, item_id, str(attempt), session_id))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_exception(*, plan_id, target_line, target_sha256, invalid_fields,
                  owner_decision, actor, reason, ts=None):
    """Собирает owner-gated sidecar-запись без изменения historical journal bytes."""
    return {
        "ts": ts or _now_iso(),
        "plan_id": plan_id,
        "target_line": target_line,
        "target_sha256": target_sha256,
        "invalid_fields": list(invalid_fields),
        "owner_decision": owner_decision,
        "actor": actor,
        "reason": reason,
    }


def validate_exception_target(plan_dir, exception, *, check_duplicate=True):
    """Проверяет provenance, owner gate и точное множество waived schema-полей.

    Sidecar физически отделён от event-журнала, поэтому exception не может ссылаться
    на другое exception и correction-цикл конструктивно невозможен.
    """
    validate_exception(exception)
    plan_dir = Path(plan_dir)
    canonical_plan_id = plan_dir.name
    if exception["plan_id"] != canonical_plan_id:
        raise JournalValidationError(
            f"exception: plan_id «{exception['plan_id']}» ≠ canonical plan directory "
            f"«{canonical_plan_id}»")
    from task import plan_layout
    try:
        journal_path = plan_layout.carrier_path(plan_dir, "journal")
    except plan_layout.PlanLayoutError as exc:
        raise JournalValidationError(f"journal: носитель не резолвится: {exc}") from exc
    try:
        lines = journal_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise JournalValidationError(f"target journal не читается: {exc}") from exc

    target_line = exception["target_line"]
    if target_line > len(lines) or not lines[target_line - 1].strip():
        raise JournalValidationError("target_line: нет такой непустой строки journal")
    raw_line = lines[target_line - 1]
    if line_sha256(raw_line) != exception["target_sha256"]:
        raise JournalValidationError("target_sha256: не совпадает с raw journal line")
    try:
        target = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        raise JournalValidationError(
            "target: malformed JSON не допускает schema exception") from exc
    target_plan_id = target.get("plan_id") if isinstance(target, dict) else None
    if target_plan_id != canonical_plan_id:
        raise JournalValidationError(
            f"target event: plan_id «{target_plan_id}» ≠ canonical plan directory "
            f"«{canonical_plan_id}»")

    target_errors = entry_validation_errors(target)
    target_fields = {field for field, _ in target_errors}
    if not target_errors:
        raise JournalValidationError("target: строка уже проходит event-схему")
    if target_fields != set(exception["invalid_fields"]):
        raise JournalValidationError(
            f"invalid_fields: ожидалось точное множество {sorted(target_fields)}")

    try:
        plan_layout.layout_version(plan_dir)
        decision_glob = plan_layout.carrier_glob(plan_dir, "decision-record")
        exists = any(p.name.startswith(exception["owner_decision"] + "-")
                     for p in decision_glob.parent.glob(decision_glob.name))
    except (OSError, UnicodeDecodeError, plan_layout.PlanLayoutError) as exc:
        raise JournalValidationError(f"owner_decision: носитель решений не читается: {exc}") from exc
    if not exists:
        raise JournalValidationError("owner_decision: D# отсутствует в объявленном носителе решений")

    if check_duplicate:
        exceptions_path = plan_dir / EXCEPTIONS_FILENAME
        if exceptions_path.is_file():
            try:
                existing_lines = exceptions_path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as exc:
                raise JournalValidationError(
                    f"existing exception sidecar не читается: {exc}") from exc
            for raw in existing_lines:
                if not raw.strip():
                    continue
                try:
                    existing = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if (isinstance(existing, dict)
                        and existing.get("target_line") == target_line
                        and existing.get("target_sha256") == exception["target_sha256"]):
                    raise JournalValidationError("target: exception уже существует")


def new_entry(*, plan_id, item_id, command, actor, result, session_id=None, run_id=None,
              attempt=1, friction=(), cost_usd=None, num_turns=None, duration_ms=None,
              note=None, ts=None, trace_ref=None, fingerprint=None, decision=None,
              batch_receipt=None, candidate_snapshot=None, second_full_justification=None):
    """Собирает запись по схеме 2026.07.18-FOREMAN P1.1 с дефолтами контракта (§2) — единая точка сборки,
    чтобы close-протокол команд не собирал dict вручную по месту россыпью полей.

    `trace_ref` (2026.07.24-AGENT-RELIABILITY P3.1, `root/contracts/unified-agent-trace-v1.md` § Journal reference)
    — ADDITIVE optional linkage to a Unified Agent Trace `trace_id`, outside
    `REQUIRED_FIELDS`: omitted (`None`, the default) it is not written at all, so
    every caller that does not pass it gets a byte-identical entry to before this
    field existed. The journal never carries trace METRICS, only this pointer."""
    entry = {
        "ts": ts or _now_iso(),
        "plan_id": plan_id,
        "item_id": _canonical_phase_audit_item_id(command, item_id),
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
    if trace_ref is not None:
        entry["trace_ref"] = trace_ref
    if fingerprint is not None:
        entry["fingerprint"] = fingerprint
    if decision is not None:
        entry["decision"] = dict(decision)
    if batch_receipt is not None:
        entry["batch_receipt"] = dict(batch_receipt)
    if candidate_snapshot is not None:
        entry["candidate_snapshot"] = dict(candidate_snapshot)
    if second_full_justification is not None:
        entry["second_full_justification"] = dict(second_full_justification)
    return entry


def _canonical_phase_audit_item_id(command, item_id):
    """New audit writers emit only canonical Pn; historical rows remain readable."""
    if command != "plan-audit":
        return item_id
    from task import review_policy
    return review_policy.phase_audit_subject(item_id) or item_id


def append(plan_dir, entry):
    """Дописывает ОДНУ запись в `plans/<ID>/journal.jsonl`. Валидирует ДО записи
    (§2) — битая запись не попадает в durable-историю плана (§1). Возвращает путь
    файла. Файла нет — создаётся (append-режим сам создаёт)."""
    validate_entry(entry)
    plan_dir = Path(plan_dir)
    validate_append_policy(entry, plan_dir=plan_dir)
    canonical_plan_id = plan_dir.name
    if entry["plan_id"] != canonical_plan_id:
        raise JournalValidationError(
            f"event plan_id «{entry['plan_id']}» ≠ canonical plan directory "
            f"«{canonical_plan_id}»")
    path = plan_dir / FILENAME
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path


def append_idempotent_terminal(plan_dir, entry):
    """Append one terminal, or return its existing line without changing bytes."""
    validate_entry(entry)
    validate_append_policy(entry, plan_dir=plan_dir)
    if entry.get("result") not in TERMINAL_CLOSE_RESULTS or not entry.get("run_id"):
        return append(plan_dir, entry), None, True
    plan_dir = Path(plan_dir)
    path = plan_dir / FILENAME
    if path.is_file():
        for line_number, raw in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                current = json.loads(raw)
            except json.JSONDecodeError:
                continue
            identity = (entry.get("item_id"), entry.get("attempt"), entry.get("run_id"))
            if (current.get("item_id"), current.get("attempt"), current.get("run_id")) != identity:
                continue
            if current.get("result") not in TERMINAL_CLOSE_RESULTS:
                continue
            if all(current.get(field) == entry.get(field) for field in ("result", "fingerprint")):
                return path, line_number, False
            raise JournalValidationError(
                f"terminal conflict: run_id уже закрыт в {FILENAME}:{line_number}")
    return append(plan_dir, entry), None, True


def append_exception(plan_dir, exception):
    """Append-only дописывает ровно одно owner-gated historical schema exception."""
    validate_exception_target(plan_dir, exception)
    path = Path(plan_dir) / EXCEPTIONS_FILENAME
    line = json.dumps(exception, ensure_ascii=False, sort_keys=True)
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
    ap.add_argument("--actor", default=None, help="`<model>/<effort>` или `owner`")
    ap.add_argument(
        "--route-evidence", default=None,
        help="альтернатива --actor: путь к JSON `task.route_evidence.capture_actual()` "
            "(P2.4/P2.6) — actor выводится канонической `<model>/<effort>`-спеллинг-формой "
            "(`findings/02` — 34 наблюдённых написания), а не собирается руками по месту")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--friction", default="", help="через запятую, из закрытого списка")
    ap.add_argument("--cost-usd", type=float, default=None)
    ap.add_argument("--num-turns", type=int, default=None)
    ap.add_argument("--duration-ms", type=float, default=None)
    ap.add_argument("--note", default=None)
    ap.add_argument(
        "--trace-ref", default=None,
        help="опционально: trace_id Unified Agent Trace (P3.1) — additive, не влияет на "
            "REQUIRED_FIELDS; опущен по умолчанию")
    ap.add_argument("--fingerprint", default=None,
                    help="SHA-256 material scope/SHA/risk или terminal evidence")
    ap.add_argument("--decision-json", default=None,
                    help="compact D12 decision evidence как JSON object")
    ap.add_argument("--batch-receipt-json", default=None,
                    help="optional digest-bound batch receipt as JSON object")
    ap.add_argument("--repair-decision-json", default=None,
                    help="closed repair-decision/v1 JSON object for a forward repair event")
    ap.add_argument("--repair-action", default=None,
                    choices=("repair-in-current-attempt", "gather-evidence", "block-candidate", "design-required"),
                    help="action returned by task.plan_repair.evaluate()")
    ep = sub.add_parser(
        "exception", help="дописать owner-gated exception для historical schema-invalid строки")
    ep.add_argument("--plan-dir", required=True, help="каталог плана plans/<PLAN-ID>")
    ep.add_argument("--plan", required=True, dest="plan_id")
    ep.add_argument("--target-line", required=True, type=int)
    ep.add_argument("--invalid-fields", required=True,
                    help="через запятую; v1 допускает только friction")
    ep.add_argument("--owner-decision", required=True, help="существующая owner-approved D#")
    ep.add_argument("--actor", required=True, help="`<model>/<effort>` или `owner`")
    ep.add_argument("--reason", required=True, help="почему exception безопасен и необходим")
    return p


def main(argv=None):
    args = _build_arg_parser().parse_args(argv)
    if args.cmd == "exception":
        journal_path = Path(args.plan_dir) / FILENAME
        try:
            lines = journal_path.read_text(encoding="utf-8").splitlines()
            raw_line = lines[args.target_line - 1]
        except (OSError, UnicodeDecodeError, IndexError) as exc:
            print(f"ERROR: target journal line не читается: {exc}", file=sys.stderr)
            return 1
        exception = new_exception(
            plan_id=args.plan_id,
            target_line=args.target_line,
            target_sha256=line_sha256(raw_line),
            invalid_fields=_parse_friction(args.invalid_fields),
            owner_decision=args.owner_decision,
            actor=args.actor,
            reason=args.reason,
        )
        try:
            path = append_exception(args.plan_dir, exception)
        except JournalValidationError as exc:
            print(f"ERROR: schema exception не прошёл валидацию: {exc}", file=sys.stderr)
            return 1
        print(f"journal: exception append → {path}")
        return 0

    if args.cmd != "append":  # pragma: no cover - argparse уже гейтит choices
        return 1
    if (args.actor is None) == (args.route_evidence is None):
        print("ERROR: ровно один из --actor / --route-evidence обязателен", file=sys.stderr)
        return 1
    actor = args.actor
    if args.route_evidence is not None:
        # Lazy import (task_contract.evaluate_finding 2026.07.24-AGENT-RELIABILITY P2.3 pattern): journal.py's own
        # schema/writer stay importable without task.route_evidence on the path.
        from task.route_evidence import RouteEvidenceError, canonical_actor
        try:
            evidence = json.loads(Path(args.route_evidence).read_text(encoding="utf-8"))
            # D72/F8: canonical_actor now reads the concrete `model` evidence field
            # (2026.07.24-AGENT-RELIABILITY P2.6), never `model_class` — a historical evidence blob predating
            # this item simply lacks "model" and renders `unknown/<effort>`.
            actor = canonical_actor(evidence.get("model"), evidence.get("effort"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError,
               RouteEvidenceError) as exc:
            print(f"ERROR: --route-evidence не читается: {exc}", file=sys.stderr)
            return 1
    decision = None
    if args.decision_json is not None:
        try:
            decision = json.loads(args.decision_json)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --decision-json невалиден: {exc}", file=sys.stderr)
            return 1
    batch_receipt = None
    if args.batch_receipt_json is not None:
        try:
            batch_receipt = json.loads(args.batch_receipt_json)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --batch-receipt-json невалиден: {exc}", file=sys.stderr)
            return 1
    repair_decision = None
    if args.repair_decision_json is not None:
        try:
            repair_decision = json.loads(args.repair_decision_json)
            from task import plan_repair
            outcome = plan_repair.evaluate(repair_decision)
            if args.repair_action != outcome["action"]:
                raise ValueError("--repair-action должен совпадать с reducer result")
            repair_digest = outcome["repair_digest"]
        except (json.JSONDecodeError, ImportError, ValueError) as exc:
            print(f"ERROR: --repair-decision-json невалиден: {exc}", file=sys.stderr)
            return 1
    elif args.repair_action is not None:
        print("ERROR: --repair-action требует --repair-decision-json", file=sys.stderr)
        return 1
    entry = new_entry(
        plan_id=args.plan_id, item_id=args.item_id, command=args.command,
        actor=actor, result=args.result, session_id=args.session_id,
        run_id=args.run_id, attempt=args.attempt,
        friction=_parse_friction(args.friction), cost_usd=args.cost_usd,
        num_turns=args.num_turns, duration_ms=args.duration_ms, note=args.note,
        trace_ref=args.trace_ref, fingerprint=args.fingerprint, decision=decision,
        batch_receipt=batch_receipt,
    )
    if repair_decision is not None:
        entry.update({"repair_decision": repair_decision, "repair_digest": repair_digest,
                      "repair_action": args.repair_action})
    try:
        path, line_number, appended = append_idempotent_terminal(args.plan_dir, entry)
    except JournalValidationError as e:
        print(f"ERROR: запись журнала не прошла валидацию: {e}", file=sys.stderr)
        return 1
    if appended:
        print(f"journal: append → {path}")
    else:
        print(f"journal: existing → {path}:{line_number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
