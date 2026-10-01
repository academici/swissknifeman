"""Parsers and carrier-local structural checks for executable plans."""
from .common import *
from .policy import *
from task import journal as plan_journal
from task import plan_decisions
from task import plan_item_state
from task import terminal_policy


def _lint_plan_md_20(lines, path, diag):
    """Warning-schema checks 2.0 on top plan.md (do not touch existing behavior):
    (a) order/headers of numbered sections `## 0-6` (P0.3 rivers#6);
    (b) Update Log: cell «What» longer UPDATE_LOG_MAX_CHARS (P0.3 rivers#5);
    (in) D-log s ≥3 solutions without a single RAG-token - missing heuristic
        carrier fact markings (SKILL §7)."""
    # (a) numbered sections: numbers in ascending order, headings depend on layout.
    numbered = []
    for i, ln in enumerate(lines):
        m = PLAN_SECTION_NUM_RE.match(ln)
        if m:
            numbered.append((int(m.group(1)), m.group(2), i + 1))
    nums = [n for n, _, _ in numbered]
    if nums != sorted(nums):
        diag.warning(path, numbered[0][2],
                     f"sections plan.md are out of order: {nums} (canon - ## 0…6 ascending)")
    try:
        layout = plan_layout.layout_version(Path(path).parent)
    except plan_layout.PlanLayoutError:
        layout = "v2"
    expected_titles = {**PLAN_SECTION_TITLES, 4: "Update Log"}
    for n, title, lineno in numbered:
        expected = expected_titles.get(n)
        if expected and title != expected:
            diag.warning(path, lineno,
                         f"section «## {n}. {title}» ≠ canonical «## {n}. {expected}»")

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
                             f"Update Log: entry «What» {len(what)} characters > "
                             f"{UPDATE_LOG_MAX_CHARS} — canon: ≤2 lines + link to "
                             "Completion Notes, not a retelling")
        try:
            decisions = plan_decisions.load_decisions(Path(path).parent)
        except plan_decisions.DecisionError:
            return  # the decision parser/projector reports the carrier defect.
        if len(decisions) >= 3 and not any(RAG_MARKER_RE.search(decision.body)
                                           for decision in decisions):
            diag.warning(Path(path).parent / "decisions", 0,
                         f"Decision Log: {len(decisions)} solutions and not a single marker "
                         f"«RAG:✅»/«RAG:{EMPTY_PLACEHOLDER}»/«[UNVERIFIED]» — carriers "
                         "facts are not marked (SKILL §7)")
        return

    # (b) Update Log — limit «What»
    _, ul_body, ul_start = _find_section(lines, UPDATE_LOG_HEADER_RE)
    if ul_body is not None:
        headers, rows, _ = _parse_table(ul_body, ul_start)
        if headers and "What" in headers:
            for row, lineno in rows:
                what_val = row.get("What", "")
                if len(what_val) > UPDATE_LOG_MAX_CHARS:
                    diag.warning(path, lineno,
                                 f"Update Log: entry «What» {len(what_val)} characters > "
                                 f"{UPDATE_LOG_MAX_CHARS} — canon: ≤2 lines + link to "
                                 f"Completion Notes, not a retelling")

    # (in) D-log ≥3 solutions without a single RAG-marker
    _, dl_body, dl_start = _find_section(lines, DECISION_LOG_HEADER_RE)
    if dl_body is not None:
        _, rows, _ = _parse_table(dl_body, dl_start)
        if len(rows) >= 3 and not any(
                RAG_MARKER_RE.search(" ".join(str(v) for v in row.values()))
                for row, _ in rows):
            diag.warning(path, dl_start,
                         f"Decision Log: {len(rows)} solutions and not a single marker "
                         f"«RAG:✅»/«RAG:{EMPTY_PLACEHOLDER}»/«[UNVERIFIED]» — carriers "
                         f"facts are not marked (SKILL §7)")


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
        diag.error(plan_md, None, "Layout v2: no section «## 5. Decision Log»")
    else:
        text = "\n".join(body).strip()
        if "|" in text or "decisions/" not in text or "plan-views.py decisions" not in text:
            diag.error(plan_md, start,
                       "Layout v2: Decision Log must be a pointer string to decisions/ and plan-views.py decisions")
    if any(re.match(r"^##\s+(?:\d+\.\s+)?Discussion\s*$", line) for line in plan_lines):
        diag.error(plan_md, None, "Layout v2: «## Discussion» prohibited; use open-questions.md")
    if not (Path(plan_dir) / "decisions").is_dir():
        diag.error(plan_md, None, "Layout v2: missing directory decisions/")


# --- m7/D10: section parser `## 7. Contracts` -----------------------------------

def _contract_key(value):
    """Contract name normalization - last path segment: donor writes
    , consumer - `REGHUB/root/contracts/…`."""
    return (value or "").strip().strip("`").rsplit("/", 1)[-1]


