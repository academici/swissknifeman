"""Plan-level orchestration, root discovery and cross-plan checks."""
from .common import *
from .policy import *
from .parsing import *
from task import plan_assurance, plan_gates, plan_readiness, plan_repair


_ROUTING_ITEM_RE = re.compile(r"^P\d+\.\d+$")
_ROUTING_RANGE_RE = re.compile(r"^(P\d+)\.(\d+)\s*[–-]\s*(P\d+)\.(\d+)$")
_ROUTING_COLUMNS = ("Batch", "Items", "Model class/effort", "Exec", "Review", "Why")
_ROUTING_BATCH_RE = re.compile(r"^[A-Z][A-Z0-9._-]*$", re.IGNORECASE)
_ROUTING_REVIEW_VALUES = frozenset(("full", "light", "none"))
_CONTINUE_FIRST_GATE_DATE = "2026.09.09"


def _lint_terminal_admission_contract(plan_path, diag):
    """Keep the command-visible terminal seam bound to its committed schemas."""
    try:
        terminal_admission.validate_contracts()
    except terminal_admission.AdmissionError as exc:
        diag.error(plan_path, None, f"terminal admission contract: {exc}")


def _lint_design_continuation(plan_dir, plan_path, plan_id, phase_id, item_id,
                              line_number, diag):
    """Reject redesign when typed repair/re-entry evidence says continue."""
    if not PLAN_ID_DATED_RE.match(plan_id) or plan_id[:10] < _CONTINUE_FIRST_GATE_DATE:
        return
    latest = plan_repair.latest_action(
        plan_dir, item_id=item_id, phase_id=None if item_id is not None else phase_id)
    if latest == "repair-in-current-attempt":
        diag.error(
            plan_path, line_number,
            "REPAIR_CONTINUATION_REQUIRED: latest repair-decision/v1 requires "
            "repair-in-current-attempt, not plan-design",
        )
    try:
        plan_readiness.validate_design_target(plan_dir, phase_id)
    except plan_readiness.ReadinessError as exc:
        diag.error(plan_path, line_number, str(exc))


def _lint_priority_continuation(plan_dir, plan_path, plan_id, item_ids,
                                line_number, diag):
    if not PLAN_ID_DATED_RE.match(plan_id) or plan_id[:10] < _CONTINUE_FIRST_GATE_DATE:
        return
    try:
        plan_readiness.validate_execution_target(plan_dir, item_ids)
    except plan_readiness.ReadinessError as exc:
        diag.error(plan_path, line_number, str(exc))


def _routing_items(cell):
    """Expand the closed one-item/same-phase-range grammar."""
    cell = cell.strip().strip("`")
    if _ROUTING_ITEM_RE.fullmatch(cell):
        return [cell]
    match = _ROUTING_RANGE_RE.fullmatch(cell)
    if (match and match.group(1) == match.group(3)
            and int(match.group(2)) <= int(match.group(4))):
        return [f"{match.group(1)}.{number}" for number in
                range(int(match.group(2)), int(match.group(4)) + 1)]
    return None


def _handoff_run_items(value):
    from task import task_contract

    match = re.search(
        r"(?:/|\b)task:plan-(?:run|exec)\s+\S+\s+"
        r"(P\d+\.\d+(?:\s*-\s*P\d+\.\d+)?"
        r"(?:\s+P\d+\.\d+(?:\s*-\s*P\d+\.\d+)?)*)", value)
    if not match:
        return []
    tokens = re.sub(r"\s*-\s*", "-", match.group(1)).split()
    try:
        return list(task_contract.normalize_batch_request(tokens))
    except ValueError:
        return []


def _lint_routing(plan_lines, plan_path, plan_id, layout, diag):
    """Validate canonical batch routing and return expanded rows for handoff checks."""
    strict = layout == "v2" and bool(PLAN_ID_NUMBERED_RE.match(plan_id))
    if strict:
        # task_contract owns the executable table boundary.  In particular, do
        # not let the first adjacent pipe table become a competing parser here.
        from task import task_contract
        try:
            table = task_contract.executable_routing_table(Path(plan_path).parent)
        except task_contract.TaskContractBuildError as exc:
            diag.error(plan_path, None, f"Routing schema: {exc}")
            return []
        headers = list(table["headers"])
        rows = list(table["rows"])
        _header = table["header_line"]
    else:
        _idx, body, start = _find_section(
            plan_lines, re.compile(r"^##\s+3\.\s+Routing\s*$"))
        if body is None:
            return []
        headers, rows, _header = _parse_table(body, start)
    if not headers or "Items" not in headers:
        return []
    expanded_rows = []
    for row, line_number in rows:
        cell = row.get("Items", "").strip().strip("`")
        items = _routing_items(cell)
        if items is None:
            diag.error(
                plan_path, line_number,
                f"Routing Items «{cell}» outside closed grammar: one allowed item Pn.m "
                "or increasing single-phase range Pn.a–Pn.b; batch is specified in a separate column")
            continue
        if strict:
            batch = row.get("Batch", "").strip()
            if not batch or not _ROUTING_BATCH_RE.fullmatch(batch):
                diag.error(plan_path, line_number,
                           f"Routing Batch «{batch}» invalid: expected `solo` or stable ID groups")
            elif batch.lower() == "solo" and len(items) != 1:
                diag.error(plan_path, line_number,
                           "Routing Batch `solo` can address exactly one item")
            try:
                task_contract.resolve_exec(row.get("Exec", ""))
            except task_contract.TaskContractBuildError as exc:
                diag.error(plan_path, line_number, str(exc))
            if row.get("Review", "").strip() not in _ROUTING_REVIEW_VALUES:
                diag.error(plan_path, line_number,
                           "Routing Review should be full, light or none")
        expanded_rows.append({**row, "_items": items, "_line": line_number})
    return expanded_rows


