"""Independent policy gates and canon registries used by plan-lint."""
from .common import *
from task import plan_decisions


def _portability_execution_paths(fields):
    """Paths (path-like tokens, backtick-quote or bare) in role field values
    item'a (ROLE-test, D47): other fields (Implementation Rules/Code Guidance/Why/…)
    are NOT scanned - mentioning there does not give the path a role execution input."""
    paths = []
    for name in PORTABILITY_ROLE_FIELDS:
        value = fields.get(name, "") or ""
        cleaned = PORTABILITY_SHELL_REDIRECT_RE.sub(" ", value)
        paths.extend(PORTABILITY_PATH_RE.findall(cleaned))
    return paths


def _plan_declares_committed_bundle_tier(plan_dir):
    """plan-portability-v1.md §Classification rule — tier(work) in relation to
    to the entire executable master plan: the protocol plan BY DESIGN carries `handoff.md`
    (multi-session/handoff always true — required media SKILL §8) → committed-bundle.
    Plan without `handoff.md` (haven't gotten to the diagram yet) is not parsed by this gate - another
    diagnostics already require the file itself."""
    return (Path(plan_dir) / "handoff.md").is_file()


def _lint_tiered_portability_22(plan_dir, plan_id, all_items, phases, diag):
    """: plan tier=committed-bundle (which is true for any executable
    design master plan, see `_plan_declares_committed_bundle_tier`) obliged
    carry ≥1 committed/predecessor-produced execution input and do not contain external
    (host/chat/mAInd/tmp/foreign) path IN ROLE execution input — otherwise `plan_lint`
    fails (`task_contract.PORTABILITY_INPUT_MISSING`/`PORTABILITY_EXTERNAL_INPUT`).
    Date plans from PORTABILITY_TIER_CANON_DATE — ERROR, older/legacy — WARNING
    (back-compat, same pattern as brief, roadmap and journal-gates)."""
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
                       f"item {item_id}: execution input «{raw_path}» — external path "
                       f"(host/chat/mAInd/tmp/foreign, PORTABILITY_EXTERNAL_INPUT, "
                       f"plan-portability-v1.md)")
            else:
                found_committed = True
    if not found_committed:
        report(Path(plan_dir) / "plan.md", None,
               f"plan carries handoff.md (tier=committed-bundle, plan-portability-v1.md "
               f"§Classification rule) without a single committed execution input in none "
               f"item'e (PORTABILITY_INPUT_MISSING)")


# --- machine gate printed boundary codes (repair of find F2) ------
# canon already required printing of BOTH
# codes write-site (`plan-audit.md` checklist), but the check was NOT machine - five items
# in a row (P3.6-P3.10) passed the audit by rerunning the predicate MANUALLY (all five → allow/allow),
# ENTRY itself in Completion Notes remained missing. Scope Anchor - DATE ITEM'a
# (column `Updated` tables «## Phase Status», ISO), NOT plan date: pattern
# BRIEF_CANON_DATE/JOURNAL_CANON_DATE/PORTABILITY_TIER_CANON_DATE would have missed here -
# this plan is dated `2026.07.24`, that is, his own future items P4.* would remain
# outside the gate, and painting closed ones after the fact is prohibited (D91, third write pass
# rejected by F2 report). Constant format - ISO HYPHEN (`YYYY-MM-DD`), and NOT a DOT, like in
# date plan_id-constants above: comparison is made with the value of CELL `Updated`, which carries
# hyphens - comparing multi-format strings to each other breaks the lexicographic order.
# The date is INTENTIONALLY one day later than the day the rule was authored (2026-07-26) — same technique as
# PORTABILITY_TIER_CANON_DATE: items, closed with the same phase on the day of authorship are not painted
# retroactive; the rule is proven by synthetic dated fixtures
# (test_plan_lint.py), rather than applying itself to the current run.
WRITE_SITE_CODES_CANON_DATE = "2026-07-27"
WRITE_SITE_CODES_V2_CANON_DATE = "2026-08-12"
ITEM_UPDATED_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Code Canon - `task_contract.evaluate()`: `pre_mutation` ∈ {allow, block:<CODE>};
# `pre_final` ∈ {allow, block:<CODE>, n/a} (D76: `n/a` — NOT green).
# --- canonical string instead re.search all over the field --------
# Old form (`WRITE_SITE_PRE_MUTATION_RE.search(clean)` on EVERYTHING Completion Notes)
# was wrong on BOTH sides: (1) fail-open — item without their own codes, but QUOTING others in
# prose, passed the gate; (2) false ERROR — item with their `allow`, quoted ABOVE
# by text `block:*`/`n/a` alien item'oh, he was blushing because `search` takes FIRST
# occurrence. Both prices are valid from the date of gate activation. Fix: ONE canonical line
# `write-site: pre_mutation: <code> · pre_final: <code>` — codes item'but they ONLY live
# on the line with this prefix; The gate does not see prosaic quotes on other lines.
WRITE_SITE_LINE_FORM = "write-site: pre_mutation: <code> · pre_final: <code>"
_WRITE_SITE_CODE = r"(allow|n/a|block:[A-Za-z0-9_]+)"
WRITE_SITE_LINE_PREFIX_RE = re.compile(r"^write-site:\s*(.*)$")
WRITE_SITE_CODE_PAIR_RE = re.compile(
    r"^pre_mutation:\s*" + _WRITE_SITE_CODE + r"\s*\W+\s*"
    r"pre_final:\s*" + _WRITE_SITE_CODE + r"\s*\.?\s*$")