def _semver_tuple(value):
    """`v2.0.2` → (2, 0, 2); we do not support pre-releases. No match → None."""
    m = SEMVER_RE.search(value or "")
    return tuple(int(g) for g in m.groups()) if m else None


def parse_contracts(lines, path, diag):
    """Optional section `## 7. Contracts` → {"exported": [...], "consumed": [...]}.
    No section - silently empty model (absence is not a defect). Crooked columns/subsections -
    WARNING (mechanism is young: ERROR would break back-compat-gate)."""
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
                     "«## 7. Contracts»: no subsections «### Exported» / «### Consumed»")
        return model

    expected = {"exported": EXPORTED_COLUMNS, "consumed": CONSUMED_COLUMNS}
    for pos, (kind, start) in enumerate(subs):
        end = subs[pos + 1][1] if pos + 1 < len(subs) else len(body)
        headers, rows, header_lineno = _parse_table(body[start + 1:end],
                                                    body_start + start + 1)
        title = kind.capitalize()
        if headers is None:
            diag.warning(path, body_start + start, f"«### {title}»: table not found")
            continue
        if tuple(headers) != expected[kind]:
            diag.warning(path, header_lineno,
                         f"«### {title}»: columns {headers} ≠ canonical "
                         f"{list(expected[kind])}")
            continue
        for row, lineno in rows:
            model[kind].append({**row, "_lineno": lineno})
    return model


def _lint_contracts_cross_plan(models, diag):
    """(m7/D10) Reconciliation of consumers with donors WITHIN the same root `plans/`.
    Communication is built FROM the consumer (`Consumed.Donor plan`) — the only deterministic
    direction. Donor outside the root (cross-repo) not checked - boundary §11.
    `Pinned` ≠ `Version` donor → WARNING «notification not posted»."""
    exported = {}  # (plan_id, contract_key) -> version-string
    for pid, model in models.items():
        for row in (model or {}).get("contracts", {}).get("exported", []):
            key = _contract_key(row.get("Contract"))
            if key:
                exported[(pid, key)] = (row.get("Version") or "").strip()

    for pid, model in models.items():
        plan_md = Path((model or {}).get("path", pid)) / "plan.md"
        for row in (model or {}).get("contracts", {}).get("consumed", []):
            donor = (row.get("Donor plan") or "").strip()
            key = _contract_key(row.get("Contract"))
            donor_ver = exported.get((donor, key))
            if donor_ver is None:
                continue  # there is no donor in this root - the linter is honestly silent (§11)
            pinned = (row.get("Pinned") or "").strip()
            dv, pv = _semver_tuple(donor_ver), _semver_tuple(pinned)
            if dv is None or pv is None or dv == pv:
                continue
            diag.warning(plan_md, row.get("_lineno"),
                         f"donor {donor}: contract {key} = {donor_ver}, consumer {pid} "
                         f"pinned to {pinned} — notification not posted (§11)")


# --- Layer 0 «brief» — required plan input (SKILL §16) ------------------------
# From this date (dated PLAN-ID) absence brief/ — ERROR; older/legacy — WARNING
# (back-compat: we don’t break existing plans, new ones without a brief are not approved).
BRIEF_CANON_DATE = "2026.07.16"


def _lint_plan_brief_20(plan_dir, plan_id, diag):
    """brief/ — layer 0 «input»: reformulated without loss of thoughts original
    owner message (00-brief.md) + added dated clarifications.
    Task: it is clear from the plan «what was at the input → what we came to». Plan without brief/
    fails approval (SKILL §16)."""
    plan_dir = Path(plan_dir)
    brief_dir = plan_dir / "brief"
    has_md = brief_dir.is_dir() and any(
        f.is_file() and f.stat().st_size > 0 for f in brief_dir.glob("*.md"))
    if has_md:
        return
    msg = (f"no layer 0 «brief»: {plan_dir.name}/brief/ with ≥1 non-empty .md "
           f"(00-brief.md — reformulated owner input, clarifications are being added; "
           f"SKILL §16)")
    if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
        diag.error(plan_dir / "plan.md", None, msg)
    else:
        diag.warning(plan_dir / "plan.md", None, msg)


def _lint_plan_roadmap_20(plan_dir, plan_id, phase_files, diag):
    """roadmap.md is required when the plan is fully detailed (no skeleton markers
    in no phase) — SKILL §8: execution occurs in batches according to the performance map,
    and not individual babysitting. Severity like brief-gate: date plans from
    BRIEF_CANON_DATE — ERROR, older/legacy — WARNING."""
    plan_dir = Path(plan_dir)
    if not phase_files:
        return
    for path in phase_files.values():
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(SKELETON_MARKER_RE.match(ln) for ln in text.splitlines()):
            return  # there are skeletons - the plan is still in authoring, roadmap not required
    rm = plan_dir / "roadmap.md"
    if rm.is_file() and rm.stat().st_size > 0:
        return
    msg = (f"plan fully detailed (no skeleton markers), a {plan_dir.name}/roadmap.md "
           f"missing - performance card required (SKILL §8)")
    if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
        diag.error(plan_dir / "plan.md", None, msg)
    else:
        diag.warning(plan_dir / "plan.md", None, msg)


