"""plan_weight — weight of required reading of the plan item.

The instrument reproduces the REQUIRED READING PATH of the performer from
`packages/task/commands/plan-run.md` literally and considers its weight in estimated
tokens on top of FROZEN calibration P0.1 (`task.token_estimate`, artifact
`configs/token-estimate-calibration.json`), checking each required file against
MEASURED limit per reading P0.2 (`configs/read-limit.json`).

Mandatory path requires explicit `Layout | v2` and matches five executor
slots frozen `read-path` contract:

    1) plan.md                         → `plan-core`
    2) phases/<Pn>/<Pn>.md             → `phase-context`
    3) phases/<Pn>/<Pn.m>.md           → `item-spec`
    4) bundles/<Pn.m>.json + selections → `item-input-bundle` + `bundle-input`
    5) phases/<Pn>/<Pn.m>.state.md     → `item-state`

Generated bundle/state pass owning freshness check before use. `handoff.md`
in layout-v2 executor path is not included.

Two measuring phase asymmetries P0 (`research/02-p0-measurement-design.md` §5)
are reproduced literally here:

* for TOKENS the measurement comes from the TOP - assessment `token_estimate` never understates on the body
  prose plans (border on dense ASCII NOT proven, D109 — is therefore considered
  `dense_ascii_share`, see below);
* according to the COMPOSITION of files, the measurement comes from the BOTTOM - `Required Reads` today prose, some positions are not
  is reduced to a path, and such positions are not included in the sum. Therefore, the report will NEVER
  prints the sum without a list of spaces: the sum without spaces is the lower estimate given
  per measured.

Whitespace Taxonomy CLOSED (`GAP_KINDS`, `research/02-…` §5): `unreadable_root` ·
`unresolved_entry` · `missing_file` · `oversized_file`. «Other» will not start.

`oversized_file` — is the only category whose weight is KNOWN and therefore INCLUDED in the amount:
file is allowed and read, it only violates the acceptance condition D2(b) (read ENTIRELY
IN ONE call). The other three categories have no weight by design - they have nothing
summarize. Position `oversized_file` carries the field `gate` (`size_bytes` | `tokens` |
`both`): P0.4 is obliged to divide the list by gates; reducing them to one number loses
failure class (D107/D108).

File check against limit - CONJUNCTION of both gates (D108,
`research/12-read-limit-design-2026-08-07.md` §5):

    pass(f) = bytes(f) ≤ limits.size_bytes.value  AND  est_tokens(f) ≤ limits.tokens.value

Token side - ESTIMATE FROM TOP: the environment counter is visible only at the moment of activation
mouth guard (`findings/15-…` O6), in CI it's not there. Page-by-page reading condition NOT
satisfies and is not a relief.

`dense_ascii_share` (D109) — proportion of file characters included in contiguous runs of length
≥ `DENSE_ASCII_MIN_RUN` characters from `[0-9A-Za-z+/=]` without whitespace delimiters. This
GATE, not gate: there is NO threshold for it, the file for it is not rejected and
«suspicious» is not marked - the thresholds freeze P0.5 on fleet numbers P0.4.

**Resolving heuristic `Required Reads`** (future contract input bundle, P3) — «best
force», described here in its entirety, because it determines what will be included in the amount:

1. The field value is cut into positions according to numbering `N)` (`ENTRY_NUMBER_RE`); no numbering
   — the entire value is considered one position.
2. Candidates are taken from TWO sources with DIFFERENT claim strengths:
   * span in backquotes (`` `…` ``) — DECLARED path;
   * bare position token - fleet plans until 2026.07 write paths without backticks
     (`1) packages/skiller/lib/skiller/analyze.py (…)`), to lose them would be to underestimate
     weight where the performer reads the file without thinking. Naked form token
     `directory/file.ext` (`_is_strong_path`) is considered the same ANNOUNCEMENT, that's all
     rest («P4 finding/research») — GUESS.
3. The token is expanded using curly braces (`core/provider/{registry,artifact,lock}.py` →
   three ways); opening wider `MAX_BRACE_EXPANSION` is considered unlucky.
4. The token is recognized as path-like (`_is_path_like`), if consists of valid pathnames
   characters And carries `/` or extension starting with LETTER (otherwise `P0.1` from prose
   «P0.1 Completion Notes» would falsely appear to be a file).
5. Path-like token resolves to roots in order: absolute path · plan directory ·
   repository root (first existing file wins).
6. The difference in assertion strength is in the miss classification: ANNOUNCED path not found
   file, is `missing_file` (path named, no file); GUESS, which did not find the file,
   does not become a separate class space and `missing_file` is not making things up - position
   remains unresolved. A position without a single allowed path and without a declared one
   miss → `unresolved_entry`.
7. Meaning `—` (canonical empty protocol placeholder) means that `Required
   Reads` no at all: zero positions, zero spaces.

Files are deduplicated along the allowed path: the executor reads the file once, and
repeated mention `phases/P1.md` in `Required Reads` does not double the weight.

Calibration and limit artifacts are MANDATORY: their absence or invalidity is intelligible
error and return code ≠ 0. There are no literal defaults for either rates or limits.
Tool opens files read ONLY (D3: other people's plans are read, but not
change), does not open the network and does not read credentials in any mode.

Mode `--exact` (D92/D99) — DIFFERENTIAL HARNESS, NOT a challenge `count_tokens`:
checks the estimate from above against the truth of the triple pass protocol P0.1
(`packages/task/scripts/calibrate-token-estimate.py`, run artifact
`calibration-probe-log.json`) on EXPLICITLY SPECIFIED files. Exists for parsing only
human edge case: manual run, mode prints warning and NEVER
does not participate in CI. `count_tokens` is not implemented by this module and is not called in any
one mode (key Console will not have an owner - declared environment property,
R21/R22 `findings/14-…`).

stdlib-only; `core` (via `task.plan_lint`) goes to the same fallback `sys.path`, as
in `plan-lint.py`. Parsing of phase files is delegated `task.plan_lint.parse_phase_md` —
to the same parser with which the plan is read by the linter: the second parser would mean the second
schema definition.
"""
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from task import (plan_admission, plan_bundle, plan_item_state, plan_lint, plan_layout,
                  token_estimate)

# --- required reading path (`plan-run.md`) ----------------------------------

