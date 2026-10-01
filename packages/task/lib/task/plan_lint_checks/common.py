"""plan_lint — deterministic executable master plan protocol validator
`plans/<PLAN-ID>/{plan.md, phases/Pn.md, handoff.md}`.

Schema (is rigidly fixed - SSOT: skill `packages/skiller/skills/general/
plan-protocol/SKILL.md` + him `snippets/{plan,phase,handoff}-template.md`;
these three files and `commands/plan-{design,exec,close,audit}.md` is already called
exactly this script as `scripts/plan-lint.py plans/<ID>`):
  plan.md      — «## 0. Meta» (TABLE `Field|Meaning`; mandatory
                 Plan ID/Title/Version/Status) + «## 4. Phase Index & Status
                 Board» (table `Phase|Title|Items 🟢/total|Status`).
  phases/Pn.md — «## Phase Status» (table `ID|Title|Status|Updated`, by
                 line on item), item-blocks (`### Pn.m — Header`, fields
                 lines `**Field:** value`) and «## Phase Handoff» at the end.
  handoff.md   — `# HANDOFF — … — after Pn.m` + fields Next/Done/Remaining/
                 Sources of truth (minimum required; the protocol also carries
                 Open risks/Workarounds — their presence is not considered superfluous).

stdlib-only (re/argparse/pathlib/json/sys), messages - in Russian.
"""
import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

try:
    # core.warn — literally the same (print "WARN: …" in stderr); reuse
    # instead of a double. Optional: core/ on PYTHONPATH adds launcher
    # (scripts/plan-lint.py), in standalone-layout (no core/) — your fallback.
    from core.term import warn as _core_warn
except ImportError:  # pragma: no cover - standalone-fallback, see docstring above
    def _core_warn(msg):
        print(f"WARN: {msg}", file=sys.stderr)

# task.journal — SSOT recording schemes and historical exception sidecar; lint
# log reuses it instead of duplicate rules (Code Guidance «anti-fitting»), same
# package `task`, same lib/ on sys.path (see scripts/plan-lint.py launcher).
from task import journal as _journal
from task import plan_continuity, plan_layout, terminal_admission
from task import review_policy as _review_policy
from task import plan_status
# task.task_contract — sole owner of string test «appearance» execution
# input'a (task-contract-v1.md §Portability, frozen); tiered-portability lint
# calls it, rather than retelling the list of prefixes with a second list (Implementation Rules P2.2).
from task import task_contract

# --- schema canon -------------------------------------------------------------

# EXACTLY 6 canonical statuses - no other lines/synonyms are not allowed.
STATUSES = (
    "⬜ Not started",
    "🟡 In progress",
    "🟢 Done",
    "🟠 Done with deviations",
    "🔴 Blocked",
    "⛔ Skipped by decision",
)
STATUS_BLOCKED = "🔴 Blocked"
STATUS_DONE = "🟢 Done"
STATUS_DEVIATIONS = "🟠 Done with deviations"
STATUS_IN_PROGRESS = "🟡 In progress"
# «terminal» = phase closed (ready/missing/delivered with reservations) —
# is used for phase-first-heuristics (WARNING), not to be confused with 🔴 (standing, not closed).
TERMINAL_STATUSES = (STATUS_DONE, STATUS_DEVIATIONS, "⛔ Skipped by decision")
EMPTY_PLACEHOLDER = "—"  # an empty field is marked with exactly this symbol (em dash)

# Meta — table `Field|Meaning`; only 4 are required identity-fields (remaining 8 of
# template - Document Type/Authoring Model/…/Approval Owner — informational, not gated).
REQUIRED_META_FIELDS = ("Plan ID", "Title", "Version", "Status")
V2_CORE_META_FIELDS = ("Plan ID", "Title")
V2_STATUS_META_FIELDS = ("Version", "Status", "Last Updated")
META_TABLE_COLUMNS = ("Field", "Meaning")
# Full canon item-fields - SKILL.md §5 / snippets/phase-template.md, strictly in this
# ok (order is not gated here, only presence - see. lint_plan).
REQUIRED_ITEM_FIELDS = (
    "Status", "Intent", "Why", "Scope Included", "Scope Excluded", "Inputs", "Files",
    "Required Reads", "Implementation Rules", "Code Guidance", "Validation",
    "Deliverables", "Completion Notes", "Pending Work", "Known Deviations",
    "Escalation Needed",
)
ITEM_SPEC_FIELDS = (
    "Intent", "Why", "Scope Included", "Scope Excluded", "Inputs", "Files",
    "Required Reads", "Implementation Rules", "Code Guidance", "Validation",
    "Deliverables",
)
ITEM_STATE_FIELDS = (
    "Status", "Completion Notes", "Pending Work", "Known Deviations",
    "Escalation Needed",
)
STATUS_BOARD_COLUMNS = ("Phase", "Title", "Items 🟢/total", "Status")
STATUS_BOARD_ITEMS_COL = "Items 🟢/total"
PHASE_STATUS_COLUMNS = ("ID", "Title", "Status", "Updated")
# handoff.md — minimum required 4 fields (the protocol also carries Open risks and
# Workarounds/Deferred/Open questions — their absence is only a warning, see WARNING).
HANDOFF_REQUIRED_FIELDS = ("Next", "Done", "Remaining", "Sources of truth")

