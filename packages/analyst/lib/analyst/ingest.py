"""analyst ingest — приём findings агента-аналитика (/analyst:deep) в ephemeral-уроки.

Агент — рассуждающий слой (каузальный нарратив, resolve CONFLICT, тексты remediation);
этот модуль — его единственная дверь в стор уроков, и дверь узкая (инварианты пакета):

- **валидация ДО первого побочного эффекта**: весь файл findings разбирается и проверяется
  целиком; невалидный JSON или схема → die БЕЗ единой записи (ни урока, ни audit-строки);
- **только ephemeral** — enforced кодом, не соглашением: `state` ≠ ephemeral или
  `detector` ≠ agent-finding в файле → die; запись идёт только через add_candidate
  (ephemeral) + страховочный assert;
- **человек в гейте**: `promote_candidate` агента — лишь маркер PROMOTE-CANDIDATE в
  evidence (виден на `analyst review`), никакого продвижения здесь нет;
- провенанс — существующим механизмом: audit_append на каждый принятый урок.

events.ndjson здесь НЕ пишем осознанно: finding агента — гипотеза, а не верифицированный
сигнал успеха (в отличие от digest, где тест реально прошёл); confidence урока начнёт
копиться с последующих наблюдений digest/promote."""
import json
import os
from pathlib import Path

from .common import die, parse_args
from .lessons import (ACTIVE_STATES, KINDS, add_candidate, audit_append,
                      classify_consolidation, new_lesson, similar_lessons)

DETECTOR = "agent-finding"   # единственный допустимый детектор уроков агента
PROMOTE_MARK = "PROMOTE-CANDIDATE"

# Схема (строгая: неизвестный ключ = die — ловим дрейф контракта агента, а не глотаем)
_TOP_KEYS = {"source", "session", "findings"}
_FINDING_KEYS = {"trigger", "action", "kind", "scope", "evidence", "meta",
                 "review_hint", "session_id", "promote_candidate",
                 "detector", "state", "source"}


# ── валидация (чистая: payload → нормализованные findings | ValueError) ──────
def validate_findings(payload):
    """Проверить схему findings-файла целиком и вернуть нормализованный список находок.

    Любое нарушение → ValueError (вызывающий превращает в die) — ДО каких-либо записей.
    Ephemeral-only и detector=agent-finding защищены здесь кодом: попытка передать иное
    состояние/детектор — ошибка схемы, а не молчаливая перезапись."""
    if not isinstance(payload, dict):
        raise ValueError("корень файла — не объект")
    unknown = set(payload) - _TOP_KEYS
    if unknown:
        raise ValueError(f"неизвестные ключи верхнего уровня: {', '.join(sorted(unknown))}")
    if payload.get("source") not in (None, "agent"):
        raise ValueError(f"source допускает только 'agent', получено: {payload.get('source')!r}")
    session = payload.get("session", "")
    if not isinstance(session, str):
        raise ValueError("session — не строка")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ValueError("findings — не список")

    out = []
    for i, f in enumerate(findings):
        where = f"findings[{i}]"
        if not isinstance(f, dict):
            raise ValueError(f"{where}: не объект")
        unknown = set(f) - _FINDING_KEYS
        if unknown:
            raise ValueError(f"{where}: неизвестные ключи: {', '.join(sorted(unknown))}")
        trigger = f.get("trigger")
        action = f.get("action")
        if not isinstance(trigger, str) or not trigger.strip():
            raise ValueError(f"{where}: trigger пуст или не строка")
        if not isinstance(action, str) or not action.strip():
            raise ValueError(f"{where}: action пуст или не строка")
        kind = f.get("kind", "heuristic")
        if kind not in KINDS:
            raise ValueError(f"{where}: kind '{kind}' (допустимо: {', '.join(KINDS)})")
        # ephemeral-only / agent-finding-only — enforced схемой (die, не молчаливый фикс)
        if "state" in f and f["state"] != "ephemeral":
            raise ValueError(f"{where}: агент пишет ТОЛЬКО ephemeral, получено state={f['state']!r}")
        if "detector" in f and f["detector"] != DETECTOR:
            raise ValueError(f"{where}: detector допускает только '{DETECTOR}', "
                             f"получено: {f['detector']!r}")
        if "source" in f and f["source"] != "agent":
            raise ValueError(f"{where}: source допускает только 'agent', получено: {f['source']!r}")
        scope = f.get("scope", "")
        if not isinstance(scope, str):
            raise ValueError(f"{where}: scope — не строка")
        evidence = f.get("evidence", [])
        if not (isinstance(evidence, list) and all(isinstance(e, str) for e in evidence)):
            raise ValueError(f"{where}: evidence — не список строк")
        meta = f.get("meta", {})
        if not isinstance(meta, dict):
            raise ValueError(f"{where}: meta — не объект")
        review_hint = f.get("review_hint", "")
        if not isinstance(review_hint, str):
            raise ValueError(f"{where}: review_hint — не строка")
        session_id = f.get("session_id", "")
        if not isinstance(session_id, str):
            raise ValueError(f"{where}: session_id — не строка")
        out.append({
            "trigger": trigger, "action": action, "kind": kind, "scope": scope,
            "evidence": list(evidence), "meta": dict(meta), "review_hint": review_hint,
            "session_id": session_id or session,
            "promote_candidate": bool(f.get("promote_candidate", False)),
        })
    return out


