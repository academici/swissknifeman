"""Plan-level orchestration, root discovery and cross-plan checks."""
from .common import *
from .policy import *
from .parsing import *
from task import plan_gates


def lint_plan(plan_dir, diag):
    """Проверяет один план (plans/<PLAN-ID>/…). Возвращает распарсенную модель (dict)."""
    plan_dir = Path(plan_dir)
    plan_id = plan_dir.name
    plan_md = plan_dir / "plan.md"
    meta, status_board = parse_plan_md(plan_md, diag)

    # 2026.07.10-SKM-ROADMAP-005 P4.3: warning-проверки идентичности (ID / workflow-скрипты / supersedes) — D24/D27/D28.
    # meta здесь — сырой dict[name]=(value,lineno) до маппинга в модель ниже.
    _meta_raw = meta if isinstance(meta, dict) else {}
    _lint_plan_identity_20(plan_dir, plan_id, _meta_raw, plan_md, diag)

    # Слой 0 «бриф» обязателен (SKILL §16): новые датовые планы — ERROR, старые — WARNING.
    _lint_plan_brief_20(plan_dir, plan_id, diag)

    # m7/D10: опциональная секция `## 7. Contracts` (нет секции — пустая модель, молча).
    plan_lines = _read_lines(plan_md)
    if plan_lines is not None:
        _lint_v2_decision_pointer(plan_dir, plan_lines, plan_md, diag)
    contracts = (parse_contracts(plan_lines, plan_md, diag) if plan_lines is not None
                 else {"exported": [], "consumed": []})

    # 2026.07.25-ECO-OPT P8.2/D103-D105: `Consequences` в D-записи (opt-in `Closure Protocol | v1` + forward-only).
    if plan_lines is not None:
        _lint_consequences_82(plan_dir, plan_id, _meta_raw, plan_lines, plan_md, diag)

    phase_files = {}  # phase_id -> Path
    layout = "v1"
    try:
        layout = plan_layout.layout_version(plan_dir)
        phase_files = plan_layout.phase_paths(plan_dir)
    except plan_layout.PlanLayoutError as exc:
        diag.error(plan_md, None, str(exc))
    board_phase_ids = set()
    if status_board:
        board_phase_ids = {row.get("Phase") for row, _ in status_board if row.get("Phase")}

    # Roadmap-гейт (SKILL §8): полностью детализированный план обязан нести roadmap.md.
    _lint_plan_roadmap_20(plan_dir, plan_id, phase_files, diag)

    # Журнал/индекс (2026.07.18-FOREMAN P1.4/D22): journal.jsonl soft/hard по дате-cutoff, index.md WARNING-only.
    _lint_plan_journal_20(plan_dir, plan_id, diag)
    _lint_plan_index_20(plan_dir, plan_id, diag)

    for pid in board_phase_ids - set(phase_files):
        diag.error(plan_md, None, f"фаза {pid} есть в Status Board, но нет phases/{pid}.md")
    for pid in set(phase_files) - board_phase_ids:
        diag.error(phase_files[pid], None, f"фаза {pid} есть как phases/{pid}.md, но нет в Status Board")

    phases = {}
    all_items = {}  # item_id -> {"phase": pid, "title":..., "status":..., "fields":...}
    for pid, path in phase_files.items():
        parsed = parse_phase_md(path, pid, diag, layout=layout)
        phases[pid] = {"path": str(path), **(parsed or {})}
        if not parsed:
            continue
        # Блоки `## Audit Pn` исключены из грепов фазы (_lines_before_audit) — свой гейт.
        phase_lines = _read_lines(path)
        if phase_lines:
            _lint_audit_scope_payload(phase_lines, path, plan_id, diag)
        # --- консистентность Phase Status(таблица) vs item.Status -----------
        table_by_id = {row.get("ID"): (row, lineno) for row, lineno in parsed["status_table"]}
        for item_id, occurrences in parsed["items"].items():
            item = occurrences[0]  # диагностика дублей уже выдана выше; для сверки берём первый
            status_val, _ = item["fields"].get("Status", ("", item["header_lineno"]))
            all_items[item_id] = {
                "phase": pid, "title": item["title"], "status": status_val,
                "fields": {k: v[0] for k, v in item["fields"].items()},
            }
            row = table_by_id.pop(item_id, None)
            if row is None:
                diag.error(path, item["header_lineno"],
                           f"item {item_id}: нет строки в «## Phase Status»")
            else:
                row_dict, row_lineno = row
                if row_dict.get("Status") != status_val:
                    diag.error(path, row_lineno,
                               f"item {item_id}: статус в Phase Status «{row_dict.get('Status')}» "
                               f"≠ статусу item «{status_val}»")
        for orphan_id, (row_dict, row_lineno) in table_by_id.items():
            diag.error(path, row_lineno,
                       f"Phase Status: строка «{orphan_id}» без соответствующего item")

        # --- item 🟢/🟠 ⇒ Completion Notes; 🟠 ⇒ Known Deviations -----------
        for item_id, occurrences in parsed["items"].items():
            item = occurrences[0]
            status_val, status_lineno = item["fields"].get("Status", ("", item["header_lineno"]))
            cn_val, cn_lineno = item["fields"].get("Completion Notes", ("", item["header_lineno"]))
            kd_val, kd_lineno = item["fields"].get("Known Deviations", ("", item["header_lineno"]))
            if status_val in (STATUS_DONE, STATUS_DEVIATIONS) and _is_empty(cn_val):
                diag.error(path, cn_lineno,
                           f"item {item_id}: статус «{status_val}» требует непустых Completion Notes")
            if status_val == STATUS_DEVIATIONS and _is_empty(kd_val):
                diag.error(path, kd_lineno,
                           f"item {item_id}: статус «{status_val}» требует непустых Known Deviations")

            # --- 🔴 ⇔ ESCALATION-блок ⇔ Escalation Needed: yes ---------------
            en_val, en_lineno = item["fields"].get("Escalation Needed", ("", item["header_lineno"]))
            en_norm = (en_val or "").strip().lower()
            # 2.0 канонизировал (P0.3 рек#4, SKILL §5): у Escalation Needed — и ТОЛЬКО
            # у него — маркер `no` равноправен «—»; оба принимаются без диагностики.
            if en_norm in ("", EMPTY_PLACEHOLDER, "no"):
                en_yes = False
            elif en_norm == "yes":
                en_yes = True
            else:
                diag.error(path, en_lineno,
                           f"item {item_id}: Escalation Needed «{en_val}» — ожидается yes/no/—")
                en_yes = None
            is_blocked = status_val == STATUS_BLOCKED
            has_escalation = item["has_escalation"]
            if en_yes is not None and not (is_blocked == en_yes == has_escalation):
                parts = (f"Status={'🔴' if is_blocked else '≠🔴'}",
                         f"Escalation Needed={'yes' if en_yes else 'no/—'}",
                         f"ESCALATION-блок={'есть' if has_escalation else 'нет'}")
                diag.error(path, item["header_lineno"],
                           f"item {item_id}: рассогласованы {', '.join(parts)} (должны совпадать)")

            # --- WARNING: пустые Required Reads/Validation у не-⬜ item -------
            if status_val and status_val != "⬜ Not started":
                rr_val, rr_lineno = item["fields"].get("Required Reads", ("", item["header_lineno"]))
                va_val, va_lineno = item["fields"].get("Validation", ("", item["header_lineno"]))
                if _is_empty(rr_val):
                    diag.warning(path, rr_lineno, f"item {item_id}: пустые Required Reads при статусе «{status_val}»")
                if _is_empty(va_val):
                    diag.warning(path, va_lineno, f"item {item_id}: пустая Validation при статусе «{status_val}»")

        # --- 2026.07.24-AGENT-RELIABILITY P4.4/D91: гейт напечатанных кодов границ pre_mutation/pre_final --
        _lint_write_site_codes_44(parsed["status_table"], parsed["items"], path, diag)

        # --- 2026.07.25-ECO-OPT P8.3/D44: 🔴/⛔ обязаны нести `Возобновление:` (opt-in Closure Protocol) --
        _lint_checkpointed_83(_meta_raw, parsed["items"], path, diag)

    # --- 2026.07.24-AGENT-RELIABILITY P2.2/D26/D47: tiered-portability (committed-bundle плана без committed
    # execution input, либо внешний путь в роли execution input) ----------------
    _lint_tiered_portability_22(plan_dir, plan_id, all_items, phases, diag)

    # --- глобальная уникальность ID item ---------------------------------
    seen = {}
    for pid, phase in phases.items():
        for item_id in phase.get("items", {}):
            seen.setdefault(item_id, []).append(pid)
    for item_id, pids in seen.items():
        if len(pids) > 1:
            diag.error(plan_dir, None, f"item {item_id}: ID переиспользован в фазах {sorted(set(pids))}")

    # --- дубли Title среди items (WARNING) --------------------------------
    titles = {}
    for item_id, info in all_items.items():
        titles.setdefault(info["title"], []).append(item_id)
    for title, ids in titles.items():
        if len(ids) > 1:
            diag.warning(plan_dir, None, f"дубль Title «{title}» среди items: {sorted(ids)}")

    # --- Status Board согласован с фазами: счётчик 🟢/всего и статус фазы --
    board_by_phase = {row.get("Phase"): (row, lineno) for row, lineno in status_board}
    for pid in phases:
        row = board_by_phase.get(pid)
        if row is None:
            continue  # уже отражено как отдельная ошибка выше (phase without Status Board row)
        row_dict, row_lineno = row
        phase_item_ids = list(phases[pid].get("items", {}).keys())
        total = len(phase_item_ids)
        done = sum(1 for iid in phase_item_ids
                   if all_items.get(iid, {}).get("status") == STATUS_DONE)
        items_cell = row_dict.get(STATUS_BOARD_ITEMS_COL, "")
        m = DONE_TOTAL_RE.match(items_cell)
        if not m:
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: колонка «{STATUS_BOARD_ITEMS_COL}» = «{items_cell}» "
                       f"— ожидается формат N/M")
        elif (int(m.group(1)), int(m.group(2))) != (done, total):
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: «{STATUS_BOARD_ITEMS_COL}» = «{items_cell}» "
                       f"≠ фактическому {done}/{total}")

        phase_status = row_dict.get("Status", "")
        item_statuses = [all_items[iid]["status"] for iid in phase_item_ids if iid in all_items]
        if item_statuses and any(s == STATUS_BLOCKED for s in item_statuses) and phase_status != STATUS_BLOCKED:
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: есть 🔴 Blocked item, но статус фазы «{phase_status}» ≠ 🔴 Blocked")
        if item_statuses and all(s == STATUS_DONE for s in item_statuses) and phase_status != STATUS_DONE:
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: все items 🟢 Done, но статус фазы «{phase_status}» ≠ 🟢 Done")

        # --- 2.0 WARNING: [NEEDS CLARIFICATION] в фазе 🟡+ = DoR-гейт не пройден --
        if phase_status and phase_status != "⬜ Not started":
            nc = phases[pid].get("needs_clarification") or []
            if nc:
                diag.warning(phases[pid]["path"], nc[0],
                             f"фаза {pid} в статусе «{phase_status}», но несёт "
                             f"{len(nc)} маркер(ов) [NEEDS CLARIFICATION] "
                             f"(строки {nc}) — DoR-гейт не пройден (SKILL §7)")

        # --- 2026.07.10-SKM-ROADMAP-005 P4.6 WARNING: workflow-как-DoR (D29) — фаза со статусом 🟡+, ЗАЯВЛЯЮЩАЯ
        # оркестрацию (грепаемый признак), но у плана нет workflow-скрипта в
        # `plans/<ID>/workflows/`. Условность: без признака оркестрации — молчит
        # (ручное item-by-item исполнение workflow не требует). warning-only.
        if (phase_status and phase_status != "⬜ Not started"
                and phases[pid].get("declares_orchestration")
                and not _plan_has_workflow_script(plan_dir)):
            diag.warning(phases[pid]["path"], None,
                         f"фаза {pid} заявляет оркестрацию (multi-agent/fan-out), но нет "
                         f"workflow-скрипта в `plans/{plan_id}/workflows/` — DoR §7 (D29)")

        # --- фаза 🟢/🟠 ⇒ Phase Handoff непуст --------------------------
        if phase_status in (STATUS_DONE, STATUS_DEVIATIONS):
            handoff_text = phases[pid].get("phase_handoff")
            if handoff_text is None:
                pass  # отсутствие секции уже отражено отдельной ошибкой
            elif _is_empty(handoff_text):
                diag.error(phases[pid]["path"], None,
                           f"фаза {pid} статус «{phase_status}», но «## Phase Handoff» пуст")

        # --- 2026.07.13-PLAN-PROTOCOL-GAP P2.15/D34 WARNING: зеркальный гейт — фаза НЕтерминальна, а Phase Handoff
        # УТВЕРЖДАЕТ закрытие и не помечен маркером инвалидации (H2, SKILL §3, 4-й шаг).
        # WARNING, не ERROR: три плана флота (истинно-положительные, carve-out D34) иначе
        # получили бы недостижимый commit-гейт в ЧУЖИХ репозиториях.
        # 2026.07.13-PLAN-PROTOCOL-GAP P3.7/D50: утверждение о закрытии ФАЗЫ читается по ПЕРВОЙ НЕПУСТОЙ СТРОКЕ блока и
        # снимается ОТРИЦАНИЕМ на ней же — иначе гейт ловит слово, а не субъект (J1).
        elif phase_status and phase_status not in TERMINAL_STATUSES:
            handoff_text = phases[pid].get("phase_handoff")
            claim_line = phases[pid].get("phase_handoff_first_line") or ""
            if (handoff_text and not _is_empty(handoff_text)
                    and PHASE_HANDOFF_CLOSURE_RE.search(claim_line)
                    and not PHASE_HANDOFF_NEGATION_RE.search(claim_line)
                    and not phases[pid].get("phase_handoff_stale")):
                diag.warning(phases[pid]["path"], phases[pid].get("phase_handoff_lineno"),
                             f"Phase Handoff протух: фаза {pid} НЕ закрыта (статус "
                             f"«{phase_status}»), а блок утверждает закрытие фазы — поставь "
                             f"его первой строкой маркер «> УСТАРЕЛ — фаза реопенена <D#>» "
                             f"(SKILL §3, 4-й шаг реопена: блок не удаляется, его перезапишет "
                             f"plan-close при следующем закрытии фазы)")

    # --- 2026.07.25-ECO-OPT P8.1/D42: отчёт закрытия фазы (opt-in `Closure Protocol | v1`) ----------
    _lint_closure_reports_81(plan_dir, plan_id, _meta_raw, phases, board_by_phase, diag)

    # D2 is a layout-v2 hard gate.  Its implementation stays outside this
    # coordinator; the gate delegates graph/weight/admission semantics to their
    # respective shared owners and contributes diagnostics at this one boundary.
    plan_gates.lint_read_budget(plan_dir, layout, diag)
    plan_gates.lint_bundle_freshness(plan_dir, layout, diag)
    plan_gates.lint_read_path_boundaries(plan_dir, layout, diag)
    plan_gates.lint_return_loop(plan_dir, layout, diag)

    # --- phase-first (WARNING): активные 🟡 items в фазе N+1 при не-терминальной N
    numbered = sorted(
        ((int(PHASE_TOKEN_RE.match(pid).group(1)), pid) for pid in board_by_phase if PHASE_TOKEN_RE.match(pid)),
    )
    by_num = dict(numbered)
    for n, pid in numbered:
        nxt_pid = by_num.get(n + 1)
        if nxt_pid is None:
            continue
        cur_status = board_by_phase[pid][0].get("Status", "")
        if cur_status in TERMINAL_STATUSES:
            continue
        nxt_items = phases.get(nxt_pid, {}).get("items", {})
        active = [iid for iid in nxt_items if all_items.get(iid, {}).get("status") == STATUS_IN_PROGRESS]
        if active:
            diag.warning(plan_dir, None,
                         f"phase-first: {nxt_pid} содержит активные 🟡 items {sorted(active)}, "
                         f"хотя {pid} ещё не терминальна (статус «{cur_status}»)")

    # --- handoff.md ---------------------------------------------------------
    handoff_path = plan_dir / "handoff.md"
    handoff = parse_handoff_md(handoff_path, diag)

    # 2026.07.25-ECO-OPT P11.3/D129: handoff.md ↔ Status Board «Pn a/b» — вне `if handoff:`
    # блока Next-резолвера ниже (независимая проверка, форма-нейтральна к Next).
    _lint_handoff_board_113(handoff, handoff_path, plan_id, board_by_phase, diag)

    if handoff:
        next_val, next_lineno = handoff["fields"].get("Next", ("", None))

        # Заголовок (D30/D37) — ссылка обязана резолвиться, иначе расширение regex'а просто
        # «разрешило всё»: у ОБЕИХ форм (`after Pn` — фаза, `after Pn.m` — item) гейтится
        # существование ФАЗЫ `Pn`. Исключение — bootstrap `P0.0` (замер флота: единственное
        # попадание item-формы — стартовый handoff, не дефект). Существование самого ITEM'а
        # `Pn.m` НЕ гейтится: 12 планов флота несут `after P0.0` (плана ещё не касались,
        # item'а P0.0 не бывает) — гейт на неё = новые ERROR флоту, back-compat запрещает.
        # Оракул «фаза существует» — ОБЪЕДИНЕНИЕ Status Board и файлов фаз (D41): это гейт
        # висячей ССЫЛКИ, а рассинхрон board↔файлы — отдельный дефект со своей диагностикой
        # («фаза Pn есть в Status Board, но нет phases/Pn.md»), дублировать её здесь нечем.
        known_phases = set(phases) | set(board_by_phase)
        title_ref = handoff.get("title_ref")
        if title_ref and title_ref != HANDOFF_TITLE_BOOTSTRAP:
            title_phase = title_ref.split(".", 1)[0]
            if title_phase not in known_phases:
                diag.error(handoff_path, handoff.get("title_lineno"),
                           f"заголовок: фаза «{title_phase}» не существует в плане")

        # ФОРМА `Next` ОБЪЯВЛЯЕТСЯ ПЕРВОЙ НЕПУСТОЙ СТРОКОЙ поля (D40). Само поле
        # МНОГОСТРОЧНОЕ: ниже идёт launch-block (таблица Model/Thinking/Context/Суть +
        # code-block), и его проза законно ЦИТИРУЕТ другие формы enum'а — голый промпт
        # item'а, чинящего сам протокол, называет и slash-команды, и «план закрыт».
        # Резолв по ВСЕМУ полю принимал такую цитату за объявление: handoff с «ЗАПУСК
        # ВРУЧНУЮ» в первой строке ловил ложный ERROR «не все items терминальны».
        next_decl = next((ln for ln in next_val.splitlines() if ln.strip()), "")
        kind, m = _resolve_next_form(next_decl)
        if kind is None:
            # Строка-объявление не назвала формы — back-compat: планы флота, у которых
            # первая строка прозаическая, а команда живёт в launch-block'е, читаются как
            # прежде (резолв по всему полю).
            kind, m = _resolve_next_form(next_val)

        # --- C2 (D8): прозаическая gate-оговорка при runnable-форме → WARNING ------
        # Автор вписал в объявление runnable slash-форму «команда есть, но не сейчас»
        # (стем «не раньше»/«делать нечего»/time-gate) вместо структурной формы «ОЖИДАНИЕ».
        # Скан — только СТРОКА-ОБЪЯВЛЕНИЕ (`next_decl`): guard-строка `# НЕ раньше:` формы
        # «ОЖИДАНИЕ» законно живёт в code-block'е и не должна триггерить C2 (форма waiting
        # к тому же не входит в C2_RUNNABLE_KINDS). Уровень — WARNING (механизм молод, D20).
        if kind in C2_RUNNABLE_KINDS and C2_WAITING_STEMS_RE.search(next_decl):
            diag.warning(handoff_path, next_lineno,
                         "Next: runnable-форма несёт прозу-оговорку о неисполнимости сейчас "
                         "(«не раньше»/«делать нечего»/time-gate) — если шаг реален, но "
                         "заблокирован временем/гейтом, объяви форму «ОЖИДАНИЕ: <условие> → "
                         "<целевая форма>» (SKILL §8): она копипастится с guard-строкой "
                         "`# НЕ раньше:`, прозаическая оговорка — нет")

        # --- 2.0: launch-block в handoff.Next (SKILL §8) --------------------------
        # Severity как у brief-гейта: датовые планы от BRIEF_CANON_DATE — ERROR
        # (владелец не должен переспрашивать модель/настройки), старее/legacy — WARNING.
        # Таблица `| Model | …`, строка `| Команда |` и code-block грепаются по всему
        # файлу: шаблон кладёт launch-block продолжением Next, но точное место не гейтим
        # (warning-уровень).
        # Для целиком закрытого плана («план закрыт») запускать нечего — не требуем.
        # Условие СОЗНАТЕЛЬНО мягче резолвера (`kind`): любое утверждение о закрытии в
        # ЛЮБОМ месте поля снимает требование launch-block'а. Ужесточение до `kind` дало бы
        # новый WARNING живому плану флота (PILOT-AZG: первая строка несёт и «план закрыт
        # целиком», и lint-ссылку `/task:plan-exec` → резолвится как exec) — back-compat §2.
        #
        # P5.8: команда теперь либо строка `| Команда |` В ТОЙ ЖЕ таблице, либо
        # code-block ниже — «ровно один из двух» = ХОТЯ БЫ ОДИН, не «строго не оба»:
        # план, несущий и строку, и code-block (back-compat старой формы, либо
        # manual/scope-payload/ОЖИДАНИЕ item, которому code-block нужен по канону §8
        # независимо от строки), гейтом не наказывается — «ровно один из двух» описывает
        # МИНИМУМ носителя команды, а не запрет на оба сразу (SKILL §8, snippets/
        # launch-block-template.md). Решение зафиксировано тестом (test_plan_lint.py).
        if LITERAL_PLAN_CLOSED not in next_val.lower():
            has_table = any(LAUNCH_TABLE_ROW_RE.match(ln) for ln in handoff["lines"])
            has_command_row = any(LAUNCH_COMMAND_ROW_RE.match(ln) for ln in handoff["lines"])
            has_fence = any(CODE_FENCE_RE.match(ln) for ln in handoff["lines"])
            if not (has_table and (has_command_row or has_fence)):
                missing = []
                if not has_table:
                    missing.append("таблицы `| Model | …`")
                if not (has_command_row or has_fence):
                    missing.append("строки `| Команда |` в таблице или code-block'а с командой")
                _lb_msg = ("Next без launch-block: нет " + " и ".join(missing) +
                           " (форма — snippets/launch-block-template.md)")
                if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
                    diag.error(handoff_path, next_lineno, _lb_msg)
                else:
                    diag.warning(handoff_path, next_lineno, _lb_msg)
        plan_closed = bool(all_items) and all(
            info["status"] in TERMINAL_STATUSES for info in all_items.values())

        def _check_plan_id(ref_plan_id):
            if ref_plan_id != plan_id:
                diag.error(handoff_path, next_lineno,
                           f"Next: PLAN-ID «{ref_plan_id}» ≠ фактическому «{plan_id}»")

        def _check_phase(ref_phase):
            if ref_phase not in phases:
                diag.error(handoff_path, next_lineno,
                           f"Next: фаза «{ref_phase}» не существует в плане")

        def _check_item(ref_item):
            if ref_item not in all_items:
                diag.error(handoff_path, next_lineno,
                           f"Next: item «{ref_item}» не существует ни в одной фазе")

        if kind == "manual":
            pass  # «ЗАПУСК ВРУЧНУЮ: <model/effort>» — форма без slash-команды, ссылок нет
        elif kind == "waiting":
            pass  # «ОЖИДАНИЕ: <условие> → <целевая форма>» (D8): целевая команда guarded в
                  # launch-block'е; ссылки объявления не резолвим (целевая форма проверится
                  # при реальном запуске по снятии гейта). launch-block требуется — как у
                  # прочих runnable-форм (не exempt): гейт launch-block выше не смотрит kind.
        elif kind == "exec":
            ref_plan_id, ref_item = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            _check_item(ref_item)
        elif kind == "run":
            ref_plan_id, ref_from, ref_to = m.group(1), m.group(2), m.group(3)
            _check_plan_id(ref_plan_id)
            _check_item(ref_from)
            if ref_to:
                _check_item(ref_to)
        elif kind == "audit-design":
            _check_plan_id(m.group(1))
        elif kind == "closed":
            if not plan_closed:
                diag.error(handoff_path, next_lineno,
                           "Next: «план закрыт», но не все items терминальны")
        elif kind == "design-item":
            ref_plan_id, ref_item = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            _check_item(ref_item)
        elif kind == "design-phase":
            ref_plan_id, ref_phase = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            _check_phase(ref_phase)
        elif kind == "audit":
            ref_plan_id, ref_phase = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            _check_phase(ref_phase)
            if ref_phase in phases:
                row = board_by_phase.get(ref_phase)
                phase_status = row[0].get("Status", "") if row else ""
                if phase_status not in TERMINAL_STATUSES:
                    diag.warning(handoff_path, next_lineno,
                                 f"Next: /task:plan-audit {ref_phase} — фаза в статусе "
                                 f"«{phase_status}», не терминальна (аудит гоняется по "
                                 f"закрытой фазе, SKILL §13)")
        elif kind == "close-archive":
            _check_plan_id(m.group(1))
            if not plan_closed:
                diag.warning(handoff_path, next_lineno,
                             "Next: /task:plan-close archive — план ещё не терминален целиком")
        elif kind == "close":
            ref_plan_id, ref_phase, ref_suffix = m.group(1), m.group(2), m.group(3)
            _check_plan_id(ref_plan_id)
            _check_phase(ref_phase)
            if ref_suffix:
                _check_item(ref_phase + ref_suffix)
        else:
            diag.error(handoff_path, next_lineno, NEXT_FORMS_HELP)

    return {
        "id": plan_id,
        "path": str(plan_dir),
        "meta": {k: v[0] for k, v in (meta or {}).items()},
        "contracts": contracts,
        "status_board": [row for row, _ in status_board],
        "phases": {
            pid: {
                "path": ph["path"],
                "status_table": [row for row, _ in ph.get("status_table", [])],
                "items": {
                    iid: {"title": occ[0]["title"], "fields": {k: v[0] for k, v in occ[0]["fields"].items()}}
                    for iid, occ in ph.get("items", {}).items()
                },
                "phase_handoff": ph.get("phase_handoff"),
            }
            for pid, ph in phases.items()
        },
        "handoff": {
            "path": str(handoff_path),
            "title_ref": (handoff or {}).get("title_ref"),
            "fields": {k: v[0] for k, v in (handoff or {}).get("fields", {}).items()},
        } if handoff else None,
    }