# --- Log Layer/index - soft/hard-gate by date-cutoff ------------
# Date plans FROM this date must be valid journal.jsonl (ERROR); older/
# legacy — WARNING (same pattern as brief/roadmap-gates, back-compat — do not break
# fleet already on its way). Cutoff = sealing date of this canon: plan
# itself dated from this date is obliged to backfill its journal.jsonl
# BEFORE committing this edit, otherwise it catches your own first ERROR-gate.
JOURNAL_CANON_DATE = "2026.07.18"


def _lint_journal_exceptions_20(plan_dir, plan_id, report):
    """Validates optional append-only sidecar historical schema exceptions.

    Returns ``target_line -> exception`` only for fully valid records.
    Sidecar is not an event log and structurally cannot form
    correction-loop: its target is always a separate string ``journal.jsonl``.
    """
    exceptions_path = Path(plan_dir) / _journal.EXCEPTIONS_FILENAME
    if not exceptions_path.is_file():
        return {}
    try:
        lines = exceptions_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        report(exceptions_path, None, "journal exceptions sidecar not readable (encoding/IO)")
        return {}
    if not any(line.strip() for line in lines):
        report(exceptions_path, None, "journal exceptions sidecar empty")
        return {}

    by_target = {}
    for i, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            exception = json.loads(raw)
        except json.JSONDecodeError as exc:
            report(exceptions_path, i,
                   f"string is not valid JSON (append-only exception NDJSON): {exc}")
            continue
        try:
            _journal.validate_exception_target(
                plan_dir, exception, check_duplicate=False)
        except _journal.JournalValidationError as exc:
            report(exceptions_path, i, f"schema exception contract fails: {exc}")
            continue

        target_line = exception["target_line"]
        if target_line in by_target:
            report(exceptions_path, i,
                   f"duplicate schema exception for journal.jsonl:{target_line}")
            continue
        by_target[target_line] = exception
    return by_target


def _lint_plan_journal_20(plan_dir, plan_id, diag):
    """journal.jsonl — append-only NDJSON,
    one record per execution item'and any launch `/task:plan-*`. Absence/empty/
    invalid file - ERROR for date plans from JOURNAL_CANON_DATE, WARNING for
    older/legacy. The recording scheme is reused from `task.journal` (SSOT — do not duplicate enum's)."""
    plan_dir = Path(plan_dir)
    jf = plan_dir / _journal.FILENAME
    is_dated_new = bool(PLAN_ID_DATED_RE.match(plan_id)) and plan_id[:10] >= JOURNAL_CANON_DATE
    report = diag.error if is_dated_new else diag.warning

    if not jf.is_file() or jf.stat().st_size == 0:
        report(plan_dir / "plan.md", None,
               f"no {plan_dir.name}/{_journal.FILENAME} (append-only history "
               f"execution, P1.1) or the file is empty is written close-protocol "
               f"/task:plan-* (lib/task/journal.py)")
        return

    try:
        lines = jf.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError):
        report(jf, None, "journal.jsonl not readable (encoding/IO)")
        return

    exceptions = _lint_journal_exceptions_20(plan_dir, plan_id, report)

    parsed_entries = []
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        try:
            entry = json.loads(ln)
        except json.JSONDecodeError as e:
            report(jf, i + 1, f"string is not valid JSON (append-only NDJSON, §1): {e}")
            continue
        if isinstance(entry, dict) and entry.get("plan_id") != plan_id:
            report(
                jf,
                i + 1,
                f"event plan_id «{entry.get('plan_id')}» ≠ canonical plan directory "
                f"«{plan_id}»; mismatch does not allow schema exception",
            )
        errors = _journal.entry_validation_errors(entry)
        if errors and i + 1 not in exceptions:
            message = "; ".join(error for _, error in errors)
            report(jf, i + 1, f"record does not pass the schema P1.1: {message}")
            continue
        parsed_entries.append((i + 1, entry))

    current_entries = set()
    by_item = {}
    for _line_number, entry in parsed_entries:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("item_id")
        if not isinstance(item_id, str):
            continue
        by_item.setdefault(item_id, []).append(entry)
    for entries in by_item.values():
        current = plan_item_state.latest_execution_event(entries)
        if current is not None:
            current_entries.add(id(current))

    for line_number, entry in parsed_entries:
        if _terminal_policy_is_active(entry):
            try:
                terminal_policy.validate_entry(
                    entry,
                    plan_dir=plan_dir if id(entry) in current_entries else None,
                )
            except terminal_policy.TerminalPolicyError as exc:
                report(jf, line_number, str(exc))


