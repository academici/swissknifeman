"""Parsers and carrier-local structural checks for executable plans."""
from .common import *
from .policy import *
from task import journal as plan_journal
from task import plan_decisions
from task import terminal_policy


def _lint_plan_md_20(lines, path, diag):
    """Warning-проверки схемы 2.0 поверх plan.md (существующее поведение не трогают):
    (а) порядок/заголовки нумерованных секций `## 0-6` (P0.3 рек#6);
    (б) Update Log: ячейка «Что» длиннее UPDATE_LOG_MAX_CHARS (P0.3 рек#5);
    (в) D-лог с ≥3 решениями без единого RAG-маркера — эвристика отсутствия
        маркировки несущих фактов (SKILL §7)."""
    # (а) нумерованные секции: номера по возрастанию, заголовки зависят от layout.
    numbered = []
    for i, ln in enumerate(lines):
        m = PLAN_SECTION_NUM_RE.match(ln)
        if m:
            numbered.append((int(m.group(1)), m.group(2), i + 1))
    nums = [n for n, _, _ in numbered]
    if nums != sorted(nums):
        diag.warning(path, numbered[0][2],
                     f"секции plan.md идут не по порядку: {nums} (канон — ## 0…6 по возрастанию)")
    try:
        layout = plan_layout.layout_version(Path(path).parent)
    except plan_layout.PlanLayoutError:
        layout = "v2"
    expected_titles = {**PLAN_SECTION_TITLES, 4: "Update Log"}
    for n, title, lineno in numbered:
        expected = expected_titles.get(n)
        if expected and title != expected:
            diag.warning(path, lineno,
                         f"секция «## {n}. {title}» ≠ канонической «## {n}. {expected}»")

    if layout == "v2":
        # The v2 core deliberately has neither an inline Update Log nor an inline
        # decision table.  Keep the existing warnings, but obtain their facts from
        # the authoritative append-only carriers rather than silently skipping
        # them with the removed sections.
        journal_path = Path(path).parent / "journal.jsonl"
        for lineno, raw in enumerate(_read_lines(journal_path) or (), 1):
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue  # `_lint_plan_journal_20` owns malformed-record reporting.
            if not isinstance(entry, dict):
                continue
            what = plan_journal.project_update_log_what(entry, lineno)
            if len(what) > UPDATE_LOG_MAX_CHARS:
                diag.warning(journal_path, lineno,
                             f"Update Log: запись «Что» {len(what)} символов > "
                             f"{UPDATE_LOG_MAX_CHARS} — канон: ≤2 строк + ссылка на "
                             "Completion Notes, не пересказ")
        try:
            decisions = plan_decisions.load_decisions(Path(path).parent)
        except plan_decisions.DecisionError:
            return  # the decision parser/projector reports the carrier defect.
        if len(decisions) >= 3 and not any(RAG_MARKER_RE.search(decision.body)
                                           for decision in decisions):
            diag.warning(Path(path).parent / "decisions", 0,
                         f"Decision Log: {len(decisions)} решений и ни одного маркера "
                         f"«RAG:✅»/«RAG:{EMPTY_PLACEHOLDER}»/«[UNVERIFIED]» — несущие "
                         "факты не промаркированы (SKILL §7)")
        return

    # (б) Update Log — лимит «Что»
    _, ul_body, ul_start = _find_section(lines, UPDATE_LOG_HEADER_RE)
    if ul_body is not None:
        headers, rows, _ = _parse_table(ul_body, ul_start)
        if headers and "Что" in headers:
            for row, lineno in rows:
                what_val = row.get("Что", "")
                if len(what_val) > UPDATE_LOG_MAX_CHARS:
                    diag.warning(path, lineno,
                                 f"Update Log: запись «Что» {len(what_val)} символов > "
                                 f"{UPDATE_LOG_MAX_CHARS} — канон: ≤2 строк + ссылка на "
                                 f"Completion Notes, не пересказ")

    # (в) D-лог ≥3 решений без единого RAG-маркера
    _, dl_body, dl_start = _find_section(lines, DECISION_LOG_HEADER_RE)
    if dl_body is not None:
        _, rows, _ = _parse_table(dl_body, dl_start)
        if len(rows) >= 3 and not any(
                RAG_MARKER_RE.search(" ".join(str(v) for v in row.values()))
                for row, _ in rows):
            diag.warning(path, dl_start,
                         f"Decision Log: {len(rows)} решений и ни одного маркера "
                         f"«RAG:✅»/«RAG:{EMPTY_PLACEHOLDER}»/«[UNVERIFIED]» — несущие "
                         f"факты не промаркированы (SKILL §7)")


def _lint_v2_decision_pointer(plan_dir, plan_lines, plan_md, diag):
    """v2 keeps decision truth in ``decisions/``, not an inline table.

    Link integrity belongs to the P2 projector, not the plan linter until P3.
    This checks the sole executable carrier shape.
    """
    try:
        if plan_layout.layout_version(plan_dir) != "v2":
            return
    except plan_layout.PlanLayoutError:
        return
    _, body, start = _find_section(plan_lines, DECISION_LOG_HEADER_RE)
    if body is None:
        diag.error(plan_md, None, "Layout v2: нет секции «## 5. Decision Log»")
    else:
        text = "\n".join(body).strip()
        if "|" in text or "decisions/" not in text or "plan-views.py decisions" not in text:
            diag.error(plan_md, start,
                       "Layout v2: Decision Log должен быть строкой-указателем на decisions/ и plan-views.py decisions")
    if any(re.match(r"^##\s+(?:\d+\.\s+)?Обсуждение\s*$", line) for line in plan_lines):
        diag.error(plan_md, None, "Layout v2: «## Обсуждение» запрещён; используйте open-questions.md")
    if not (Path(plan_dir) / "decisions").is_dir():
        diag.error(plan_md, None, "Layout v2: отсутствует каталог decisions/")


# --- m7/D10: парсер секции `## 7. Contracts` -----------------------------------