# --- regex-canon ---------------------------------------------------------
ITEM_HEADER_RE = re.compile(r"^###\s+(P\d+\.\d+)\s+—\s+(.*)$")
SECTION_HEADER_RE = re.compile(r"^##\s+\S.*$")  # level 2 (### level 3 does not match)
META_HEADER_RE = re.compile(r"^##\s+0\.\s+Meta\s*$")
STATUS_BOARD_HEADER_RE = re.compile(r"^##\s+4\.\s+Phase Index & Status Board\s*$")
PHASE_STATUS_HEADER_RE = re.compile(r"^##\s+Phase Status\s*$")
PHASE_HANDOFF_HEADER_RE = re.compile(r"^##\s+Phase Handoff\s*$")
FIELD_RE = re.compile(r"^\*\*([^*:]+):\*\*\s*(.*)$")
ESCALATION_RE = re.compile(r"^>\s*🔴\s*ESCALATION\s+(P\d+\.\d+)\s*:")
# Two header forms handoff (SKILL §8 / D30): `after Pn.m` — closed item; `after Pn` —
# closed/audited/re-designed PHASE (step without «last closed item'a» like
# destination). The group gives the link: with a dot - item, without a dot - phase (resolves to
# lint_plan). Other forms (`after phase 2`, `after P2 item 8`) remain ERROR.
HANDOFF_TITLE_RE = re.compile(r"^#\s+HANDOFF\s+—.*—\s+after\s+(P\d+(?:\.\d+)?)\s*$")
HANDOFF_TITLE_HELP = ("header does not match either of the two forms (SKILL §8): "
                      "«# HANDOFF — … — after Pn.m» (item) · «# HANDOFF — … — after Pn» (phase)")
# Bootstrap-start form handoff'a: the plan has not yet been touched, phases `P0` does not happen.
# Exactly this line is not «any phase P0» and not «any item .0»: extension = hole in the gate.
HANDOFF_TITLE_BOOTSTRAP = "P0.0"
# `handoff.Next` accepts the closed semantic enum, including D80 design finish/roadmap.
# below the regular order for each (except plan-run/«plan closed», already announced). Order
# checks in the resolver (see lint_plan) goes from specific to general: design-item BEFORE
# design-phase (otherwise `(?!\.\d)`-lookahead phase form simply will not allow the match to be lost
# thread item), plan-close-archive BEFORE general plan-close (otherwise «archive» would read like
# «phase»/PLAN-ID of the general form - although for the general form it is required `P\d+`, no conflict; those
# at least we fix the order explicitly, and do not rely on a side effect regex).
PLAN_DESIGN_ITEM_RE = re.compile(r"/task:plan-design\s+(\S+)\s+(P\d+\.\d+)")
# The next step is valid and how «first detail the skeleton phase» (Execution Rules
# protocol expressly prescribe plan-design before plan-run on phases without filled
# 16 fields) — link to PHASE (Pn), not on item (Pn.m).
PLAN_DESIGN_PHASE_RE = re.compile(r"/task:plan-design\s+(\S+)\s+(P\d+)(?!\.\d)\b")
PLAN_DESIGN_FINISH_RE = re.compile(r"/task:plan-design\s+(\S+)\s+finish\b")
PLAN_DESIGN_ROADMAP_RE = re.compile(r"/task:plan-design\s+(\S+)\s+roadmap\b")
# One execution command; `plan-exec` is its legacy spelling (readers accept both).
PLAN_RUN_RE = re.compile(r"/task:plan-(?:run|exec)\s+(\S+)\s+(P\d+\.\d+)(?:\s*-\s*(P\d+\.\d+))?")
# Pre-exec design-review of the entire plan (plan-audit, mode design).
PLAN_AUDIT_DESIGN_RE = re.compile(r"/task:plan-audit\s+(\S+)\s+design\b")
PLAN_AUDIT_RE = re.compile(r"/task:plan-audit\s+(\S+)\s+(P\d+)(?!\.\d)\b")
PLAN_CLOSE_ARCHIVE_RE = re.compile(r"/task:plan-close\s+archive\s+(\S+)")
PLAN_CLOSE_RE = re.compile(r"/task:plan-close\s+(\S+)\s+(P\d+)(\.\d+)?\b")
SEMANTIC_NEXT_RE = re.compile(
    r"^(run-items|exec-items|audit-design|design-phase|design-item|design-finish|"
    r"design-roadmap|audit-phase|close|archive|terminal|manual|waiting):\s*(.*)$")