# Literals §1 in order; the test checks them against the actual command text -
# edit `plan-run.md` is obliged to break the test, and not to disagree with the tool silently.
MANDATORY_PATH_LITERALS = (
    "plans/<PLAN-ID>/plan.md",
    "plans/<PLAN-ID>/handoff.md",
    "plans/<PLAN-ID>/phases/Pn.md",
    "**Required Reads**",
)
V2_MANDATORY_PATH_LITERALS = (
    "scripts/plan-work.py prepare",
    "selected item capsule",
    "plan-work.py validate",
    "plan-work.py close",
)
PLAN_RUN_RELPATH = Path("packages/task/commands/plan-run.md")

V1_ROLES = ("plan", "handoff", "phase", "required_read")
V2_CARRIER_ROLES = (
    "plan-core", "phase-context", "item-spec", "item-input-bundle", "item-state")
V2_INPUT_ROLE = "bundle-input"
# Backward-compatible public alias used by existing consumers/tests.
ROLES = V1_ROLES

# --- whitespace taxonomy (closed, research/02 §5) --------------------------------

GAP_UNREADABLE_ROOT = "unreadable_root"
GAP_UNRESOLVED_ENTRY = "unresolved_entry"
GAP_MISSING_FILE = "missing_file"
GAP_OVERSIZED_FILE = "oversized_file"
GAP_KINDS = (GAP_UNREADABLE_ROOT, GAP_UNRESOLVED_ENTRY, GAP_MISSING_FILE, GAP_OVERSIZED_FILE)

GATE_SIZE_BYTES = "size_bytes"
GATE_TOKENS = "tokens"
GATE_BOTH = "both"
GATES = (GATE_SIZE_BYTES, GATE_TOKENS, GATE_BOTH)

# --- dense_ascii_share (D109) ------------------------------------------------------

# The classifier belongs to token_estimate; retaining this public alias avoids a second owner.
DENSE_ASCII_MIN_RUN = token_estimate.DENSE_ASCII_MIN_RUN
dense_ascii_share = token_estimate.dense_ascii_share

# --- resolution Required Reads ------------------------------------------------------

ENTRY_NUMBER_RE = re.compile(r"(?:^|\s)(\d{1,2})\)\s")
BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")
# An empty field is marked with exactly this symbol - the canon registry holds `plan_lint`.
EMPTY_PLACEHOLDER = plan_lint.EMPTY_PLACEHOLDER
# Framing punctuation around bare token (herringbone quotes, parentheses, commas).
BARE_TOKEN_STRIP = "«»\"'(),;:.…“”[]"
BRACE_GROUP_RE = re.compile(r"\{([^{}]*)\}")
MAX_BRACE_EXPANSION = 64
# Plan IDs are explicitly Unicode-capable (for example, `№1`).  A path is
# never executed here: it is resolved with pathlib and read only.  Restrict
# the lexical form to one non-whitespace, non-backtick token so a declared
# Unicode path keeps the same fail-closed missing-file semantics as ASCII.
PATH_TOKEN_RE = re.compile(r"^[^\s`]+$")
# The extension must begin with a LETTER: `.md`/`.py`/`.json` — path, `P0.1` — prose.
PATH_SUFFIX_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")

DEFAULT_READ_LIMIT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "read-limit.json"
)
DEFAULT_CANON_BUDGET_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "canon-weight-budget.json"
)

# Artifact of differential harvesting run P0.1 — single source «truth» for
# `--exact` (the same path that writes `calibrate-token-estimate.py`); the root is taken from
# layout of the module itself, and not from cwd.
DEFAULT_PROBE_LOG_RELPATH = Path("packages/task/configs/calibration-probe-log-v2.json")
_MONOREPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PROBE_LOG_PATH = _MONOREPO_ROOT / DEFAULT_PROBE_LOG_RELPATH

SCHEMA = "plan-weight-v1"

# Environment variables from which the current environment model is taken for WARNING o
# discrepancy with `tokenizer.model_id` calibration (mitigation pre-mortem #1). None
# is set - no warning: absence of evidence is not conjectured.
SESSION_MODEL_ENV = ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "CLAUDE_CODE_MODEL")
SESSION_PROVIDER_ENV = ("TOKEN_ESTIMATE_PROVIDER",)


class PlanWeightError(Exception):
    """Invalid tool input (artifact, plan, arguments) — fail-closed, exit ≠ 0."""


# --- limit artifact ---------------------------------------------------------------