def _lint_plan_index_20(plan_dir, plan_id, diag):
    """index.md — file map+provenance,
    OPTIONAL (is not a carrier of fact, unlike a journal/brief - P1.2 §1). Absence -
    ALWAYS WARNING, regardless of plan date (no ERROR-branches as opposed to log)."""
    plan_dir = Path(plan_dir)
    idx = plan_dir / "index.md"
    if not idx.is_file() or idx.stat().st_size == 0:
        diag.warning(plan_dir / "plan.md", None,
                     f"no {plan_dir.name}/index.md (file map + provenance "
                     f"findings/research→phase, P1.2, optional) — snippet "
                     f"snippets/index-template.md")


# --- warning-checks: ID / workflow-scripts / supersedes ----

def _lint_plan_identity_20(plan_dir, plan_id, meta, plan_md, diag):
    """Three WARNING-plan identity checks (all - warning, back-compat D24):
    (1) directory-name vs. union PLAN-ID-patterns;
    (2) workflow-scripts (`*.js` c `export const meta`) out `plans/<ID>/workflows/`
        or with a non-canonical name - two separate messages (place / name);
    (3) plan without Meta `supersedes` when the code name matches the archive one.
    `meta` — dict[name] = (value, lineno) from parse_plan_md (maybe None/empty)."""
    plan_dir = Path(plan_dir)
    meta = meta or {}

    # Short IDs are opt-in for legacy plans; allocation spans live + archive.
    short_id, short_line = meta.get("Short ID", (None, None))
    if short_id is not None:
        if not re.fullmatch(r"PLAN[1-9][0-9]*", short_id):
            diag.error(plan_md, short_line, "Short ID should look like PLAN<N>, N > 0")
        else:
            plans_root = plan_dir.parent.parent if plan_dir.parent.name == "archive" else plan_dir.parent
            candidates = list(plans_root.glob("*/plan.md"))
            candidates.extend(plans_root.glob("archive/*/plan.md"))
            for peer_md in sorted(candidates):
                if peer_md.parent.name == plan_id:
                    continue  # live/archive copies are one existing identity
                peer_lines = _read_lines(peer_md) or ()
                _, peer_meta, _ = _find_section(peer_lines, META_HEADER_RE)
                for line in peer_meta or ():
                    match = re.fullmatch(r"\s*\|\s*Short ID\s*\|\s*(PLAN[1-9][0-9]*)\s*\|\s*", line)
                    if match and match.group(1) == short_id:
                        diag.error(plan_md, short_line,
                                   f"Short ID {short_id} duplicate {peer_md.relative_to(plans_root)}")
                        break

    # (1) PLAN-ID: historical forms readable, but new date plans
    # are required to bear `№N`; ordinal linked to Title and is unique within the date.
    if not (PLAN_ID_LEGACY_RE.match(plan_id) or PLAN_ID_DATED_RE.match(plan_id)):
        diag.warning(plan_dir, None,
                     f"directory-plan name «{plan_id}» is not canon PLAN-ID "
                     f"(old `[A-Z][A-Z0-9-]+` OR new "
                     f"`YYYY.MM.DD-№N-CODE-NAME`)")

    numbered = PLAN_ID_NUMBERED_RE.match(plan_id)
    numbered_candidate = PLAN_ID_NUMBERED_CANDIDATE_RE.match(plan_id)
    if (PLAN_ID_LEGACY_DATED_RE.match(plan_id)
            and plan_id[:10] >= NUMBERED_PLAN_ID_CANON_DATE):
        diag.error(plan_dir, None,
                   f"new date PLAN-ID «{plan_id}» requires a sequence number: "
                   "`YYYY.MM.DD-№N-CODE-NAME`")
    if numbered_candidate and int(numbered_candidate.group("ordinal")) == 0:
        diag.error(plan_dir, None, "sequence number PLAN-ID must be positive")
    if numbered:
        ordinal = numbered.group("ordinal")
        title = (meta.get("Title", ("", None))[0] or "").strip()
        expected_prefix = f"Plan №{ordinal}"
        if not (title == expected_prefix or title.startswith(expected_prefix + " — ")):
            diag.error(plan_md, meta.get("Title", ("", None))[1],
                       f"Title must start with «{expected_prefix} — …» "
                       f"for PLAN-ID «{plan_id}»")

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
                       f"PLAN-ID «{plan_id}» duplicates the sequence number "
                       f"№{ordinal} for {numbered.group('date')}: {', '.join(sorted(duplicates))}")

    codename = _plan_codename(plan_id)

    # (2) place/name workflow-scripts (only `.js` with marker `export const meta`)
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
                         f"workflow-script «{rel}» out `plans/{plan_id}/workflows/` — "
                         f"only house workflow-plan scripts (D28)")
        if not name_re.match(js.name):
            diag.warning(js, None,
                         f"workflow-script «{js.name}» with a non-canonical name - "
                         f"canon `wf-{codename}-<purpose>.js` (D28)")

    # (3) supersedes: code name matches archive plan without Meta supersedes
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
                         f"plan «{plan_id}» repeats codename «{codename}» archived "
                         f"plan, but does not carry Meta `supersedes` — wave continuity "
                         f"track not declared (D27)")