def _contract_key(value):
    """Нормализация имени контракта — последний сегмент пути: донор пишет
    `root/contracts/module-manifest.md`, потребитель — `REGHUB/root/contracts/…`."""
    return (value or "").strip().strip("`").rsplit("/", 1)[-1]


def _semver_tuple(value):
    """`v2.0.2` → (2, 0, 2); пре-релизы не поддерживаем (D10). Нет матча → None."""
    m = SEMVER_RE.search(value or "")
    return tuple(int(g) for g in m.groups()) if m else None


def parse_contracts(lines, path, diag):
    """Опциональная секция `## 7. Contracts` → {"exported": [...], "consumed": [...]}.
    Секции нет — молча пустая модель (отсутствие не дефект). Кривые колонки/подсекции —
    WARNING (механизм молод: ERROR сломал бы back-compat-гейт)."""
    model = {"exported": [], "consumed": []}
    _, body, body_start = _find_section(lines, CONTRACTS_HEADER_RE)
    if body is None:
        return model

    subs = []
    for i, ln in enumerate(body):
        if CONTRACTS_EXPORTED_RE.match(ln):
            subs.append(("exported", i))
        elif CONTRACTS_CONSUMED_RE.match(ln):
            subs.append(("consumed", i))
    if not subs:
        diag.warning(path, body_start,
                     "«## 7. Contracts»: нет подсекций «### Exported» / «### Consumed»")
        return model

    expected = {"exported": EXPORTED_COLUMNS, "consumed": CONSUMED_COLUMNS}
    for pos, (kind, start) in enumerate(subs):
        end = subs[pos + 1][1] if pos + 1 < len(subs) else len(body)
        headers, rows, header_lineno = _parse_table(body[start + 1:end],
                                                    body_start + start + 1)
        title = kind.capitalize()
        if headers is None:
            diag.warning(path, body_start + start, f"«### {title}»: таблица не найдена")
            continue
        if tuple(headers) != expected[kind]:
            diag.warning(path, header_lineno,
                         f"«### {title}»: колонки {headers} ≠ канонических "
                         f"{list(expected[kind])}")
            continue
        for row, lineno in rows:
            model[kind].append({**row, "_lineno": lineno})
    return model


def _lint_contracts_cross_plan(models, diag):
    """(m7/D10) Сверка потребителей с донорами В ПРЕДЕЛАХ одного корня `plans/`.
    Связь строится ОТ потребителя (`Consumed.Донор-план`) — единственное детерминированное
    направление. Донор вне корня (кросс-репо) не проверяется — граница §11.
    `Pinned` ≠ `Версия` донора → WARNING «уведомление не разнесено»."""
    exported = {}  # (plan_id, contract_key) -> версия-строка
    for pid, model in models.items():
        for row in (model or {}).get("contracts", {}).get("exported", []):
            key = _contract_key(row.get("Контракт"))
            if key:
                exported[(pid, key)] = (row.get("Версия") or "").strip()

    for pid, model in models.items():
        plan_md = Path((model or {}).get("path", pid)) / "plan.md"
        for row in (model or {}).get("contracts", {}).get("consumed", []):
            donor = (row.get("Донор-план") or "").strip()
            key = _contract_key(row.get("Контракт"))
            donor_ver = exported.get((donor, key))
            if donor_ver is None:
                continue  # донора нет в этом корне — линтер честно молчит (§11)
            pinned = (row.get("Pinned") or "").strip()
            dv, pv = _semver_tuple(donor_ver), _semver_tuple(pinned)
            if dv is None or pv is None or dv == pv:
                continue
            diag.warning(plan_md, row.get("_lineno"),
                         f"донор {donor}: контракт {key} = {donor_ver}, потребитель {pid} "
                         f"запинен на {pinned} — уведомление не разнесено (§11)")


# --- Слой 0 «бриф» — обязательный вход плана (SKILL §16) ------------------------
# С этой даты (датовый PLAN-ID) отсутствие brief/ — ERROR; старее/legacy — WARNING
# (back-compat: существующие планы не ломаем, новые без брифа утверждение не проходят).
BRIEF_CANON_DATE = "2026.07.16"


def _lint_plan_brief_20(plan_dir, plan_id, diag):
    """brief/ — слой 0 «вход»: переформулированное без потери мыслей исходное
    сообщение владельца (00-brief.md) + дописываемые датированные уточнения.
    Задача: из плана видно «что было на входе → к чему пришли». План без brief/
    не проходит утверждение (SKILL §16)."""
    plan_dir = Path(plan_dir)
    brief_dir = plan_dir / "brief"
    has_md = brief_dir.is_dir() and any(
        f.is_file() and f.stat().st_size > 0 for f in brief_dir.glob("*.md"))
    if has_md:
        return
    msg = (f"нет слоя 0 «бриф»: {plan_dir.name}/brief/ с ≥1 непустым .md "
           f"(00-brief.md — переформулированный вход владельца, уточнения дописываются; "
           f"SKILL §16)")
    if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
        diag.error(plan_dir / "plan.md", None, msg)
    else:
        diag.warning(plan_dir / "plan.md", None, msg)


def _lint_plan_roadmap_20(plan_dir, plan_id, phase_files, diag):
    """roadmap.md обязателен, когда план полностью детализирован (нет скелет-маркеров
    ни в одной фазе) — SKILL §8: исполнение идёт батчами по исполнительской карте,
    а не поштучным бэбиситтингом. Severity как у brief-гейта: датовые планы от
    BRIEF_CANON_DATE — ERROR, старее/legacy — WARNING."""
    plan_dir = Path(plan_dir)
    if not phase_files:
        return
    for path in phase_files.values():
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(SKELETON_MARKER_RE.match(ln) for ln in text.splitlines()):
            return  # есть скелеты — план ещё в авторинге, roadmap не требуется
    rm = plan_dir / "roadmap.md"
    if rm.is_file() and rm.stat().st_size > 0:
        return
    msg = (f"план полностью детализирован (скелет-маркеров нет), а {plan_dir.name}/roadmap.md "
           f"отсутствует — исполнительская карта обязательна (SKILL §8)")
    if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
        diag.error(plan_dir / "plan.md", None, msg)
    else:
        diag.warning(plan_dir / "plan.md", None, msg)