def load_read_limit(path=None):
    """Reads and validates `configs/read-limit.json` (form - `research/12-…` §3).

    BOTH fields are read (`limits.size_bytes.value`, `limits.tokens.value`); absence
    any of the two = invalid artifact (D107). There are no literal defaults."""
    path = Path(path) if path is not None else DEFAULT_READ_LIMIT_PATH
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanWeightError(f"read limit artifact not readable: {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PlanWeightError(f"read limit artifact - invalid JSON: {path}: {exc}") from exc

    limits = data.get("limits")
    if not isinstance(limits, dict):
        raise PlanWeightError(f"read limit artifact: no section «limits»: {path}")
    values = {}
    for gate in (GATE_SIZE_BYTES, GATE_TOKENS):
        node = limits.get(gate)
        if not isinstance(node, dict) or "value" not in node:
            raise PlanWeightError(
                f"read limit artifact: no gate «limits.{gate}.value» — environment carries TWO "
                f"independent gate, one scalar limit must lie (D107): {path}")
        value = node["value"]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise PlanWeightError(
                f"read limit artifact: limits.{gate}.value must be integer > 0, "
                f"received {value!r}: {path}")
        values[gate] = value
    return {"path": str(path), "artifact": data,
            "size_bytes": values[GATE_SIZE_BYTES], "tokens": values[GATE_TOKENS]}


def session_model_id(explicit=None):
    """Current environment model: explicit argument, otherwise first exposed variable
    from `SESSION_MODEL_ENV`. Nothing set - `None` (evidence of absence)."""
    if explicit:
        return explicit
    for name in SESSION_MODEL_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return None


def session_provider_id(explicit=None):
    if explicit:
        return explicit
    for name in SESSION_PROVIDER_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return None


# --- file measurement ---------------------------------------------------------------

def measure_file(path, *, role, artifact, limits, model_id=None):
    """One mandatory path file entry: bytes, token score TOP, dense share
    ASCII and the result of CONJUNCTION of both gates (D108).

    The file is read in bytes and decoded utf-8 with replacement of faulty sequences:
    mandatory path can also be non-text (`.json`-artifacts, scripts), and measurement is required
    give a number, not an exception - the weight is still calculated based on the decoded text."""
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    est = token_estimate.estimate_text(text, artifact=artifact, session_model_id=model_id)
    size_ok = len(raw) <= limits["size_bytes"]
    tokens_ok = est <= limits["tokens"]
    return {
        "path": str(path),
        "role": role,
        "bytes": len(raw),
        "chars": len(text),
        "est_tokens": est,
        "dense_ascii_share": dense_ascii_share(text),
        "gates": {GATE_SIZE_BYTES: size_ok, GATE_TOKENS: tokens_ok},
        "passes": size_ok and tokens_ok,
    }


def measure_bytes(raw, *, path, role, artifact, limits, model_id=None):
    """Measure one digest-qualified selection without pretending it is a whole file."""
    text = raw.decode("utf-8", errors="replace")
    est = token_estimate.estimate_text(text, artifact=artifact, session_model_id=model_id)
    size_ok = len(raw) <= limits["size_bytes"]
    tokens_ok = est <= limits["tokens"]
    return {
        "path": str(path),
        "role": role,
        "bytes": len(raw),
        "chars": len(text),
        "est_tokens": est,
        "dense_ascii_share": dense_ascii_share(text),
        "gates": {GATE_SIZE_BYTES: size_ok, GATE_TOKENS: tokens_ok},
        "passes": size_ok and tokens_ok,
    }


def measure_document(path, measurer):
    """Measure one UTF-8 instruction carrier in tokens and physical lines."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PlanWeightError(f"document is not readable: {path}: {exc}") from exc
    text = raw.decode("utf-8", errors="replace")
    return {
        "path": str(path),
        "bytes": len(raw),
        "lines": len(text.splitlines()),
        "est_tokens": token_estimate.estimate_text(
            text, artifact=measurer.artifact, session_model_id=measurer.model_id),
    }


def load_canon_budget(path):
    """Load the D93 two-threshold canon budget; malformed policy fails closed."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanWeightError(f"canon budget is not readable JSON: {path}: {exc}") from exc
    required = ("canon_path", "baseline", "warning_fraction", "regression_percent",
                "vendor_line_guidance", "exceptions")
    missing = [key for key in required if key not in data]
    if missing:
        raise PlanWeightError(f"canon budget lacks required keys {missing}: {path}")
    baseline = data["baseline"]
    if not isinstance(baseline, dict) or not isinstance(baseline.get("est_tokens"), int):
        raise PlanWeightError(f"canon budget baseline.est_tokens must be an integer: {path}")
    warning = data["warning_fraction"]
    regression = data["regression_percent"]
    if (not isinstance(warning, (int, float)) or isinstance(warning, bool)
            or not 0 < warning < 1):
        raise PlanWeightError(f"canon budget warning_fraction must be between 0 and 1: {path}")
    if (not isinstance(regression, (int, float)) or isinstance(regression, bool)
            or regression < 0):
        raise PlanWeightError(f"canon budget regression_percent must be non-negative: {path}")
    exceptions = data["exceptions"]
    if not isinstance(exceptions, list):
        raise PlanWeightError(f"canon budget exceptions must be a list: {path}")
    for entry in exceptions:
        if not isinstance(entry, dict) or not entry.get("expires_at"):
            raise PlanWeightError(f"every canon budget exception needs expires_at: {path}")
        try:
            date.fromisoformat(entry["expires_at"])
        except (TypeError, ValueError) as exc:
            raise PlanWeightError(
                f"invalid canon budget exception expiry {entry.get('expires_at')!r}: {path}") from exc
    return data


def evaluate_canon_budget(budget_path, measurer, *, today=None):
    """Evaluate hard cap, warning threshold, regression allowance, and dated exceptions."""
    budget_path = Path(budget_path)
    budget = load_canon_budget(budget_path)
    canon_path = Path(budget["canon_path"])
    if not canon_path.is_absolute():
        canon_path = _MONOREPO_ROOT / canon_path
    current = measure_document(canon_path, measurer)
    baseline = budget["baseline"]
    hard_cap = measurer.limits["tokens"]
    warning_at = int(hard_cap * budget["warning_fraction"])
    regression_limit = int(
        baseline["est_tokens"] * (1 + budget["regression_percent"] / 100))
    today = today or date.today()
    active = [entry for entry in budget["exceptions"]
              if date.fromisoformat(entry["expires_at"]) >= today]
    cap_exceeded = current["est_tokens"] > hard_cap
    regression_exceeded = current["est_tokens"] > regression_limit
    has_justification = bool((budget.get("regression_justification") or "").strip())
    failures = []
    if cap_exceeded and not active:
        failures.append("hard_cap")
    if regression_exceeded and not has_justification and not active:
        failures.append("regression")
    return {
        "schema": "canon-weight-v1",
        "budget_path": str(budget_path),
        "current": current,
        "baseline": baseline,
        "hard_cap_tokens": hard_cap,
        "warning_threshold_tokens": warning_at,
        "warning": current["est_tokens"] >= warning_at,
        "regression_limit_tokens": regression_limit,
        "regression_justification": budget.get("regression_justification", ""),
        "vendor_line_guidance": budget["vendor_line_guidance"],
        "active_exceptions": active,
        "failures": failures,
        "passes": not failures,
    }


def violated_gate(file_record):
    """Which of the two gates is broken: `size_bytes` | `tokens` | `both`; `None` — both ok."""
    gates = file_record["gates"]
    if gates[GATE_SIZE_BYTES] and gates[GATE_TOKENS]:
        return None
    if not gates[GATE_SIZE_BYTES] and not gates[GATE_TOKENS]:
        return GATE_BOTH
    return GATE_SIZE_BYTES if not gates[GATE_SIZE_BYTES] else GATE_TOKENS


# --- resolution Required Reads ------------------------------------------------------

def split_semicolon_entries(value):
    """Split list separators, preserving quoted paths and parenthesized annotations."""
    entries, start, depth, quoted = [], 0, 0, False
    for index, char in enumerate(value):
        if char == "`":
            quoted = not quoted
        elif not quoted:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            elif char == ";" and depth == 0:
                if value[start:index].strip():
                    entries.append(value[start:index].strip())
                start = index + 1
    if value[start:].strip():
        entries.append(value[start:].strip())
    return entries


def split_entries(value):
    """Field value `Required Reads` → list of positions by numbering `N)`. No numbering
    — positions are separated by semicolons outside of paths and annotations. Canonical empty
    placeholder `—` means no Required Reads, rather than an unresolved position."""
    text = " ".join((value or "").split())
    if not text or text == EMPTY_PLACEHOLDER:
        return []
    marks = [m for m in ENTRY_NUMBER_RE.finditer(text)]
    if not marks:
        return split_semicolon_entries(text)
    entries = []
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        entry = text[start:end].strip().rstrip(".").strip()
        if entry:
            entries.append(entry)
    return entries


def expand_braces(token):
    """`a/{x,y}.py` → `['a/x.py', 'a/y.py']`. Opening wider `MAX_BRACE_EXPANSION`
    returns the original token intact (then it is not path-like and will go into space)."""
    m = BRACE_GROUP_RE.search(token)
    if not m:
        return [token]
    head, tail = token[:m.start()], token[m.end():]
    out = []
    for alt in m.group(1).split(","):
        alt = alt.strip()
        if not alt:
            continue
        out.extend(expand_braces(head + alt + tail))
        if len(out) > MAX_BRACE_EXPANSION:
            return [token]
    return out or [token]


def _is_path_like(token):
    if not token or not PATH_TOKEN_RE.match(token) or token.endswith("/"):
        return False
    return "/" in token or bool(PATH_SUFFIX_RE.search(token))


def _is_strong_path(token):
    """`directory/file.ext` — form that cannot be confused with prose: and a directory separator,
    and an extension starting with a letter."""
    return _is_path_like(token) and "/" in token and bool(PATH_SUFFIX_RE.search(token))


def path_candidates(entry):
    """Path-like position candidates in order of appearance: `[(token, declared)]`, where
    `declared` — whether the token was in backquotes. DECLARED path - author's statement
    plan (miss = `missing_file`); bare token - resolver's guess (the miss is silent,
    position remains unresolved)."""
    candidates, seen = [], set()

    def take(raw, declared):
        for token in expand_braces(raw.strip()):
            if _is_path_like(token) and token not in seen:
                seen.add(token)
                candidates.append((token, declared))

    for span in BACKTICK_SPAN_RE.findall(entry):
        take(span, True)
    for word in BACKTICK_SPAN_RE.sub(" ", entry).split():
        token = word.strip(BARE_TOKEN_STRIP)
        # Naked view token `directory/file.ext` — same path declaration as in backticks
        # (form of fleet plans until 2026.07); bare token without extension («P4
        # finding/research») remains a guess, the miss of which does not invent a space.
        take(token, _is_strong_path(token))
    return candidates


def resolve_candidate(token, roots):
    """First existing root file is ok `roots`; `None` — not found."""
    p = Path(token)
    if p.is_absolute():
        return p if p.is_file() else None
    for root in roots:
        if root is None:
            continue
        cand = Path(root) / token
        if cand.is_file():
            return cand
    return None


# --- item measurement / plan -------------------------------------------------------------

def repo_root_for(plan_dir):
    """Plan repository root: directory's closest ancestor `plans/` (archived plans
    `plans/archive/<ID>` give the same root). Catalog outside `plans/` — plan parent."""
    plan_dir = Path(plan_dir).resolve()
    for anc in plan_dir.parents:
        if anc.name == "plans":
            return anc.parent
    return plan_dir.parent


class Measurer:
    """General measurement context: artifacts, cache of measured files (plan.md is measured once
    for the entire plan, not for each item), environment model."""

    def __init__(self, *, calibration_path=None, read_limit_path=None, model_id=None, provider_id=None):
        try:
            self.artifact = token_estimate.load_artifact(calibration_path)
        except token_estimate.TokenEstimateArtifactError as exc:
            raise PlanWeightError(str(exc)) from exc
        self.limits = load_read_limit(read_limit_path)
        self.model_id = session_model_id(model_id)
        self.provider_id = session_provider_id(provider_id)
        self._cache = {}
        self.warned_model = False
        target = self.artifact["calibration_target"]
        if ((self.model_id and self.model_id != target["requested_model_id"])
                or (self.provider_id and self.provider_id != target["provider"])):
            # WARNING, is not a blocker (mitigation pre-mortem #1): assessment remains valid,
            # but its anchor is removed under another model - the consumer must see this.
            print(f"WARNING: plan_weight: calibration removed under "
                  f"«{target['provider']}/{target['requested_model_id']}», environment - "
                  f"«{self.provider_id}/{self.model_id}»: estimate may not be accurate", file=sys.stderr)
            self.warned_model = True

    def file(self, path, role):
        key = str(Path(path).resolve())
        cached = self._cache.get(key)
        if cached is None:
            cached = measure_file(path, role=role, artifact=self.artifact,
                                  limits=self.limits,
                                  # WARNING prints Measurer once, not every file.
                                  model_id=None)
            self._cache[key] = cached
        record = dict(cached)
        record["role"] = role
        return record

    def selected(self, raw, *, path, role):
        return measure_bytes(raw, path=path, role=role, artifact=self.artifact,
                             limits=self.limits, model_id=None)


def measure_item(plan_dir, item_id, fields, measurer, *, phase_file=None, repo_root=None,
                 rel_to=None):
    """Weight of the required path of ONE point, dispatched by declared plan layout.

    Returns the entry with `files` (permitted, with weights) and `gaps` (closed taxonomy).
    Amount `weight_tokens` is calculated by the allowed subset - a list of spaces
    is ALWAYS printed next to it (otherwise this is the lower estimate given for the measured)."""
    plan_dir = Path(plan_dir)
    repo_root = Path(repo_root) if repo_root is not None else repo_root_for(plan_dir)
    files, gaps, seen = [], [], set()

    root_readable = repo_root.is_dir() and os.access(repo_root, os.R_OK)
    if not root_readable:
        gaps.append({"kind": GAP_UNREADABLE_ROOT, "path": str(repo_root),
                     "detail": "plan repository root is not readable - "
                               "positions Required Reads do not resolve from the root"})

    def add(path, role, entry=None, *, raw=None, selector=None, display_suffix=""):
        resolved_path = Path(path).resolve()
        selector_key = json.dumps(selector or {"kind": "whole_file"}, sort_keys=True)
        key = (str(resolved_path), selector_key)
        if key in seen:
            return False
        seen.add(key)
        try:
            record = (measurer.file(path, role) if raw is None else
                      measurer.selected(raw, path=path, role=role))
        except OSError as exc:
            gaps.append({"kind": GAP_MISSING_FILE, "path": _rel(path, rel_to), "role": role,
                         "entry": entry, "detail": f"file cannot be read: {exc}"})
            return False
        record["path"] = f"{_rel(record['path'], rel_to)}{display_suffix}"
        files.append(record)
        gate = violated_gate(record)
        if gate is not None:
            gaps.append({"kind": GAP_OVERSIZED_FILE, "path": record["path"], "role": role,
                         "entry": entry, "gate": gate,
                         "bytes": record["bytes"], "est_tokens": record["est_tokens"],
                         "detail": f"file does not pass the gate «{gate}» single reading limit "
                                   f"(D2b: mandatory unit must be read in ONE call)"})
        return True

    def add_carrier(path, role):
        path = Path(path)
        if path.is_file():
            add(path, role)
        else:
            gaps.append({"kind": GAP_MISSING_FILE, "path": _rel(path, rel_to), "role": role,
                         "entry": None,
                         "detail": "required plan layout file is missing"})

    roots = [plan_dir] + ([repo_root] if root_readable else [])

    def add_required_reads():
        """Resolve spec reads when no trusted bundle can carry them yet.

        Layout v2 normally consumes only digest-qualified bundle entries.  Admission,
        however, must still see a declared missing producer input before that bundle
        can exist; otherwise the consumer is circularly classified as ``ready`` and
        bundle materialization fails.  The fallback is deliberately limited to the
        Required Reads resolver and is used only while the bundle is
        absent or untrusted.
        """
        for entry in split_entries(_field(fields, "Required Reads")):
            hits = 0
            declared_misses = 0
            for token, declared in path_candidates(entry):
                resolved = resolve_candidate(token, roots)
                if resolved is not None:
                    hits += 1
                    add(resolved, "required_read", entry=_preview(entry))
                    continue
                if declared:
                    declared_misses += 1
                    gaps.append({"kind": GAP_MISSING_FILE, "path": token,
                                 "role": "required_read", "entry": _preview(entry),
                                 "detail": "the path is named, but the file is not under the plan directory, "
                                           "not under the repository root"})
            if hits == 0 and declared_misses == 0:
                gaps.append({"kind": GAP_UNRESOLVED_ENTRY, "entry": _preview(entry),
                             "detail": "position is not cast to an existing path - "
                                       "in prose the named input is not available to the resolver"})

    try:
        plan_layout.layout_version(plan_dir)
        plan_core = plan_layout.plan_core_path(plan_dir)
        item_spec = plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)
        bundle_path = plan_layout.carrier_path(plan_dir, "bundle", item_id=item_id)
        state_path = plan_layout.carrier_path(plan_dir, "item-state", item_id=item_id)
    except plan_layout.PlanLayoutError as exc:
        raise PlanWeightError(str(exc)) from exc

    add_carrier(plan_core, "plan-core")
    add_carrier(Path(phase_file) if phase_file is not None else
                plan_layout.phase_path(plan_dir, item_id.split(".")[0]), "phase-context")
    add_carrier(item_spec, "item-spec")

    bundle_fresh = bundle_path.is_file()
    if bundle_fresh:
        add_carrier(bundle_path, "item-input-bundle")
    if bundle_fresh:
        try:
            plan_bundle.build(plan_dir, item_id, check=True)
        except plan_bundle.BundleError as exc:
            bundle_fresh = False
            gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                         "path": _rel(bundle_path, rel_to),
                         "role": "item-input-bundle", "entry": None,
                         "detail": f"generated bundle not byte-fresh: {exc}"})
        if bundle_fresh:
            try:
                bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                bundle = None
                gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                             "path": _rel(bundle_path, rel_to),
                             "role": "item-input-bundle", "entry": None,
                             "detail": f"generated bundle is not readable: {exc}"})
            for unit in bundle.get("entries", ()) if bundle else ():
                source = resolve_candidate(unit["path"], roots)
                if source is None:
                    gaps.append({"kind": GAP_MISSING_FILE, "path": unit["path"],
                                 "role": V2_INPUT_ROLE, "entry": unit.get("declaration_ref"),
                                 "detail": "digest-qualified bundle input missing"})
                    continue
                try:
                    source_raw = source.read_bytes()
                    selected = plan_bundle._selected_bytes(source_raw, unit["selector"], source)
                except (OSError, plan_bundle.BundleError) as exc:
                    gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                                 "path": _rel(source, rel_to), "role": V2_INPUT_ROLE,
                                 "entry": unit.get("declaration_ref"),
                                 "detail": f"bundle selection is not readable: {exc}"})
                    continue
                if (hashlib.sha256(source_raw).hexdigest() != unit["sha256"]
                        or hashlib.sha256(selected).hexdigest() != unit["selected_sha256"]):
                    gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                                 "path": _rel(source, rel_to), "role": V2_INPUT_ROLE,
                                 "entry": unit.get("declaration_ref"),
                                 "detail": "bundle source/selection digest mismatch"})
                    continue
                selector = unit["selector"]
                suffix = ("" if selector["kind"] == "whole_file" else
                          f"#section:{selector['anchor']}")
                add(source, V2_INPUT_ROLE, entry=unit.get("declaration_ref"), raw=selected,
                    selector=selector, display_suffix=suffix)
    else:
        # A future producer output cannot be bundled before it exists. Expose
        # the spec edge to stage-aware admission so the consumer becomes
        # pending-producer instead of a false ready/bundle failure.
        add_required_reads()

    state_fresh = state_path.is_file()
    if state_fresh:
        try:
            plan_item_state.build_states(plan_dir, item_id=item_id, check=True)
        except plan_item_state.ItemStateError as exc:
            gaps.append({"kind": GAP_UNRESOLVED_ENTRY,
                         "path": _rel(state_path, rel_to), "role": "item-state",
                         "entry": None,
                         "detail": f"generated item state not byte-fresh: {exc}"})
    add_carrier(state_path, "item-state")

    weight = sum(f["est_tokens"] for f in files)
    input_roles = {"required_read", V2_INPUT_ROLE}
    floor = sum(f["est_tokens"] for f in files if f["role"] not in input_roles)
    return {
        "item_id": item_id,
        "status": _field(fields, "Status"),
        "files": files,
        "gaps": gaps,
        "weight_tokens": weight,
        "weight_bytes": sum(f["bytes"] for f in files),
        "floor_tokens": floor,
        "required_reads_tokens": weight - floor,
        "resolved_files": len(files),
        "gap_counts": {kind: sum(1 for g in gaps if g["kind"] == kind) for kind in GAP_KINDS},
    }