# --- parsing schema files --------------------------------------------------------------

def parse_plan_md(path, diag):
    """plan.md → (meta: dict[name]=(value,lineno), status_board: list[(row,lineno)])."""
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "plan.md missing or unreadable")
        return None, []

    _lint_plan_md_20(lines, path, diag)

    try:
        layout = plan_layout.layout_version(Path(path).parent)
    except plan_layout.PlanLayoutError:
        layout = "v2"

    meta = {}
    _, meta_body, meta_start = _find_section(lines, META_HEADER_RE)
    if meta_body is None:
        diag.error(path, None, "no section «## 0. Meta»")
    else:
        headers, rows, header_lineno = _parse_table(meta_body, meta_start)
        if headers is None:
            diag.error(path, meta_start, "Meta: table `Field|Meaning` not found")
        elif tuple(headers) != META_TABLE_COLUMNS:
            diag.error(path, header_lineno,
                       f"Meta: columns {headers} ≠ expected {list(META_TABLE_COLUMNS)}")
        else:
            for row, lineno in rows:
                meta[row.get("Field", "")] = (row.get("Meaning", ""), lineno)
        required_fields = V2_CORE_META_FIELDS if layout == "v2" else REQUIRED_META_FIELDS
        for field in required_fields:
            if field not in meta:
                diag.error(path, meta_start, f"Meta: no required field «{field}»")

    if layout == "v2":
        numbered = {int(match.group(1)): match.group(2)
                    for line in lines if (match := PLAN_SECTION_NUM_RE.match(line))}
        allowed = {0, 1, 2, 3, 4, 5, 7}
        for number in sorted(set(numbered) - allowed):
            diag.error(path, None,
                       f"Layout v2: section «## {number}. {numbered[number]}» is not part of the closed kernel")
        for field in V2_STATUS_META_FIELDS:
            if field in meta:
                diag.error(path, meta[field][1],
                           f"Layout v2: field Meta «{field}» lives only in status.md")
        try:
            status_meta, status_board = plan_status.parse_status_view(Path(path).parent)
        except plan_status.StatusError as exc:
            diag.error(Path(path).parent / "status.md", None, str(exc))
            return meta, []
        meta.update(status_meta)
        core_row = plan_layout.registry().get("plan-core", {})
        if core_row.get("volatility") not in ("stable", "slow"):
            diag.error(path, None,
                       "Layout v2: plan-core not declared stable/slow in the media registry")
        return meta, status_board

    status_board = []
    _, board_body, board_start = _find_section(lines, STATUS_BOARD_HEADER_RE)
    if board_body is None:
        diag.error(path, None, "no section «## 4. Phase Index & Status Board»")
    else:
        headers, rows, header_lineno = _parse_table(board_body, board_start)
        if headers is None:
            diag.error(path, board_start, "Status Board: table not found")
        elif tuple(headers) != STATUS_BOARD_COLUMNS:
            diag.error(path, header_lineno,
                       f"Status Board: columns {headers} ≠ expected {list(STATUS_BOARD_COLUMNS)}")
        else:
            status_board = rows
            for row, lineno in rows:
                st = row.get("Status", "")
                if st not in STATUSES:
                    diag.error(path, lineno, f"Status Board: invalid status «{st}»")
                if not PHASE_TOKEN_RE.match(row.get("Phase", "")):
                    diag.error(path, lineno,
                               f"Status Board: Phase «{row.get('Phase')}» doesn't look like Pn")

    return meta, status_board