SEMANTIC_NEXT_COMMANDS = {
    "run-items": (("task:plan-run", "task:plan-exec"), "run"),
    "exec-items": (("task:plan-run", "task:plan-exec"), "run"),  # legacy spelling
    "audit-design": (("task:plan-audit",), "audit-design"),
    "design-phase": (("task:plan-design",), "design-phase"),
    "design-item": (("task:plan-design",), "design-item"),
    "design-finish": (("task:plan-design",), "design-finish"),
    "design-roadmap": (("task:plan-design",), "design-roadmap"),
    "audit-phase": (("task:plan-audit",), "audit"),
    "close": (("task:plan-close",), "close"),
    "archive": (("task:plan-close",), "close-archive"),
}
MANUAL_RUN_MARKER = "MANUAL START"  # owner-run form: without slash-commands, searched for as a substring
LITERAL_WAITING = "WAITING:"  # 9-I form Next (§8, D8): healthy expectation of external time/gate, searched by substring
NEXT_FORMS_HELP = (
    "Next does not match any of the valid forms (SKILL §8): "
    "`<kind>: task:<plan-command> <arguments>` (provider-neutral canon) · "
    "/task:plan-run <ID> Pn.a[-Pn.b] (legacy: /task:plan-exec) · "
    "/task:plan-design <ID> Pn · /task:plan-design <ID> Pn.m · "
    "/task:plan-design <ID> finish · /task:plan-design <ID> roadmap · "
    "/task:plan-audit <ID> Pn · /task:plan-audit <ID> design · "
    "/task:plan-close <ID> Pn[.m] · /task:plan-close archive <ID> · "
    "«plan closed» · «MANUAL START: <model/effort>» · «WAITING: <condition> → <target form>»"
)
PHASE_FILENAME_RE = re.compile(r"^(P\d+)\.md$")
PHASE_TOKEN_RE = re.compile(r"^P(\d+)$")
DONE_TOTAL_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
ACTIVE_FIELD_RE = re.compile(r"^\*\*Active:\*\*\s*(.+)$")
ACTIVE_FILENAME = "ACTIVE.md"
README_FILENAME = "README.md"

# --- canon 2.0 (all checks below - ONLY warning, we don’t break existing plans) --
# Skeleton phase marker (SKILL §5): with empty fields items are legal without it
# item with ≥50% empty fields - warning (P0.3 rivers#1).
SKELETON_MARKER_RE = re.compile(r"^>\s*SKELETON\s+[—-]\s+not detailed")
# Ambiguity marker (SKILL §7): in phase with status 🟡+ (not ⬜) = DoR-warning.
NEEDS_CLARIFICATION_RE = re.compile(r"\[NEEDS CLARIFICATION")
# append-only block `## Audit Pn` EXCLUDED from the phase grep region. Auditor
# reports predicate validation («markers X — 0») and must MENTION the marker verbatim;
# grep over the entire file would give an honest report (A4: first version `## Audit P3` dropped
# gate with its own string). Gate region ends at FIRST `## Audit` — below him alive
# No phase specification (block append-only, is added AFTER items and Phase Handoff).
AUDIT_BLOCK_HEADER_RE = re.compile(r"^##\s+Audit\b")
AUDIT_PHASE_HEADER_RE = re.compile(r"^##\s+Audit\s+(P\d+)\s+—\s+(\d{4}-\d{2}-\d{2})\s*$")
# Terminal reducer evidence became mandatory only after the historical P0–P6
# journal/audit carriers were sealed.  Keep the boundary timestamp-precise: a
# date-only cutoff would retroactively reject records written earlier that day.
TERMINAL_POLICY_ACTIVATED_AT = "2026-08-14T00:00:00Z"
AUDIT_SEMANTIC_NEXT_RE = re.compile(r"^\s*(?:Semantic Next:|\*\*Next:\*\*)\s*`?([^`]+?)`?\.?\s*$")
# RAG-carrier fact markers (SKILL §7, enum of three values - D29) — heuristic by
# D-log. `RAG:—` (repo-grounded) is written via em dash, like EMPTY_PLACEHOLDER;
# ASCII-hyphen is not canonicalized.
RAG_MARKER_RE = re.compile(r"RAG:✅|RAG:" + EMPTY_PLACEHOLDER + r"|\[UNVERIFIED\]")
# launch-block in handoff.Next (SKILL §6): canonical output = metadata table + fenced command
# block. `| Command |` only remains reader-side back-compat for old plans.
LAUNCH_TABLE_ROW_RE = re.compile(
    r"^\|\s*(?:Model(?:\s+class)?\s*\||Batch\s*\|\s*Model\s*\|)"
)
LAUNCH_BATCH_ROW_RE = re.compile(r"^\|\s*Batch\s*\|\s*([^|]+?)\s*\|")
LAUNCH_COMMAND_ROW_RE = re.compile(r"^\|\s*Command\s*\|")
LAUNCH_CONTEXT_ROW_RE = re.compile(r"^\|\s*Context\s*\|\s*([^|]+?)\s*\|")
CODE_FENCE_RE = re.compile(r"^\s*```")
# Layout-v2 `Context` launch-block'a (SKILL §6, D16/D30/D125) — EXACTLY three
# values. The registry is NOT used ANYWHERE outside `--conflicts`: before this
# item'and field `Context` was not gated by any registry never - canon reconciliation↔implementation for
# it is added here for the FIRST TIME, and not republished from an existing gate (Pending Work P5.9
# names the extension to live-gate as a separate task - this item only makes the class matchable).
CONTEXT_VALUES = (
    "continue-root",
    "isolated-child-return",
    "cold-start-root",
)
CONTINUITY_GATE_DATE = "2026.09.09"
# The canonical literal directive lives in EN-only `SKILL.md`;
# regex is owned by this module, and `--conflicts` and the tests reuse it.
I18N_KEEP_RE = re.compile(r"<!--\s*i18n-keep:\s*(.+?)\s*-->")
# Canonical order of numbered sections plan.md (P0.3 rivers#6).
PLAN_SECTION_NUM_RE = re.compile(r"^##\s+(\d+)\.\s+(.*?)\s*$")
PLAN_SECTION_TITLES = {
    0: "Meta", 1: "Context", 2: "Execution Rules", 3: "Routing",
    4: "Phase Index & Status Board", 5: "Decision Log", 6: "Update Log",
}
# --- m7/D10: `## 7. Contracts` — media cross-plan notification ---------------
# Section is optional and young → ALL finds on it WARNING-level (ERROR would break
# back-compat-gate: no living fleet plan has a section).
# Identified by TITLE, not by number: number 7 is canon for NEW plans, but
# living plans have already occupied it with their sections (VLT-HSEAM «## 7. Discussion») — hard
# linking the number would give them new ones WARNING «≠ canonical «## 7. Contracts»».
CONTRACTS_HEADER_RE = re.compile(r"^##\s+(?:\d+\.\s+)?Contracts\s*$")
CONTRACTS_EXPORTED_RE = re.compile(r"^\s*###\s+Exported\s*$")
CONTRACTS_CONSUMED_RE = re.compile(r"^\s*###\s+Consumed\s*$")
EXPORTED_COLUMNS = ("Contract", "Version", "Status", "Consumers", "Notified")
CONSUMED_COLUMNS = ("Contract", "Donor plan", "Pinned", "Spotted", "Reaction")
SEMVER_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
DECISION_LOG_HEADER_RE = re.compile(r"^##\s+5\.\s+Decision Log\s*$")
UPDATE_LOG_HEADER_RE = re.compile(r"^##\s+6\.\s+Update Log\s*$")
UPDATE_LOG_MAX_CHARS = 300  # limit «What» Update Log (P0.3 rivers#5, EDUFY 54KB-incident)
PHASE_CONTEXT_HEADER_RE = re.compile(r"^##\s+Phase Context\s*$")
# threshold «item is essentially empty» for skeleton marker requirement
SKELETON_EMPTY_RATIO = 0.5