def _field(fields, name):
    """Meaning item-fields. `plan_lint._parse_fields` gives `(value, string)`; tests and
    direct calls are free to pass a bare string - both forms are read the same."""
    value = fields.get(name, "")
    if isinstance(value, tuple):
        value = value[0]
    return value or ""


def _preview(text, limit=96):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _rel(path, rel_to):
    if rel_to is None:
        return str(path)
    try:
        return str(Path(path).resolve().relative_to(Path(rel_to).resolve()))
    except ValueError:
        return str(path)


def measure_plan(plan_dir, measurer, *, only_item=None):
    """Measurement of all points of the plan (or one, `only_item`). Parsing phase files -
    `task.plan_lint.parse_phase_md`: is the same parser that the linter uses to read the plan."""
    plan_dir = Path(plan_dir)
    if not (plan_dir / "plan.md").is_file():
        raise PlanWeightError(f"not a plan directory (no plan.md): {plan_dir}")
    repo_root = repo_root_for(plan_dir)
    diag = plan_lint.Diagnostics()  # linter diagnostics are not our job here - extinguished
    meta, _ = plan_lint.parse_plan_md(plan_dir / "plan.md", diag)
    plan_id = (meta or {}).get("Plan ID", (plan_dir.name, None))[0] or plan_dir.name

    items = []
    specs = {}
    item_index = []
    try:
        phase_files = plan_layout.phase_paths(plan_dir)
    except plan_layout.PlanLayoutError as exc:
        raise PlanWeightError(str(exc)) from exc
    layout = plan_layout.layout_version(plan_dir)
    for phase_id, phase_path in phase_files.items():
        parsed = plan_lint.parse_phase_md(phase_path, phase_id, diag, layout=layout)
        if parsed is None:
            continue
        for item_id, occurrences in parsed["items"].items():
            occurrence = occurrences[0]
            fields = {k: v for k, v in occurrence["fields"].items()}
            item_index.append({"item_id": item_id, "status": _field(fields, "Status")})
            specs[item_id] = {
                "required_read_entries": split_entries(_field(fields, "Required Reads")),
                "deliverables": _field(fields, "Deliverables"),
            }
            if only_item is not None and item_id != only_item:
                continue
            record = measure_item(plan_dir, item_id, fields, measurer,
                                  phase_file=phase_path, repo_root=repo_root, rel_to=repo_root)
            record["phase_id"] = phase_id
            record["title"] = occurrence["title"]
            items.append(record)

    if only_item is not None and not any(item["item_id"] == only_item for item in items):
        raise PlanWeightError(f"item {only_item} not found in {plan_dir}")

    admission = None
    if layout == "v2":
        try:
            admission = plan_admission.classify(plan_dir, items, specs, item_index=item_index)
        except plan_admission.AdmissionError as exc:
            raise PlanWeightError(str(exc)) from exc
    selected_items = ([item for item in items if item["item_id"] == only_item]
                      if only_item is not None else items)
    if admission is not None and only_item is not None:
        admission = dict(admission)
        admission["counts"] = {
            state: sum(item["admission_state"] == state for item in selected_items)
            for state in plan_admission.STATES
        }
        admission["gap_counts"] = {}
        for item in selected_items:
            for gap in item["admission_gaps"]:
                code = gap["code"]
                admission["gap_counts"][code] = admission["gap_counts"].get(code, 0) + 1
        admission["ready_failed"] = sum(
            item["admission_state"] == plan_admission.STATE_READY
            and item["admission_pass"] is False for item in selected_items)
    gaps_total = sum(len(i["gaps"]) for i in selected_items)
    return {
        "plan_id": plan_id,
        "plan_dir": _rel(plan_dir, repo_root),
        "repo_root": str(repo_root),
        "items": selected_items,
        "totals": {
            "items": len(selected_items),
            "gaps": gaps_total,
            "gap_counts": {kind: sum(i["gap_counts"][kind] for i in selected_items)
                           for kind in GAP_KINDS},
            "max_item_weight_tokens": max((i["weight_tokens"] for i in selected_items), default=0),
            "min_item_weight_tokens": min((i["weight_tokens"] for i in selected_items), default=0),
            "max_floor_tokens": max((i["floor_tokens"] for i in selected_items), default=0),
            "admission": admission,
        },
    }