def _parse_v2_item_file(path, item_id, diag):
    """Read one handwritten item spec plus its generated state carrier."""
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "technical specification file item is missing or unreadable")
        return None
    item_blocks = [item for item in _find_items(lines) if item[0] == item_id]
    if len(item_blocks) != 1:
        diag.error(path, None,
                   f"item {item_id}: exactly one header expected «### {item_id} — …»")
        return None
    actual_id, title, header_lineno, body_lines, body_start = item_blocks[0]
    fields, duplicates = _parse_fields(body_lines, body_start, FIELD_RE)
    for field in ITEM_SPEC_FIELDS:
        if field not in fields:
            diag.error(path, header_lineno, f"item {item_id}: no TK field «{field}»")
    for field in ITEM_STATE_FIELDS:
        if field in fields:
            diag.error(path, fields[field][1],
                       f"item {item_id}: origin field «{field}» is prohibited in the technical specification file")
    for field, (_value, lineno) in fields.items():
        if field not in ITEM_SPEC_FIELDS and field not in ITEM_STATE_FIELDS and field != "Authority":
            diag.error(path, lineno,
                       f"item {item_id}: field «{field}» is not included in the closed list of the technical specifications file")
    for name, first_ln, first_val, dup_ln, dup_val in duplicates:
        if name in ITEM_SPEC_FIELDS or name == "Authority":
            diag.error(path, dup_ln,
                       f"item {item_id}: TK field «{name}» occurs repeatedly "
                       f"(first {path.name}:{first_ln} → «{_preview(first_val)}», "
                       f"repeat {path.name}:{dup_ln} → «{_preview(dup_val)}»)")

    canonical_index = {field: index for index, field in enumerate(ITEM_SPEC_FIELDS)}
    present_order = [field for field in fields if field in canonical_index]
    if present_order != sorted(present_order, key=canonical_index.get):
        diag.warning(path, header_lineno,
                     f"item {item_id}: fields are not in canonical order "
                     "(canon - SKILL §5 / phase-template)")

    state_path = path.with_name(path.stem + ".state.md")
    state_lines = _read_lines(state_path)
    if state_lines is None:
        diag.error(state_path, None, f"item {item_id}: required state snapshot missing or unreadable")
        return None
    state_fields, state_duplicates = _parse_fields(state_lines, 1, FIELD_RE)
    for field in ITEM_STATE_FIELDS:
        if field not in state_fields:
            diag.error(state_path, None, f"item {item_id}: there is no outcome field in the nugget «{field}»")
    for field in ITEM_SPEC_FIELDS:
        if field in state_fields:
            diag.error(state_path, state_fields[field][1],
                       f"item {item_id}: TK field «{field}» not allowed in status nugget")
    for field, (_value, lineno) in state_fields.items():
        if field not in ITEM_STATE_FIELDS and field not in ITEM_SPEC_FIELDS:
            diag.error(state_path, lineno,
                       f"item {item_id}: field «{field}» is not in the private list of the status nugget")
    for name, first_ln, first_val, dup_ln, dup_val in state_duplicates:
        if name in ITEM_STATE_FIELDS:
            diag.error(state_path, dup_ln,
                       f"item {item_id}: origin field «{name}» occurs repeatedly "
                       f"(first {state_path.name}:{first_ln} → «{_preview(first_val)}», "
                       f"repeat {state_path.name}:{dup_ln} → «{_preview(dup_val)}»)")

    merged = {}
    if "Authority" in fields:
        merged["Authority"] = fields["Authority"]
    for field in REQUIRED_ITEM_FIELDS:
        if field in fields:
            merged[field] = fields[field]
        elif field in state_fields:
            merged[field] = state_fields[field]
    status_value, status_lineno = merged.get("Status", ("", header_lineno))
    if status_value and status_value not in STATUSES:
        diag.error(state_path, status_lineno,
                   f"item {item_id}: invalid status «{status_value}»")
    return {"title": title, "header_lineno": header_lineno, "fields": merged,
            "has_escalation": any(ESCALATION_RE.match(line)
                                    and ESCALATION_RE.match(line).group(1) == actual_id
                                    for line in (*lines, *state_lines)),
            "spec_lines": lines, "state_lines": state_lines}


def _parse_phase_v2(path, phase_id, diag):
    """Assemble a v2 phase model from its thin index, item specs, and states."""
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "phase index missing or unreadable")
        return None
    if _find_section(lines, PHASE_STATUS_HEADER_RE)[1] is not None:
        diag.error(path, None, "Layout v2: «## Phase Status» not allowed in thin phase index")
    if _find_items(lines):
        diag.error(path, None, "Layout v2: item-blocks live only in separate technical specification files")

    _, ctx_body, _ = _find_section(lines, PHASE_CONTEXT_HEADER_RE)
    if ctx_body is None:
        diag.error(path, None, "no section «## Phase Context»")
    is_skeleton = bool(ctx_body and any(SKELETON_MARKER_RE.match(line) for line in ctx_body))
    _, handoff_body, handoff_start = _find_section(lines, PHASE_HANDOFF_HEADER_RE)
    if handoff_body is None:
        diag.error(path, None, "no section «## Phase Handoff»")
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
                   f"Layout v2: could not be retrieved journal-backed Updated: {exc}")
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
                         f"item {item_id}: {empty}/{len(REQUIRED_ITEM_FIELDS)} fields are empty, "
                         "and in Phase Context no marker «> SKELETON — not detailed…» — "
                         "either detail or mark the phase with a skeleton")

    return {"status_table": status_table, "items": items, "phase_handoff": handoff_text,
            "phase_handoff_stale": bool(PHASE_HANDOFF_STALE_RE.match(handoff_first_line)),
            "phase_handoff_lineno": handoff_lineno, "phase_handoff_first_line": handoff_first_line,
            "is_skeleton": is_skeleton,
            "needs_clarification": [i + 1 for i, line in enumerate(gate_lines)
                                    if NEEDS_CLARIFICATION_RE.search(line)],
            "declares_orchestration": any(phase_declares_orchestration(line)
                                           for line in orchestration_lines)}