def _lint_routing_coverage(plan_path, plan_id, layout, routing_rows, all_items, diag):
    """Every new-plan item is assigned exactly once; real batches stay phase-local."""
    if layout != "v2" or not PLAN_ID_NUMBERED_RE.match(plan_id):
        return
    owners = {}
    batches = {}
    for row in routing_rows:
        batch = row.get("Batch", "").strip()
        for item_id in row["_items"]:
            owners.setdefault(item_id, []).append(row["_line"])
            if batch.lower() != "solo":
                batches.setdefault(batch, []).append((item_id, row))
    for item_id in sorted(all_items):
        lines = owners.get(item_id, [])
        if not lines:
            diag.error(plan_path, None, f"Routing schema: item {item_id} is not assigned to any Batch, neither solo")
        elif len(lines) > 1:
            diag.error(plan_path, lines[-1], f"Routing schema: item {item_id} assigned more than once")
    for item_id, lines in owners.items():
        if item_id not in all_items:
            diag.error(plan_path, lines[0], f"Routing schema: unknown item {item_id}")
    for batch, members in batches.items():
        item_ids = [item_id for item_id, _row in members]
        phases = {item_id.split(".", 1)[0] for item_id in item_ids}
        from task import task_contract
        try:
            exec_modes = {task_contract.resolve_exec(row.get("Exec", ""))
                          for _item_id, row in members}
        except task_contract.TaskContractBuildError:
            continue  # The row validator already reports the unknown spelling.
        numbers = sorted(int(item_id.split(".", 1)[1]) for item_id in item_ids)
        if len(item_ids) < 2:
            diag.error(plan_path, members[0][1]["_line"],
                       f"Routing Batch {batch} contains one item: use `solo`")
        if len(phases) != 1:
            diag.error(plan_path, members[0][1]["_line"],
                       f"Routing Batch {batch} crosses the phase audit/close boundary")
        if len(exec_modes) != 1:
            diag.error(plan_path, members[0][1]["_line"],
                       f"Routing Batch {batch} mixes incompatible Exec-modes {sorted(exec_modes)}")
        if numbers and numbers != list(range(numbers[0], numbers[-1] + 1)):
            diag.error(plan_path, members[0][1]["_line"],
                       f"Routing Batch {batch} is not adjacent-chain")


def _next_runnable_item(phases, all_items, *, ready_items=None):
    """Return the first item that may enter an execution dispatch.

    Bundles are generated evidence, not authoring input.  A future item can
    legitimately name an artifact produced by its predecessor, so requiring
    its bundle while that predecessor is unfinished makes the plan impossible
    to design.  The first non-terminal item behind a fully terminal prefix is
    different: an executor must be able to read its five mandatory slots now.
    """
    for phase_id in sorted(phases, key=lambda value: int(value[1:])):
        phase = phases[phase_id]
        for item_id in phase.get("items", {}):
            status = all_items.get(item_id, {}).get("status")
            if status in TERMINAL_STATUSES:
                continue
            if status in ("⬜ Not started", STATUS_IN_PROGRESS):
                if ready_items is not None and item_id not in ready_items:
                    continue
                return item_id
            return None
    return None


def _lint_next_runnable_bundle(plan_dir, layout, phases, all_items, diag):
    """Fail closed when the next executable Layout-v2 item lacks a fresh bundle."""
    if layout != "v2":
        return
    # The journal's owning check applies the D22 soft/hard cutoff.  Without
    # that carrier there is no execution position to check here; execution
    # admission still fails closed in plan_recovery.
    if not (Path(plan_dir) / "journal.jsonl").is_file():
        return
    from task import plan_recovery
    try:
        ready_items = plan_recovery.design_ready_items(plan_dir)
    except (plan_recovery.RecoveryError, ValueError) as exc:
        diag.error(Path(plan_dir) / "plan.md", None, str(exc))
        return
    item_id = _next_runnable_item(phases, all_items, ready_items=ready_items)
    if item_id is None:
        return

    # Deferred import keeps the plan_lint ↔ plan_bundle public compatibility
    # cycle out of module initialization while reusing the owning renderer.
    from task import plan_bundle

    phase_id = item_id.split(".", 1)[0]
    item_path = Path(phases[phase_id]["path"])
    try:
        target = plan_layout.carrier_path(plan_dir, "bundle", item_id=item_id)
        expected = plan_bundle.render(plan_dir, item_id).encode("utf-8")
    except (plan_layout.PlanLayoutError, plan_bundle.BundleError) as exc:
        diag.error(
            item_path, None,
            f"item {item_id}: bundle next run item is not collected: {exc}; "
            "first classify and correct the local reversible media in the current "
            "execution attempt, then run plan-views.py bundle --item "
            f"{item_id}; task:plan-design is valid only with proven new material "
            "decision surface",
        )
        return
    if plan_readiness.design_gate_enabled(plan_dir):
        return  # selected execution start materializes the validated bundle
    try:
        actual = target.read_bytes()
    except OSError:
        diag.error(
            item_path, None,
            f"required bundle next run item {item_id} missing: {target}; "
            f"run plan-views.py bundle --item {item_id}",
        )
        return
    if actual != expected:
        diag.error(
            target, None,
            f"required bundle next run item {item_id} is deprecated; "
            f"run plan-views.py bundle --item {item_id}",
        )