# --- root-level проверки (path = plans/ целиком, не одиночный plans/<ID>) -----

def lint_plans_root(root, models, diag):
    """Проверки, применимые только к каталогу `plans/` целиком (см. discover_plan_dirs:
    отличается от одиночного `plans/<ID>` тем, что там нет `plan.md` рядом с собой).
    `models` — {plan_id: model|None} уже пролинтованных подкаталогов (для сверки, что
    Active указывает на реально существующий каталог-план, и для подсчёта 🟡 In progress).

    (а) есть plans/ACTIVE.md → поле «**Active:**» обязано быть «—» либо именем
        существующего каталога-плана, иначе ERROR;
    (б) нет ACTIVE.md и ≥2 планов со статусом «🟡 In progress» (Meta plan.md) →
        WARNING «активный план неоднозначен»;
    (в) плоские *.md в корне plans/ (кроме ACTIVE.md/README.md) — черновики plan mode,
        оставшиеся без протокола, → одно WARNING со списком и подсказкой from-draft;
    (г) cross-plan сверка `## 7. Contracts`: Pinned потребителя ≠ Версии донора того же
        корня → WARNING «уведомление не разнесено» (m7/D10, §11).
    """
    root = Path(root)
    _lint_contracts_cross_plan(models, diag)

    active_path = root / ACTIVE_FILENAME
    active_lines = _read_lines(active_path)
    if active_lines is not None:
        value, value_lineno = None, None
        for i, ln in enumerate(active_lines):
            m = ACTIVE_FIELD_RE.match(ln)
            if m:
                value, value_lineno = m.group(1).strip(), i + 1
                break
        if value is None:
            diag.error(active_path, None, "нет поля «**Active:**» в ACTIVE.md")
        elif value != EMPTY_PLACEHOLDER and value not in models:
            diag.error(active_path, value_lineno,
                       f"Active «{value}» не указывает на существующий план "
                       f"(нет каталога plans/{value}/)")
    else:
        in_progress = sorted(
            pid for pid, model in models.items()
            if (model or {}).get("meta", {}).get("Status") == STATUS_IN_PROGRESS
        )
        if len(in_progress) >= 2:
            diag.warning(root, None,
                         "активный план неоднозначен: нет plans/ACTIVE.md, а планов со "
                         f"статусом «{STATUS_IN_PROGRESS}» {len(in_progress)}: {in_progress}")

    drafts = sorted(
        p.name for p in root.glob("*.md")
        if p.is_file() and p.name not in (ACTIVE_FILENAME, README_FILENAME)
    )
    if drafts:
        diag.warning(root, None,
                     "черновики plan mode: " + ", ".join(drafts) +
                     " — разверни /task:plan-design from-draft")