def _write_site_canonical_codes(completion_notes):
    """Finds the canonical string `write-site:` in Completion Notes and
    returns `(pre_mutation, pre_final)` — LINE BY LINE (field parser returns
    multiline), and not `re.search` all over the field. Markdown-string wrapper
    (backtiki, `**`, presenters `- `/`> `, spaces) is cut off BEFORE the match - print form
    carries them. Lines WITHOUT prefix `write-site:` (quotes, explanations) not
    are considered at all, even if they contain `pre_mutation:`/`pre_final:` —
    exactly this closes fail-open. String Prefixed, but not parsed into form
    (order broken/delimiter OR is a prosaic string pattern quote -
    `` `write-site: pre_mutation: <code> · pre_final: <code>` `` as an explanation
    rules, - such a quote also begins with the wrapped line) DOES NOT count
    is canonical and does not stop the search: the search continues further along the field.
    Not a single parsable line in the entire field → `None`, ERROR «no codes»."""
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
    """ (repair of find F2), accuracy -: item with status
    🟢/🟠, whose `Updated` ISO-dated after layout-specific forward-only cutoff
    (`WRITE_SITE_CODES_CANON_DATE` for v1, `WRITE_SITE_CODES_V2_CANON_DATE` for v2),
    must carry the canonical string `write-site:` (see `_write_site_canonical_codes`)
    with BOTH codes `allow` (D76: `n/a` — not green). Unparsimable/missing date =
    item outside the scope - SILENCE, not WARNING (I10: no existing closed item
    doesn't blush in retrospect). Inside the scope - ERROR (rule is already canon:
    `plan-audit.md` checklist «write-site»; machine verifiability - P4.4/P10.1)."""
    status_by_id = {row.get("ID"): row for row, _ in status_table}
    for item_id, occurrences in items.items():
        item = occurrences[0]
        status_val, _ = item["fields"].get("Status", ("", item["header_lineno"]))
        if status_val not in (STATUS_DONE, STATUS_DEVIATIONS):
            continue
        status_row = status_by_id.get(item_id, {})
        updated = status_row.get("Updated", "") or ""
        cutoff = (WRITE_SITE_CODES_V2_CANON_DATE
                  if status_row.get("Layout") == "v2" else WRITE_SITE_CODES_CANON_DATE)
        if not ITEM_UPDATED_ISO_RE.match(updated) or updated < cutoff:
            continue
        cn_val, cn_lineno = item["fields"].get("Completion Notes", ("", item["header_lineno"]))
        codes = _write_site_canonical_codes(cn_val)
        if codes is None:
            diag.error(path, cn_lineno,
                       f"item {item_id}: closed «{status_val}» without printed boundary codes "
                       f"pre_mutation/pre_final in Completion Notes (expected string "
                       f"`{WRITE_SITE_LINE_FORM}`)")
            continue
        pre_mutation, pre_final = codes
        if pre_mutation != "allow":
            diag.error(path, cn_lineno,
                       f"item {item_id}: pre_mutation: {pre_mutation} at status "
                       f"«{status_val}» — closing on non-allow (D76)")
        if pre_final != "allow":
            diag.error(path, cn_lineno,
                       f"item {item_id}: pre_final: {pre_final} at status "
                       f"«{status_val}» — closing on non-allow (D76)")


