"""plan_reader — очередь исполнения ОДНОЙ фазы плана для драйвера exec-волны
(P4.2, `root/contracts/driver-plan-protocol-v2.md` §2/§3).

Три источника фактов читаются ПРОЦЕССОМ (D29 — межпакетная граница: Python-импорт
пакета `task` из этого модуля и склейка `sys.path` к его `lib`-каталогу запрещены):
    S1 — модель плана целиком:  `python3 packages/task/scripts/plan-lint.py <dir> --json`
    S2 — маршрут item'а:        `python3 -m task.task_contract build --plan-dir <dir> --item <id>`
Собственный разбор (S4/S5, §3.1/§3.2 контракта) заведён РОВНО на две точки, у которых
готового читателя в репозитории нет ни одного:
    S4 — ячейка `Exec` строки `## 3. Routing` (зеркалит `task_contract._find_routing_row`);
    S5 — префиксный токен формы `**Next:**` (закрытый enum 11 форм, D40 — только
         семантический префикс; исторические `/task:…`-входы совместимости S5 не
         резолвит — контракт §3.2 явно ограничивает разбор ТОЛЬКО префиксным токеном).

Функции чистые (path in → dict out): ни `print`, ни `sys.exit`, ни записи на диск —
печать и коды возврата принадлежат CLI (P4.6). stdlib-only."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from core import find_monorepo_root

# --- закрытый набор причин отказа вождения (Deliverables P4.2) ----------------
EXEC_NOT_PLAN_EXEC = "EXEC-NOT-PLAN-EXEC"
ROUTING_INCONSISTENT = "ROUTING-INCONSISTENT"
ROUTING_UNRESOLVED = "ROUTING-UNRESOLVED"
NEXT_FORM_UNSUPPORTED = "NEXT-FORM-UNSUPPORTED"
PLAN_UNREADABLE = "PLAN-UNREADABLE"
ITEM_TERMINAL = "ITEM-TERMINAL"

# §4.1 контракта — шесть канонических статусов; терминальные для очереди драйвера —
# ровно те три, что `plan_lint.TERMINAL_STATUSES` считает закрытием item'а.
TERMINAL_STATUSES = ("🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision")

# §9 канона (frozen ladder) — используется РОВНО в одну сторону: не для деривации
# права вождения (D31 запрещает), а для детекта ROUTING-INCONSISTENT (Exec=plan-exec
# при паре, деривация которой даёт manual). Байт-в-байт `task_contract.MODEL_CLASS_ORDER`
# / `EFFORT_ORDER` (task_contract.py:46-47) — свой второй носитель этих же литералов не
# заводится, но и импорт `task.*` запрещён (D29), поэтому значения скопированы явно.
MODEL_CLASS_ORDER = ("economy", "implementation", "frontier")
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max")

# --- §3.1 контракта — S4, зеркало `task_contract._find_routing_row` -----------
# (task_contract.py:92-93, :177, :268-303): тот же заголовок секции, тот же матчер
# ячейки `Items` (равенство `Pn.m` либо диапазон одной фазы), тот же диагностичный
# (не route-дающий) отказ на списке через запятую.
_SECTION_HEADER_RE = re.compile(r"^##\s+\S.*$")
_ROUTING_HEADER_RE = re.compile(r"^##\s+3\.\s+Routing\s*$")
_ROUTING_RANGE_RE = re.compile(r"^(P\d+)\.(\d+)\s*[–-]\s*(P\d+)\.(\d+)$")
_ROUTING_ITEMS_HEADER = "Items"
_ROUTING_EXEC_HEADER = "Exec"

# --- §3.2 контракта — S5, только префиксный токен `plan_lint.SEMANTIC_NEXT_RE`
# (plan_lint.py:127-129). Легаси-входы совместимости (`/task:…`, «ЗАПУСК ВРУЧНУЮ»,
# «ОЖИДАНИЕ:») НЕ резолвятся — граница разбора названа контрактом явно, догадка о
# них здесь была бы третьей неоправданной точкой собственного парсинга.
_NEXT_FORM_RE = re.compile(
    r"^(exec-items|run-items|audit-design|design-phase|design-item|audit-phase|close|archive|"
    r"terminal|manual|waiting):")


def _read_plan_lines(path):
    """`plan.md` построчно (без `\\n`), как `plan_lint._read_lines`. `None` — файл
    отсутствует/не читается (вызывающий обязан отнестись к этому как к отказу, не
    как к пустой секции)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text.replace("\r\n", "\n").split("\n")


