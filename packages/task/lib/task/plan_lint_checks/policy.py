"""Independent policy gates and canon registries used by plan-lint."""
from .common import *
from task import plan_decisions


def _portability_execution_paths(fields):
    """Пути (path-like токены, backtick-цитата или голые) в значениях ролевых полей
    item'а (ROLE-тест, D47): другие поля (Implementation Rules/Code Guidance/Why/…)
    НЕ сканируются — упоминание там не даёт пути роль execution input."""
    paths = []
    for name in PORTABILITY_ROLE_FIELDS:
        value = fields.get(name, "") or ""
        cleaned = PORTABILITY_SHELL_REDIRECT_RE.sub(" ", value)
        paths.extend(PORTABILITY_PATH_RE.findall(cleaned))
    return paths


def _plan_declares_committed_bundle_tier(plan_dir):
    """plan-portability-v1.md §Classification rule — tier(work) применительно к
    исполняемому мастер-плану целиком: план протокола ПО КОНСТРУКЦИИ несёт `handoff.md`
    (multi-session/handoff всегда true — обязательный носитель SKILL §8) → committed-bundle.
    План без `handoff.md` (ещё не дошёл до схемы) этим гейтом не разбирается — другая
    диагностика уже требует сам файл."""
    return (Path(plan_dir) / "handoff.md").is_file()


def _lint_tiered_portability_22(plan_dir, plan_id, all_items, phases, diag):
    """2026.07.24-AGENT-RELIABILITY P2.2/D26/D47: план tier=committed-bundle (что верно для любого исполняемого
    мастер-плана по конструкции, см. `_plan_declares_committed_bundle_tier`) обязан
    нести ≥1 committed/predecessor-produced execution input и не содержать внешний
    (host/chat/mAInd/tmp/foreign) путь В РОЛИ execution input — иначе `plan_lint`
    отказывает (`task_contract.PORTABILITY_INPUT_MISSING`/`PORTABILITY_EXTERNAL_INPUT`).
    Датовые планы от PORTABILITY_TIER_CANON_DATE — ERROR, старее/legacy — WARNING
    (back-compat, тот же паттерн, что у brief/roadmap/journal-гейтов)."""
    if not _plan_declares_committed_bundle_tier(plan_dir):
        return
    report = (diag.error if (PLAN_ID_DATED_RE.match(plan_id)
                             and plan_id[:10] >= PORTABILITY_TIER_CANON_DATE) else diag.warning)
    found_committed = False
    for item_id, info in sorted(all_items.items()):
        item_path = phases.get(info.get("phase"), {}).get("path", plan_dir)
        for raw_path in _portability_execution_paths(info.get("fields", {})):
            if task_contract.is_external_path(raw_path):
                report(item_path, None,
                       f"item {item_id}: execution input «{raw_path}» — внешний путь "
                       f"(host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, "
                       f"plan-portability-v1.md)")
            else:
                found_committed = True
    if not found_committed:
        report(Path(plan_dir) / "plan.md", None,
               f"план несёт handoff.md (tier=committed-bundle, plan-portability-v1.md "
               f"§Classification rule) без единого committed execution input ни в одном "
               f"item'е (PORTABILITY_INPUT_MISSING)")


# --- 2026.07.24-AGENT-RELIABILITY P4.4/D91: машинный гейт напечатанных кодов границ (ремонт находки Ф2) ------
# findings/P3.11-terminal-audit-2.md § Ф2, событие 2 из 2: канон уже требовал печати ОБОИХ
# кодов write-site (`plan-audit.md` чеклист), но проверка была НЕ машинной — пять items
# подряд (P3.6-P3.10) прошли аудит перепрогоном предиката ВРУЧНУЮ (все пять → allow/allow),
# сама ЗАПИСЬ в Completion Notes осталась отсутствующей. Якорь скоупа — ДАТА ITEM'а
# (колонка `Updated` таблицы «## Phase Status», ISO), А НЕ дата плана: паттерн
# BRIEF_CANON_DATE/JOURNAL_CANON_DATE/PORTABILITY_TIER_CANON_DATE здесь промахнулся бы —
# этот план датирован `2026.07.24`, то есть его собственные будущие items P4.* остались бы
# вне гейта, а красить закрытые задним числом запрещено (D91, третий проход по записи
# отвергнут отчётом Ф2). Формат константы — ISO ДЕФИС (`YYYY-MM-DD`), а НЕ ТОЧКА, как у
# датовых plan_id-констант выше: сравнение идёт со значением ЯЧЕЙКИ `Updated`, которая несёт
# дефисы — сравнение разноформатных строк друг с другом ломает лексикографический порядок.
# Дата НАМЕРЕННО на день позже дня авторства правила (2026-07-26) — тот же приём, что у
# PORTABILITY_TIER_CANON_DATE: items, закрываемые ЭТОЙ же фазой в день авторства, не красятся
# задним числом; правило доказывается синтетическими датированными фикстурами
# (test_plan_lint.py), а не самоприменением к текущему прогону.
WRITE_SITE_CODES_CANON_DATE = "2026-07-27"
ITEM_UPDATED_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Канон кодов — `task_contract.evaluate()`: `pre_mutation` ∈ {allow, block:<CODE>};
# `pre_final` ∈ {allow, block:<CODE>, n/a} (D76: `n/a` — НЕ зелёное).
# --- 2026.07.25-ECO-OPT P10.1/D88/D102: каноническая строка вместо re.search по всему полю --------
# Старая форма (`WRITE_SITE_PRE_MUTATION_RE.search(clean)` по ВСЕМУ Completion Notes)
# ошибалась в ОБЕ стороны: (1) fail-open — item без своих кодов, но ЦИТИРУЮЩИЙ чужие в
# прозе, проходил гейт; (2) ложный ERROR — item со своими `allow`, процитировавший ВЫШЕ
# по тексту `block:*`/`n/a` чужого item'а, краснел, потому что `search` берёт ПЕРВОЕ
# вхождение. Обе цены реальны с даты активации гейта. Починка: ОДНА каноническая строка
# `write-site: pre_mutation: <код> · pre_final: <код>` (D88) — коды item'а живут ТОЛЬКО
# на строке с этим префиксом; прозаические цитаты на других строках гейт не видит.
WRITE_SITE_LINE_FORM = "write-site: pre_mutation: <код> · pre_final: <код>"
_WRITE_SITE_CODE = r"(allow|n/a|block:[A-Za-z0-9_]+)"
WRITE_SITE_LINE_PREFIX_RE = re.compile(r"^write-site:\s*(.*)$")
WRITE_SITE_CODE_PAIR_RE = re.compile(
    r"^pre_mutation:\s*" + _WRITE_SITE_CODE + r"\s*\W+\s*"
    r"pre_final:\s*" + _WRITE_SITE_CODE + r"\s*\.?\s*$")