def lint_plan(plan_dir, diag):
    """Tests one plan (plans/<PLAN-ID>/…). Returns the parsed model (dict)."""
    plan_dir = Path(plan_dir)
    plan_id = plan_dir.name
    plan_md = plan_dir / "plan.md"
    _lint_terminal_admission_contract(plan_md, diag)
    meta, status_board = parse_plan_md(plan_md, diag)

    # warning-identity checks (ID / workflow-scripts / supersedes) — D24/D27/D28.
    # meta here - raw dict[name]=(value,lineno) before mapping to the model below.
    _meta_raw = meta if isinstance(meta, dict) else {}
    _lint_plan_identity_20(plan_dir, plan_id, _meta_raw, plan_md, diag)

    # Layer 0 «brief» required (SKILL §16): new date plans - ERROR, old - WARNING.
    _lint_plan_brief_20(plan_dir, plan_id, diag)

    # m7/D10: optional section `## 7. Contracts` (no section - empty model, silent).
    plan_lines = _read_lines(plan_md)
    if plan_lines is not None:
        _lint_v2_decision_pointer(plan_dir, plan_lines, plan_md, diag)
    contracts = (parse_contracts(plan_lines, plan_md, diag) if plan_lines is not None
                 else {"exported": [], "consumed": []})

    # -D105: `Consequences` in D-records (opt-in `Closure Protocol | v1` + forward-only).
    if plan_lines is not None:
        _lint_consequences_82(plan_dir, plan_id, _meta_raw, plan_lines, plan_md, diag)

    phase_files = {}  # phase_id -> Path
    layout = "v2"
    try:
        layout = plan_layout.layout_version(plan_dir)
        phase_files = plan_layout.phase_paths(plan_dir)
    except plan_layout.PlanLayoutError as exc:
        diag.error(plan_md, None, str(exc))
        return {"plan_id": plan_id, "meta": meta or {}, "phases": {}, "items": {}}
    routing_rows = []
    if plan_lines is not None:
        routing_rows = _lint_routing(plan_lines, plan_md, plan_id, layout, diag)
    board_phase_ids = set()
    if status_board:
        board_phase_ids = {row.get("Phase") for row, _ in status_board if row.get("Phase")}

    # Roadmap-gate (SKILL §8): a fully detailed plan is required to bear roadmap.md.
    _lint_plan_roadmap_20(plan_dir, plan_id, phase_files, diag)

    # Log/index: journal.jsonl soft/hard by date-cutoff, index.md WARNING-only.
    _lint_plan_journal_20(plan_dir, plan_id, diag)
    _lint_plan_index_20(plan_dir, plan_id, diag)

    for pid in board_phase_ids - set(phase_files):
        diag.error(plan_md, None, f"phase {pid} is in Status Board, but no phases/{pid}.md")
    for pid in set(phase_files) - board_phase_ids:
        diag.error(phase_files[pid], None, f"phase {pid} is like phases/{pid}.md, but not in Status Board")

    phases = {}
    all_items = {}  # item_id -> {"phase": pid, "title":..., "status":..., "fields":...}
    for pid, path in phase_files.items():
        parsed = parse_phase_md(path, pid, diag, layout=layout)
        phases[pid] = {"path": str(path), **(parsed or {})}
        if not parsed:
            continue
        # Blocks `## Audit Pn` excluded from phase greps (_lines_before_audit) — your gate.
        phase_lines = _read_lines(path)
        if phase_lines:
            # Legacy intent is advisory; malformed handwritten structure still
            # gets its ordinary schema diagnostic, never an audit requirement.
            if "> **Phase Assurance | v1.**" in phase_lines:
                try:
                    assurance = plan_assurance.parse("\n".join(phase_lines))
                    if assurance["audit_intent"] == "required":
                        diag.warning(path, None,
                                     "PHASE_AUDIT_INTENT_ADVISORY: Audit Intent: required does not assign audit; "
                                     "next time you edit, use direct-close-eligible")
                except plan_assurance.AssuranceError as exc:
                    diag.error(path, None, str(exc))
            _lint_audit_scope_payload(phase_lines, path, plan_id, diag)
            _lint_audit_terminal_policy(
                phase_lines, path, plan_dir, plan_id, pid, diag)
        # --- consistency Phase Status(table) vs item.Status -----------
        table_by_id = {row.get("ID"): (row, lineno) for row, lineno in parsed["status_table"]}
        for item_id, occurrences in parsed["items"].items():
            item = occurrences[0]  # duplicate diagnostics have already been issued above; to check we take the first one
            from task import review_packet
            try:
                review_packet.validate_design(plan_dir, {key: value[0] for key, value in item["fields"].items()})
            except review_packet.ReviewError as exc:
                diag.error(path, item["header_lineno"], str(exc))
            from task import task_contract
            try:
                task_contract.declared_authority(item_id, item["fields"])
            except task_contract.TaskContractBuildError as exc:
                diag.error(path, item["header_lineno"], str(exc))
            status_val, _ = item["fields"].get("Status", ("", item["header_lineno"]))
            all_items[item_id] = {
                "phase": pid, "title": item["title"], "status": status_val,
                "fields": {k: v[0] for k, v in item["fields"].items()},
            }
            row = table_by_id.pop(item_id, None)
            if row is None:
                diag.error(path, item["header_lineno"],
                           f"item {item_id}: no line in «## Phase Status»")
            else:
                row_dict, row_lineno = row
                if row_dict.get("Status") != status_val:
                    diag.error(path, row_lineno,
                               f"item {item_id}: status in Phase Status «{row_dict.get('Status')}» "
                               f"≠ status item «{status_val}»")
        for orphan_id, (row_dict, row_lineno) in table_by_id.items():
            diag.error(path, row_lineno,
                       f"Phase Status: string «{orphan_id}» without corresponding item")

        # --- item 🟢/🟠 ⇒ Completion Notes; 🟠 ⇒ Known Deviations -----------
        for item_id, occurrences in parsed["items"].items():
            item = occurrences[0]
            status_val, status_lineno = item["fields"].get("Status", ("", item["header_lineno"]))
            cn_val, cn_lineno = item["fields"].get("Completion Notes", ("", item["header_lineno"]))
            kd_val, kd_lineno = item["fields"].get("Known Deviations", ("", item["header_lineno"]))
            if status_val in (STATUS_DONE, STATUS_DEVIATIONS) and _is_empty(cn_val):
                diag.error(path, cn_lineno,
                           f"item {item_id}: status «{status_val}» requires non-empty Completion Notes")
            if status_val == STATUS_DEVIATIONS and _is_empty(kd_val):
                diag.error(path, kd_lineno,
                           f"item {item_id}: status «{status_val}» requires non-empty Known Deviations")

            # --- 🔴 ⇔ ESCALATION-block ⇔ Escalation Needed: yes ---------------
            en_val, en_lineno = item["fields"].get("Escalation Needed", ("", item["header_lineno"]))
            en_norm = (en_val or "").strip().lower()
            # 2.0 canonized (P0.3 rivers#4, SKILL §5): y Escalation Needed — and ONLY
            # he has a marker `no` is equal «—»; both are accepted without diagnostics.
            if en_norm in ("", EMPTY_PLACEHOLDER, "no"):
                en_yes = False
            elif en_norm == "yes":
                en_yes = True
            else:
                diag.error(path, en_lineno,
                           f"item {item_id}: Escalation Needed «{en_val}» — pending yes/no/—")
                en_yes = None
            is_blocked = status_val == STATUS_BLOCKED
            has_escalation = item["has_escalation"]
            if en_yes is not None and not (is_blocked == en_yes == has_escalation):
                parts = (f"Status={'🔴' if is_blocked else '≠🔴'}",
                         f"Escalation Needed={'yes' if en_yes else 'no/—'}",
                         f"ESCALATION-block={'yes' if has_escalation else 'no'}")
                diag.error(path, item["header_lineno"],
                           f"item {item_id}: mismatched {', '.join(parts)} (must match)")

            # --- WARNING: empty Required Reads/Validation for non-⬜ item -------
            if status_val and status_val != "⬜ Not started":
                rr_val, rr_lineno = item["fields"].get("Required Reads", ("", item["header_lineno"]))
                va_val, va_lineno = item["fields"].get("Validation", ("", item["header_lineno"]))
                if _is_empty(rr_val):
                    diag.warning(path, rr_lineno, f"item {item_id}: empty Required Reads at status «{status_val}»")
                if _is_empty(va_val):
                    diag.warning(path, va_lineno, f"item {item_id}: empty Validation at status «{status_val}»")

        # --- gate printed boundary codes pre_mutation/pre_final --
        _lint_write_site_codes_44(parsed["status_table"], parsed["items"], path, diag)

        # --- 🔴/⛔ are required to bear `Resume:` (opt-in Closure Protocol) --
        _lint_checkpointed_83(_meta_raw, parsed["items"], path, diag)

    # --- tiered-portability (committed-bundle plan without committed
    # execution input, or external path in the role execution input) ----------------
    _lint_tiered_portability_22(plan_dir, plan_id, all_items, phases, diag)
    _lint_next_runnable_bundle(plan_dir, layout, phases, all_items, diag)

    # --- global uniqueness ID item ---------------------------------
    seen = {}
    for pid, phase in phases.items():
        for item_id in phase.get("items", {}):
            seen.setdefault(item_id, []).append(pid)
    for item_id, pids in seen.items():
        if len(pids) > 1:
            diag.error(plan_dir, None, f"item {item_id}: ID reused in phases {sorted(set(pids))}")

    # --- duplicates Title among items (WARNING) --------------------------------
    titles = {}
    for item_id, info in all_items.items():
        titles.setdefault(info["title"], []).append(item_id)
    for title, ids in titles.items():
        if len(ids) > 1:
            diag.warning(plan_dir, None, f"take Title «{title}» among items: {sorted(ids)}")

    _lint_routing_coverage(plan_md, plan_id, layout, routing_rows, all_items, diag)
    if layout == "v2" and PLAN_ID_NUMBERED_RE.match(plan_id) and routing_rows:
        # Exercise the executor's only Batch compiler during lint too, so static
        # authoring checks cannot diverge from pre-mutation admission.
        from task import task_contract
        try:
            task_contract.compile_batch_routing(plan_dir)
        except task_contract.TaskContractBuildError as exc:
            diag.error(plan_md, None, f"Routing compiler: {exc}")

    # --- Status Board phase matched: counter 🟢/total and phase status --
    from task import plan_repeat
    try:
        aggregate_statuses = plan_repeat.aggregate_statuses(
            plan_dir, {iid: info['status'] for iid, info in all_items.items()})
    except (ValueError, OSError) as exc:
        diag.error(plan_md, None, str(exc))
        aggregate_statuses = {iid: info['status'] for iid, info in all_items.items()}
    board_by_phase = {row.get("Phase"): (row, lineno) for row, lineno in status_board}
    for pid in phases:
        row = board_by_phase.get(pid)
        if row is None:
            continue  # is already reported as a separate error above (phase without Status Board row)
        row_dict, row_lineno = row
        phase_item_ids = list(phases[pid].get("items", {}).keys())
        total = len(phase_item_ids)
        done = sum(1 for iid in phase_item_ids
                   if aggregate_statuses.get(iid) == STATUS_DONE)
        items_cell = row_dict.get(STATUS_BOARD_ITEMS_COL, "")
        m = DONE_TOTAL_RE.match(items_cell)
        if not m:
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: column «{STATUS_BOARD_ITEMS_COL}» = «{items_cell}» "
                       f"— expected format N/M")
        elif (int(m.group(1)), int(m.group(2))) != (done, total):
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: «{STATUS_BOARD_ITEMS_COL}» = «{items_cell}» "
                       f"≠ actual {done}/{total}")

        phase_status = row_dict.get("Status", "")
        item_statuses = [aggregate_statuses[iid] for iid in phase_item_ids if iid in all_items]
        terminal_block_override = plan_gates.terminal_blocked_phase_closure(plan_dir, pid)
        if (item_statuses and any(s == STATUS_BLOCKED for s in item_statuses)
                and phase_status != STATUS_BLOCKED
                and not (terminal_block_override and phase_status == STATUS_DEVIATIONS)):
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: yes 🔴 Blocked item, but phase status «{phase_status}» ≠ 🔴 Blocked")
        if (item_statuses and all(s == STATUS_DONE for s in item_statuses)
                and phase_status not in (STATUS_DONE, STATUS_IN_PROGRESS)):
            diag.error(plan_md, row_lineno,
                       f"Status Board {pid}: all items 🟢 Done, but phase status «{phase_status}» "
                       f"is not audit candidate 🟡 In progress or closed 🟢 Done")

        # --- 2.0 WARNING: [NEEDS CLARIFICATION] in phase 🟡+ = DoR-gate failed --
        if phase_status and phase_status != "⬜ Not started":
            nc = phases[pid].get("needs_clarification") or []
            if nc:
                diag.warning(phases[pid]["path"], nc[0],
                             f"phase {pid} in status «{phase_status}», but carries "
                             f"{len(nc)} marker(ov) [NEEDS CLARIFICATION] "
                             f"(lines {nc}) — DoR-gate failed (SKILL §7)")

        # --- WARNING: workflow-like-DoR — phase with status 🟡+, APPLICANT
        # orchestration (grabable sign), but there is no plan workflow-script in
        # `plans/<ID>/workflows/`. Convention: without a sign of orchestration - silent
        # (manual item-by-item execution workflow does not require). warning-only.
        if (phase_status and phase_status != "⬜ Not started"
                and phases[pid].get("declares_orchestration")
                and not _plan_has_workflow_script(plan_dir)):
            diag.warning(phases[pid]["path"], None,
                         f"phase {pid} states orchestration (multi-agent/fan-out), but no "
                         f"workflow-script in `plans/{plan_id}/workflows/` — DoR §7 (D29)")

        # --- phase 🟢/🟠 ⇒ Phase Handoff is not empty --------------------------
        if phase_status in (STATUS_DONE, STATUS_DEVIATIONS):
            handoff_text = phases[pid].get("phase_handoff")
            if handoff_text is None:
                pass  # the absence of a section is already reflected in a separate error
            elif _is_empty(handoff_text):
                closure_fresh = False
                if layout == "v2":
                    # Execution output belongs in the generated closure; editing
                    # authored phase prose would stale its immutable design audit.
                    from task import plan_closure
                    try:
                        plan_closure.build_closure(plan_dir, pid, check=True)
                        closure_fresh = True
                    except plan_closure.ClosureError:
                        pass
                if not closure_fresh:
                    diag.error(phases[pid]["path"], None,
                               f"phase {pid} status «{phase_status}», but «## Phase Handoff» empty")

        # --- WARNING: mirror gate - phase is NOT terminal, but Phase Handoff
        # APPROVES closure and is not marked with invalidation marker (H2, SKILL §3, 4-th step).
        # WARNING, not ERROR: three fleet plans (true positive, carve-out D34) otherwise
        # would get unreachable commit-gate in OTHER repositories.
        # the PHASE closing statement is read from the FIRST NON-EMPTY LINE of the block and
        # is removed by NEGATING it - otherwise the gate catches the word, not the subject (J1).
        elif phase_status and phase_status not in TERMINAL_STATUSES:
            handoff_text = phases[pid].get("phase_handoff")
            claim_line = phases[pid].get("phase_handoff_first_line") or ""
            if (handoff_text and not _is_empty(handoff_text)
                    and PHASE_HANDOFF_CLOSURE_RE.search(claim_line)
                    and not PHASE_HANDOFF_NEGATION_RE.search(claim_line)
                    and not phases[pid].get("phase_handoff_stale")):
                diag.warning(phases[pid]["path"], phases[pid].get("phase_handoff_lineno"),
                             f"Phase Handoff rotten: phase {pid} NOT closed (status "
                             f"«{phase_status}»), and the block approves the closing of the phase - put "
                             f"its first line marker «> DEPRECATED — phase reopened <D#>» "
                             f"(SKILL §3, 4-th step of reopen: the block is not deleted, it will be overwritten "
                             f"plan-close at the next phase close)")

    # --- phase closing report (opt-in `Closure Protocol | v1`) ----------
    _lint_closure_reports_81(plan_dir, plan_id, _meta_raw, phases, board_by_phase, diag)

    # D2 is a layout-v2 hard gate.  Its implementation stays outside this
    # coordinator; the gate delegates graph/weight/admission semantics to their
    # respective shared owners and contributes diagnostics at this one boundary.
    plan_gates.lint_read_budget(plan_dir, layout, diag)
    # Bundle freshness is checked above for the single next runnable item.  A
    # future item may legitimately require an artifact produced by its
    # predecessor, so validating every ready-looking item here would turn that
    # dependency into a false stop.
    plan_gates.lint_read_path_boundaries(plan_dir, layout, diag)
    plan_gates.lint_return_loop(plan_dir, layout, diag)

    # --- phase-first (WARNING): active 🟡 items in phase N+1 for non-terminal N
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
                         f"phase-first: {nxt_pid} contains active 🟡 items {sorted(active)}, "
                         f"although {pid} is not terminal yet (status «{cur_status}»)")

    # --- handoff.md ---------------------------------------------------------
    handoff_path = plan_dir / "handoff.md"
    handoff = parse_handoff_md(handoff_path, diag)

    # handoff.md ↔ Status Board «Pn a/b» — out `if handoff:`
    # block Next-resolver below (independent verification, form-neutral Next).
    _lint_handoff_board_113(handoff, handoff_path, plan_id, board_by_phase, diag)

    if handoff:
        next_val, next_lineno = handoff["fields"].get("Next", ("", None))

        # Title - the link must resolve, otherwise the extension regex'but simply
        # «resolved everything»: for BOTH forms (`after Pn` — phase, `after Pn.m` — item) gated
        # existence of PHASE `Pn`. Exception - bootstrap `P0.0` (fleet measurement: single
        # hit item-forms - start handoff, not a defect). The existence of the ITEM'a
        # `Pn.m` NOT gated: 12 fleet plans are carried `after P0.0` (the plan has not yet been touched upon,
        # item'a P0.0 does not happen) — gate on her = new ERROR fleet, back-compat prohibits.
        # Oracle «phase exists» — COMBINATION Status Board and phase files: this is a gate
        # dangling LINK, and out of sync board↔files - a separate defect with its own diagnostics
        # («phase Pn is in Status Board, but no phases/Pn.md»), there is nothing to duplicate it here.
        known_phases = set(phases) | set(board_by_phase)
        title_ref = handoff.get("title_ref")
        if title_ref and title_ref not in {HANDOFF_TITLE_BOOTSTRAP, "plan"}:
            title_phase = title_ref.split(".", 1)[0]
            if title_phase not in known_phases:
                diag.error(handoff_path, handoff.get("title_lineno"),
                           f"title: phase «{title_phase}» does not exist in the plan")

        # FORM `Next` IS DECLARED AS THE FIRST NON-EMPTY LINE OF THE FIELD. The field itself
        # MULTILINE: goes below launch-block (table Model/Thinking/Context/The bottom line +
        # code-block), and his prose legitimately QUOTES other forms enum'a - bare prompt
        # item'and, fixing the protocol itself, calls and slash-commands, and «plan closed».
        # The ENTIRE field resolver took this quote as an ad: handoff with «STARTING
        # MANUALLY» in the first line was catching false ERROR «not all items terminal».
        next_decl = next((ln for ln in next_val.splitlines() if ln.strip()), "")
        kind, m = _resolve_next_form(next_decl)
        if kind is None:
            # The declaration line did not name the form - back-compat: fleet plans that have
            # the first line is prosaic, and the command lives in launch-block'e, read as
            # before (resolve over the entire field).
            kind, m = _resolve_next_form(next_val)

        # New numbered layout-v2 plans keep the chosen batch visible at every
        # executable session boundary.  The handoff cannot silently collapse a
        # roadmap batch into an unlabelled single-item launch.
        if layout == "v2" and PLAN_ID_NUMBERED_RE.match(plan_id):
            execution_match = None
            if kind == "run":
                execution_match = m
            elif kind == "manual":
                execution_match = re.search(
                    r"(?:/|\b)task:plan-run\s+\S+\s+(P\d+\.\d+)", next_val)
            if kind in ("run", "manual"):
                batch_rows = [LAUNCH_BATCH_ROW_RE.match(line) for line in next_val.splitlines()]
                batch_values = [match.group(1).strip() for match in batch_rows if match]
                if not batch_values:
                    diag.error(handoff_path, next_lineno,
                               "handoff.Next: no line `| Batch | <id|solo> |`; "
                               "new execution boundary loses batch/solo")
                elif execution_match:
                    first_item = (execution_match.group(2) if kind == "run"
                                  else execution_match.group(1))
                    expected = next((row.get("Batch", "").strip() for row in routing_rows
                                     if first_item in row.get("_items", [])), None)
                    if expected and batch_values[0] != expected:
                        diag.error(handoff_path, next_lineno,
                                   f"handoff.Next: Batch «{batch_values[0]}» ≠ Routing «{expected}» "
                                   f"for {first_item}")
                    if expected and batch_values[0] == expected:
                        if kind == "run":
                            command_items = _handoff_run_items(next_decl)
                        else:
                            command_items = (_handoff_run_items(next_val)
                                             or re.findall(r"\bP\d+\.\d+\b", next_decl))
                        members = ([first_item] if expected.lower() == "solo" else sorted(
                            (item_id for row in routing_rows
                             if row.get("Batch", "").strip() == expected
                             for item_id in row.get("_items", [])
                             if all_items.get(item_id, {}).get("status") not in
                             (STATUS_DONE, STATUS_DEVIATIONS, STATUS_BLOCKED,
                              "⛔ Skipped by decision")),
                            key=lambda value: tuple(int(part) for part in value[1:].split(".")),
                        ))
                        if command_items != members:
                            diag.error(
                                handoff_path, next_lineno,
                                f"handoff.Next: Batch {expected} should address all remaining "
                                f"adjacent-suffix {members}, received {command_items}")

        # The continuity controller became a live write-site gate for plans
        # authored on/after its activation date.  Older layout-v2 carriers keep
        # their historical strings reader-side, but new handoffs must persist a
        # canonical reducer outcome (and the sole cold-start reason).
        if (layout == "v2" and PLAN_ID_DATED_RE.match(plan_id)
                and plan_id[:10] >= CONTINUITY_GATE_DATE
                and kind != "closed"):
            context_rows = [LAUNCH_CONTEXT_ROW_RE.match(line)
                            for line in next_val.splitlines()]
            contexts = [match.group(1).strip().strip("`")
                        for match in context_rows if match]
            if len(contexts) != 1:
                diag.error(
                    handoff_path, next_lineno,
                    "handoff.Next: continuity gate requires exactly one line `| Context | … |`",
                )
            else:
                try:
                    from task import plan_delivery
                    route = plan_delivery._route_from_lines(next_val.splitlines())
                    plan_delivery._continuity(route, allow_legacy=False)
                except (plan_continuity.ContinuityError, plan_delivery.DeliveryError) as exc:
                    diag.error(
                        handoff_path, next_lineno,
                        f"handoff.Next: CONTINUITY_CONTEXT_INVALID ({exc})",
                    )

        # --- C2: prosaic gate-disclaimer when runnable-form → WARNING ------
        # The author wrote in the ad runnable slash-form «there is a command, but not now»
        # (stem «not before»/«nothing to do»/time-gate) instead of structural form «WAITING».
        # Scan - AD LINE only (`next_decl`): guard-string `# NOT before:` forms
        # «WAITING» legally lives in code-block'should not trigger C2 (form waiting
        # is also not included in C2_RUNNABLE_KINDS). Level - WARNING (the mechanism is young, D20).
        if kind in C2_RUNNABLE_KINDS and C2_WAITING_STEMS_RE.search(next_decl):
            diag.warning(handoff_path, next_lineno,
                         "Next: runnable-form carries a prose clause about the unenforceability now "
                         "(«not before»/«nothing to do»/time-gate) — if the step is real, but "
                         "blocked by time/gate, declare the form «WAITING: <condition> → "
                         "<target form>» (SKILL §8): she copy-pasted from guard-line "
                         "`# NOT before:`, prosaic disclaimer - no")

        # --- 2.0: launch-block in handoff.Next (SKILL §8) --------------------------
        # Severity like brief-gate: date plans from BRIEF_CANON_DATE — ERROR
        # (the owner should not ask the model again/settings), older/legacy — WARNING.
        # Table `| Model | …`, legacy-string `| Command |` and code-block crawling all over
        # file: the template puts launch-block continued Next, but we don’t gate the exact location
        # (warning-level).
        # For a fully closed plan («plan closed») there is nothing to run - we don’t require it.
        # `continue-root` is not either user-facing launch: executor continues the same
        # admitted batch. Waiting remains boundary even if its historical Context
        # wrong/is compatible written as continue-root.
        # The condition is CONSCIOUSLY softer than the resolver (`kind`): any closure statement in
        # ANY place in the field removes the requirement launch-block'a. Tightening up `kind` would give
        # new WARNING live fleet plan (PILOT-AZG: the first line carries and «plan closed
        # in full», and lint-link `/task:plan-exec` → resolves as run) — back-compat §2.
        #
        # New canonical form always uses fenced command block is out of table. old
        # line `| Command |` continue to accept reader-side, so that format editing is not
        # invalidated already closed handoff's fleet.
        handoff_contexts = [match.group(1).strip().strip("`")
                            for match in (LAUNCH_CONTEXT_ROW_RE.match(line)
                                          for line in next_val.splitlines()) if match]
        needs_launch = (LITERAL_PLAN_CLOSED not in next_val.lower()
                        and (kind == "waiting" or handoff_contexts != ["continue-root"]))
        if needs_launch:
            has_table = any(LAUNCH_TABLE_ROW_RE.match(ln) for ln in handoff["lines"])
            has_command_row = any(LAUNCH_COMMAND_ROW_RE.match(ln) for ln in handoff["lines"])
            has_fence = any(CODE_FENCE_RE.match(ln) for ln in handoff["lines"])
            if not (has_table and (has_command_row or has_fence)):
                missing = []
                if not has_table:
                    missing.append("tables `| Model | …`")
                if not (has_command_row or has_fence):
                    missing.append("fenced command block (legacy: lines `| Command |`)")
                _lb_msg = ("Next without launch-block: no " + " and ".join(missing) +
                           " (form - snippets/launch-block-template.md)")
                if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
                    diag.error(handoff_path, next_lineno, _lb_msg)
                else:
                    diag.warning(handoff_path, next_lineno, _lb_msg)
        plan_closed = bool(all_items) and all(
            info["status"] in TERMINAL_STATUSES for info in all_items.values())

        def _check_plan_id(ref_plan_id):
            if ref_plan_id != plan_id:
                diag.error(handoff_path, next_lineno,
                           f"Next: PLAN-ID «{ref_plan_id}» ≠ actual «{plan_id}»")

        def _check_phase(ref_phase):
            if ref_phase not in phases:
                diag.error(handoff_path, next_lineno,
                           f"Next: phase «{ref_phase}» does not exist in the plan")

        def _check_item(ref_item):
            if ref_item not in all_items:
                diag.error(handoff_path, next_lineno,
                           f"Next: item «{ref_item}» does not exist in any phase")

        if kind == "manual":
            pass  # «MANUAL START: <model/effort>» — form without slash-commands, no links
        elif kind == "waiting":
            pass # «WAITING: <condition> → <target form>»: target command guarded in
                  # launch-block'e; ad links are not resolved (target form will be validated
                  # during real launch after removing the gate). launch-block required - same as
                  # others runnable-forms (not exempt): gate launch-block doesn't look above kind.
        elif kind == "run":
            ref_plan_id, ref_from, ref_to = m.group(1), m.group(2), m.group(3)
            _check_plan_id(ref_plan_id)
            _check_item(ref_from)
            if ref_to:
                _check_item(ref_to)
            requested = _routing_items(
                ref_from + (f"-{ref_to}" if ref_to else "")) or (
                    [ref_from, ref_to] if ref_to else [ref_from])
            _lint_priority_continuation(
                plan_dir, handoff_path, plan_id, requested, next_lineno, diag)
        elif kind == "audit-design":
            _check_plan_id(m.group(1))
        elif kind == "closed":
            if not plan_closed:
                diag.error(handoff_path, next_lineno,
                           "Next: «plan closed», but not all items terminal")
        elif kind == "design-item":
            ref_plan_id, ref_item = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            _check_item(ref_item)
            _lint_design_continuation(
                plan_dir, handoff_path, plan_id, ref_item.split(".", 1)[0], ref_item,
                next_lineno, diag)
        elif kind == "design-phase":
            ref_plan_id, ref_phase = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            if not plan_readiness.backlog_design_skeleton(plan_dir, ref_phase):
                _check_phase(ref_phase)
            _lint_design_continuation(
                plan_dir, handoff_path, plan_id, ref_phase, None, next_lineno, diag)
        elif kind in ("design-finish", "design-roadmap"):
            _check_plan_id(m.group(1))
        elif kind == "audit":
            ref_plan_id, ref_phase = m.group(1), m.group(2)
            _check_plan_id(ref_plan_id)
            _check_phase(ref_phase)
            if ref_phase in phases:
                row = board_by_phase.get(ref_phase)
                phase_status = row[0].get("Status", "") if row else ""
                phase_items = [
                    info for item_id, info in all_items.items()
                    if item_id.startswith(ref_phase + ".")
                ]
                terminal_candidate = bool(phase_items) and all(
                    info["status"] in TERMINAL_STATUSES for info in phase_items
                )
                if phase_status not in TERMINAL_STATUSES and not terminal_candidate:
                    diag.warning(handoff_path, next_lineno,
                                 f"Next: /task:plan-audit {ref_phase} — phase is not terminal: "
                                 f"status «{phase_status}», not all of her items terminal "
                                 f"(audit requires terminal phase candidate, SKILL §13)")
        elif kind == "close-archive":
            _check_plan_id(m.group(1))
            if not plan_closed:
                diag.warning(handoff_path, next_lineno,
                             "Next: /task:plan-close archive — the plan is not yet completely terminal")
        elif kind == "close":
            _check_plan_id(m.group(1))
            from task import plan_completion
            try:
                plan_completion.candidate(plan_dir)
            except (ValueError, OSError) as exc:
                diag.error(handoff_path, next_lineno, f"PLAN_CLOSE_NOT_READY: {exc}")
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