def build_lessons(findings, *, scope_default, project):
    """Нормализованные findings → словари уроков (чистая: без IO). detector/source
    зашиты константами — агенту неоткуда подменить провенанс."""
    out = []
    for f in findings:
        evidence = list(f["evidence"])
        sid = f["session_id"]
        if sid and f"session:{sid}" not in evidence:
            evidence.append(f"session:{sid}")
        if f["promote_candidate"] and PROMOTE_MARK not in evidence:
            evidence.append(PROMOTE_MARK)   # маркер человеку на review; промоут — не здесь
        out.append(new_lesson(
            trigger=f["trigger"], action=f["action"], kind=f["kind"],
            scope=f["scope"] or scope_default, session_id=sid, project=project,
            detector=DETECTOR, source="agent", evidence=evidence,
            meta=f["meta"], review_hint=f["review_hint"]))
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────
def cmd_ingest(env, argv):
    """analyst ingest --file F [--dry-run] [--json]
    — принять findings агента-аналитика в .claude/analyst/lessons/ephemeral/."""
    opts, _ = parse_args(argv, {"--file": "str", "--dry-run": "bool",
                                "--json": "bool", "--project": "str"})
    if opts["help"]:
        print("analyst ingest --file F [--dry-run] [--json]\n"
              "  Принять findings агента (/analyst:deep) в ephemeral-уроки. Валидация схемы\n"
              "  до первой записи (невалидный файл → ни одной записи); только ephemeral,\n"
              "  detector=agent-finding — enforced кодом. Промоут — человек (analyst review).")
        return
    if not opts["file"]:
        die("--file обязателен: analyst ingest --file findings.json")
    path = Path(os.path.expanduser(opts["file"]))
    if not path.is_file():
        die(f"файл findings не найден: {path}")

    # валидация ЦЕЛИКОМ до первого побочного эффекта: битый JSON/схема → die без записей
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"невалидный JSON findings ({path}): {e} — ни одной записи не сделано")
    try:
        findings = validate_findings(payload)
    except ValueError as e:
        die(f"схема findings не прошла валидацию: {e} — ни одной записи не сделано")

    ppath = os.getcwd()
    project = Path(os.path.abspath(ppath)).name
    cands = build_lessons(findings, scope_default=f"project:{project}", project=project)

    if opts["dry_run"] or opts["json"]:
        payload_out = {"session": payload.get("session", ""), "project": project,
                       "findings": [{"id": c["id"], "kind": c["kind"],
                                     "trigger": c["trigger"],
                                     "promote_candidate": PROMOTE_MARK in c["evidence"]}
                                    for c in cands]}
        if opts["json"]:
            print(json.dumps(payload_out, ensure_ascii=False, indent=2))
        else:
            print(f"\nanalyst ingest (dry-run) — {len(cands)} finding(ов) из {path.name}\n")
            for c in payload_out["findings"]:
                mark = "  ★ PROMOTE-CANDIDATE" if c["promote_candidate"] else ""
                print(f"  • [{c['kind']}] {c['trigger']}{mark}")
            print()
        return

    created = skipped = 0
    for L in cands:
        assert L["state"] == "ephemeral", "инвариант ingest: только ephemeral"
        # семантический дедуп как в digest: NOOP по mem0-классификации → не плодим
        sim = similar_lessons(ppath, L["trigger"], L["action"],
                              states=ACTIVE_STATES, threshold=0.4)
        cons = classify_consolidation(L["trigger"], L["action"], sim)
        if cons["action"] == "NOOP":
            skipped += 1
            continue
        _lesson, was_new = add_candidate(ppath, L)
        if not was_new:
            skipped += 1
            continue
        created += 1
        audit_append(ppath, {"action": "ingest", "id": L["id"], "detector": DETECTOR,
                             "session": L["provenance"]["session_id"],
                             "state": "ephemeral", "consolidation": cons["action"]})

    marks = sum(1 for L in cands if PROMOTE_MARK in L["evidence"])
    print(f"\nanalyst ingest — {created} нов(ых) урок(ов) в ephemeral"
          f"{f', {skipped} пропущено (дубль/похоже на существующий)' if skipped else ''}"
          f"{f'; {marks} с маркером {PROMOTE_MARK}' if marks else ''}.")
    if created:
        print("  Смотри: analyst review   ·   промоут (только человек): analyst promote <id>\n")
    else:
        print("  Новых уроков из findings не принято.\n")