# --- Слой журнала/индекса (2026.07.18-FOREMAN P1.4/D22) — soft/hard-гейт по дате-cutoff ------------
# Датовые планы ОТ этой даты обязаны нести валидный journal.jsonl (ERROR); старее/
# legacy — WARNING (тот же паттерн, что у brief/roadmap-гейтов, back-compat — не ломаем
# уже идущий флот). Cutoff = дата запечатывания этого канона (P1.4/D47): план
# 2026.07.18-FOREMAN сам датовый от этой даты — обязан бэкфиллить свой journal.jsonl
# ДО коммита этой правки, иначе первым же ловит собственный ERROR-гейт.
JOURNAL_CANON_DATE = "2026.07.18"


def _lint_journal_exceptions_20(plan_dir, plan_id, report):
    """Валидирует optional append-only sidecar historical schema exceptions.

    Возвращает ``target_line -> exception`` только для полностью валидных записей.
    Sidecar не является журналом событий и конструктивно не может образовать
    correction-цикл: его target всегда строка отдельного ``journal.jsonl``.
    """
    exceptions_path = Path(plan_dir) / _journal.EXCEPTIONS_FILENAME
    if not exceptions_path.is_file():
        return {}
    try:
        lines = exceptions_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        report(exceptions_path, None, "journal exceptions sidecar не читается (кодировка/IO)")
        return {}
    if not any(line.strip() for line in lines):
        report(exceptions_path, None, "journal exceptions sidecar пуст")
        return {}

    by_target = {}
    for i, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            exception = json.loads(raw)
        except json.JSONDecodeError as exc:
            report(exceptions_path, i,
                   f"строка не валидный JSON (append-only exception NDJSON): {exc}")
            continue
        try:
            _journal.validate_exception_target(
                plan_dir, exception, check_duplicate=False)
        except _journal.JournalValidationError as exc:
            report(exceptions_path, i, f"schema exception не проходит контракт: {exc}")
            continue

        target_line = exception["target_line"]
        if target_line in by_target:
            report(exceptions_path, i,
                   f"duplicate schema exception для journal.jsonl:{target_line}")
            continue
        by_target[target_line] = exception
    return by_target


def _lint_plan_journal_20(plan_dir, plan_id, diag):
    """journal.jsonl (2026.07.18-FOREMAN P1.1, root/contracts/plan-journal-schema.md) — append-only NDJSON,
    одна запись на исполнение item'а любым запуском `/task:plan-*`. Отсутствие/пустой/
    невалидный файл — ERROR для датовых планов от JOURNAL_CANON_DATE, WARNING для
    старее/legacy. Схема записи реюзается из `task.journal` (SSOT — не дублируем enum'ы)."""
    plan_dir = Path(plan_dir)
    jf = plan_dir / _journal.FILENAME
    is_dated_new = bool(PLAN_ID_DATED_RE.match(plan_id)) and plan_id[:10] >= JOURNAL_CANON_DATE
    report = diag.error if is_dated_new else diag.warning

    if not jf.is_file() or jf.stat().st_size == 0:
        report(plan_dir / "plan.md", None,
               f"нет {plan_dir.name}/{_journal.FILENAME} (append-only история "
               f"исполнения, P1.1) или файл пуст — пишется close-протоколом "
               f"/task:plan-* (lib/task/journal.py)")
        return

    try:
        lines = jf.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError):
        report(jf, None, "journal.jsonl не читается (кодировка/IO)")
        return

    exceptions = _lint_journal_exceptions_20(plan_dir, plan_id, report)

    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        try:
            entry = json.loads(ln)
        except json.JSONDecodeError as e:
            report(jf, i + 1, f"строка не валидный JSON (append-only NDJSON, §1): {e}")
            continue
        if isinstance(entry, dict) and entry.get("plan_id") != plan_id:
            report(
                jf,
                i + 1,
                f"event plan_id «{entry.get('plan_id')}» ≠ canonical plan directory "
                f"«{plan_id}»; mismatch не допускает schema exception",
            )
        errors = _journal.entry_validation_errors(entry)
        if errors and i + 1 not in exceptions:
            message = "; ".join(error for _, error in errors)
            report(jf, i + 1, f"запись не проходит схему P1.1: {message}")
            continue
        if _terminal_policy_is_active(entry):
            try:
                terminal_policy.validate_entry(entry, plan_dir=plan_dir)
            except terminal_policy.TerminalPolicyError as exc:
                report(jf, i + 1, str(exc))


def _lint_plan_index_20(plan_dir, plan_id, diag):
    """index.md (2026.07.18-FOREMAN P1.2, root/contracts/plan-index-schema.md) — карта файлов+провенанс,
    ОПЦИОНАЛЕН (не носитель факта, в отличие от журнала/брифа — P1.2 §1). Отсутствие —
    ВСЕГДА WARNING, независимо от даты плана (нет ERROR-ветки в отличие от журнала)."""
    plan_dir = Path(plan_dir)
    idx = plan_dir / "index.md"
    if not idx.is_file() or idx.stat().st_size == 0:
        diag.warning(plan_dir / "plan.md", None,
                     f"нет {plan_dir.name}/index.md (карта файлов + провенанс "
                     f"findings/research→фаза, P1.2, опционален) — снипет "
                     f"snippets/index-template.md")


# --- 2026.07.10-SKM-ROADMAP-005 P4.3 warning-проверки: ID / workflow-скрипты / supersedes (D24/D27/D28) ----