def _write_site_canonical_codes(completion_notes):
    """Находит каноническую строку `write-site:` (D88) в Completion Notes и
    возвращает `(pre_mutation, pre_final)` — ПОСТРОЧНО (поле парсер отдаёт
    многострочным), а не `re.search` по всему полю. Markdown-обёртка строки
    (бэктики, `**`, ведущие `- `/`> `, пробелы) срезается ДО матча — форма печати
    несёт их. Строки БЕЗ префикса `write-site:` (цитаты, объяснения) не
    рассматриваются вовсе, даже если в них встречаются `pre_mutation:`/`pre_final:` —
    ровно это закрывает fail-open. Строка С префиксом, но не разбирающаяся в форму
    (сломан порядок/разделитель, ЛИБО это прозаическая цитата шаблона строки —
    `` `write-site: pre_mutation: <код> · pre_final: <код>` `` как объяснение
    правила, — с обёрнутой строки такая цитата тоже начинается) НЕ считается
    канонической и не останавливает поиск: перебор продолжается дальше по полю.
    Ни одной разбирающейся строки во всём поле → `None`, ERROR «кодов нет»."""
    for raw_line in (completion_notes or "").replace("`", "").splitlines():
        line = raw_line.replace("*", "").strip()
        while line[:1] in ("-", ">"):
            line = line[1:].strip()
        prefix = WRITE_SITE_LINE_PREFIX_RE.match(line)
        if not prefix:
            continue
        pair = WRITE_SITE_CODE_PAIR_RE.match(prefix.group(1).strip())
        if pair:
            return pair.group(1), pair.group(2)
    return None


def _lint_write_site_codes_44(status_table, items, path, diag):
    """2026.07.24-AGENT-RELIABILITY P4.4/D91 (ремонт находки Ф2), точность — 2026.07.25-ECO-OPT P10.1/D88/D102: item со статусом
    🟢/🟠, чей `Updated` (Phase Status) ISO-датирован ≥ WRITE_SITE_CODES_CANON_DATE,
    обязан нести каноническую строку `write-site:` (см. `_write_site_canonical_codes`)
    с ОБОИМИ кодами `allow` (D76: `n/a` — не зелёное). Непарсимая/отсутствующая дата =
    item вне скоупа — МОЛЧАНИЕ, а не WARNING (И10: ни один существующий закрытый item
    не краснеет задним числом). Внутри скоупа — ERROR (правило уже канон:
    `plan-audit.md` чеклист «write-site»; машинная проверяемость — P4.4/P10.1)."""
    updated_by_id = {row.get("ID"): row.get("Updated", "") for row, _ in status_table}
    for item_id, occurrences in items.items():
        item = occurrences[0]
        status_val, _ = item["fields"].get("Status", ("", item["header_lineno"]))
        if status_val not in (STATUS_DONE, STATUS_DEVIATIONS):
            continue
        updated = updated_by_id.get(item_id, "") or ""
        if not ITEM_UPDATED_ISO_RE.match(updated) or updated < WRITE_SITE_CODES_CANON_DATE:
            continue
        cn_val, cn_lineno = item["fields"].get("Completion Notes", ("", item["header_lineno"]))
        codes = _write_site_canonical_codes(cn_val)
        if codes is None:
            diag.error(path, cn_lineno,
                       f"item {item_id}: закрыт «{status_val}» без напечатанных кодов границ "
                       f"pre_mutation/pre_final в Completion Notes (ожидается строка "
                       f"`{WRITE_SITE_LINE_FORM}`)")
            continue
        pre_mutation, pre_final = codes
        if pre_mutation != "allow":
            diag.error(path, cn_lineno,
                       f"item {item_id}: pre_mutation: {pre_mutation} при статусе "
                       f"«{status_val}» — закрытие на не-allow (D76)")
        if pre_final != "allow":
            diag.error(path, cn_lineno,
                       f"item {item_id}: pre_final: {pre_final} при статусе "
                       f"«{status_val}» — закрытие на не-allow (D76)")