def parse_phase_md(path, phase_id, diag, *, layout="v2"):
    """phases/Pn.md → dict with status_table/items/handoff (see lint_plan)."""
    if layout == "v2":
        return _parse_phase_v2(path, phase_id, diag)
    diag.error(path, None, "PLAN_LAYOUT_V1_RETIRED: is executed only Layout v2")
    return None

    # Historical parser retained below only for source archive compatibility.
    lines = _read_lines(path)
    if lines is None:
        diag.error(path, None, "phase file missing or unreadable")
        return None

    status_table = []
    _, ps_body, ps_start = _find_section(lines, PHASE_STATUS_HEADER_RE)
    if ps_body is None:
        diag.error(path, None, "no section «## Phase Status»")
    else:
        headers, rows, header_lineno = _parse_table(ps_body, ps_start)
        if headers is None:
            diag.error(path, ps_start, "Phase Status: table not found")
        elif tuple(headers) != PHASE_STATUS_COLUMNS:
            diag.error(path, header_lineno,
                       f"Phase Status: columns {headers} ≠ expected {list(PHASE_STATUS_COLUMNS)}")
        else:
            status_table = rows
            for row, lineno in rows:
                st = row.get("Status", "")
                if st not in STATUSES:
                    diag.error(path, lineno, f"Phase Status: invalid status «{st}»")

    for bad_ln, lineno in _malformed_item_headers(lines):
        diag.error(path, lineno,
                    f"header item does not match regex `^### (P\\d+\\.\\d+) — `: «{bad_ln}»")

    # --- 2.0: skeleton marker in Phase Context (legalizes empty fields items) ------
    is_skeleton = False
    _, ctx_body, _ = _find_section(lines, PHASE_CONTEXT_HEADER_RE)
    if ctx_body is not None:
        is_skeleton = any(SKELETON_MARKER_RE.match(ln) for ln in ctx_body)

    # --- region of BOTH greps in phase - before the first `## Audit` (append-block
    # audit legitimately quotes the markers on which it is reporting; see AUDIT_BLOCK_HEADER_RE)
    gate_lines = _lines_before_audit(lines)

    # --- 2.0: markers [NEEDS CLARIFICATION] — are lined into lint_plan by phase status
    needs_clarification = [i + 1 for i, ln in enumerate(gate_lines)
                           if NEEDS_CLARIFICATION_RE.search(ln)]

    # --- does the phase state orchestration (grabable sign, D29) — is being lined
    # in lint_plan (workflow-like-DoR: phase with orchestration without workflow-script = warning)
    _, phase_context, _ = _find_section(gate_lines, PHASE_CONTEXT_HEADER_RE)
    declares_orchestration = any(phase_declares_orchestration(ln) for ln in (phase_context or ()))

    items = {}
    for item_id, title, header_lineno, body_lines, body_start in _find_items(lines):
        prefix_m = PHASE_TOKEN_RE.match(item_id.split(".")[0])
        if prefix_m and item_id.split(".")[0] != phase_id:
            diag.error(path, header_lineno,
                       f"item {item_id}: prefix «{item_id.split('.')[0]}» does not match "
                       f"with phase file «{phase_id}»")
        fields, dup_fields = _parse_fields(body_lines, body_start, FIELD_RE)
        for f in REQUIRED_ITEM_FIELDS:
            if f not in fields:
                diag.error(path, header_lineno,
                           f"item {item_id}: no required field «{f}» (item skeleton-phase "
                           f"is required to carry all 16 fields with the value «—»; detail - "
                           f"/task:plan-design <ID> {phase_id})")

        # --- D90: repeat field in body item'a - the last occurrence silently replaces
        # early legitimate value (y linter'a I y task_contract) --------------
        for name, first_ln, first_val, dup_ln, dup_val in dup_fields:
            if name in REQUIRED_ITEM_FIELDS:
                diag.error(path, dup_ln,
                           f"item {item_id}: field «{name}» occurs repeatedly "
                           f"(first {path.name}:{first_ln} → «{_preview(first_val)}», "
                           f"repeat {path.name}:{dup_ln} → «{_preview(dup_val)}») — scheduled "
                           f"parser and task_contract silently take the LAST occurrence (D90): "
                           f"string `**{name}:**` inside the prose of another field (for example, "
                           f"Completion Notes) replaces the acceptance value - remove "
                           f"stars/colon at the inline mention or move it to "
                           f"free text without form field")

        # --- 2.0 WARNING: order 16 canonical fields (P0.3 rivers#6) ------------
        canon_index = {f: i for i, f in enumerate(REQUIRED_ITEM_FIELDS)}
        present_order = [f for f in fields if f in canon_index]
        if present_order != sorted(present_order, key=canon_index.get):
            diag.warning(path, header_lineno,
                         f"item {item_id}: fields are not in canonical order "
                         f"(canon - SKILL §5 / phase-template)")

        # --- 2.0 WARNING: ≥50% empty fields without skeleton marker (P0.3 rivers#1) -----
        empty = sum(1 for f in REQUIRED_ITEM_FIELDS if _is_empty(fields.get(f, ("",))[0]))
        if not is_skeleton and empty >= len(REQUIRED_ITEM_FIELDS) * SKELETON_EMPTY_RATIO:
            diag.warning(path, header_lineno,
                         f"item {item_id}: {empty}/{len(REQUIRED_ITEM_FIELDS)} fields are empty, "
                         f"and in Phase Context no marker «> SKELETON — not detailed…» — "
                         f"either detail or mark the phase with a skeleton")
        status_val, _ = fields.get("Status", ("", header_lineno))
        if status_val and status_val not in STATUSES:
            diag.error(path, header_lineno, f"item {item_id}: invalid status «{status_val}»")
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
                       f"item {item_id}: is repeated in the file (lines {lns})")

    _, handoff_body, handoff_start = _find_section(lines, PHASE_HANDOFF_HEADER_RE)
    handoff_stale = False
    handoff_first_line = ""
    if handoff_body is None:
        diag.error(path, None, "no section «## Phase Handoff»")
        handoff_text = None
        handoff_lineno = None
    else:
        handoff_text = "\n".join(handoff_body).strip()
        handoff_lineno = handoff_start - 1  # header line itself «## Phase Handoff»
        # invalidation token - FIRST non-empty line of block (lines to lint_plan);
        # the predicate judges by it «block asserts phase closure» (subject, not word)
        handoff_first_line = next((ln for ln in handoff_body if ln.strip()), "").strip()
        handoff_stale = bool(PHASE_HANDOFF_STALE_RE.match(handoff_first_line))

    return {"status_table": status_table, "items": items, "phase_handoff": handoff_text,
            "phase_handoff_stale": handoff_stale, "phase_handoff_lineno": handoff_lineno,
            "phase_handoff_first_line": handoff_first_line,
            "is_skeleton": is_skeleton, "needs_clarification": needs_clarification,
            "declares_orchestration": declares_orchestration}