def _lint_plan_identity_20(plan_dir, plan_id, meta, plan_md, diag):
    """Три WARNING-проверки идентичности плана (все — warning, back-compat D24):
    (1) имя каталога-плана против union PLAN-ID-паттернов (D24);
    (2) workflow-скрипты (`*.js` c `export const meta`) вне `plans/<ID>/workflows/`
        или с неканоничным именем (D28) — два раздельных сообщения (место / имя);
    (3) план без Meta `supersedes` при совпадении кодового имени с архивным (D27).
    `meta` — dict[name] = (value, lineno) из parse_plan_md (может быть None/пустым)."""
    plan_dir = Path(plan_dir)
    meta = meta or {}

    # (1) PLAN-ID: исторические формы readable, но новые датовые планы
    # обязаны нести `№N`; ordinal связан с Title и уникален внутри даты.
    if not (PLAN_ID_LEGACY_RE.match(plan_id) or PLAN_ID_DATED_RE.match(plan_id)):
        diag.warning(plan_dir, None,
                     f"имя каталога-плана «{plan_id}» не соответствует канону PLAN-ID "
                     f"(старый `[A-Z][A-Z0-9-]+` ИЛИ новый "
                     f"`ГГГГ.ММ.ДД-№N-КОДОВОЕ-ИМЯ`)")

    numbered = PLAN_ID_NUMBERED_RE.match(plan_id)
    numbered_candidate = PLAN_ID_NUMBERED_CANDIDATE_RE.match(plan_id)
    if (PLAN_ID_LEGACY_DATED_RE.match(plan_id)
            and plan_id[:10] >= NUMBERED_PLAN_ID_CANON_DATE):
        diag.error(plan_dir, None,
                   f"новый датовый PLAN-ID «{plan_id}» требует порядковый номер: "
                   "`ГГГГ.ММ.ДД-№N-КОДОВОЕ-ИМЯ`")
    if numbered_candidate and int(numbered_candidate.group("ordinal")) == 0:
        diag.error(plan_dir, None, "порядковый номер PLAN-ID должен быть положительным")
    if numbered:
        ordinal = numbered.group("ordinal")
        title = (meta.get("Title", ("", None))[0] or "").strip()
        expected_prefix = f"План №{ordinal}"
        if not (title == expected_prefix or title.startswith(expected_prefix + " — ")):
            diag.error(plan_md, meta.get("Title", ("", None))[1],
                       f"Title должен начинаться с «{expected_prefix} — …» "
                       f"для PLAN-ID «{plan_id}»")

        plans_root = plan_dir.parent.parent if plan_dir.parent.name == "archive" else plan_dir.parent
        peers = [p for p in plans_root.iterdir() if p.is_dir() and p.name != "archive"]
        archive_dir = plans_root / "archive"
        if archive_dir.is_dir():
            peers.extend(p for p in archive_dir.iterdir() if p.is_dir())
        duplicates = []
        for peer in peers:
            if peer == plan_dir:
                continue
            # A post-archive continuation temporarily lives beside its archived
            # copy under the same Plan ID. It is one plan in two lifecycle
            # locations, not a second plan claiming the ordinal.
            if peer.name == plan_id:
                continue
            match = PLAN_ID_NUMBERED_RE.match(peer.name)
            if (match and match.group("date") == numbered.group("date")
                    and match.group("ordinal") == ordinal):
                duplicates.append(peer.relative_to(plans_root).as_posix())
        if duplicates:
            diag.error(plan_dir, None,
                       f"PLAN-ID «{plan_id}» дублирует порядковый номер "
                       f"№{ordinal} за {numbered.group('date')}: {', '.join(sorted(duplicates))}")

    codename = _plan_codename(plan_id)

    # (2) место/имя workflow-скриптов (только `.js` с маркером `export const meta`)
    name_re = _workflow_name_re(codename)
    for js in sorted(plan_dir.rglob("*.js")):
        if not js.is_file():
            continue
        # A lossless v1 source snapshot is provenance, not a live plan-owned
        # workflow location.  Its historical scripts must not be reclassified
        # as v2 topology violations.
        if js.relative_to(plan_dir).parts[:2] == ("artifacts", "migration-source-v1"):
            continue
        try:
            text = js.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if WORKFLOW_META_MARKER not in text:
            continue
        if js.name == DEV_LOOP_EXEMPT_NAME:
            continue
        rel = js.relative_to(plan_dir)
        if not (rel.parts and rel.parts[0] == WORKFLOW_DIR_NAME):
            diag.warning(js, None,
                         f"workflow-скрипт «{rel}» вне `plans/{plan_id}/workflows/` — "
                         f"единственный дом workflow-скриптов плана (D28)")
        if not name_re.match(js.name):
            diag.warning(js, None,
                         f"workflow-скрипт «{js.name}» с неканоничным именем — "
                         f"канон `wf-{codename}-<назначение>.js` (D28)")

    # (3) supersedes: совпадение кодового имени с архивным планом без Meta supersedes
    archive_dir = plan_dir.parent / "archive"
    if archive_dir.is_dir():
        archived = {
            _plan_codename(p.name)
            for p in archive_dir.iterdir()
            if p.is_dir()
            and not (p.name == plan_id and (p / "plan.md").is_file())
        }
        supersedes_val = (meta.get("supersedes", ("", None))[0] or "").strip()
        if codename in archived and _is_empty(supersedes_val):
            diag.warning(plan_md, None,
                         f"план «{plan_id}» повторяет кодовое имя «{codename}» архивного "
                         f"плана, но не несёт Meta `supersedes` — преемственность волны "
                         f"трека не объявлена (D27)")


# --- парсинг файлов схемы -----------------------------------------------------