# --- canon ID / place-name workflow-script / supersedes --
# Since 2026-08-12 forward-only canon new PLAN-ID carries a positive daily ordinal:
# `YYYY.MM.DD-№N-CODE-NAME`.  The previous date format remains
# readable for history; `PLAN_ID_DATED_RE` deliberately combines both forms to
# age brief/journal gates were not lost numbered plans.
NUMBERED_PLAN_ID_CANON_DATE = "2026.08.12"
PLAN_ID_NUMBERED_RE = re.compile(
    r"^(?P<date>\d{4}\.\d{2}\.\d{2})-№(?P<ordinal>[1-9][0-9]*)-(?P<codename>[A-Z][A-Z0-9-]*)$")
PLAN_ID_NUMBERED_CANDIDATE_RE = re.compile(
    r"^(?P<date>\d{4}\.\d{2}\.\d{2})-№(?P<ordinal>[0-9]+)-(?P<codename>[A-Z][A-Z0-9-]*)$")
PLAN_ID_LEGACY_DATED_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}-[A-Z][A-Z0-9-]*$")
PLAN_ID_DATED_RE = re.compile(
    r"^\d{4}\.\d{2}\.\d{2}-(?:№[1-9][0-9]*-)?[A-Z][A-Z0-9-]*$")
PLAN_ID_LEGACY_RE = re.compile(r"^[A-Z][A-Z0-9-]+$")
# Marker workflow-script in the body.js — detection by SUBSTRING (not eval/import JS,
# use case `parse_script_meta`).
WORKFLOW_META_MARKER = "export const meta"
WORKFLOW_DIR_NAME = "workflows" # the only house of plan scripts
# Resident agent-pack class (harness dev-loop.js) — not a planned artifact, exempt by
# file name from location/check-name (findings A4).
DEV_LOOP_EXEMPT_NAME = "dev-loop.js"

# --- workflow-like-DoR — combable sign of the declared orchestration ---
# CONSERVATIVE set of markers in Phase Context: explicit `scriptPath` launch-block'ah,
# «orchestration», «multi-agent»/`multi-agent`. Rule Code Guidance «when in doubt DO NOT
# trigger» outweighs literal list: boomer `fan-out` INTENTIONALLY excluded -
# as a single word it catches irrelevant prose (e.g. «distortion when fan-out» in
# Known Deviations about token accounting), giving false warning. Convention: manual
# item-by-item execution workflow does not require - the marker must be intentional.
ORCHESTRATION_MARKER_RE = re.compile(r"scriptPath|orchestration|multi-agent|multi-agent", re.IGNORECASE)
ORCHESTRATION_NEGATION_RE = re.compile(
    r"(?:not\s+(?:statement\w*|required\w*|use\w*|needed\w*)|"
    r"without\s+(?:workflow|orchestration\w*|scriptPath|multi-agent\w*|multi-agent)|"
    r"(?:scriptPath|orchestration\w*|multi-agent\w*|multi-agent)\w*\s+"
    r"(?:not\s+(?:statement\w*|required\w*)|missing\w*))",
    re.IGNORECASE,
)