# --- 2026.07.25-ECO-OPT P8.1/D42: отчёт закрытия фазы `closure/<Pn>.json` (схема v1) --------------
# Класс свидетельства фазы не фиксировался нигде: `Phase Handoff` — проза плюс git-хеш, и
# синтетика читается как результат (research/11-P8-target-design.md §1). Отчёт закрытия —
# машиночитаемый файл на фазу, ВКЛЮЧАЕТСЯ opt-in полем `## 0. Meta` → `Closure Protocol | v1`:
# плана без поля правило не касается НИ ОДНОЙ строкой диагностики (аддитивность — тест, а не
# обещание; закрытые записи живых планов не переписываются). Ревалидация ПОСЛОЙНАЯ (рамка
# переноса, findings/rayt-deep-2026-07-25.md §8.3 #17/#29): один JSON на фазу + две уже
# распарсенные таблицы; обхода дерева и пересчёта хешей файлов плана здесь нет.
# У КАЖДОГО хеша схемы назван потребитель (иначе «provenance theatre», §9.6): `git.head_sha` —
# якорь чисел §8 канона; `inputs_sha256` — детект правки ТЗ фазы после закрытия (`plan-audit`).
CLOSURE_META_FIELD = "Closure Protocol"
CLOSURE_PROTOCOL_V1 = "v1"  # ЕДИНСТВЕННОЕ легальное значение поля (D42)
CLOSURE_DIR_NAME = "closure"
CLOSURE_SCHEMA_VERSION = 1
# Класс свидетельства — enum РОВНО из трёх (D42): на каких ДАННЫХ получен результат.
# НЕ путать с закрытым перечнем классов ДОКАЗАТЕЛЬСТВА `recomputed`/`cross-checked`/
# `pinned-not-recomputable`/`unknown` (`source-evidence-verification-v1.md`, другая ось —
# выводимо ли утверждение из коммиченного bundle'а): оба словаря действуют, ни один не
# заменяет другой (канон `plan-protocol` §8, реконсайл 2026-07-26).
CLOSURE_EVIDENCE_CLASSES = ("real", "synthetic", "baseline_pending")
CLOSURE_REQUIRED_KEYS = ("schema_version", "plan", "phase", "closed_at", "closed_by",
                         "phase_status", "git", "inputs_sha256", "items", "gates",
                         "metrics", "limitations", "external_side_effects")
CLOSURE_CLOSED_BY_KEYS = ("command", "actor")
CLOSURE_GIT_KEYS = ("head_sha", "branch", "dirty")
# `items`/`gates` — записи с классом свидетельства; `metrics` несёт его в `label`
# (числа нет ⇒ `baseline_pending` с причиной, а НЕ отсутствие строки — ради этого приём и взят).
CLOSURE_ENTRY_KEYS = {"items": ("id", "status", "evidence_class", "evidence"),
                      "gates": ("id", "status", "evidence_class", "evidence"),
                      "metrics": ("name", "value", "label")}
CLOSURE_LIST_KEYS = ("items", "gates", "metrics", "limitations", "external_side_effects")


def _closure_report_path(plan_dir, phase_id):
    """Дом отчёта закрытия — `plans/<PLAN-ID>/closure/<Pn>.json` (D42)."""
    return Path(plan_dir) / CLOSURE_DIR_NAME / f"{phase_id}.json"


def _closure_load(report_path, diag):
    """Читает отчёт закрытия; любой отказ НАЗЫВАЕТ файл и причину (рамка переноса:
    fail-closed без имени объекта запрещён — findings §8.3 issue #19). None = не разобран."""
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        diag.error(report_path, None, f"отчёт закрытия не читается: {error}")
        return None
    except json.JSONDecodeError as error:
        diag.error(report_path, None, f"отчёт закрытия не разбирается как JSON: {error}")
        return None
    if not isinstance(data, dict):
        diag.error(report_path, None,
                   f"отчёт закрытия: ожидался объект схемы v{CLOSURE_SCHEMA_VERSION}, "
                   f"получен {type(data).__name__}")
        return None
    return data


def _closure_lint_schema(data, report_path, plan_id, phase_id, diag):
    """Проверка 1 — схема v1: отсутствие ключа = ОШИБКА СХЕМЫ, а не «нет данных»
    («нет данных» выражается ЗНАЧЕНИЕМ — `baseline_pending` с причиной, D42).
    Проверка 3 — `evidence_class: "real"` при пустом `evidence` = ERROR с id записи."""
    for key in CLOSURE_REQUIRED_KEYS:
        if key not in data:
            diag.error(report_path, None, f"отчёт закрытия: нет обязательного ключа «{key}»")
    if data.get("schema_version") != CLOSURE_SCHEMA_VERSION:
        diag.error(report_path, None,
                   f"отчёт закрытия: schema_version «{data.get('schema_version')}» ≠ "
                   f"{CLOSURE_SCHEMA_VERSION} (иных версий схемы не существует)")
    for key, expected in (("plan", plan_id), ("phase", phase_id)):
        if key in data and data.get(key) != expected:
            diag.error(report_path, None,
                       f"отчёт закрытия: «{key}» = «{data.get(key)}» ≠ фактическому «{expected}»")
    for key, subkeys in (("closed_by", CLOSURE_CLOSED_BY_KEYS), ("git", CLOSURE_GIT_KEYS),
                         ("inputs_sha256", ())):
        value = data.get(key)
        if key in data and not isinstance(value, dict):
            diag.error(report_path, None,
                       f"отчёт закрытия: «{key}» — ожидался объект, получен {type(value).__name__}")
            continue
        for subkey in subkeys:
            if isinstance(value, dict) and subkey not in value:
                diag.error(report_path, None,
                           f"отчёт закрытия: нет обязательного ключа «{key}.{subkey}»")
    if isinstance(data.get("inputs_sha256"), dict) and not data["inputs_sha256"]:
        diag.error(report_path, None,
                   "отчёт закрытия: «inputs_sha256» пуст — потребитель (plan-audit) ловит по "
                   "нему правку ТЗ фазы после закрытия; хеш без потребителя не пишем, "
                   "потребителя без хеша — тем более")
    for key in CLOSURE_LIST_KEYS:
        if key in data and not isinstance(data[key], list):
            diag.error(report_path, None,
                       f"отчёт закрытия: «{key}» — ожидался список, получен "
                       f"{type(data[key]).__name__}")
    for key, entry_keys in CLOSURE_ENTRY_KEYS.items():
        for pos, entry in enumerate(data.get(key) if isinstance(data.get(key), list) else []):
            if not isinstance(entry, dict):
                diag.error(report_path, None,
                           f"отчёт закрытия: «{key}[{pos}]» — ожидался объект, получен "
                           f"{type(entry).__name__}")
                continue
            name = entry.get("id") or entry.get("name") or f"{key}[{pos}]"
            for subkey in entry_keys:
                if subkey not in entry:
                    diag.error(report_path, None,
                               f"отчёт закрытия: «{key}» запись «{name}» без ключа «{subkey}»")
            # Носитель класса и носитель ДОКАЗАТЕЛЬСТВА различаются по виду записи:
            # items/gates несут `evidence_class` + `evidence` (команда и её вывод),
            # metrics — `label` + `value` (само число). Пустое доказательство при классе
            # `real` = fail-closed: это либо `synthetic`, либо `baseline_pending` с причиной.
            klass_key, proof_key = (("label", "value") if key == "metrics"
                                    else ("evidence_class", "evidence"))
            klass = entry.get(klass_key)
            if klass_key in entry and klass not in CLOSURE_EVIDENCE_CLASSES:
                diag.error(report_path, None,
                           f"отчёт закрытия: «{key}» запись «{name}»: {klass_key} «{klass}» вне "
                           f"enum'а {list(CLOSURE_EVIDENCE_CLASSES)}")
            if klass == "real" and _is_empty(str(entry.get(proof_key, "") or "")):
                diag.error(report_path, None,
                           f"отчёт закрытия: «{key}» запись «{name}» заявлена "
                           f"«real» с пустым {proof_key} — класс real требует команду и её вывод "
                           f"(иначе это synthetic либо baseline_pending с причиной)")