def parse_plan_md(path, diag):
    """plan.md → (meta: dict[name]=(value,lineno), status_board: list[(row,lineno)])."""
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "plan.md отсутствует или не читается")
        return None, []

    _lint_plan_md_20(lines, path, diag)

    try:
        layout = plan_layout.layout_version(Path(path).parent)
    except plan_layout.PlanLayoutError:
        layout = "v2"

    meta = {}
    _, meta_body, meta_start = _find_section(lines, META_HEADER_RE)
    if meta_body is None:
        diag.error(path, None, "нет секции «## 0. Meta»")
    else:
        headers, rows, header_lineno = _parse_table(meta_body, meta_start)
        if headers is None:
            diag.error(path, meta_start, "Meta: таблица `Поле|Значение` не найдена")
        elif tuple(headers) != META_TABLE_COLUMNS:
            diag.error(path, header_lineno,
                       f"Meta: колонки {headers} ≠ ожидаемых {list(META_TABLE_COLUMNS)}")
        else:
            for row, lineno in rows:
                meta[row.get("Поле", "")] = (row.get("Значение", ""), lineno)
        required_fields = V2_CORE_META_FIELDS if layout == "v2" else REQUIRED_META_FIELDS
        for field in required_fields:
            if field not in meta:
                diag.error(path, meta_start, f"Meta: нет обязательного поля «{field}»")

    if layout == "v2":
        numbered = {int(match.group(1)): match.group(2)
                    for line in lines if (match := PLAN_SECTION_NUM_RE.match(line))}
        allowed = {0, 1, 2, 3, 4, 5, 7}
        for number in sorted(set(numbered) - allowed):
            diag.error(path, None,
                       f"Layout v2: секция «## {number}. {numbered[number]}» не входит в закрытый состав ядра")
        for field in V2_STATUS_META_FIELDS:
            if field in meta:
                diag.error(path, meta[field][1],
                           f"Layout v2: поле Meta «{field}» живёт только в status.md")
        try:
            status_meta, status_board = plan_status.parse_status_view(Path(path).parent)
        except plan_status.StatusError as exc:
            diag.error(Path(path).parent / "status.md", None, str(exc))
            return meta, []
        meta.update(status_meta)
        core_row = plan_layout.registry().get("plan-core", {})
        if core_row.get("volatility") not in ("stable", "slow"):
            diag.error(path, None,
                       "Layout v2: plan-core не объявлен stable/slow в реестре носителей")
        return meta, status_board

    status_board = []
    _, board_body, board_start = _find_section(lines, STATUS_BOARD_HEADER_RE)
    if board_body is None:
        diag.error(path, None, "нет секции «## 4. Phase Index & Status Board»")
    else:
        headers, rows, header_lineno = _parse_table(board_body, board_start)
        if headers is None:
            diag.error(path, board_start, "Status Board: таблица не найдена")
        elif tuple(headers) != STATUS_BOARD_COLUMNS:
            diag.error(path, header_lineno,
                       f"Status Board: колонки {headers} ≠ ожидаемых {list(STATUS_BOARD_COLUMNS)}")
        else:
            status_board = rows
            for row, lineno in rows:
                st = row.get("Status", "")
                if st not in STATUSES:
                    diag.error(path, lineno, f"Status Board: недопустимый статус «{st}»")
                if not PHASE_TOKEN_RE.match(row.get("Phase", "")):
                    diag.error(path, lineno,
                               f"Status Board: Phase «{row.get('Phase')}» не похож на Pn")

    return meta, status_board


def _parse_v2_item_file(path, item_id, diag):
    """Read one handwritten item spec plus its generated state carrier."""
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "файл ТЗ item отсутствует или не читается")
        return None
    item_blocks = [item for item in _find_items(lines) if item[0] == item_id]
    if len(item_blocks) != 1:
        diag.error(path, None,
                   f"item {item_id}: ожидается ровно один заголовок «### {item_id} — …»")
        return None
    actual_id, title, header_lineno, body_lines, body_start = item_blocks[0]
    fields, duplicates = _parse_fields(body_lines, body_start, FIELD_RE)
    for field in ITEM_SPEC_FIELDS:
        if field not in fields:
            diag.error(path, header_lineno, f"item {item_id}: нет поля ТЗ «{field}»")
    for field in ITEM_STATE_FIELDS:
        if field in fields:
            diag.error(path, fields[field][1],
                       f"item {item_id}: поле исхода «{field}» запрещено в файле ТЗ")
    for field, (_value, lineno) in fields.items():
        if field not in ITEM_SPEC_FIELDS and field not in ITEM_STATE_FIELDS:
            diag.error(path, lineno,
                       f"item {item_id}: поле «{field}» не входит в закрытый список файла ТЗ")
    for name, first_ln, first_val, dup_ln, dup_val in duplicates:
        if name in ITEM_SPEC_FIELDS:
            diag.error(path, dup_ln,
                       f"item {item_id}: поле ТЗ «{name}» встречается повторно "
                       f"(первое {path.name}:{first_ln} → «{_preview(first_val)}», "
                       f"повтор {path.name}:{dup_ln} → «{_preview(dup_val)}»)")

    canonical_index = {field: index for index, field in enumerate(ITEM_SPEC_FIELDS)}
    present_order = [field for field in fields if field in canonical_index]
    if present_order != sorted(present_order, key=canonical_index.get):
        diag.warning(path, header_lineno,
                     f"item {item_id}: поля идут не в каноническом порядке "
                     "(канон — SKILL §5 / phase-template)")

    state_path = path.with_name(path.stem + ".state.md")
    state_lines = _read_lines(state_path)
    if state_lines is None:
        diag.error(state_path, None, f"item {item_id}: обязательный слепок состояния отсутствует или не читается")
        return None
    state_fields, state_duplicates = _parse_fields(state_lines, 1, FIELD_RE)
    for field in ITEM_STATE_FIELDS:
        if field not in state_fields:
            diag.error(state_path, None, f"item {item_id}: в слепке нет поля исхода «{field}»")
    for field in ITEM_SPEC_FIELDS:
        if field in state_fields:
            diag.error(state_path, state_fields[field][1],
                       f"item {item_id}: поле ТЗ «{field}» запрещено в слепке состояния")
    for field, (_value, lineno) in state_fields.items():
        if field not in ITEM_STATE_FIELDS and field not in ITEM_SPEC_FIELDS:
            diag.error(state_path, lineno,
                       f"item {item_id}: поле «{field}» не входит в закрытый список слепка состояния")
    for name, first_ln, first_val, dup_ln, dup_val in state_duplicates:
        if name in ITEM_STATE_FIELDS:
            diag.error(state_path, dup_ln,
                       f"item {item_id}: поле исхода «{name}» встречается повторно "
                       f"(первое {state_path.name}:{first_ln} → «{_preview(first_val)}», "
                       f"повтор {state_path.name}:{dup_ln} → «{_preview(dup_val)}»)")

    merged = {}
    for field in REQUIRED_ITEM_FIELDS:
        if field in fields:
            merged[field] = fields[field]
        elif field in state_fields:
            merged[field] = state_fields[field]
    status_value, status_lineno = merged.get("Status", ("", header_lineno))
    if status_value and status_value not in STATUSES:
        diag.error(state_path, status_lineno,
                   f"item {item_id}: недопустимый статус «{status_value}»")
    return {"title": title, "header_lineno": header_lineno, "fields": merged,
            "has_escalation": any(ESCALATION_RE.match(line)
                                    and ESCALATION_RE.match(line).group(1) == actual_id
                                    for line in lines),
            "spec_lines": lines, "state_lines": state_lines}