def phase_declares_orchestration(line):
    """Return whether one Phase Context line declares a workflow requirement.

    D11 deliberately keeps this predicate line-scoped: an explicit negation applies
    only to the statement that contains it, so a later positive declaration remains
    effective. Item specs are not phase declarations and their acceptance prose must
    not manufacture a workflow requirement.
    """
    return bool(ORCHESTRATION_MARKER_RE.search(line) and not ORCHESTRATION_NEGATION_RE.search(line))

# --- rotten `## Phase Handoff` during rheopen phase (H2) --------------
# Reopen (SKILL §3, 4-th step) DOES NOT delete the change block, but marks it with the FIRST NON-EMPTY line
# marker `> DEPRECATED — phase reopened <D#>` (delivery provenance is preserved, falsehood is removed);
# overwrites the block `plan-close` the next time the phase is closed. Bold marker style
# (`> **DEPRECATED - …**`) legal - the gate looks at the beginning of the line. It is the FIRST line, not
# «somewhere in the text»: otherwise the gate is bypassed by mentioning the word.
PHASE_HANDOFF_STALE_RE = re.compile(r"^>\s*\*{0,2}\s*DEPRECATED\b")
# NARROW predicate «block APPROVES phase closure». Forms taken from fleet measurements
# (8 roots / 38 plans): naive «block
# is non-empty for non-terminal phase» hits 104 phases (skeletons/blanks - false positive),
# these three forms are 4 phases, all true positive. DO NOT expand the list «just in case»:
# every extra word is a risk of false WARNING on a hundred phases (will go to the registry CANON_LITERALS,
#). Case insensitive (fleet writes and «Terminal…», and «terminal…»).
PHASE_HANDOFF_CLOSURE_LITERALS = ("terminal", "phase closed", "Submitted:")
PHASE_HANDOFF_CLOSURE_RE = re.compile(
    "|".join(re.escape(lit) for lit in PHASE_HANDOFF_CLOSURE_LITERALS), re.IGNORECASE)
# gate judges by the SUBJECT of the statement, and not by the word it encounters. Closing
# literal is searched ONLY in the FIRST non-empty line of the block (in the same place where the marker is searched
# `> DEPRECATED`), and is extinguished by NEGATION on the same line. Base (J1, living fleet form
# `themeon//P5`): «**Phase P5 is NOT closed.** Terminal only P5.1 and P5.2
# (2/10)» — word «Terminal» refers to ITEMS, block literally denies phase closure,
# and grep throughout the entire block gave a FALSE positive WARNING. Negation is checked for the SAME
# line, not block by block: «phase closed … but P5.3 is not closed yet» below in the text should not
# suppress true triggering (form `vaulter/VLT-REMED/P5` must stay WARNING).
PHASE_HANDOFF_NEGATION_LITERALS = ("not closed",)
PHASE_HANDOFF_NEGATION_RE = re.compile(
    "|".join(re.escape(lit) for lit in PHASE_HANDOFF_NEGATION_LITERALS), re.IGNORECASE)

# --- tiered-portability lint (plan-portability-v1.md, task_contract.py) ---
# Path ROLE classification (execution input vs provenance) — POSITIONAL test: path
# execution-input, only if appears in VALUE fields Inputs/Required Reads/Validation
# SPECIFIC item'a (the same «what item really reads» — plan-portability-v1.md
# §Provenance vs execution input). Other prose of the plan (Implementation Rules, Code Guidance,
# brief/, findings/) is NOT scanned at all - mentioning a path there by design cannot become
# execution input, which is what it is self-conformance fixture of this plan (tmp/-link in
# brief/00-brief.md must pass). Regex by substring `tmp/` for THIS step (role)
# DISABLED - Only field position is used. String test «appearance» paths
# (absolute/`~`/`../`/URL/`tmp/`-root) — SEPARATE step AFTER the role has already been resolved
# positionally (task_contract.is_external_path, task-contract-v1.md §Portability, frozen).
# Severity-cutoff (same pattern as BRIEF_CANON_DATE/JOURNAL_CANON_DATE): date
# plans FROM this date - ERROR, older - WARNING. Date INTENTIONALLY later than the day of sealing
# rules (2026-07-26, P2.2): fleet-frozen on a living tree (`bash
# packages/task/scripts/validate.sh`) opened ~40 `~`/absolute paths in Required
# Reads/Validation OTHER active plans -
# Date the rule before their date; the foreign-surface check rejects new records without them.
# participation. The rule itself has already been applied and tested (unit tests drive it to
# ERROR-shooting gallery with synthetic date fixtures); deferred cutoff — only about what
# ALREADY EXISTING fleet plans are not painted retroactively (back-compat §2).
PORTABILITY_TIER_CANON_DATE = "2026.07.27"
PORTABILITY_ROLE_FIELDS = ("Inputs", "Required Reads", "Validation")
# Shell-redirect (`> file` / `>> file`) in the field Validation — PURPOSE of diagnostic record
# (output her own team), not execution input; is cut BEFORE the paths are scanned, otherwise
# scratch redirect `>/tmp/…` would read like «item reads /tmp/…» (false positive).
PORTABILITY_SHELL_REDIRECT_RE = re.compile(r">>?\s*\S+")
# Candidate path - any path-like token (≥1 `/`, path-safe characters), backtick-quote or
# naked (snippets/protocol fixtures do not require quoting) — is scanned over ALL text
# fields, not one at a time «atomic» backtick-spanu (he often carries the whole team). Prefix
# `./` (repo-relative CLI-invocation of the form `./packages/skiller/bin/skiller`) — SEPARATE thread
# from naked `/` (absolute path): without it leading point «eaten» would be a regex, and
# `./packages/…` would read like `/packages/…` (absolute, external) — false positive.
PORTABILITY_PATH_RE = re.compile(
    r"(?:~/|\.\./|\./|/)?[A-Za-z0-9_.][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.][A-Za-z0-9_.-]*)+")


