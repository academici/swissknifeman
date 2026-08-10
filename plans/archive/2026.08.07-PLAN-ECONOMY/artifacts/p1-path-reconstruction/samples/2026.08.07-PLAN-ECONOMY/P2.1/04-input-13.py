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

def _resolve_next_form(next_field_text):
    """S5 — форма `**Next:**` из ПЕРВОЙ непустой строки поля (D40). Возвращает
    `(kind, declaring_line)`; `kind=None`, если строка не начинается ни с одного из
    11 закрытых префиксов (легаси-входы совместимости сюда не попадают, §3.2)."""
    declaring_line = next(
        (ln.strip() for ln in (next_field_text or "").splitlines() if ln.strip()), "")
    m = _NEXT_FORM_RE.match(declaring_line)
    return (m.group(1) if m else None), declaring_line