# --- phase closing report `closure/<Pn>.json` (diagram v1) --------------
# The phase evidence class was not recorded anywhere: `Phase Handoff` — prose plus git-hash, and
# synthetic reads as a result (research/11-P8-target-design.md §1). Closing report -
# machine readable file per phase, INCLUDED opt-in field `## 0. Meta` → `Closure Protocol | v1`:
# plan without a field the rule does not apply to ANY diagnostic line (additivity is a test, not
# promise; closed recordings of live plans are not overwritten). Revalidation LAYERED (frame
# transfer, findings/rayt-deep-2026-07-25.md §8.3 #17/#29): one JSON per phase + two already
# parsed tables; There is no tree traversal or recalculation of plan file hashes here.
# EACH schema hash has a consumer named (otherwise «provenance theatre», §9.6): `git.head_sha` —
# number anchor §8 canon; `inputs_sha256` — detection of editing phase specifications after closing (`plan-audit`).
CLOSURE_META_FIELD = "Closure Protocol"
CLOSURE_PROTOCOL_V1 = "v1" # THE ONLY legal value of the field
CLOSURE_DIR_NAME = "closure"
CLOSURE_SCHEMA_VERSION = 1
# Certificate class - enum EXACTLY out of three: on what DATA the result was obtained.
# NOT to be confused with the closed list of PROOF classes `recomputed`/`cross-checked`/
# `pinned-not-recomputable`/`unknown` (`source-evidence-verification-v1.md`, other axis -
# is the statement deducible from the commercial bundle'a): both dictionaries are valid, neither
# replaces another (canon `plan-protocol` §8, reconsult 2026-07-26).
CLOSURE_EVIDENCE_CLASSES = ("real", "synthetic", "baseline_pending")
CLOSURE_REQUIRED_KEYS = ("schema_version", "plan", "phase", "closed_at", "closed_by",
                         "phase_status", "git", "inputs_sha256", "items", "gates",
                         "metrics", "limitations", "external_side_effects")
CLOSURE_CLOSED_BY_KEYS = ("command", "actor")
CLOSURE_GIT_KEYS = ("head_sha", "branch", "dirty")
# `items`/`gates` — records with certificate class; `metrics` carries it to `label`
# (no number ⇒ `baseline_pending` with a reason, and NOT the absence of a line - this is why the technique was taken).
CLOSURE_ENTRY_KEYS = {"items": ("id", "status", "evidence_class", "evidence"),
                      "gates": ("id", "status", "evidence_class", "evidence"),
                      "metrics": ("name", "value", "label")}
CLOSURE_LIST_KEYS = ("items", "gates", "metrics", "limitations", "external_side_effects")


def _closure_report_path(plan_dir, phase_id):
    """Closing report house - `plans/<PLAN-ID>/closure/<Pn>.json`."""
    return Path(plan_dir) / CLOSURE_DIR_NAME / f"{phase_id}.json"


def _closure_load(report_path, diag):
    """Reads the closing report; any refusal NAMES the file and the reason (transfer frame:
    fail-closed without an object name is prohibited - findings §8.3 issue #19). None = is not parsed."""
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        diag.error(report_path, None, f"closing report is not read: {error}")
        return None
    except json.JSONDecodeError as error:
        diag.error(report_path, None, f"closing report has invalid JSON: {error}")
        return None
    if not isinstance(data, dict):
        diag.error(report_path, None,
                   f"close report: schema object expected v{CLOSURE_SCHEMA_VERSION}, "
                   f"received {type(data).__name__}")
        return None
    return data


def _closure_lint_schema(data, report_path, plan_id, phase_id, diag):
    """Check 1 - Schematic v1: missing key = SCHEMA ERROR, not «no data»
    («no data» is expressed by VALUE - `baseline_pending` with reason, D42).
    Check 3 - `evidence_class: "real"` when empty `evidence` = ERROR with id records."""
    for key in CLOSURE_REQUIRED_KEYS:
        if key not in data:
            diag.error(report_path, None, f"closing report: no required key «{key}»")
    if data.get("schema_version") != CLOSURE_SCHEMA_VERSION:
        diag.error(report_path, None,
                   f"closing report: schema_version «{data.get('schema_version')}» ≠ "
                   f"{CLOSURE_SCHEMA_VERSION} (no other versions of the schema exist)")
    for key, expected in (("plan", plan_id), ("phase", phase_id)):
        if key in data and data.get(key) != expected:
            diag.error(report_path, None,
                       f"closing report: «{key}» = «{data.get(key)}» ≠ actual «{expected}»")
    for key, subkeys in (("closed_by", CLOSURE_CLOSED_BY_KEYS), ("git", CLOSURE_GIT_KEYS),
                         ("inputs_sha256", ())):
        value = data.get(key)
        if key in data and not isinstance(value, dict):
            diag.error(report_path, None,
                       f"closing report: «{key}» — object expected, received {type(value).__name__}")
            continue
        for subkey in subkeys:
            if isinstance(value, dict) and subkey not in value:
                diag.error(report_path, None,
                           f"closing report: no required key «{key}.{subkey}»")
    if isinstance(data.get("inputs_sha256"), dict) and not data["inputs_sha256"]:
        diag.error(report_path, None,
                   "closing report: «inputs_sha256» empty - consumer (plan-audit) catches by "
                   "for him to edit the phase specifications after closing; we don’t write a hash without a consumer, "
                   "consumer without a hash - especially")
    for key in CLOSURE_LIST_KEYS:
        if key in data and not isinstance(data[key], list):
            diag.error(report_path, None,
                       f"closing report: «{key}» — expected list, received "
                       f"{type(data[key]).__name__}")
    for key, entry_keys in CLOSURE_ENTRY_KEYS.items():
        for pos, entry in enumerate(data.get(key) if isinstance(data.get(key), list) else []):
            if not isinstance(entry, dict):
                diag.error(report_path, None,
                           f"closing report: «{key}[{pos}]» — object expected, received "
                           f"{type(entry).__name__}")
                continue
            name = entry.get("id") or entry.get("name") or f"{key}[{pos}]"
            for subkey in entry_keys:
                if subkey not in entry:
                    diag.error(report_path, None,
                               f"closing report: «{key}» entry «{name}» without key «{subkey}»")
            # The class carrier and the EVIDENCE carrier differ in the type of record:
            # items/gates carry `evidence_class` + `evidence` (command and its output),
            # metrics — `label` + `value` (the number itself). Empty proof with class
            # `real` = fail-closed: this is either `synthetic`, or `baseline_pending` with the reason.
            klass_key, proof_key = (("label", "value") if key == "metrics"
                                    else ("evidence_class", "evidence"))
            klass = entry.get(klass_key)
            if klass_key in entry and klass not in CLOSURE_EVIDENCE_CLASSES:
                diag.error(report_path, None,
                           f"closing report: «{key}» entry «{name}»: {klass_key} «{klass}» out "
                           f"enum'a {list(CLOSURE_EVIDENCE_CLASSES)}")
            if klass == "real" and _is_empty(str(entry.get(proof_key, "") or "")):
                diag.error(report_path, None,
                           f"closing report: «{key}» entry «{name}» declared "
                           f"«real» with empty {proof_key} — class real requires a command and its output "
                           f"(otherwise it synthetic or baseline_pending with reason)")