def _plan_codename(plan_id):
    """Plan code name - for name derivation workflow-script and supersedes-reconciliations:
    dated ID `YYYY.MM.DD-NAME` → part after date; old ID → all ID; always `.lower()`.
    Examples: → `flex`; `SKM-ROADMAP-005` → `skm-roadmap-005`."""
    numbered = PLAN_ID_NUMBERED_RE.match(plan_id)
    if numbered:
        return numbered.group("codename").lower()
    if PLAN_ID_DATED_RE.match(plan_id) and "-" in plan_id:
        return plan_id.split("-", 1)[1].lower()
    return plan_id.lower()


def _workflow_name_re(codename):
    """Canonical name workflow-script - `wf-<code-name-lower>-<purpose>.js`."""
    return re.compile(r"^wf-" + re.escape(codename) + r"-[a-z0-9-]+\.js$")


def _plan_has_workflow_script(plan_dir):
    """Does the plan have at least one `.js`-workflow-script (with marker `export const meta`)
    in `plans/<ID>/workflows/` — sign «ready workflow» for DoR-checks.
    Detection WITHOUT execution JS (substring marker, use case)."""
    workflows_dir = Path(plan_dir) / WORKFLOW_DIR_NAME
    if not workflows_dir.is_dir():
        return False
    for js in workflows_dir.glob("*.js"):
        if not js.is_file():
            continue
        try:
            if WORKFLOW_META_MARKER in js.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeDecodeError):
            continue
    return False


class Diagnostics:
    """Moneybox ERROR/WARNING with human readable output (Russian, file:line)."""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self._raw_errors = [] # (path, msg) — for normalized_keys
        self._raw_warnings = []

    def error(self, path, line, msg):
        self.errors.append(f"{_loc(path, line)}: {msg}")
        self._raw_errors.append((Path(path), msg))

    def warning(self, path, line, msg):
        self.warnings.append(f"{_loc(path, line)}: {msg}")
        self._raw_warnings.append((Path(path), msg))

    @property
    def ok(self):
        return not self.errors

    def normalized_keys(self, base_dir):
        """Multiset `(kind, rel_path, msg)` for tree comparison (`--baseline`,
        ): path - relative `base_dir` (if under it, otherwise as is),
        line number is NOT involved (shifting lines from its own diff should not turn
        old error in «new»)."""
        base_dir = Path(base_dir).resolve()

        def rel(path):
            try:
                return str(Path(path).resolve().relative_to(base_dir))
            except ValueError:
                return str(path)

        def stable_message(message):
            message = re.sub(
                r"(read-budget-v1: item P\d+\.\d+: weight )\d+( > threshold \d+ evaluation tokens)",
                r"\1<observed>\2",
                message,
            )
            return re.sub(
                r"(read-budget-v1: item P\d+\.\d+: file .+ — )\d+( bytes, )\d+( evaluation tokens; limits per reading )",
                r"\1<observed-bytes>\2<observed-tokens>\3",
                message,
            )

        keys = [("ERROR", rel(p), stable_message(m)) for p, m in self._raw_errors]
        keys += [("WARN", rel(p), stable_message(m)) for p, m in self._raw_warnings]
        return keys


def _loc(path, line):
    return f"{path}:{line}" if line else str(path)


def _is_empty(value):
    v = (value or "").strip()
    return v == "" or v == EMPTY_PLACEHOLDER


def _terminal_policy_is_active(entry):
    """Whether an append-only event was authored after policy activation.

    The journal timestamp is the carrier for an audit block as well: its heading
    intentionally contains only a date and cannot distinguish two writes on the
    activation day.
    """
    return (isinstance(entry, dict)
            and isinstance(entry.get("ts"), str)
            and entry["ts"] >= TERMINAL_POLICY_ACTIVATED_AT)


# --- low-level parsing markdown -----------------------------------------