def _resolve_next_form(text):
    """Resolve form `Next` from enum'a §8 in the text: `(kind, match)` or `(None, None)`.

    Order - from specific form to general; the first match determines the checking of links,
    the rest are not tried. «plan closed» is checked IMMEDIATELY after plan-run (and not
    among others regex-forms): is a complete statement about the state of the plan, not slash-command
    — Next closed plan sometimes MENTIONS the following command in prose («… owner decides:
    `/task:plan-close archive <ID>` or …», see EDUFY-2), and this prose should not
    intercept the resolver. Manual-marker - last: the form has no links, it resolves
    only because none slash-form not declared.

    Form «WAITING» — FIRST, BEFORE plan-run: its declaration line embed'it target
    `/task:plan-run` (will start when the gate is removed), which would otherwise intercept the resolver as
    `run` — mirror of why «plan closed» comes right after run.
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
        expected_commands, expected_kind = SEMANTIC_NEXT_COMMANDS[semantic_kind]
        command, separator, arguments = payload.partition(" ")
        if command not in expected_commands or not separator:
            return "invalid-semantic", None
        legacy_kind, match = _resolve_next_form("/" + command + " " + arguments)
        return (legacy_kind, match) if legacy_kind == expected_kind else (
            "invalid-semantic", None)
    if LITERAL_WAITING in text:
        return "waiting", None
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
        diag.error(path, None, "handoff.md missing or unreadable")
        return None

    title_lineno = None
    title_ref = None  # `Pn.m` (item) or `Pn` (phase) — resolves to lint_plan
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
        diag.error(path, None, "no header «# HANDOFF — … — after Pn.m» / «… — after Pn»")

    body_start = (title_lineno or 0) + 1
    # handoff-fields out Scope (D90 — only REQUIRED_ITEM_FIELDS
    # items'ov) — duplicates deliberately discarded, not diagnosed here.
    fields, _dup_handoff_fields = _parse_fields(lines[body_start - 1:], body_start, FIELD_RE)
    for f in HANDOFF_REQUIRED_FIELDS:
        if f not in fields:
            diag.error(path, body_start, f"no required field «{f}»")

    return {"title_ref": title_ref, "title_lineno": title_lineno,
            "fields": fields, "lines": lines}


# --- lint of one plan ------------------------------------------------------------------

__all__ = tuple(name for name in globals() if not name.startswith("__"))