def _parse_phase_v2(path, phase_id, diag):
    """Assemble a v2 phase model from its thin index, item specs, and states."""
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "индекс фазы отсутствует или не читается")
        return None
    if _find_section(lines, PHASE_STATUS_HEADER_RE)[1] is not None:
        diag.error(path, None, "Layout v2: «## Phase Status» запрещён в тонком индексе фазы")
    if _find_items(lines):
        diag.error(path, None, "Layout v2: item-блоки живут только в отдельных файлах ТЗ")

    _, ctx_body, _ = _find_section(lines, PHASE_CONTEXT_HEADER_RE)
    if ctx_body is None:
        diag.error(path, None, "нет секции «## Phase Context»")
    is_skeleton = bool(ctx_body and any(SKELETON_MARKER_RE.match(line) for line in ctx_body))
    _, handoff_body, handoff_start = _find_section(lines, PHASE_HANDOFF_HEADER_RE)
    if handoff_body is None:
        diag.error(path, None, "нет секции «## Phase Handoff»")
        handoff_text = None
        handoff_lineno = None
        handoff_first_line = ""
    else:
        handoff_text = "\n".join(handoff_body).strip()
        handoff_lineno = handoff_start - 1
        handoff_first_line = next((line for line in handoff_body if line.strip()), "").strip()

    items = {}
    status_table = []
    gate_lines = _lines_before_audit(lines)
    # Phase Context is the sole carrier for this phase-level declaration.  Keep
    # `gate_lines` broad for the structural checks below, but do not let a
    # downstream handoff or item prose manufacture a workflow requirement.
    orchestration_lines = tuple(ctx_body or ())
    try:
        owner_status = plan_status.status_model(path.parents[2])
        updated_by_id = {
            item["id"]: item["updated"]
            for phase in owner_status["phases"] if phase["id"] == phase_id
            for item in phase["items"]
        }
    except (plan_status.StatusError, plan_layout.PlanLayoutError) as exc:
        diag.error(path.parents[2] / "status.md", None,
                   f"Layout v2: не удалось получить journal-backed Updated: {exc}")
        updated_by_id = {}
    try:
        spec_paths = plan_layout.item_spec_paths(path.parents[2], phase_id)
    except plan_layout.PlanLayoutError as exc:
        diag.error(path, None, str(exc))
        spec_paths = []
    for spec_path in spec_paths:
        item_id = spec_path.stem
        item = _parse_v2_item_file(spec_path, item_id, diag)
        if item is None:
            continue
        items.setdefault(item_id, []).append(item)
        status, status_lineno = item["fields"].get("Status", ("", item["header_lineno"]))
        status_table.append(({"ID": item_id, "Title": item["title"], "Status": status,
                              "Updated": updated_by_id.get(item_id, ""),
                              "Layout": "v2"}, status_lineno))
        gate_lines.extend(item["spec_lines"])
        gate_lines.extend(item["state_lines"])
        empty = sum(1 for field in REQUIRED_ITEM_FIELDS
                    if _is_empty(item["fields"].get(field, ("",))[0]))
        if not is_skeleton and empty >= len(REQUIRED_ITEM_FIELDS) * SKELETON_EMPTY_RATIO:
            diag.warning(spec_path, item["header_lineno"],
                         f"item {item_id}: {empty}/{len(REQUIRED_ITEM_FIELDS)} полей пусты, "
                         "а в Phase Context нет маркера «> СКЕЛЕТ — не детализирован…» — "
                         "либо детализировать, либо пометить фазу скелетом")

    return {"status_table": status_table, "items": items, "phase_handoff": handoff_text,
            "phase_handoff_stale": bool(PHASE_HANDOFF_STALE_RE.match(handoff_first_line)),
            "phase_handoff_lineno": handoff_lineno, "phase_handoff_first_line": handoff_first_line,
            "is_skeleton": is_skeleton,
            "needs_clarification": [i + 1 for i, line in enumerate(gate_lines)
                                    if NEEDS_CLARIFICATION_RE.search(line)],
            "declares_orchestration": any(phase_declares_orchestration(line)
                                           for line in orchestration_lines)}