def _closure_lint_correspondence(data, report_path, phase_id, parsed_phase, board_row, diag):
    """Check 4 - `items[]` ↔ lines `## Phase Status` phases (extra/missing id or
    other status); check 5 - `phase_status` ↔ phase string in Status Board (`plan.md`).
    Both are on ALREADY parsed tables: the gate does not perform a separate tree traversal."""
    if board_row is not None:
        board_status = board_row[0].get("Status", "")
        if "phase_status" in data and data.get("phase_status") != board_status:
            diag.error(report_path, None,
                       f"closing report: phase_status «{data.get('phase_status')}» "
                       f"≠ phase status {phase_id} in Status Board «{board_status}»")
    if parsed_phase is None:
        return  # there is no phase file - a separate diagnostic has already been issued, there is nothing to duplicate
    table = {row.get("ID"): row.get("Status", "")
             for row, _ in parsed_phase.get("status_table", [])}
    reported = {}
    for entry in (data.get("items") if isinstance(data.get("items"), list) else []):
        if isinstance(entry, dict) and entry.get("id"):
            reported[entry["id"]] = entry.get("status")
    for item_id in sorted(set(reported) - set(table)):
        diag.error(report_path, None,
                   f"closing report: item «{item_id}» is in items[], but there is no line in "
                   f"«## Phase Status» phases {phase_id}")
    for item_id in sorted(set(table) - set(reported)):
        diag.error(report_path, None,
                   f"closing report: item «{item_id}» is in «## Phase Status» phases "
                   f"{phase_id}, but is missing from items[]")
    for item_id in sorted(set(table) & set(reported)):
        if reported[item_id] != table[item_id]:
            diag.error(report_path, None,
                       f"closing report: item «{item_id}»: status «{reported[item_id]}» ≠ "
                       f"status in «## Phase Status» «{table[item_id]}»")


def _lint_closure_reports_81(plan_dir, plan_id, meta, phases, board_by_phase, diag):
    """, all five closing report checks. Activation - opt-in Meta-field
    `Closure Protocol | v1`: without it the function is completely silent (additivity). Check 2 -
    terminal phase, field enabled, no file → ERROR with EXPECTED PATH (fail-closed
    names an object). The non-terminal report phase is not required to have; but IF the file is there -
    it is parsed according to the same scheme (otherwise the enabled protocol would silently pass garbage)."""
    plan_md = Path(plan_dir) / "plan.md"
    declared, meta_lineno = (meta or {}).get(CLOSURE_META_FIELD, (None, None))
    if declared is None:
        return
    declared = declared.strip()
    if declared != CLOSURE_PROTOCOL_V1:
        diag.error(plan_md, meta_lineno,
                   f"Meta «{CLOSURE_META_FIELD}»: value «{declared}» — "
                   f"the only legal one is «{CLOSURE_PROTOCOL_V1}» (canon plan-protocol §8)")
        return
    for phase_id in sorted(set(phases) | set(board_by_phase)):
        report_path = _closure_report_path(plan_dir, phase_id)
        board_row = board_by_phase.get(phase_id)
        board_status = board_row[0].get("Status", "") if board_row else ""
        if not report_path.is_file():
            if board_status in TERMINAL_STATUSES:
                diag.error(plan_md, board_row[1] if board_row else None,
                           f"phase {phase_id} terminal («{board_status}») when "
                           f"`{CLOSURE_META_FIELD} | {CLOSURE_PROTOCOL_V1}`, but there is "
                           f"no closing report; expected file {report_path}")
            continue
        data = _closure_load(report_path, diag)
        if data is None:
            continue
        _closure_lint_schema(data, report_path, plan_id, phase_id, diag)
        _closure_lint_correspondence(data, report_path, phase_id, phases.get(phase_id),
                                     board_row, diag)