def _closure_lint_correspondence(data, report_path, phase_id, parsed_phase, board_row, diag):
    """Проверка 4 — `items[]` ↔ строки `## Phase Status` фазы (лишний/недостающий id либо
    иной статус); проверка 5 — `phase_status` ↔ строка фазы в Status Board (`plan.md`).
    Обе — на УЖЕ распарсенных таблицах: отдельного обхода дерева гейт не делает."""
    if board_row is not None:
        board_status = board_row[0].get("Status", "")
        if "phase_status" in data and data.get("phase_status") != board_status:
            diag.error(report_path, None,
                       f"отчёт закрытия: phase_status «{data.get('phase_status')}» ≠ статусу "
                       f"фазы {phase_id} в Status Board «{board_status}»")
    if parsed_phase is None:
        return  # файла фазы нет — отдельная диагностика уже выдана, дублировать нечем
    table = {row.get("ID"): row.get("Status", "")
             for row, _ in parsed_phase.get("status_table", [])}
    reported = {}
    for entry in (data.get("items") if isinstance(data.get("items"), list) else []):
        if isinstance(entry, dict) and entry.get("id"):
            reported[entry["id"]] = entry.get("status")
    for item_id in sorted(set(reported) - set(table)):
        diag.error(report_path, None,
                   f"отчёт закрытия: item «{item_id}» есть в items[], но нет строки в "
                   f"«## Phase Status» фазы {phase_id}")
    for item_id in sorted(set(table) - set(reported)):
        diag.error(report_path, None,
                   f"отчёт закрытия: item «{item_id}» есть в «## Phase Status» фазы "
                   f"{phase_id}, но отсутствует в items[]")
    for item_id in sorted(set(table) & set(reported)):
        if reported[item_id] != table[item_id]:
            diag.error(report_path, None,
                       f"отчёт закрытия: item «{item_id}»: status «{reported[item_id]}» ≠ "
                       f"статусу в «## Phase Status» «{table[item_id]}»")


def _lint_closure_reports_81(plan_dir, plan_id, meta, phases, board_by_phase, diag):
    """2026.07.25-ECO-OPT P8.1/D42, все пять проверок отчёта закрытия. Активация — opt-in Meta-поле
    `Closure Protocol | v1`: без него функция молчит целиком (аддитивность). Проверка 2 —
    фаза терминальна, поле включено, файла нет → ERROR с ОЖИДАЕМЫМ ПУТЁМ (fail-closed
    называет объект). Нетерминальная фаза отчёта не обязана иметь; но ЕСЛИ файл лежит —
    он разбирается по той же схеме (иначе включённый протокол молча пропускал бы мусор)."""
    plan_md = Path(plan_dir) / "plan.md"
    declared, meta_lineno = (meta or {}).get(CLOSURE_META_FIELD, (None, None))
    if declared is None:
        return
    declared = declared.strip()
    if declared != CLOSURE_PROTOCOL_V1:
        diag.error(plan_md, meta_lineno,
                   f"Meta «{CLOSURE_META_FIELD}»: значение «{declared}» — единственное "
                   f"легальное «{CLOSURE_PROTOCOL_V1}» (канон plan-protocol §8)")
        return
    for phase_id in sorted(set(phases) | set(board_by_phase)):
        report_path = _closure_report_path(plan_dir, phase_id)
        board_row = board_by_phase.get(phase_id)
        board_status = board_row[0].get("Status", "") if board_row else ""
        if not report_path.is_file():
            if board_status in TERMINAL_STATUSES:
                diag.error(plan_md, board_row[1] if board_row else None,
                           f"фаза {phase_id} терминальна («{board_status}») при "
                           f"`{CLOSURE_META_FIELD} | {CLOSURE_PROTOCOL_V1}`, но отчёта "
                           f"закрытия нет — ожидается файл {report_path}")
            continue
        data = _closure_load(report_path, diag)
        if data is None:
            continue
        _closure_lint_schema(data, report_path, plan_id, phase_id, diag)
        _closure_lint_correspondence(data, report_path, phase_id, phases.get(phase_id),
                                     board_row, diag)