def parse_phase_md(path, phase_id, diag, *, layout="v2"):
    """phases/Pn.md → dict со status_table/items/handoff (см. lint_plan)."""
    if layout == "v2":
        return _parse_phase_v2(path, phase_id, diag)
    diag.error(path, None, "PLAN_LAYOUT_V1_RETIRED: исполняется только Layout v2")
    return None

    # Historical parser retained below only for source archive compatibility.
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "файл фазы отсутствует или не читается")
        return None

    status_table = []
    _, ps_body, ps_start = _find_section(lines, PHASE_STATUS_HEADER_RE)
    if ps_body is None:
        diag.error(path, None, "нет секции «## Phase Status»")
    else:
        headers, rows, header_lineno = _parse_table(ps_body, ps_start)
        if headers is None:
            diag.error(path, ps_start, "Phase Status: таблица не найдена")
        elif tuple(headers) != PHASE_STATUS_COLUMNS:
            diag.error(path, header_lineno,
                       f"Phase Status: колонки {headers} ≠ ожидаемых {list(PHASE_STATUS_COLUMNS)}")
        else:
            status_table = rows
            for row, lineno in rows:
                st = row.get("Status", "")
                if st not in STATUSES:
                    diag.error(path, lineno, f"Phase Status: недопустимый статус «{st}»")

    for bad_ln, lineno in _malformed_item_headers(lines):
        diag.error(path, lineno,
                    f"заголовок item не соответствует regex `^### (P\\d+\\.\\d+) — `: «{bad_ln}»")

    # --- 2.0: скелет-маркер в Phase Context (легализует пустые поля items) ------
    is_skeleton = False
    _, ctx_body, _ = _find_section(lines, PHASE_CONTEXT_HEADER_RE)
    if ctx_body is not None:
        is_skeleton = any(SKELETON_MARKER_RE.match(ln) for ln in ctx_body)

    # --- 2026.07.13-PLAN-PROTOCOL-GAP P3.8/D52: регион ОБОИХ грепов по фазе — до первого `## Audit` (append-блок
    # аудита законно цитирует маркеры, по которым отчитывается; см. AUDIT_BLOCK_HEADER_RE)
    gate_lines = _lines_before_audit(lines)

    # --- 2.0: маркеры [NEEDS CLARIFICATION] — линуются в lint_plan по статусу фазы
    needs_clarification = [i + 1 for i, ln in enumerate(gate_lines)
                           if NEEDS_CLARIFICATION_RE.search(ln)]

    # --- 2026.07.10-SKM-ROADMAP-005 P4.6: заявляет ли фаза оркестрацию (грепаемый признак, D29) — линуется
    # в lint_plan (workflow-как-DoR: фаза с оркестрацией без workflow-скрипта = warning)
    _, phase_context, _ = _find_section(gate_lines, PHASE_CONTEXT_HEADER_RE)
    declares_orchestration = any(phase_declares_orchestration(ln) for ln in (phase_context or ()))

    items = {}
    for item_id, title, header_lineno, body_lines, body_start in _find_items(lines):
        prefix_m = PHASE_TOKEN_RE.match(item_id.split(".")[0])
        if prefix_m and item_id.split(".")[0] != phase_id:
            diag.error(path, header_lineno,
                       f"item {item_id}: префикс «{item_id.split('.')[0]}» не совпадает "
                       f"с файлом фазы «{phase_id}»")
        fields, dup_fields = _parse_fields(body_lines, body_start, FIELD_RE)
        for f in REQUIRED_ITEM_FIELDS:
            if f not in fields:
                diag.error(path, header_lineno,
                           f"item {item_id}: нет обязательного поля «{f}» (item фазы-скелета "
                           f"обязан нести все 16 полей со значением «—»; детализация — "
                           f"/task:plan-design <ID> {phase_id})")

        # --- D90: повтор поля в теле item'а — последнее вхождение молча подменяет
        # раннее легитимное значение (у linter'а И у task_contract) --------------
        for name, first_ln, first_val, dup_ln, dup_val in dup_fields:
            if name in REQUIRED_ITEM_FIELDS:
                diag.error(path, dup_ln,
                           f"item {item_id}: поле «{name}» встречается повторно "
                           f"(первое {path.name}:{first_ln} → «{_preview(first_val)}», "
                           f"повтор {path.name}:{dup_ln} → «{_preview(dup_val)}») — плановый "
                           f"парсер и task_contract молча берут ПОСЛЕДНЕЕ вхождение (D90): "
                           f"строка `**{name}:**` внутри прозы другого поля (например, "
                           f"Completion Notes) подменяет собой приёмочное значение — уберите "
                           f"звёздочки/двоеточие у инлайн-упоминания или перенесите его в "
                           f"свободный текст без формы поля")

        # --- 2.0 WARNING: порядок 16 канонических полей (P0.3 рек#6) ------------
        canon_index = {f: i for i, f in enumerate(REQUIRED_ITEM_FIELDS)}
        present_order = [f for f in fields if f in canon_index]
        if present_order != sorted(present_order, key=canon_index.get):
            diag.warning(path, header_lineno,
                         f"item {item_id}: поля идут не в каноническом порядке "
                         f"(канон — SKILL §5 / phase-template)")

        # --- 2.0 WARNING: ≥50% пустых полей без скелет-маркера (P0.3 рек#1) -----
        empty = sum(1 for f in REQUIRED_ITEM_FIELDS if _is_empty(fields.get(f, ("",))[0]))
        if not is_skeleton and empty >= len(REQUIRED_ITEM_FIELDS) * SKELETON_EMPTY_RATIO:
            diag.warning(path, header_lineno,
                         f"item {item_id}: {empty}/{len(REQUIRED_ITEM_FIELDS)} полей пусты, "
                         f"а в Phase Context нет маркера «> СКЕЛЕТ — не детализирован…» — "
                         f"либо детализировать, либо пометить фазу скелетом")
        status_val, _ = fields.get("Status", ("", header_lineno))
        if status_val and status_val not in STATUSES:
            diag.error(path, header_lineno, f"item {item_id}: недопустимый статус «{status_val}»")
        has_escalation = any(
            ESCALATION_RE.match(ln) and ESCALATION_RE.match(ln).group(1) == item_id
            for ln in body_lines
        )
        items.setdefault(item_id, []).append({
            "title": title, "header_lineno": header_lineno, "fields": fields,
            "has_escalation": has_escalation,
        })

    for item_id, occurrences in items.items():
        if len(occurrences) > 1:
            lns = ", ".join(str(o["header_lineno"]) for o in occurrences)
            diag.error(path, occurrences[0]["header_lineno"],
                       f"item {item_id}: повторяется в файле (строки {lns})")

    _, handoff_body, handoff_start = _find_section(lines, PHASE_HANDOFF_HEADER_RE)
    handoff_stale = False
    handoff_first_line = ""
    if handoff_body is None:
        diag.error(path, None, "нет секции «## Phase Handoff»")
        handoff_text = None
        handoff_lineno = None
    else:
        handoff_text = "\n".join(handoff_body).strip()
        handoff_lineno = handoff_start - 1  # строка самого заголовка «## Phase Handoff»
        # 2026.07.13-PLAN-PROTOCOL-GAP P2.15/D34: маркер инвалидации — ПЕРВАЯ непустая строка блока (линуется в lint_plan);
        # 2026.07.13-PLAN-PROTOCOL-GAP P3.7/D50: по ней же судит предикат «блок утверждает закрытие фазы» (субъект, не слово)
        handoff_first_line = next((ln for ln in handoff_body if ln.strip()), "").strip()
        handoff_stale = bool(PHASE_HANDOFF_STALE_RE.match(handoff_first_line))

    return {"status_table": status_table, "items": items, "phase_handoff": handoff_text,
            "phase_handoff_stale": handoff_stale, "phase_handoff_lineno": handoff_lineno,
            "phase_handoff_first_line": handoff_first_line,
            "is_skeleton": is_skeleton, "needs_clarification": needs_clarification,
            "declares_orchestration": declares_orchestration}