def sweep(roots, measurer):
    """Measurement using several roots (`plans/` or specific `plans/<ID>`) — input P0.4.
    Root - top-level accounting unit (`roots[]`, D110): each entry root
    gets closed status `resolved`/`unreadable`/`missing`, inaccessible root NOT
    drops the run and does not carry the rest (`OSError` around the resolver is intercepted).
    A plan that could not be parsed falls into `errors` (carrier of the outcome of the PLAN,
    not root) and does NOT drop the run: the summary must also name what is not measured."""
    plans, errors, roots_out = [], [], []
    for root in roots:
        try:
            discovered = plan_lint.discover_plan_dirs(Path(root))
        except OSError as exc:
            roots_out.append({"root": str(root), "status": "unreadable", "discovered": 0,
                               "measured": 0, "failed": 0, "detail": str(exc)})
            continue
        if discovered is None:
            roots_out.append({"root": str(root), "status": "missing", "discovered": 0,
                               "measured": 0, "failed": 0,
                               "detail": "root does not exist or is not a directory"})
            continue
        measured = failed = 0
        for plan_dir in discovered:
            try:
                plans.append(measure_plan(plan_dir, measurer))
                measured += 1
            except (PlanWeightError, OSError) as exc:
                errors.append({"root": str(root), "plan_dir": str(plan_dir), "error": str(exc)})
                failed += 1
        roots_out.append({"root": str(root), "status": "resolved", "discovered": len(discovered),
                           "measured": measured, "failed": failed, "detail": None})
    return {
        "roots": roots_out,
        "plans": plans,
        "errors": errors,
        "totals": {
            "plans": len(plans),
            "items": sum(p["totals"]["items"] for p in plans),
            "gaps": sum(p["totals"]["gaps"] for p in plans),
            "gap_counts": {kind: sum(p["totals"]["gap_counts"][kind] for p in plans)
                           for kind in GAP_KINDS},
            "roots": {
                "total": len(roots_out),
                "resolved": sum(1 for r in roots_out if r["status"] == "resolved"),
                "unreadable": sum(1 for r in roots_out if r["status"] == "unreadable"),
                "missing": sum(1 for r in roots_out if r["status"] == "missing"),
            },
        },
    }