# --- 2026.07.25-ECO-OPT P8.2/D103-D105: `Consequences` в D-записи (research/11 §2, research/23) ---
# Носитель — инлайн-подполе `**Consequences:**` внутри ячейки `Решение` (пятая колонка
# отклонена: шапка D-лога — литерал реестра CANON_LITERALS, её правка = переписывание
# шапки во всех планах флота, D43). Гейт — ОПТ-IN ДВАЖДЫ (та же дисциплина, что у
# `_lint_closure_reports_81`): (1) Meta-поле `Closure Protocol | v1`, (2) `Дата` D-записи
# ≥ CONSEQUENCES_CANON_DATE (forward-only — механика WRITE_SITE_CODES_CANON_DATE выше,
# И10: непарсимая/отсутствующая дата = вне скоупа, МОЛЧАНИЕ). Дата константы —
# ДЕНЬ ПОСЛЕ последней существующей записи без `Consequences` (D98, ECO-OPT
# 2026-07-27) — измерено `research/23-P8.2-refine-2026-07-27.md` §2: без даты гейт
# закрылся бы красным собственным планом (D98 нет носителя и бэкфилл ЗАПРЕЩЁН, §2).
CONSEQUENCES_CANON_DATE = "2026-07-28"
CONSEQUENCES_LITERAL = "**Consequences:**"
# Префиксный ISO-матч ячейки `Дата` (не барный `==`, D103 §2): FOREMAN D7 несёт
# `2026-07-18 (финализирован P0.4)` — суффикс после даты легален, а строгий полный
# матч читал бы это как непарсимое и терял смысл прецедента.
CONSEQUENCES_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
# Предикат отмены/замены решения — ИЗМЕРЕННЫЙ (research/23 §1), не переписанный со
# спеки дословно: спека (`supersedes D`/`отменён`/`отменяет D`) ловит НОЛЬ записей на
# ECO-OPT (краткое причастие склоняется, «ё» факультативна — D98 несёт форму
# «отменена»); широкий стем `отмен` (любая форма) даёт 6 срабатываний, 4 из них —
# ОТРИЦАНИЕ «не отменяет»/«не отменена» (ложный ERROR). Негативный lookbehind
# `(?<!не )` СНИМАТЬ НЕЛЬЗЯ: без него 4 из 6 срабатываний на этом же плане ложные
# (D11/D19/D26 и др., research/23 §1). Стем-лист держать УЗКИМ — три семантики, не
# десять слов (Code Guidance 2026.07.25-ECO-OPT P8.2): каждый лишний стем — риск ложного ERROR на сотнях
# планов флота.
CONSEQUENCES_STEMS_RE = re.compile(
    r"supersedes D|отменяет D|(?<!не )отмен(?:ён|ен|ена|ено|ены)\b")


def _lint_consequences_82(plan_dir, plan_id, meta, plan_lines, plan_md, diag):
    """2026.07.25-ECO-OPT P8.2/D103-D105: ячейка `Решение` строки `## 5. Decision Log`, матчащая
    CONSEQUENCES_STEMS_RE (отмена/замена решения) и датированная (`Дата`) ≥
    CONSEQUENCES_CANON_DATE, обязана нести `**Consequences:**` — иначе ERROR с
    номером D-записи (fail-closed называет объект). Активация — ДВОЙНОЙ opt-in:
    без Meta `Closure Protocol | v1` функция молчит целиком (аддитивность, тест).

    Честная граница (Code Guidance P8.2, обязана быть написана вслух и здесь):
    канон требует `Consequences` у КАЖДОЙ несущей D-записи; эта проверка ловит только
    МАШИННО-ДЕТЕКТИРУЕМЫЙ подкласс — запись, явно объявляющую отмену/замену другого
    решения тремя измеренными формами выше. Полное покрытие канона гейт не даёт и
    не заявляет (findings/rayt-deep-2026-07-25.md §9.4 — формализм галочки)."""
    declared, _ = (meta or {}).get(CLOSURE_META_FIELD, (None, None))
    if declared is None or declared.strip() != CLOSURE_PROTOCOL_V1:
        return

    try:
        is_v2 = plan_layout.layout_version(plan_dir) == "v2"
    except plan_layout.PlanLayoutError:
        is_v2 = False
    if is_v2:
        try:
            pattern = plan_layout.carrier_glob(plan_dir, "decision-record")
        except plan_layout.PlanLayoutError:
            return
        for decision_path in sorted(pattern.parent.glob(pattern.name)):
            if not decision_path.is_file():
                continue
            try:
                fields, body = plan_decisions.parse_frontmatter(
                    decision_path.read_text(encoding="utf-8"), path=decision_path)
            except (OSError, plan_decisions.DecisionError):
                continue  # parse_decision/projector own malformed-record diagnostics.
            decision_id = fields.get("id", decision_path.stem.split("-", 1)[0])
            date = fields.get("date", "")
            if (not isinstance(date, str) or date < CONSEQUENCES_CANON_DATE
                    or not CONSEQUENCES_STEMS_RE.search(body)):
                continue
            if not re.search(r"^##\s+Consequences\s*$", body, re.MULTILINE):
                diag.error(decision_path, 1,
                           f"Decision Log {decision_id}: маркер отмены/замены решения "
                           f"без `{CONSEQUENCES_LITERAL}` (канон plan-protocol §6, forward-only "
                           f"с {CONSEQUENCES_CANON_DATE}, D103)")
        return

    _, dl_body, dl_start = _find_section(plan_lines, DECISION_LOG_HEADER_RE)
    if dl_body is None:
        return
    _, rows, _ = _parse_table(dl_body, dl_start)
    for row, lineno in rows:
        decision = row.get("Решение", "") or ""
        if not CONSEQUENCES_STEMS_RE.search(decision):
            continue
        date_match = CONSEQUENCES_DATE_PREFIX_RE.match((row.get("Дата", "") or "").strip())
        if not date_match or date_match.group(1) < CONSEQUENCES_CANON_DATE:
            continue  # непарсимая/старая дата — вне скоупа, МОЛЧАНИЕ (И10, forward-only)
        if CONSEQUENCES_LITERAL not in decision:
            diag.error(plan_md, lineno,
                       f"Decision Log {row.get('D#', '?')}: маркер отмены/замены решения "
                       f"без `{CONSEQUENCES_LITERAL}` (канон plan-protocol §6, forward-only "
                       f"с {CONSEQUENCES_CANON_DATE}, D103)")