def _read_lines(path):
    """Reads the file line by line (without \\n). None — if there is no file/is not readable."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text.replace("\r\n", "\n").split("\n")


def _section_header_indexes(lines):
    """Indexes of all level 2 header rows (`## …`, NOT `### …`)."""
    return [i for i, ln in enumerate(lines) if SECTION_HEADER_RE.match(ln)]


def _section_body(lines, header_idx, header_idxs):
    """Section body header_idx: lines before the next `##`-header or EOF.
    Returns (body_lines, first_line_no) — line_no 1-index, for diagnostics."""
    following = [i for i in header_idxs if i > header_idx]
    end = following[0] if following else len(lines)
    return lines[header_idx + 1:end], header_idx + 2  # +2: 1-index + shift to next. line


def _find_section(lines, header_re):
    """Looks for the FIRST line that matches header_re, among `##`-headers.
    Returns (header_idx, body_lines, body_start_lineno) or (None, None, None)."""
    header_idxs = _section_header_indexes(lines)
    for idx in header_idxs:
        if header_re.match(lines[idx]):
            body, start_lineno = _section_body(lines, idx, header_idxs)
            return idx, body, start_lineno
    return None, None, None


def _lines_before_audit(lines):
    """Phase lines BEFORE the first append-block `## Audit` — phase grep region.
    Source list prefix ⇒ line numbers (i + 1) remain valid for diagnostic purposes."""
    for i, ln in enumerate(lines):
        if AUDIT_BLOCK_HEADER_RE.match(ln):
            return lines[:i]
    return lines


def _lint_audit_scope_payload(lines, path, plan_id, diag):
    """Scope-payload launch-block'and in blocks `## Audit Pn` (SKILL §8, D-canon 2026-07-17).

    Audit with verdict RED/ATTENTION PASSES over the findings to the next session, and the naked team
    loses: the receiving session rediscovers the findings itself, and `handoff.md` at this moment still
    points to the PREVIOUS step and leads past. Causing incident - audit P0 plan
    : launch-block `/task:plan-design <ID> P0` without payload'and the owner
    read as «phase is proposed to be developed anew», a `plan-audit.md` exactly naked
    command and prescribed. Rule cold-start («input dock paths») existed before
    incident - the form and gate were missing.

    The PRESENCE of four lines is gated; meaningfulness `SCORE:`/`DO NOT TOUCH:` machine is not
    measures (report-quality — next audit matter). Severity — like brief/launch-block:
    date plans from BRIEF_CANON_DATE — ERROR, older/legacy — WARNING (back-compat §2:
    living fleet plans were written before canon and they cannot be painted retroactively).
    """
    header_idxs = _section_header_indexes(lines)
    for idx in header_idxs:
        if not AUDIT_BLOCK_HEADER_RE.match(lines[idx]):
            continue
        body, _ = _section_body(lines, idx, header_idxs)
        if not body:
            continue
        body_text = "\n".join(body)
        verdict = AUDIT_VERDICT_RE.search(body_text)
        # A block without a verdict line is not an audit report in the form (free note): don't gate,
        # otherwise the linter will start demanding payload from arbitrary `## Audit …`-header.
        if not verdict or verdict.group(1) not in AUDIT_FINDINGS_VERDICTS:
            continue
        missing = []
        if not any(LAUNCH_TABLE_ROW_RE.match(ln) for ln in body):
            missing.append("tables `| Model | …`")
        if not any(CODE_FENCE_RE.match(ln) for ln in body):
            missing.append("code-block with the command")
        missing.extend("lines `%s`" % m for m in SCOPE_PAYLOAD_MARKERS if m not in body_text)
        if not missing:
            continue
        msg = (f"«{lines[idx].strip()}»: verdict {verdict.group(1)} reports findings, but "
               f"launch-block incomplete - no " + ", ".join(missing) +
               " (scope-payload — SKILL §8, snippets/launch-block-template.md)")
        if PLAN_ID_DATED_RE.match(plan_id) and plan_id[:10] >= BRIEF_CANON_DATE:
            diag.error(path, idx + 1, msg)
        else:
            diag.warning(path, idx + 1, msg)


def _lint_audit_terminal_policy(lines, path, plan_dir, plan_id, phase_id, diag):
    """Bind the latest phase audit block to reducer evidence and its exact Next.

    This is the machine seam D24 previously lacked: prose can no longer turn an
    ordinary repair into ``audit-red → plan-design``.  Historical blocks remain
    warnings; new blocks are errors.  Delivery and journal append enforce the same
    policy without a date carve-out.
    """
    header_idxs = _section_header_indexes(lines)
    matching = []
    for idx in header_idxs:
        match = AUDIT_PHASE_HEADER_RE.fullmatch(lines[idx].strip())
        if match and match.group(1) == phase_id:
            matching.append((idx, match.group(2)))
    if not matching:
        return
    idx, audit_date = matching[-1]
    body, _ = _section_body(lines, idx, header_idxs)
    body_text = "\n".join(body)
    verdict_match = AUDIT_VERDICT_RE.search(body_text)
    if not verdict_match:
        return

    latest = None
    journal_path = Path(plan_dir) / _journal.FILENAME
    if journal_path.is_file():
        try:
            rows = journal_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            rows = []
        for raw in rows:
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
                _journal.validate_entry(event)
            except (json.JSONDecodeError, _journal.JournalValidationError):
                continue
            if (event.get("command") == "plan-audit"
                    and _review_policy.phase_audit_subject(event.get("item_id")) == phase_id
                    and event.get("result") in {"audit-green", "audit-attention", "audit-red"}):
                latest = event
    report = diag.error if _terminal_policy_is_active(latest) else diag.warning
    if latest is None:
        report(path, idx + 1,
               f"latest Audit {phase_id}: no phase-audit journal event for terminal policy")
        return

    expected_result = {
        "GREEN": "audit-green", "ATTENTION": "audit-attention", "RED": "audit-red",
    }[verdict_match.group(1)]
    if latest.get("result") != expected_result:
        report(path, idx + 1,
               f"latest Audit {phase_id}: verdict {verdict_match.group(1)} does not match "
               f"with journal result {latest.get('result')!r}")
        return
    next_exact = None
    for line in body:
        match = AUDIT_SEMANTIC_NEXT_RE.fullmatch(line)
        if match:
            next_exact = match.group(1).strip()
            break
    if not next_exact:
        report(path, idx + 1,
               f"latest Audit {phase_id}: no provider-neutral Semantic Next")
        return
    try:
        _review_policy.validate_phase_audit_continuation(
            latest, plan_id=plan_id, next_exact=next_exact, plan_dir=plan_dir)
    except _review_policy.ReviewPolicyError as exc:
        report(path, idx + 1, str(exc))


def _parse_table(body_lines, body_start_lineno):
    """Parses the first markdown-table in a row block. Returns
    (headers, rows, header_lineno) — rows: list[dict[col] = (value, row_lineno)].
    (None, [], None) — if there is no table in the block."""
    start = None
    for i, ln in enumerate(body_lines):
        if ln.strip().startswith("|"):
            start = i
            break
    if start is None:
        return None, [], None

    def split_row(ln):
        s = ln.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [c.strip() for c in s.split("|")]

    headers = split_row(body_lines[start])
    rows = []
    i = start + 2  # string start+1 — delimiter `---|---`, skipped without format checking
    while i < len(body_lines) and body_lines[i].strip().startswith("|"):
        cells = split_row(body_lines[i])
        row = {headers[j]: (cells[j] if j < len(cells) else "") for j in range(len(headers))}
        rows.append((row, body_start_lineno + i))
        i += 1
    return headers, rows, body_start_lineno + start


def _parse_fields(body_lines, body_start_lineno, field_re):
    """Parses field strings `**Field:** value` (value may continue
    on the following lines until the next field/end of block). Returns
    (fields, duplicates): fields — dict[name] = (value, lineno) LAST occurrence
    (back-compat: consumers as read dict, read like this); duplicates —
    [(name, first_lineno, first_value, dup_lineno, dup_value)] for EVERY repeat
    occurrence of the key, in order of appearance (D90: `**Field:**`-line inside free prose
    of another field - e.g. `**Validation:**`, added in Completion Notes, — matchit is the same
    `field_re` and silently overrides the field's earlier legitimate value; the caller decides
    diagnose the finding or skip it - handoff-fields out Scope,
    only item-fields)."""
    fields = {}
    first_seen = {}
    duplicates = []
    cur_key = cur_lineno = None
    cur_val = []

    def flush():
        if cur_key is not None:
            value = "\n".join(cur_val).strip()
            if cur_key in first_seen:
                prev_lineno, prev_value = first_seen[cur_key]
                duplicates.append((cur_key, prev_lineno, prev_value, cur_lineno, value))
            else:
                first_seen[cur_key] = (cur_lineno, value)
            fields[cur_key] = (value, cur_lineno)

    for i, ln in enumerate(body_lines):
        m = field_re.match(ln)
        if m:
            flush()
            cur_key = m.group(1).strip()
            cur_lineno = body_start_lineno + i
            rest = m.group(2).strip()
            cur_val = [rest] if rest else []
        elif ESCALATION_RE.match(ln):
            # The generated state keeps the escalation quote after the last field.
            # It is a sibling marker, not a continuation of Escalation Needed.
            continue
        elif cur_key is not None:
            if ln.strip() or cur_val:
                cur_val.append(ln.rstrip())
    flush()
    return fields, duplicates


def _preview(text, limit=72):
    """First non-empty value string, truncated to `limit` (D90-diagnostics: both sides
    discrepancies in one line of the report - the full multi-line value is not readable there)."""
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return first_line if len(first_line) <= limit else first_line[:limit].rstrip() + "…"


def _find_items(lines):
    """All item-blocks `### Pn.m — Header` in the file. Returns
    list[(item_id, title, header_lineno, body_lines, body_start_lineno)]
    (list - not dict: duplicates ID should not silently collapse)."""
    header_idxs = [i for i, ln in enumerate(lines) if ln.startswith("###")]
    section_idxs = _section_header_indexes(lines)
    boundaries = sorted(set(header_idxs) | set(section_idxs) | {len(lines)})
    items = []
    for idx in header_idxs:
        m = ITEM_HEADER_RE.match(lines[idx])
        if not m:
            continue  # header like "### …" no match item-pattern - not item
        item_id, title = m.group(1), m.group(2).strip()
        nxt = min(b for b in boundaries if b > idx)
        items.append((item_id, title, idx + 1, lines[idx + 1:nxt], idx + 2))
    return items


def _malformed_item_headers(lines):
    """Lines `### …`, similar to item-header (yes Pn.m), but not passed
    strict regex (e.g. without ` — ` delimiter) — separate ERROR-category."""
    bad = []
    loose_re = re.compile(r"^###\s+(P\d+\.\d+)\b")
    for i, ln in enumerate(lines):
        if ln.startswith("###") and loose_re.match(ln) and not ITEM_HEADER_RE.match(ln):
            bad.append((ln, i + 1))
    return bad


# --- warning-checks 2.0 for plan.md ------------------------------------------

__all__ = tuple(name for name in globals() if not name.startswith("__"))