# --- -D105: `Consequences` in D-records (research/11 §2, research/23) ---
# Bearer - inline subfield `**Consequences:**` inside the cell `Solution` (fifth column
# rejected: header D-log - registry literal CANON_LITERALS, her edit = rewrite
# caps in all fleet plans, D43). Gate - OPT-IN TWICE (same discipline as
# `_lint_closure_reports_81`): (1) Meta-field `Closure Protocol | v1`, (2) `Date` D-records
# ≥ CONSEQUENCES_CANON_DATE (forward-only — mechanics WRITE_SITE_CODES_CANON_DATE above,
# Unparsable or missing dates are out of scope. Constant date:
# DAY AFTER the last existing record without `Consequences` (D98, ECO-OPT
# 2026-07-27) — measured `research/23-P8.2-refine-2026-07-27.md` §2: no date gate
# would close in red with its own plan (D98 no carrier and backfill PROHIBITED, §2).
CONSEQUENCES_CANON_DATE = "2026-07-28"
CONSEQUENCES_LITERAL = "**Consequences:**"
# Prefix ISO-cell match `Date` (not bar `==`, D103 §2): FOREMAN D7 carries
# `2026-07-18 (finalized The P0.4)` — suffix after the date is legal, but the strict one is complete
# match would read this as unparsable and lose the sense of the precedent.
CONSEQUENCES_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
# Cancel predicate/solution replacement - MEASURED (research/23 §1), not rewritten from
# specs verbatim: specs (`supersedes D`/`canceled`/`cancels D`) catches ZERO records on
# ECO-OPT (the short participle accepts both spelling variants; the record uses
# «canceled»); wide stem `cancel` (any form) gives 6 triggers, 4 of them -
# DENIAL «does not cancel»/«not canceled» (false ERROR). Negative lookbehind
# `(?<!not )` CANNOT BE REMOVED: without it, 4 out of 6 alarms on the same plane are false
# (D11/D19/D26 etc., research/23 §1). Keep the stem list NARROW - three semantics, not
# ten words (Code Guidance): every extra stem is a risk of false ERROR on hundreds
# fleet plans.
CONSEQUENCES_STEMS_RE = re.compile(
    r"supersedes D|cancels D|(?<!not )cancel(?:s|ed|ing)?\b", re.IGNORECASE)


def _lint_consequences_82(plan_dir, plan_id, meta, plan_lines, plan_md, diag):
    """-D105: cell `Solution` lines `## 5. Decision Log`, matching
    CONSEQUENCES_STEMS_RE (cancel/replacement solution) and dated (`Date`) ≥
    CONSEQUENCES_CANON_DATE, is required to bear `**Consequences:**` — otherwise ERROR with
    number D-records (fail-closed names an object). Activation - DOUBLE opt-in:
    without Meta `Closure Protocol | v1` function is completely silent (additivity, test).

    Fair Border (Code Guidance P8.2, must be written out loud here too):
    canon requires `Consequences` for EACH carrier D-records; this check only catches
    MACHINE DETECTIVE subclass - an entry that explicitly declares cancellation/replacement of another
    solutions to the three measured shapes above. The gate does not provide full coverage of the canon and
    does not state (findings/rayt-deep-2026-07-25.md §9.4 — checkmark formalism)."""
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
                           f"Decision Log {decision_id}: cancellation token/replacement solution "
                           f"without `{CONSEQUENCES_LITERAL}` (canon plan-protocol §6, forward-only "
                           f"with {CONSEQUENCES_CANON_DATE}, D103)")
        return

    _, dl_body, dl_start = _find_section(plan_lines, DECISION_LOG_HEADER_RE)
    if dl_body is None:
        return
    _, rows, _ = _parse_table(dl_body, dl_start)
    for row, lineno in rows:
        decision = row.get("Solution", "") or ""
        if not CONSEQUENCES_STEMS_RE.search(decision):
            continue
        date_match = CONSEQUENCES_DATE_PREFIX_RE.match((row.get("Date", "") or "").strip())
        if not date_match or date_match.group(1) < CONSEQUENCES_CANON_DATE:
            continue  # Unparsable/old date: out of scope (forward-only).
        if CONSEQUENCES_LITERAL not in decision:
            diag.error(plan_md, lineno,
                       f"Decision Log {row.get('D#', '?')}: cancellation token/replacement solution "
                       f"without `{CONSEQUENCES_LITERAL}` (canon plan-protocol §6, forward-only "
                       f"with {CONSEQUENCES_CANON_DATE}, D103)")