# --- 2026.07.25-ECO-OPT P8.3/D44: `CHECKPOINTED` — отказ несёт точную команду возобновления ------
# Носитель — строка `Возобновление: <команда>` в поле `Pending Work` item'а (НЕ седьмой
# статус, НЕ семнадцатое поле — оба варианта отклонены D44, ломают контракт трёх живых
# планов/`plans/cross-plan-files.py`). Активация — тот же opt-in, что у 2026.07.25-ECO-OPT P8.1/P8.2:
# Meta-поле `Closure Protocol | v1` (без даты-канона — на дату детализации в этом плане
# живых 🔴/⛔ items с включённым протоколом нет, задним числом красить нечего).
STATUS_SKIPPED = "⛔ Skipped by decision"
RESUME_LITERAL = "Возобновление:"
RESUME_LINE_RE = re.compile(r"^Возобновление:\s*(.*)$")
D_REF_RE = re.compile(r"\bD\d+\b")


def _find_resume_line(pending_work):
    """Ищет строку `Возобновление: …` в поле Pending Work — построчно (та же дисциплина,
    что `_write_site_canonical_codes`), markdown-обёртка (`-`/`>`/`` ` ``/`**`) срезается
    ДО матча. Возвращает значение ПОСЛЕ двоеточия (обрезанное) либо `None`, если строки нет."""
    for raw_line in (pending_work or "").replace("`", "").splitlines():
        line = raw_line.replace("*", "").strip()
        while line[:1] in ("-", ">"):
            line = line[1:].strip()
        m = RESUME_LINE_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def _lint_checkpointed_83(meta, items, path, diag):
    """2026.07.25-ECO-OPT P8.3/D44: item со статусом `🔴 Blocked` обязан нести в Pending Work непустую
    строку `Возобновление: <команда>` (форма `Возобновление: — (внешний блокер: …)` —
    легальное «непусто» для блокера без локального шага, Code Guidance P8.3); item со
    статусом `⛔ Skipped by decision` обязан нести РОВНО `Возобновление: —` И ссылку
    `D<номер>` в том же поле (решение о пропуске предъявляется записью, не молчанием)."""
    declared, _ = (meta or {}).get(CLOSURE_META_FIELD, (None, None))
    if declared is None or declared.strip() != CLOSURE_PROTOCOL_V1:
        return
    for item_id, occurrences in items.items():
        item = occurrences[0]
        status_val, _ = item["fields"].get("Status", ("", item["header_lineno"]))
        if status_val not in (STATUS_BLOCKED, STATUS_SKIPPED):
            continue
        pw_val, pw_lineno = item["fields"].get("Pending Work", ("", item["header_lineno"]))
        resume = _find_resume_line(pw_val)
        if status_val == STATUS_BLOCKED:
            if resume is None or _is_empty(resume):
                diag.error(path, pw_lineno,
                           f"item {item_id}: {STATUS_BLOCKED} без строки "
                           f"`{RESUME_LITERAL} <команда>` в Pending Work — отказ обязан "
                           f"нести точную команду продолжения, а не «пропущено» (D44)")
        else:
            has_d_ref = bool(D_REF_RE.search(pw_val or ""))
            if resume is None or resume != EMPTY_PLACEHOLDER or not has_d_ref:
                diag.error(path, pw_lineno,
                           f"item {item_id}: {STATUS_SKIPPED} без `{RESUME_LITERAL} "
                           f"{EMPTY_PLACEHOLDER}` и ссылки `D<номер>` в Pending Work — "
                           f"решение о пропуске обязано быть предъявлено D-записью (D44)")


# --- 2026.07.25-ECO-OPT P11.3/D129: кросс-документный чек `handoff.md` ↔ «## 4. Phase Index
# & Status Board» (F8 аудита P9: handoff соврал `P9 4/4`, доска несла `2/4`, права доска).
# Дом — plan_lint.py, не verify-citations.py (D129): это согласованность двух секций ОДНОГО
# плана, не резолв пути/цитаты — обратное решение размыло бы оба инструмента (`research/27-…`
# §2.4, Scope Excluded P10.2 остаётся в силе). Forward-only по ДАТЕ ЗАГОЛОВКА handoff'а
# (та же дисциплина, что WRITE_SITE_CODES_CANON_DATE/CONSEQUENCES_CANON_DATE): handoff старше
# канон-даты не диагностируется вовсе, даже WARNING (И10 — не красим существующий флот задним
# числом). Severity внутри скоупа — как у launch-block-гейта (D-канон 2.0): датовый `plan_id`
# от BRIEF_CANON_DATE → ERROR, легаси → WARNING (`plan_id[:10]` — дата, не handoff-дата).
HANDOFF_BOARD_CANON_DATE = "2026-07-28"
HANDOFF_TITLE_DATE_RE = re.compile(r"^#\s+HANDOFF\s+—\s*(\d{4}-\d{2}-\d{2})\s+—")
# Узкий шаблон намеренно (Code Guidance P11.3, анти-самообман): РОВНО `Pn a/b` — не «33/44»,
# не проценты, не голая проза «закрыто 4 из 4». Замер (`findings/P11-citation-gate-
# measurements.md` §4) — 3 вхождения на трёх живых планах, 1 расхождение (F8), 0 ложных;
# расширение на прозу вернуло бы шум, который узость сегодня держит на нуле.
HANDOFF_BOARD_REF_RE = re.compile(r"\bP(\d+)\s+(\d+)/(\d+)\b")