def _split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _routing_table(plan_lines):
    """`## 3. Routing` → (headers, rows) с rows: `[(row_dict, lineno), ...]`; `(None,
    None)` если секции или таблицы в ней нет. Тот же генерический разбор markdown-
    таблицы, что `plan_lint._find_section`/`_parse_table` (не второй формат, тот же
    самый — переписанный здесь байт-в-байт по алгоритму, потому что импорт запрещён,
    D29)."""
    header_idxs = [i for i, ln in enumerate(plan_lines) if _SECTION_HEADER_RE.match(ln)]
    body = None
    for idx in header_idxs:
        if _ROUTING_HEADER_RE.match(plan_lines[idx]):
            following = [i for i in header_idxs if i > idx]
            end = following[0] if following else len(plan_lines)
            body = plan_lines[idx + 1:end]
            break
    if body is None:
        return None, None

    table_start = None
    for i, ln in enumerate(body):
        if ln.strip().startswith("|"):
            table_start = i
            break
    if table_start is None:
        return None, None

    headers = _split_row(body[table_start])
    rows = []
    i = table_start + 2  # table_start+1 — строка-разделитель `---|---`
    while i < len(body) and body[i].strip().startswith("|"):
        cells = _split_row(body[i])
        row = {headers[j]: (cells[j] if j < len(cells) else "") for j in range(len(headers))}
        rows.append((row, i))
        i += 1
    return headers, rows


def _row_covers_item(cell, item_id, phase_token, item_n):
    """Ровно ДВЕ легальные формы ячейки `Items` (canon §9): равенство `Pn.m` либо
    диапазон одной фазы `Pn.a–Pn.b` (оба вида тире). Список через запятую сюда не
    попадает — он проверяется отдельно, только для ДИАГНОСТИКИ отказа."""
    if cell == item_id:
        return True
    m = _ROUTING_RANGE_RE.match(cell)
    return bool(m and item_n is not None and m.group(1) == phase_token == m.group(3)
                and int(m.group(2)) <= item_n <= int(m.group(4)))


def _resolve_exec_cell(plan_lines, item_id):
    """S4 — ячейка `Exec` строки §3 Routing, покрывающей `item_id`. Возвращает
    `(value, None)` на успехе либо `(None, причина)`. Значение НЕ дериватируется из
    маршрута ни в одну сторону (D31) — это дословное чтение ячейки, право вождения
    решает вызывающий."""
    headers, rows = _routing_table(plan_lines)
    if headers is None:
        return None, "в `plan.md` нет секции «## 3. Routing» с таблицей"
    if _ROUTING_EXEC_HEADER not in headers:
        return None, "таблица «## 3. Routing» без колонки «Exec» (легаси-форма §3 без колонки)"

    phase_token = item_id.split(".")[0]
    try:
        item_n = int(item_id.split(".")[1])
    except (IndexError, ValueError):
        item_n = None

    for row, _lineno in rows:
        cell = (row.get(_ROUTING_ITEMS_HEADER, "") or "").strip().strip("`")
        if _row_covers_item(cell, item_id, phase_token, item_n):
            value = (row.get(_ROUTING_EXEC_HEADER, "") or "").strip().strip("`")
            return value, None

    for row, lineno in rows:
        cell = (row.get(_ROUTING_ITEMS_HEADER, "") or "").strip().strip("`")
        if "," in cell and any(
            _row_covers_item(t.strip().strip("`"), item_id, phase_token, item_n)
            for t in cell.split(",")
        ):
            return None, (
                f"§3 Routing строка {cell!r} (строка {lineno}) — список через запятую, "
                "нелегальная форма ячейки `Items` (canon §9): маршрут из совпавшего "
                "токена не берётся, это остаётся отказом")

    return None, f"нет строки §3 Routing, покрывающей {item_id}"


def _resolve_next_form(next_field_text):
    """S5 — форма `**Next:**` из ПЕРВОЙ непустой строки поля (D40). Возвращает
    `(kind, declaring_line)`; `kind=None`, если строка не начинается ни с одного из
    11 закрытых префиксов (легаси-входы совместимости сюда не попадают, §3.2)."""
    declaring_line = next(
        (ln.strip() for ln in (next_field_text or "").splitlines() if ln.strip()), "")
    m = _NEXT_FORM_RE.match(declaring_line)
    return (m.group(1) if m else None), declaring_line