# --- `CHECKPOINTED` — failure carries the exact resume command ------
# Medium - string `Resume: <command>` in the field `Pending Work` item'a (NOT the seventh
# status, NOT the seventeenth field - both options are rejected D44, break the contract of three living
# plans/`packages/task/scripts/cross-plan-files.py`). Activation - the same opt-in, that of:
# Meta-field `Closure Protocol | v1` (without canon date - as of the date of detailing in this plan
# alive 🔴/⛔ items with the protocol enabled no, there is nothing to paint in hindsight).
STATUS_SKIPPED = "⛔ Skipped by decision"
RESUME_LITERAL = "Resume:"
RESUME_LINE_RE = re.compile(r"^Resume:\s*(.*)$")
D_REF_RE = re.compile(r"\bD\d+\b")


def _find_resume_line(pending_work):
    """Searches for a string `Resume: …` in the field Pending Work — line by line (same discipline,
    what `_write_site_canonical_codes`), markdown-wrapper (`-`/`>`/`` ` ``/`**`) is cut off
    BEFORE the match. Returns the value AFTER the colon (cropped) or `None`, if there is no line."""
    for raw_line in (pending_work or "").replace("`", "").splitlines():
        line = raw_line.replace("*", "").strip()
        while line[:1] in ("-", ">"):
            line = line[1:].strip()
        m = RESUME_LINE_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def _lint_checkpointed_83(meta, items, path, diag):
    """: item with status `🔴 Blocked` is required to bear Pending Work non-empty
    line `Resume: <command>` (form `Resume: — (external blocker: …)` —
    legal «non-empty» for a blocker without a local step, Code Guidance P8.3); item with
    status `⛔ Skipped by decision` must bear EXACTLY `Resume: —` and a link
    `D<number>` in the same field (the decision to pass is made by recording, not by silence)."""
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
                           f"item {item_id}: {STATUS_BLOCKED} without line "
                           f"`{RESUME_LITERAL} <command>` in Pending Work — refusal is required "
                           f"carry the exact continue command rather than «missing» (D44)")
        else:
            has_d_ref = bool(D_REF_RE.search(pw_val or ""))
            if resume is None or resume != EMPTY_PLACEHOLDER or not has_d_ref:
                diag.error(path, pw_lineno,
                           f"item {item_id}: {STATUS_SKIPPED} without `{RESUME_LITERAL} "
                           f"{EMPTY_PLACEHOLDER}` and links `D<number>` in Pending Work — "
                           f"the decision to pass must be presented D-entry (D44)")


# --- cross-document check `handoff.md` ↔ «## 4. Phase Index
# & Status Board» (F8 audit P9: handoff lied `P9 4/4`, board carried `2/4`, rights board).
# House - plan_lint.py, not verify-plan-citations.py: is the consistency of two sections of ONE
# plan, path not resolved/quotes - the opposite solution would blur both tools (`research/27-…`
# §2.4, Scope Excluded P10.2 remains valid). Forward-only by TITLE DATE handoff'a
# (same discipline as WRITE_SITE_CODES_CANON_DATE/CONSEQUENCES_CANON_DATE): handoff older
# Canon dates are not diagnosed, even as warnings; do not retroactively mark the existing fleet.
# number). Severity inside the scope - like launch-block-gate (D-canon 2.0): dated `plan_id`
# from BRIEF_CANON_DATE → ERROR, legacy → WARNING (`plan_id[:10]` — date, not handoff-date).
HANDOFF_BOARD_CANON_DATE = "2026-07-28"
HANDOFF_TITLE_DATE_RE = re.compile(r"^#\s+HANDOFF\s+—\s*(\d{4}-\d{2}-\d{2})\s+—")
# Narrow template intentionally (Code Guidance P11.3, anti-self-deception): EXACTLY `Pn a/b` — not «33/44»,
# not percentages, not bare prose «closed 4 of 4». Metering (`findings/P11-citation-gate-
# measurements.md` §4) — 3 occurrences on three living planes, 1 divergence, 0 false;
# extension to prose would bring back the noise that narrowness today keeps at zero.
HANDOFF_BOARD_REF_RE = re.compile(r"\bP(\d+)\s+(\d+)/(\d+)\b")