def _lint_handoff_board_113(handoff, handoff_path, plan_id, board_by_phase, diag):
    """2026.07.25-ECO-OPT P11.3/D129: каждое вхождение `Pn a/b` в handoff.md обязано совпадать
    со значением колонки `STATUS_BOARD_ITEMS_COL` строки `Pn` доски «## 4. Phase Index &
    Status Board»; расхождение — диагностика, называющая ОБЕ стороны. Фаза `Pn`, отсутствующая
    в доске, — «висячая ссылка». Непарсимая/более старая дата заголовка handoff'а — МОЛЧАНИЕ
    (forward-only, аддитивность И10), не ERROR/WARNING."""
    if not handoff:
        return
    title_lineno = handoff.get("title_lineno")
    lines = handoff.get("lines") or []
    if not title_lineno or title_lineno > len(lines):
        return
    date_m = HANDOFF_TITLE_DATE_RE.match(lines[title_lineno - 1])
    if not date_m or date_m.group(1) < HANDOFF_BOARD_CANON_DATE:
        return
    report = (diag.error if (PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE)
              else diag.warning)
    for i, ln in enumerate(lines):
        for m in HANDOFF_BOARD_REF_RE.finditer(ln):
            phase_id = f"P{m.group(1)}"
            handoff_ratio = f"{m.group(2)}/{m.group(3)}"
            row = board_by_phase.get(phase_id)
            if row is None:
                report(handoff_path, i + 1,
                       f"handoff.md: «{phase_id} {handoff_ratio}» ссылается на фазу «{phase_id}», "
                       f"отсутствующую в «## 4. Phase Index & Status Board» (висячая ссылка)")
                continue
            board_ratio = row[0].get(STATUS_BOARD_ITEMS_COL, "")
            if board_ratio != handoff_ratio:
                report(handoff_path, i + 1,
                       f"handoff.md:{i + 1} говорит «{phase_id} {handoff_ratio}», доска «## 4. "
                       f"Phase Index & Status Board» несёт «{phase_id} {board_ratio}» "
                       f"(расхождение)")


# --- 2026.07.13-PLAN-PROTOCOL-GAP P2.16/D35: реестр непереводимых литералов (H3) ---------------------------
# ЕДИНСТВЕННЫЙ источник строк, которые линтер сверяет с ТЕКСТОМ ПЛАНА байт-в-байт.
# Дисциплина (гейт — tests/test_canon_literals.py):
#   * `CANON_LITERALS` — строка, которую протокол ТРЕБУЕТ писать дословно (шапки таблиц,
#     маркеры, формы `Next`). Агент флота берёт её из EN-канона `SKILL.md` ⇒ каждая обязана
#     нести директиву `<!-- i18n-keep: … -->` в EN-only `SKILL.md`.
#     Тест T2 сверяет реестр с директивами напрямую.
#   * `HEURISTIC_LITERALS` — ДЕТЕКТОРЫ НАМЕРЕНИЯ в свободной прозе (стеммы, регистронезависимо):
#     автор их дословно не пишет, EN-канон их не несёт и нести не обязан ⇒ директив у них нет.
#   * Тест T1 (AST-обход этого файла) не даёт завести кириллическую сверку МИМО обоих реестров —
#     ровно так выпал `план закрыт` (H3: инлайн-строка без константы, гейт литералов к ней слеп).
# Диагностические сообщения (`diag.error`/`diag.warning`) — НЕ литералы сверки: они не грепаются
# по тексту плана, в реестр не входят. `EMPTY_PLACEHOLDER` («—») сверяется, но директиву не
# получает (H13: em dash есть в любом EN-тексте — контракта такая директива не даёт).
LITERAL_PLAN_CLOSED = "план закрыт"  # форма `Next` целиком закрытого плана (SKILL §8)
LITERAL_PHASE_HANDOFF_STALE = "> УСТАРЕЛ — фаза реопенена"  # маркер инвалидации (SKILL §3, D34)
# --- scope-payload launch-block'а, несущего находки (SKILL §8, D-канон 2026-07-17) ---
# Вердикт блока `## Audit Pn`: значения латиницей (RED/ATTENTION/GREEN) — переводу не
# подлежат by nature, директив не требуют; кириллична только сама шапка поля.
LITERAL_AUDIT_VERDICT = "Вердикт:"
AUDIT_VERDICT_RE = re.compile(LITERAL_AUDIT_VERDICT + r"\s*\**\s*(RED|ATTENTION|GREEN)\b")
# Вердикты, чей launch-block ПЕРЕДАЁТ находки следующей сессии ⇒ обязан нести scope-payload.
# GREEN находок не несёт — с него payload не требуем (иначе маркеры выродятся в ритуал).
AUDIT_FINDINGS_VERDICTS = ("RED", "ATTENTION")
# Четыре обязательные строки payload'а. Порядок в каноне фиксирован, гейт проверяет
# ПРИСУТСТВИЕ (содержательность `СКОУП:`/`НЕ ТРОГАТЬ:` машина не меряет — это report-quality).
SCOPE_PAYLOAD_MARKERS = ("РЕЖИМ:", "ВХОД:", "СКОУП:", "НЕ ТРОГАТЬ:")
CANON_LITERALS = (
    "Поле | Значение",                                        # шапка Meta (plan.md §0)
    "Items 🟢/всего",                                          # колонка Status Board (§4)
    "D# | Дата | Решение | Почему",                           # шапка Decision Log (§5)
    "Дата | Кто (role/model) | Что",                          # шапка Update Log (§6)
    "Контракт | Версия | Статус | Потребители | Уведомлены",   # шапка Contracts/Exported (§7)
    "Контракт | Донор-план | Pinned | Замечено | Реакция",     # шапка Contracts/Consumed (§7)
    "> СКЕЛЕТ — не детализирован",                            # маркер фазы-скелета (§5)
    MANUAL_RUN_MARKER,                                        # «ЗАПУСК ВРУЧНУЮ» — Exec=manual (§9)
    "[NEEDS CLARIFICATION",                                   # маркер неоднозначности (§7)
    "RAG:✅",                                                  # enum RAG-маркеров (§7, D29)
    "RAG:" + EMPTY_PLACEHOLDER,
    "[UNVERIFIED]",
    LITERAL_PLAN_CLOSED,
    LITERAL_PHASE_HANDOFF_STALE,
    LITERAL_WAITING,                                          # форма `Next` «ОЖИДАНИЕ» (SKILL §8, D8)
    LITERAL_AUDIT_VERDICT,                                    # шапка вердикта `## Audit Pn` (§8)
    *SCOPE_PAYLOAD_MARKERS,                                   # scope-payload launch-block'а (§8)
    "pre_mutation:",                                          # write-site код границы (§8, 2026.07.24-AGENT-RELIABILITY P4.4/D91)
    "pre_final:",                                             # write-site код границы (§8, P4.4/D91)
    "write-site:",                                            # каноническая строка (§8, 2026.07.25-ECO-OPT P10.1/D102:
                                                               # T1 латиницу не ловит, регистрация решением)
    CLOSURE_META_FIELD,                                       # Meta-поле активации отчёта закрытия
                                                               # (§8, 2026.07.25-ECO-OPT P8.1/D42: латиница — та же
                                                               # регистрация решением, что у write-site:)
    CONSEQUENCES_LITERAL,                                     # §6, 2026.07.25-ECO-OPT P8.2/D103-D105: латиница — та же
                                                               # регистрация решением, T1 её не ловит
    RESUME_LITERAL,                                           # §6, 2026.07.25-ECO-OPT P8.3/D44: кириллица — обязательна
                                                               # i18n-директива в EN-only SKILL.md
    "Команда",                                                # строка таблицы launch-block'а (§8, P5.8/LAUNCH_COMMAND_ROW_RE)
)
# --- 2026.07.15-PLANFLOW-UX P2.1/D8: C2-детектор прозы-оговорки в объявлении `Next` (WARNING) ----------
# Автор пишет runnable slash-форму «команда есть, но не сейчас» вместо структурной формы
# «ОЖИДАНИЕ: <условие> → <целевая форма>» (recon §3.2, живой SKM-MASTER-002). Стем-лист
# УЗКИЙ и финализирован по замеру ДЕЛЬТЫ флота (§8 D53), не «на глаз»: каждый лишний стем —
# риск ложного WARNING на сотнях handoff'ов (зеркало D34). Сканируется только СТРОКА-ОБЪЯВЛЕНИЕ
# (`next_decl`), НЕ весь launch-block: guard-строка `# НЕ раньше:` законно живёт в code-block'е.
C2_WAITING_STEMS = ("не раньше", "делать нечего", "тайм-гейт", "time-gate")
C2_WAITING_STEMS_RE = re.compile(
    "|".join(re.escape(s) for s in C2_WAITING_STEMS), re.IGNORECASE)