def _resolve_next_form(text):
    """Резолвит форму `Next` из enum'а §8 в тексте: `(kind, match)` либо `(None, None)`.

    Порядок — от специфичной формы к общей; первая сматчившая определяет проверку ссылок,
    остальные не пробуются (D4). «план закрыт» проверяется СРАЗУ после plan-exec (а не
    среди прочих regex-форм): это цельное утверждение о состоянии плана, а не slash-команда
    — Next закрытого плана иногда УПОМИНАЕТ следующую команду прозой («… решает владелец:
    `/task:plan-close archive <ID>` либо …», см. EDUFY-2), и эта проза не должна
    перехватывать резолвер. Manual-маркер — последним: у формы нет ссылок, она резолвится
    лишь тем, что ни одна slash-форма не объявлена.

    Форма «ОЖИДАНИЕ» (D8) — ПЕРВОЙ, ДО plan-exec: её строка-объявление embed'ит целевой
    `/task:plan-exec` (запустится по снятии гейта), который иначе перехватил бы резолвер как
    `exec` — зеркало того, почему «план закрыт» стоит сразу после exec.
    """
    semantic = SEMANTIC_NEXT_RE.match(text.strip())
    if semantic:
        semantic_kind, payload = semantic.groups()
        if semantic_kind == "terminal":
            return ("closed", None) if LITERAL_PLAN_CLOSED in payload.lower() else (
                "invalid-semantic", None)
        if semantic_kind == "manual":
            return "manual", None
        if semantic_kind == "waiting":
            return "waiting", None
        expected_command, expected_kind = SEMANTIC_NEXT_COMMANDS[semantic_kind]
        command, separator, arguments = payload.partition(" ")
        if command != expected_command or not separator:
            return "invalid-semantic", None
        legacy_kind, match = _resolve_next_form("/" + command + " " + arguments)
        return (legacy_kind, match) if legacy_kind == expected_kind else (
            "invalid-semantic", None)
    if LITERAL_WAITING in text:
        return "waiting", None
    m = PLAN_EXEC_RE.search(text)
    if m:
        return "exec", m
    m = PLAN_RUN_RE.search(text)
    if m:
        return "run", m
    if LITERAL_PLAN_CLOSED in text.lower():
        return "closed", None
    for kind, rx in (("design-item", PLAN_DESIGN_ITEM_RE),
                     ("design-finish", PLAN_DESIGN_FINISH_RE),
                     ("design-roadmap", PLAN_DESIGN_ROADMAP_RE),
                     ("design-phase", PLAN_DESIGN_PHASE_RE),
                     ("audit-design", PLAN_AUDIT_DESIGN_RE),
                     ("audit", PLAN_AUDIT_RE),
                     ("close-archive", PLAN_CLOSE_ARCHIVE_RE),
                     ("close", PLAN_CLOSE_RE)):
        m = rx.search(text)
        if m:
            return kind, m
    if MANUAL_RUN_MARKER in text:
        return "manual", None
    return None, None


def parse_handoff_md(path, diag):
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "handoff.md отсутствует или не читается")
        return None

    title_lineno = None
    title_ref = None  # `Pn.m` (item) либо `Pn` (фаза) — резолвится в lint_plan
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            m = HANDOFF_TITLE_RE.match(ln)
            title_lineno = i + 1
            if m:
                title_ref = m.group(1)
            else:
                diag.error(path, title_lineno, HANDOFF_TITLE_HELP)
            break
    else:
        diag.error(path, None, "нет заголовка «# HANDOFF — … — after Pn.m» / «… — after Pn»")

    body_start = (title_lineno or 0) + 1
    # handoff-поля вне Scope 2026.07.31-SKM-LEAN P5.9 (D90 — только REQUIRED_ITEM_FIELDS
    # items'ов) — duplicates осознанно отброшены, не диагностируются здесь.
    fields, _dup_handoff_fields = _parse_fields(lines[body_start - 1:], body_start, FIELD_RE)
    for f in HANDOFF_REQUIRED_FIELDS:
        if f not in fields:
            diag.error(path, body_start, f"нет обязательного поля «{f}»")

    return {"title_ref": title_ref, "title_lineno": title_lineno,
            "fields": fields, "lines": lines}


# --- линт одного плана ---------------------------------------------------

__all__ = tuple(name for name in globals() if not name.startswith("__"))