def _lint_handoff_board_113(handoff, handoff_path, plan_id, board_by_phase, diag):
    """: every occurrence `Pn a/b` in handoff.md must match
    with column value `STATUS_BOARD_ITEMS_COL` lines `Pn` boards «## 4. Phase Index &
    Status Board»; discrepancy - diagnostic calling BOTH sides. Phase `Pn`, missing
    on the board, - «dangling link». Unparsimable/older header date handoff'a - SILENCE
    (forward-only, additivity I10), not ERROR/WARNING."""
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
                       f"handoff.md: «{phase_id} {handoff_ratio}» refers to the phase «{phase_id}», "
                       f"missing from «## 4. Phase Index & Status Board» (dangling link)")
                continue
            board_ratio = row[0].get(STATUS_BOARD_ITEMS_COL, "")
            if board_ratio != handoff_ratio:
                report(handoff_path, i + 1,
                       f"handoff.md:{i + 1} says «{phase_id} {handoff_ratio}», board «## 4. "
                       f"Phase Index & Status Board» carries «{phase_id} {board_ratio}» "
                       f"(discrepancy)")


# --- registry of untranslatable literals (H3) ---------------------------
# The ONLY source of strings that the linter checks against the PLAN TEXT byte-for-byte.
# Discipline (gate — tests/test_canon_literals.py):
# * `CANON_LITERALS` — line that the protocol REQUIRES to be written verbatim (table headers,
# markers, forms `Next`). A fleet agent takes it from EN-canon `SKILL.md` ⇒ everyone is obliged
# carry directive `<!-- i18n-keep: … -->` in EN-only `SKILL.md`.
# Test T2 checks the registry against directives directly.
# * `HEURISTIC_LITERALS` — INTENT DETECTORS in free prose (stems, case insensitive):
# the author does not write them verbatim, EN-canon does not carry them and is not obliged to carry them ⇒ they have no directives.
# * Test T1 (AST-bypass this file) does not allow you to create a Cyrillic reconciliation PAST both registries -
# fell out exactly like that `plan closed` (H3: inline string without a constant, the literal gate is blind to it).
# Diagnostic messages (`diag.error`/`diag.warning`) — NOT matching literals: they don't stack
# according to the text of the plan, are not included in the register. `EMPTY_PLACEHOLDER` («—») is checked, but the directive is not
# gets (H13: em dash is in any EN-text - such a directive does not provide a contract).
LITERAL_PLAN_CLOSED = "plan closed"  # form `Next` completely closed plan (SKILL §8)
LITERAL_PHASE_HANDOFF_STALE = "> DEPRECATED — phase reopened"  # invalidation token (SKILL §3, D34)
# --- scope-payload launch-block'a, carrying finds (SKILL §8, D-canon 2026-07-17) ---
# Block verdict `## Audit Pn`: meanings in Latin (RED/ATTENTION/GREEN) — no translation
# are subject to by nature, directives are not required; Only the field header itself is Cyrillic.
LITERAL_AUDIT_VERDICT = "Verdict:"
AUDIT_VERDICT_RE = re.compile(LITERAL_AUDIT_VERDICT + r"\s*\**\s*(RED|ATTENTION|GREEN)\b")
# Verdicts, whose launch-block FORWARDS findings to next session ⇒ is required to bear scope-payload.
# GREEN does not carry any finds - from it payload not required (otherwise the markers will degenerate into a ritual).
AUDIT_FINDINGS_VERDICTS = ("RED", "ATTENTION")
# Four required lines payload'a. The order in the canon is fixed, the gate checks
# PRESENCE (content `SCORE:`/`DO NOT TOUCH:` the machine does not measure - this report-quality).
SCOPE_PAYLOAD_MARKERS = ("MODE:", "ENTRANCE:", "SCORE:", "DO NOT TOUCH:")
CANON_LITERALS = (
    "Field | Meaning",                                        # hat Meta (plan.md §0)
    "Items 🟢/total",                                          # column Status Board (§4)
    "D# | Date | Solution | Why",                           # hat Decision Log (§5)
    "Date | Who (role/model) | What",                          # hat Update Log (§6)
    "Contract | Version | Status | Consumers | Notified",   # hat Contracts/Exported (§7)
    "Contract | Donor plan | Pinned | Spotted | Reaction",     # hat Contracts/Consumed (§7)
    "> SKELETON — not detailed",                            # skeleton phase marker (§5)
    MANUAL_RUN_MARKER,                                        # «MANUAL START» — owner-run form
    "[NEEDS CLARIFICATION",                                   # ambiguity marker (§7)
    "RAG:✅",                                                  # enum RAG-markers (§7, D29)
    "RAG:" + EMPTY_PLACEHOLDER,
    "[UNVERIFIED]",
    LITERAL_PLAN_CLOSED,
    LITERAL_PHASE_HANDOFF_STALE,
    LITERAL_WAITING,                                          # form `Next` «WAITING» (SKILL §8, D8)
    LITERAL_AUDIT_VERDICT,                                    # verdict header `## Audit Pn` (§8)
    *SCOPE_PAYLOAD_MARKERS,                                   # scope-payload launch-block'a (§8)
    "pre_mutation:", # write-site border code (§8)
    "pre_final:",                                             # write-site border code (§8, P4.4/D91)
    "write-site:", # canonical string (§8,:
                                                               # T1 does not catch the Latin alphabet, registration is a solution)
    CLOSURE_META_FIELD,                                       # Meta-close report activation field
                                                               # (§8,: Latin - the same
                                                               # registration decision that write-site:)
    CONSEQUENCES_LITERAL, # §6, -D105: Latin - the same
                                                               # registration solution, T1 doesn't catch it
    RESUME_LITERAL, # §6,: Cyrillic - required
                                                               # i18n-directive in EN-only SKILL.md
    "Command",                                                # legacy reader compatibility (LAUNCH_COMMAND_ROW_RE)
)
# --- C2-prose-disclaimer detector in an ad `Next` (WARNING) ----------
# The author writes runnable slash-form «there is a command, but not now» instead of structural form
# «WAITING: <condition> → <target form>» (recon §3.2, alive SKM-MASTER-002). Stem list
# NARROW and finalized according to fleet DELTA measurement (§8 D53), not «by eye»: every extra stem -
# risk of false WARNING on hundreds handoff'ov (mirror D34). Only AD LINE is scanned
# (`next_decl`), NOT all launch-block: guard-string `# NOT before:` legally lives in code-block'e.
C2_WAITING_STEMS = ("not before", "nothing to do", "time gate", "time-gate")
C2_WAITING_STEMS_RE = re.compile(
    "|".join(re.escape(s) for s in C2_WAITING_STEMS), re.IGNORECASE)