# --- дискавери множества планов ----------------------------------------------

ARCHIVE_DIR_NAME = "archive"  # N3/D14: контейнер архивных планов, сам планом не является


def discover_plan_dirs(root):
    """path — либо сам plans/<ID> (есть plan.md), либо plans/ (перебор подкаталогов).
    `plans/archive/` в переборе НЕ участвует как план (N3/D14) — вместо неё в перебор
    попадают её подкаталоги `plans/archive/<ID>` (архивные планы линтуются как планы)."""
    root = Path(root)
    if (root / "plan.md").is_file():
        return [root]
    if not root.is_dir():
        return None
    dirs = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        # Tooling caches/configuration are not executable-plan directories.  They
        # can be created by the validation run itself, so treating them as plans
        # makes the gate non-idempotent.
        if p.name.startswith(".") or p.name == "__pycache__":
            continue
        if p.name == ARCHIVE_DIR_NAME:
            dirs.extend(sorted(a for a in p.iterdir()
                               if a.is_dir() and not a.name.startswith(".")
                               and a.name != "__pycache__"))
            continue
        dirs.append(p)
    return dirs


# --- --conflicts: канон ↔ реализация (2026.07.31-SKM-LEAN P5.9, roadmap plan-audit-loop.md §A.1) -----
# Третья нога конфликт-скана — сверка `SKILL.ru.md` с реестрами-константами ЭТОГО модуля.
# Первые две ноги (свежесть перевода RU→EN, присутствие i18n-keep литералов в EN и в теле RU)
# уже покрыты `check-translations.sh` — не переиздаются здесь (Implementation Rule 2).
#
# Работает БЕЗ аргумента-плана (Implementation Rule 5): сверяет АРТЕФАКТЫ канона, не
# конкретный `plans/<ID>`. Каждая сверка — структурная (код-фенс/бэктик-спан/маркированный
# список — устойчивый якорь), не эвристический парс свободной прозы (Implementation Rule 3).
# Находка несёт ОБЕ стороны с `файл:строка` (Implementation Rule 4). `--conflicts` ничего не
# ОБЪЯВЛЯЕТ заново — сравнивает канон и уже существующие реестры `plan_lint.py`; единственное
# исключение — `CONTEXT_VALUES` (см. её комментарий выше), которую этот item вводит именно
# затем, чтобы для класса «значения Context» было ЧТО сравнивать (без неё сверка этого
# класса структурно невозможна — Scope Included этого item'а прямо требует её как одну из
# шести граней).

__all__ = tuple(name for name in globals() if not name.startswith("__"))