# --- root-level checks (path = plans/ whole, not single plans/<ID>) -----

def lint_plans_root(root, models, diag):
    """Checks that apply only to the directory `plans/` in full (see discover_plan_dirs:
    is different from single `plans/<ID>` because it's not there `plan.md` next to you).
    `models` — {plan_id: model|None} already linked subdirectories (to verify that
    Active points to a real-life directory plan, and to calculate 🟡 In progress).

    (a) yes plans/ACTIVE.md → field «**Active:**» must be «—» or name
        existing directory-plan, otherwise ERROR;
    (b) no ACTIVE.md and ≥2 plans with status «🟡 In progress» (Meta plan.md) →
        WARNING «active plan is ambiguous»;
    (in) flat *.md at the root plans/ (except ACTIVE.md/README.md) — drafts plan mode,
        remaining without protocol, → one WARNING with list and tooltip from-draft;
    (g) cross-plan reconciliation `## 7. Contracts`: Pinned consumer ≠ Donor versions of the same
        root → WARNING «notification not posted» (m7/D10, §11).
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
            diag.error(active_path, None, "no field «**Active:**» in ACTIVE.md")
        elif value != EMPTY_PLACEHOLDER and value not in models:
            diag.error(active_path, value_lineno,
                       f"Active «{value}» does not point to an existing plan "
                       f"(no directory plans/{value}/)")
    else:
        in_progress = sorted(
            pid for pid, model in models.items()
            if (model or {}).get("meta", {}).get("Status") == STATUS_IN_PROGRESS
        )
        if len(in_progress) >= 2:
            diag.warning(root, None,
                         "active plan is ambiguous: no plans/ACTIVE.md, and plans with "
                         f"status «{STATUS_IN_PROGRESS}» {len(in_progress)}: {in_progress}")

    drafts = sorted(
        p.name for p in root.glob("*.md")
        if p.is_file() and p.name not in (ACTIVE_FILENAME, README_FILENAME)
    )
    if drafts:
        diag.warning(root, None,
                     "drafts plan mode: " + ", ".join(drafts) +
                     " — expand /task:plan-design from-draft")


# --- discovery of many plans ----------------------------------------------

ARCHIVE_DIR_NAME = "archive"  # N3/D14: container of archived plans, not a plan itself
ARCHIVED_V2_STRICT_CUTOFF = "2026.09.09"


def _is_historical_archive(plan_id: str) -> bool:
    """Keep pre-cutover archived v2 carriers out of the mutable root gate.

    An archive preserves the protocol that produced it.  Root-wide validation
    must not turn later rules (state projection, downstream receipt or handoff
    shape) into a demand to rewrite append-only historical evidence.  Explicit
    linting of a named plan remains available for forensic work.
    """
    return bool(PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] < ARCHIVED_V2_STRICT_CUTOFF)


def discover_plan_dirs(root):
    """path — or himself plans/<ID> (yes plan.md), or plans/ (searching through subdirectories).
    `plans/archive/` does NOT participate in the search as a plan (N3/D14). From his
    subdirectories, only the current linter remains executable Layout v2;
    historical v1/missing-layout bytes are inert source archive and
    are checked by the old compatible tag."""
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
            for archived in sorted(p.iterdir()):
                if (not archived.is_dir() or archived.name.startswith(".")
                        or archived.name == "__pycache__"):
                    continue
                try:
                    plan_text = (archived / "plan.md").read_text(encoding="utf-8")
                except OSError:
                    continue
                if (re.search(r"^\|\s*Layout\s*\|\s*v2\s*\|", plan_text, re.MULTILINE)
                        and not _is_historical_archive(archived.name)):
                    dirs.append(archived)
            continue
        dirs.append(p)
    return dirs


# --- --conflicts: canon ↔ implementation -----
# Conflict scan checks EN-only `SKILL.md` with implementation constant registries.
# Exact literals reuse the common `CANON_LITERALS`, and not the second registry.
#
# Works WITHOUT plan argument (Implementation Rule 5): checks canon ARTIFACTS, not
# specific `plans/<ID>`. Each reconciliation is structural (code-fence/backtick span/marked
# list - stable anchor), not a heuristic parser of free prose (Implementation Rule 3).
# The find carries BOTH sides `file:string` (Implementation Rule 4). `--conflicts` nothing
# ANNOUNCES - compares canon and existing registries `plan_lint.py`; singular
# exception - `CONTEXT_VALUES` (see her comment above), which this item enters exactly
# then for the class «values Context» there was WHAT to compare (without it, checking this
# class is structurally impossible - Scope Included this item'but directly demands it as one of
# six edges).

__all__ = tuple(name for name in globals() if not name.startswith("__"))