# Forms Next, carrying executable slash-command NOW (not waiting/manual/closed) — only on
# them C2 triggered: prosaic clause when The runnable-command is the anti-pattern.
C2_RUNNABLE_KINDS = frozenset({"run", "design-item", "design-phase", "audit",
                               "audit-design", "close", "close-archive"})

# Anchors `--conflicts` (P5.9 + D79 EN-only) are grouped in canonical `SKILL.md`.
# These are stable English anchors link prose to registers of implementation.
CONFLICTS_ANCHOR_STATUSES = "EXACTLY 6 canonical strings"
CONFLICTS_ANCHOR_ITEM_FIELDS = "`**Field:** value`, in this order:"
CONFLICTS_ANCHOR_NEXT_FORMS = "| Form Next | When |"
CONFLICTS_ANCHOR_CONTEXT = "EXACTLY one of three values"
CONFLICTS_ANCHOR_LAUNCH_TABLE = "| Parameter | Meaning |"
CONFLICTS_ANCHOR_LAYOUT_V2 = "Layout v2 carrier contract"

# Heuristics: `orchestration`/`multi-agent` — detection of declared orchestration (ORCHESTRATION_MARKER_RE,
# D29); `PHASE_HANDOFF_CLOSURE_LITERALS` — detect «block asserts phase closure»;
# `PHASE_HANDOFF_NEGATION_LITERALS` — detect negation in the same statement; C2-themes
# (Cyrillic) — detect prose clause in `Next`; CONFLICTS_ANCHOR_* — see comment
# above. All groups are looking for MEANING in the author’s prose/canon, not a canonical token for a third party
# reader ⇒ presence in EN not required (i18n-keep not needed).
HEURISTIC_LITERALS = (("orchestration", "multi-agent") + PHASE_HANDOFF_CLOSURE_LITERALS
                      + PHASE_HANDOFF_NEGATION_LITERALS
                      + ("not before", "nothing to do", "time gate", "Discussion")
                      + (CONFLICTS_ANCHOR_STATUSES, CONFLICTS_ANCHOR_ITEM_FIELDS,
                         CONFLICTS_ANCHOR_NEXT_FORMS, CONFLICTS_ANCHOR_CONTEXT,
                         CONFLICTS_ANCHOR_LAUNCH_TABLE, CONFLICTS_ANCHOR_LAYOUT_V2)
                      # -D105: themes CONSEQUENCES_STEMS_RE — INTENT detector
                      # (cancel/replacement solution) in free prose D-log; EN-they are not canon
                      # carries and is not required to carry (research/23 §3).
                      + ("cancels", "canceled", "canceled", "canceled", "canceled", "canceled"))

__all__ = tuple(name for name in globals() if not name.startswith("__"))