def _call_plan_lint(plan_dir, monorepo_root, *, timeout=60):
    """S1: `python3 packages/task/scripts/plan-lint.py <plan_dir> --json` (§2 контракта,
    команда воспроизведена дословно). Ненулевой код / битый JSON / сбой запуска —
    отказ источника (fail-loud, §2: «не различаем «есть диагностики» и «сбой
    парсера» — оба класса недоступности источника»), не пустая модель."""
    script = Path(monorepo_root) / "packages" / "task" / "scripts" / "plan-lint.py"
    try:
        proc = subprocess.run(
            ["python3", str(script), str(plan_dir), "--json"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"plan-lint.py не запустился: {exc}"
    if proc.returncode != 0:
        return None, (
            f"plan-lint.py завершился кодом {proc.returncode} (fail-loud — источник "
            f"S1 недоступен, не «нечего делать»): {proc.stderr.strip()[-800:]}")
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"plan-lint.py --json не распознан как JSON: {exc}"


def _call_task_contract_build(plan_dir, item_id, monorepo_root, *, timeout=60):
    """S2: `python3 -m task.task_contract build --plan-dir <plan_dir> --item <item_id>`
    (§2 контракта), с `PYTHONPATH`, указывающим на `lib`-каталог пакета `task`
    (см. `task_lib` ниже). Возвращает
    `({"model_class", "effort"}, None)` либо `(None, причина)` — item-specific отказ,
    НЕ деградация всей очереди (S1 уже дала статус/порядок; недоступен только
    маршрут этого item'а — `ROUTING-UNRESOLVED`)."""
    task_lib = str(Path(monorepo_root) / "packages" / "task" / "lib")
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = task_lib if not existing else task_lib + os.pathsep + existing
    try:
        proc = subprocess.run(
            ["python3", "-m", "task.task_contract", "build",
             "--plan-dir", str(plan_dir), "--item", item_id],
            capture_output=True, text=True, timeout=timeout, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"task.task_contract build не запустился: {exc}"
    if proc.returncode != 0:
        return None, (f"task.task_contract build --item {item_id} завершился кодом "
                      f"{proc.returncode}: {proc.stderr.strip()[-800:]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return None, f"task.task_contract build --item {item_id}: вывод не JSON: {exc}"
    required = (payload.get("route") or {}).get("required") or {}
    model_class, effort = required.get("model_class"), required.get("effort")
    if not model_class or not effort:
        return None, (f"task.task_contract build --item {item_id}: route.required "
                      f"неполон: {required!r}")
    return {"model_class": model_class, "effort": effort}, None


def _classify_drivability(exec_value, exec_error, route, route_error):
    """Право вождения — §7 таблицы «событие → класс» + §9 канона, РОВНО в порядке:
    Exec дословно «plan-exec» (D31, деривация никогда не ДАЁТ права) → маршрут
    резолвится (S2) → деривация §9 маршрута НЕ говорит «manual» (используется ТОЛЬКО
    на отказ, ROUTING-INCONSISTENT). Любое сомнение — отказ (fail-safe)."""
    if exec_value != "plan-exec":
        detail = exec_error or f"Exec={exec_value!r} (ожидается дословно «plan-exec», D31)"
        return False, EXEC_NOT_PLAN_EXEC, detail
    if route is None:
        return False, ROUTING_UNRESOLVED, route_error or "маршрут item'а не резолвится (S2)"
    derived_manual = (
        MODEL_CLASS_ORDER.index(route["model_class"]) > MODEL_CLASS_ORDER.index("implementation")
        or EFFORT_ORDER.index(route["effort"]) > EFFORT_ORDER.index("medium")
    )
    if derived_manual:
        return False, ROUTING_INCONSISTENT, (
            f"Exec=plan-exec при {route['model_class']}/{route['effort']} — деривация §9 "
            "даёт manual (плановый дефект, драйвер его не «чинит»)")
    return True, None, None


def _degraded(plan_dir, phase_id, reason):
    return {
        "plan_dir": str(plan_dir), "phase_id": phase_id,
        "degraded": True, "degraded_reasons": [reason],
        "next_form": None, "items": [], "excluded_terminal": [],
    }


def queue(plan_dir, phase_id, *, monorepo_root=None):
    """Очередь исполнения фазы `phase_id` плана `plan_dir` — item'ы в порядке
    `## Phase Status`, терминальные исключены (`excluded_terminal` несёт их поимённо
    с `ITEM-TERMINAL`, честный знаменатель для сводки волны P4.5/P4.6), по каждому
    оставшемуся — маршрут, значение `Exec`, право вождения либо причина отказа из
    закрытого набора. `degraded=True` — источник S1 недоступен: `items=[]` в этом
    случае НЕ означает «фаза сделана», вызывающий обязан проверить сам флаг
    (анти-самообман, Code Guidance P4.2).

    `monorepo_root` — переопределение для тестов (иначе резолвится от `plan_dir`
    через `find_monorepo_root`; standalone-раскладка без `packages/task` → degraded,
    не тихий пропуск, D29)."""
    plan_dir = Path(plan_dir)
    if monorepo_root is None:
        monorepo_root = find_monorepo_root(plan_dir.resolve())
        if monorepo_root is None:
            return _degraded(plan_dir, phase_id, (
                f"монорепо-корень не найден от {plan_dir} — пакет `task` недоступен "
                "(standalone-раскладка): драйвер отказывает в вождении, а не молчит"))
    monorepo_root = Path(monorepo_root)

    data, reason = _call_plan_lint(plan_dir, monorepo_root)
    if data is None:
        return _degraded(plan_dir, phase_id, reason)

    plan_key = plan_dir.name
    plan_model = (data.get("plans") or {}).get(plan_key)
    if plan_model is None:
        return _degraded(plan_dir, phase_id,
                          f"plan-lint --json не содержит модель плана «{plan_key}»")

    phase_model = (plan_model.get("phases") or {}).get(phase_id)
    if phase_model is None:
        return _degraded(plan_dir, phase_id, f"фаза «{phase_id}» не найдена в модели плана")

    handoff = plan_model.get("handoff") or {}
    next_raw = (handoff.get("fields") or {}).get("Next", "") or ""
    next_kind, next_declaring_line = _resolve_next_form(next_raw)
    next_form = {"kind": next_kind, "declaring_line": next_declaring_line}

    plan_lines = _read_plan_lines(plan_dir / "plan.md") if next_kind is not None else None

    status_rows = phase_model.get("status_table") or []
    items_fields = phase_model.get("items") or {}

    result_items = []
    excluded_terminal = []
    for row in status_rows:
        item_id = row.get("ID")
        if not item_id:
            continue
        fields = (items_fields.get(item_id) or {}).get("fields") or {}
        status = fields.get("Status") or row.get("Status") or ""

        if status in TERMINAL_STATUSES:
            excluded_terminal.append({
                "item_id": item_id, "status": status, "refusal": ITEM_TERMINAL,
            })
            continue

        if next_kind is None:
            result_items.append({
                "item_id": item_id, "status": status,
                "route": None, "route_error": None,
                "exec": None, "exec_error": None,
                "drivable": False, "refusal": NEXT_FORM_UNSUPPORTED,
                "refusal_detail": (
                    f"форма `Next` вне закрытого enum §8 (S5, строка: {next_declaring_line!r})"
                    " — вождение фазы отказано целиком, не по item'у"),
            })
            continue

        if plan_lines is None:
            exec_value, exec_error = None, "`plan.md` недоступен для чтения §3 Routing"
        else:
            exec_value, exec_error = _resolve_exec_cell(plan_lines, item_id)
        route, route_error = _call_task_contract_build(plan_dir, item_id, monorepo_root)

        drivable, refusal, refusal_detail = _classify_drivability(
            exec_value, exec_error, route, route_error)

        result_items.append({
            "item_id": item_id, "status": status,
            "route": route, "route_error": route_error,
            "exec": exec_value, "exec_error": exec_error,
            "drivable": drivable, "refusal": refusal, "refusal_detail": refusal_detail,
        })

    return {
        "plan_dir": str(plan_dir), "phase_id": phase_id,
        "degraded": False, "degraded_reasons": [],
        "next_form": next_form, "items": result_items,
        "excluded_terminal": excluded_terminal,
    }