def envelope(measurer, payload):
    """Stable machine output wrapper (`--json`) — keys are content independent."""
    art = measurer.artifact
    out = {
        "schema": SCHEMA,
        "calibration": {
            "version": art["version"],
            "target": art["calibration_target"],
            "safety_multiplier": art["safety_multiplier"],
        },
        "limits": {GATE_SIZE_BYTES: measurer.limits["size_bytes"],
                   GATE_TOKENS: measurer.limits["tokens"],
                   "path": measurer.limits["path"]},
        "session_model_id": measurer.model_id,
        "session_provider_id": measurer.provider_id,
        "dense_ascii_min_run": DENSE_ASCII_MIN_RUN,
    }
    out.update(payload)
    return out


# --- mode --exact (differential harness P0.1, D92) ----------------------------

EXACT_WARNING = (
    "WARNING: --exact — MANUAL mode of edge case analysis, outside CI: truth is taken "
    "from the artifact of the differential harvesting run P0.1 (triple pass protocol), "
    "network tool does not open and `count_tokens` does not call")


def load_probe_log(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanWeightError(f"Harness run artifact is not readable: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlanWeightError(f"Harness run artifact - invalid JSON: {path}: {exc}") from exc
    probes = data.get("accepted_samples", data.get("probes"))
    if not isinstance(probes, list):
        raise PlanWeightError(f"harness run artifact: no list «probes»: {path}")
    return data


def exact_compare(paths, measurer, probe_log_path):
    """Verification of the TOP estimate with the truth of the Harness run on explicitly specified files.
    The file without an entry in the run artifact is called directly («there is no truth»), and not silently
    is skipped: the gap in the proof is also the result of a measurement."""
    import hashlib

    log = load_probe_log(probe_log_path)
    by_sha, by_path = {}, {}
    for rec in log.get("accepted_samples", log["probes"]):
        if rec.get("rejected") or rec.get("true_tokens") is None:
            continue
        sha = rec.get("sample_sha256", rec.get("sha256"))
        if sha:
            by_sha[sha] = rec
        source_path = rec.get("source_path", rec.get("path"))
        if source_path:
            # Records store repo-relative paths (portable across machines); a legacy absolute
            # path is still honoured.  The repository root is the parent of packages/task/configs.
            resolved_log = Path(probe_log_path).resolve()
            anchor = resolved_log.parents[3] if len(resolved_log.parents) > 3 else resolved_log.parent
            by_path[str((anchor / source_path).resolve())] = rec

    rows = []
    for path in paths:
        p = Path(path)
        if not p.is_file():
            rows.append({"path": str(p), "error": "no file"})
            continue
        text = p.read_bytes().decode("utf-8", errors="replace")
        est = token_estimate.estimate_text(text, artifact=measurer.artifact)
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        rec = by_sha.get(sha) or by_path.get(str(p.resolve()))
        row = {"path": str(p), "est_tokens": est, "sha256": sha,
               "dense_ascii_share": dense_ascii_share(text)}
        if rec is None:
            row["truth"] = None
            row["match"] = None
            row["note"] = ("there is no truth in the Harness run artifact - the file was not included in "
                           "body P0.1 or has changed since the run")
        else:
            truth = float(rec["true_tokens"])
            row["truth"] = truth
            row["match"] = "sha256" if sha in by_sha else "path"
            row["true_over_estimate"] = (truth / est) if est else None
            row["understated"] = bool(est < truth)
        rows.append(row)
    return {"probe_log": str(probe_log_path), "files": rows,
            "understated": sum(1 for r in rows if r.get("understated"))}


# --- human-readable output --------------------------------------------------------

def _fmt_item(record, limits):
    lines = [f"  {record['item_id']} — {record.get('title', '')}".rstrip(),
             f"    weight: {record['weight_tokens']} tokens with an upper estimate "
             f"({record['weight_bytes']} bytes, files {record['resolved_files']}); "
             f"layout floor: {record['floor_tokens']}, Required Reads: "
             f"{record['required_reads_tokens']}"]
    over = [g for g in record["gaps"] if g["kind"] == GAP_OVERSIZED_FILE]
    if over:
        lines.append(f"    over one read limit "
                     f"({limits['size_bytes']} bytes / {limits['tokens']} tokens): {len(over)}")
    # The list of spaces is ALWAYS printed - the sum without it would be a lower estimate,
    # issued as measured (research/02 §5).
    if record["gaps"]:
        lines.append(f"    spaces ({len(record['gaps'])}):")
        for gap in record["gaps"]:
            gate = f" gate={gap['gate']}" if gap.get("gate") else ""
            target = gap.get("path") or gap.get("entry") or ""
            lines.append(f"      [{gap['kind']}{gate}] {target}")
    else:
        lines.append("    spaces: none")
    if "admission_state" in record:
        verdict = ("pass" if record["admission_pass"] is True else
                   "fail" if record["admission_pass"] is False else "deferred")
        producer = (f"; producer={record['producer_item']}"
                    if record.get("producer_item") else "")
        lines.append(f"    admission: {record['admission_state']} — {verdict}{producer}")
        for gap in record.get("admission_gaps", []):
            target = gap.get("path") or gap.get("entry") or gap.get("detail") or ""
            lines.append(f"      [{gap['code']}] {target}")
    return lines


def _print_plan(plan, limits):
    print(f"plan {plan['plan_id']} ({plan['plan_dir']}) — items {plan['totals']['items']}, "
          f"spaces {plan['totals']['gaps']}")
    for record in plan["items"]:
        for line in _fmt_item(record, limits):
            print(line)
    counts = plan["totals"]["gap_counts"]
    print(f"  total: max. item weight {plan['totals']['max_item_weight_tokens']} tokens, "
          f"min. {plan['totals']['min_item_weight_tokens']}, max. floor "
          f"{plan['totals']['max_floor_tokens']}; spaces by category: "
          + ", ".join(f"{k}={counts[k]}" for k in GAP_KINDS))


# --- CLI ---------------------------------------------------------------------------

def _add_common_options(parser, suppress):
    """General options - both before and after the subcommand (`plan <dir> --json` — form Validation
    P0.3). Subcommands have defaults suppressed: otherwise argparse would overwrite the value with them,
    specified BEFORE the subcommand."""
    import argparse

    flag_default = argparse.SUPPRESS if suppress else False
    opt_default = argparse.SUPPRESS if suppress else None
    parser.add_argument("--json", action="store_true", default=flag_default,
                        help="machine output (stable keys)")
    parser.add_argument("--calibration", default=opt_default,
                        help="path to calibration artifact P0.1 (default - configs/)")
    parser.add_argument("--read-limit", default=opt_default,
                        help="path to the read limit artifact P0.2 (default - configs/)")
    parser.add_argument("--session-model", default=opt_default,
                        help="model of the current environment for WARNING about discrepancies with calibration")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="plan-weight",
        description="Weight of required reading of the plan item (plan-run.md) in estimated "
                    "tokens, with each file checked against both read limit gates "
                    "and a closed whitespace taxonomy.")
    _add_common_options(parser, suppress=False)
    parser.add_argument("--exact", nargs="+", metavar="FILE", default=None,
                        help="MANUAL mode (out CI): check the estimate against the truth of the run "
                             "differential harness P0.1 on the specified files")
    parser.add_argument("--probe-log", default=None,
                        help="Harness run artifact P0.1 for --exact")
    parser.add_argument("--file", default=None,
                        help="measure one document (tokens and strings)")

    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, suppress=True)

    sub = parser.add_subparsers(dest="cmd")
    p_item = sub.add_parser("item", help="weight of one point", parents=[common])
    p_item.add_argument("plan_dir")
    p_item.add_argument("item_id")
    p_plan = sub.add_parser("plan", help="weight of each plan item", parents=[common])
    p_plan.add_argument("plan_dir")
    p_sweep = sub.add_parser("sweep", help="measured at the roots of plans (input P0.4)", parents=[common])
    p_sweep.add_argument("roots", nargs="+")
    p_canon = sub.add_parser("canon", help="D93: two-threshold canon weight gate",
                             parents=[common])
    p_canon.add_argument("--budget", default=str(DEFAULT_CANON_BUDGET_PATH))

    args = parser.parse_args(argv)
    if args.exact is None and args.file is None and args.cmd is None:
        parser.error("subcommand needed item|plan|sweep|canon or mode --file/--exact")

    try:
        measurer = Measurer(calibration_path=args.calibration,
                            read_limit_path=args.read_limit,
                            model_id=args.session_model)
        if args.exact is not None:
            print(EXACT_WARNING, file=sys.stderr)
            probe_log = args.probe_log or DEFAULT_PROBE_LOG_PATH
            payload = exact_compare(args.exact, measurer, probe_log)
            if args.json:
                print(json.dumps(envelope(measurer, {"exact": payload}),
                                 ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"true: {payload['probe_log']}")
                for row in payload["files"]:
                    if row.get("error"):
                        print(f"  {row['path']}: {row['error']}")
                    elif row["truth"] is None:
                        print(f"  {row['path']}: rating {row['est_tokens']} — {row['note']}")
                    else:
                        print(f"  {row['path']}: rating {row['est_tokens']}, true "
                              f"{row['truth']:.0f}, true/rating "
                              f"{row['true_over_estimate']:.3f}"
                              + ("  ← UNDERSTANDING" if row["understated"] else ""))
            return 0

        if args.file is not None:
            payload = measure_document(args.file, measurer)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"{payload['path']}: {payload['est_tokens']} tokens, "
                      f"{payload['lines']} lines")
            return 0

        if args.cmd == "canon":
            payload = evaluate_canon_budget(args.budget, measurer)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                before = payload["baseline"]
                current = payload["current"]
                print(f"canon before: {before['est_tokens']} tokens, {before['lines']} lines "
                      f"@ {before['git_anchor']}")
                print(f"canon after: {current['est_tokens']} tokens, {current['lines']} lines "
                      f"@ working-tree")
                print(f"hard cap: {payload['hard_cap_tokens']} tokens; warning: "
                      f"{payload['warning_threshold_tokens']} tokens; regression limit: "
                      f"{payload['regression_limit_tokens']} tokens")
                print(f"vendor guidance: under {payload['vendor_line_guidance']} lines "
                      f"(independent guidance; current {current['lines']})")
                if payload["active_exceptions"]:
                    expiries = ", ".join(e["expires_at"] for e in payload["active_exceptions"])
                    print(f"active dated exception(s), expiry: {expiries}")
                if payload["warning"]:
                    print("WARNING: canon reached the warning threshold", file=sys.stderr)
                if payload["failures"]:
                    print("ERROR: canon budget failed: "
                          + ", ".join(payload["failures"]), file=sys.stderr)
            return 0 if payload["passes"] else 3

        if args.cmd == "sweep":
            payload = sweep(args.roots, measurer)
            if args.json:
                print(json.dumps(envelope(measurer, payload), ensure_ascii=False,
                                 indent=2, sort_keys=True))
            else:
                for root in payload["roots"]:
                    if root["status"] in ("unreadable", "missing"):
                        print(f"NOT MEASURED: {root['root']}: {root['detail']}")
                    elif root["status"] == "resolved" and root["discovered"] == 0:
                        print(f"NO PLANS: {root['root']}")
                for plan in payload["plans"]:
                    _print_plan(plan, measurer.limits)
                for err in payload["errors"]:
                    print(f"NOT MEASURED: {err['plan_dir']}: {err['error']}")
                counts = payload["totals"]["gap_counts"]
                root_counts = payload["totals"]["roots"]
                print(f"total: plans {payload['totals']['plans']}, items "
                      f"{payload['totals']['items']}, spaces {payload['totals']['gaps']} ("
                      + ", ".join(f"{k}={counts[k]}" for k in GAP_KINDS) + "), roots "
                      f"{root_counts['total']} (resolved={root_counts['resolved']}, "
                      f"unreadable={root_counts['unreadable']}, missing={root_counts['missing']})")
            return 0

        only = args.item_id if args.cmd == "item" else None
        plan = measure_plan(args.plan_dir, measurer, only_item=only)
        if args.json:
            print(json.dumps(envelope(measurer, plan), ensure_ascii=False,
                             indent=2, sort_keys=True))
        else:
            _print_plan(plan, measurer.limits)
        return 0
    except PlanWeightError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