# Формы Next, несущие исполнимую slash-команду СЕЙЧАС (не waiting/manual/closed) — только на
# них C2 срабатывает: прозаическая оговорка при runnable-команде и есть анти-паттерн.
C2_RUNNABLE_KINDS = frozenset({"exec", "run", "design-item", "design-phase", "audit",
                               "audit-design", "close", "close-archive"})

# Якоря `--conflicts` (P5.9 + D79 EN-only) грепаются в каноническом `SKILL.md`.
# Эти стабильные English anchors связывают прозу с реестрами реализации.
CONFLICTS_ANCHOR_STATUSES = "EXACTLY 6 canonical strings"
CONFLICTS_ANCHOR_ITEM_FIELDS = "`**Field:** value`, in this order:"
CONFLICTS_ANCHOR_NEXT_FORMS = "| Форма Next | Когда |"
CONFLICTS_ANCHOR_CONTEXT = "EXACTLY one of three values"
CONFLICTS_ANCHOR_LAUNCH_TABLE = "| Параметр | Значение |"

# Эвристики: `оркестрац`/`мультиагент` — детект заявленной оркестрации (ORCHESTRATION_MARKER_RE,
# D29); `PHASE_HANDOFF_CLOSURE_LITERALS` — детект «блок утверждает закрытие фазы» (D34);
# `PHASE_HANDOFF_NEGATION_LITERALS` — детект отрицания в том же утверждении (D50); C2-стемы
# (кириллические) — детект прозы-оговорки в `Next` (D8); CONFLICTS_ANCHOR_* — см. комментарий
# выше. Все группы ищут СМЫСЛ в прозе автора/канона, а не канонический токен для стороннего
# читателя ⇒ присутствие в EN не требуется (i18n-keep не нужен).
HEURISTIC_LITERALS = (("оркестрац", "мультиагент") + PHASE_HANDOFF_CLOSURE_LITERALS
                      + PHASE_HANDOFF_NEGATION_LITERALS
                      + ("не раньше", "делать нечего", "тайм-гейт", "Обсуждение")
                      + (CONFLICTS_ANCHOR_STATUSES, CONFLICTS_ANCHOR_ITEM_FIELDS,
                         CONFLICTS_ANCHOR_NEXT_FORMS, CONFLICTS_ANCHOR_CONTEXT,
                         CONFLICTS_ANCHOR_LAUNCH_TABLE)
                      # 2026.07.25-ECO-OPT P8.2/D103-D105: стемы CONSEQUENCES_STEMS_RE — детектор НАМЕРЕНИЯ
                      # (отмена/замена решения) в свободной прозе D-лога; EN-канон их не
                      # несёт и нести не обязан (research/23 §3).
                      + ("отменяет", "отменён", "отменен", "отменена", "отменено", "отменены"))

__all__ = tuple(name for name in globals() if not name.startswith("__"))
