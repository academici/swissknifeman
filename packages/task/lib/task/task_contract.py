"""task_contract — Task Contract v1 compiler (2026.07.24-AGENT-RELIABILITY P2.2).

The single checked seam `packages/task/commands/plan-*.md` call at the pre-mutation and
pre-final boundaries instead of restating the rule in prose. It owns exactly what the
frozen contracts assign it and nothing else:

  * content-hash recomputation and the precedence/conflict resolution ladder
    (`root/contracts/task-contract-v1.md` §Version / §Precedence, 2026.07.24-AGENT-RELIABILITY P0.2, frozen);
  * the twelve ordered pre-mutation reason codes and the three ordered pre-final reason
    codes of the same contract (frozen; reused verbatim, never re-minted);
  * the slice-partition and cold-start checks of the same contract (frozen);
  * the portability tier classification and lint predicate of
    `plans/2026.07.24-AGENT-RELIABILITY/root/contracts/plan-portability-v1.md` (2026.07.24-AGENT-RELIABILITY P2.1),
    including the one new reason code that layer adds
    (`PORTABILITY_TIER_MISCLASSIFIED`, `artifacts/P2.1/state-transition-cases.json`
    `new_reason_codes`).

Authoring pattern reused from
`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.2/validate_task_contract.py` (a frozen
plan artifact, never imported or modified — the item's Required Reads name it as the
pattern to follow, not a library to import); this module is the first executable version
that lives in the package and is called by name from the canonical plan commands.

stdlib-only.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

SCHEMA_VERSION = "task-contract/v1"

# Ordered ladders — index = rank, a lower index outranks a higher one
# (task-contract-v1.md §Precedence ladder / §Route, frozen 2026.07.24-AGENT-RELIABILITY P0.2 enums).
CARRIER_PRECEDENCE = (
    "owner-instruction",
    "plan-decision",
    "item-spec",
    "package-canon",
    "handoff-carrier",
    "incidental-diagnostic",
)
MODEL_CLASS_ORDER = ("economy", "implementation", "frontier")
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max")

# task-contract-v1.md §Public acceptance — proof classes that may satisfy a deterministic
# acceptance predicate (D30): `pinned-not-recomputable`/`unknown` never do.
DETERMINISTIC_PROOF_CLASSES = ("recomputed", "cross-checked")

# task-contract-v1.md §Root/subagent slice — the eleven payload keys, partitioned exactly.
SLICE_PARTITION_KEYS = frozenset({
    "goal", "must", "never", "done", "authority", "next", "route", "version",
    "evidence", "portability", "conflicts",
})
SLICE_SUBAGENT_REQUIRED = frozenset(
    {"goal", "must", "never", "done", "authority", "next", "route", "version"})
SLICE_ROOT_ONLY_REQUIRED = frozenset({"evidence", "portability", "conflicts"})

# task-contract-v1.md §Portability — an execution input that is absolute, `~`-rooted,
# parent-escaping, `tmp/`-rooted or URL-shaped is external BY CONSTRUCTION once its ROLE
# (execution input vs provenance) is already decided — this is the frozen 2026.07.24-AGENT-RELIABILITY P0.2 string test
# over an ALREADY-CLASSIFIED input, not the D47 role test itself. The role test (which path
# even belongs in `execution_inputs` in the first place) lives upstream of this compiler, in
# whatever builds the `portability` block (root supervisor / `plan_lint`'s tiered-portability
# check) — it is a POSITIONAL test (does the item read this path in Inputs/Required
# Reads/Validation), never a substring match on `tmp/` (D47, plan-portability-v1.md
# §Provenance vs execution input).
_EXTERNAL_PREFIXES = ("/", "~", "../", "tmp/")
_EXTERNAL_SUBSTRINGS = ("/../", "/tmp/", "://")

# --------------------------------------------------------------------------
# build() — Task Contract v1 producer (2026.07.24-AGENT-RELIABILITY P2.6, F1). Field-mapping table lives in
# `plans/2026.07.24-AGENT-RELIABILITY/findings/P2.6-contract-mapping.md`.
# --------------------------------------------------------------------------

# New 2026.07.24-AGENT-RELIABILITY P2.6 reason codes — not pre-declared by 2026.07.24-AGENT-RELIABILITY P2.1's frozen
# `artifacts/P2.1/state-transition-cases.json::new_reason_codes` (this item introduces
# them directly, same authoring discipline: a distinct_from a frozen 2026.07.24-AGENT-RELIABILITY P0.2 code, never a
# redefinition — D64).
BUNDLE_ARTIFACT_MISSING = "BUNDLE_ARTIFACT_MISSING"
BUNDLE_PRIVACY_MISMATCH = "BUNDLE_PRIVACY_MISMATCH"

_SCOPE_CLAUSE_SPLIT_RE = re.compile(r";\s*")
_INPUTS_SPLIT_RE = re.compile(r"\s*·\s*")
_REQUIRED_READS_SPLIT_RE = re.compile(r"(?:^|\s)\d+\)\s+")
_IMPL_RULE_SPLIT_RE = re.compile(r"\*\*\(\d+\)\*\*\s*")
_ANTI_CLAUSE_SPLIT_RE = re.compile(r"\*{0,2}(?:Анти|Anti)[\w-]*\s*:\*{0,2}\s*")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_ROUTING_HEADER_RE = re.compile(r"^##\s+3\.\s+Routing\s*$")
_ROUTING_RANGE_RE = re.compile(r"^(P\d+)\.(\d+)\s*[–-]\s*(P\d+)\.(\d+)$")
_AUDIT_BLOCK_HEADER_RE = re.compile(r"^##\s+Audit\s+(P\d+)\b")
_OWNER_GRANT_RE = re.compile(r"\[OWNER-GRANT:([A-Z0-9][A-Z0-9.-]+)\]")
_OWNER_REVOKE_RE = re.compile(r"\[OWNER-REVOKE:([A-Z0-9][A-Z0-9.-]+)\]")
# Protected authority is deliberately a small, exact Decision Log record rather than
# prose searched by substring.  Backticks make the three values unambiguous even when
# a branch or scope contains ordinary punctuation.  The Decision Log must reference a
# separately recorded repository-owner message in the plan's Layer-0 brief; a copyable
# Meta ``Approval Owner`` label is identity metadata, not an authority carrier.
_OWNER_GRANT_RECORD_RE = re.compile(
    r"^\[OWNER-GRANT:(?P<gate_id>[A-Z0-9][A-Z0-9.-]+)\]\s+"
    r"branch=`(?P<branch>[^`\n]+)`;\s*"
    r"scope=`(?P<scope>[^`\n]+)`;\s*"
    r"owner-message=`(?P<owner_message>brief/[A-Za-z0-9][A-Za-z0-9._-]*\.md"
    r"#[A-Za-z0-9][A-Za-z0-9._-]*)`$")
_OWNER_MESSAGE_REF_RE = re.compile(
    r"^brief/(?P<filename>[A-Za-z0-9][A-Za-z0-9._-]*\.md)"
    r"#(?P<message_id>[A-Za-z0-9][A-Za-z0-9._-]*)$")
_OWNER_MESSAGE_RECORD_RE = re.compile(
    r"^\[REPOSITORY-OWNER-MESSAGE:(?P<message_id>[A-Za-z0-9][A-Za-z0-9._-]*)\]\s+"
    r"\[OWNER-GRANT:(?P<gate_id>[A-Z0-9][A-Z0-9.-]+)\]\s+"
    r"branch=`(?P<branch>[^`\n]+)`;\s*"
    r"scope=`(?P<scope>[^`\n]+)`;\s*"
    r"provenance=`repository-owner`$")

SLICE_SUBAGENT_KEYS = ("goal", "must", "never", "done", "authority", "next", "route", "version")
SLICE_ROOT_ONLY_KEYS = ("evidence", "portability", "conflicts")


class TaskContractBuildError(ValueError):
    """A typed refusal to compile a Task Contract — never a fabricated
    placeholder value (Implementation Rules 2026.07.24-AGENT-RELIABILITY P2.6 (2), anti-padding). Carries
    the offending item and field name so the caller can act on it directly,
    the same shape `RouteEvidenceError`/`ReviewPolicyError` already use."""

    def __init__(self, item_id: str, field: str, message: str):
        super().__init__(f"{item_id}: {field}: {message}")
        self.item_id = item_id
        self.field = field


def _split_nonempty(text: str, pattern: "re.Pattern") -> list:
    return [p.strip() for p in pattern.split(text or "") if p and p.strip()]


def _first_backtick_or_text(clause: str) -> str:
    m = _BACKTICK_RE.search(clause)
    return m.group(1) if m else clause.strip()


def _marker_clauses(text: str, marker_re: "re.Pattern") -> list:
    """Splits `text` at each match of `marker_re` (a labelled/numbered marker —
    `**(N)**`, `N) `, `**Анти-…:**`), discarding any text before the FIRST
    marker (ordinary prose, not a clause of the marked kind). No marker
    present → `[]`, never "the whole text as one accidental clause" (unlike
    `_split_nonempty`'s `; `/`·` semicolon-style split, where a single
    unmarked sentence legitimately IS one clause)."""
    markers = list(marker_re.finditer(text or ""))
    clauses = []
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        clause = text[m.end():end].strip()
        if clause:
            clauses.append(clause)
    return clauses


def _anti_clauses(code_guidance_text: str) -> list:
    """Code Guidance anti-clauses (`**Анти-подгонка:** …` / `Anti-…:` — bold or
    plain, both observed in the fleet) feeding `never[]`. An item that spells
    no anti-clause at all yields `[]` — `never[]` still satisfies its
    minItems via `Scope Excluded` alone."""
    return _marker_clauses(code_guidance_text, _ANTI_CLAUSE_SPLIT_RE)


def _require_field(item_id: str, fields: dict, name: str):
    value, lineno = fields.get(name, ("", None))
    value = (value or "").strip()
    if not value or value == "—":
        raise TaskContractBuildError(item_id, name,
                                     "field is empty (\"—\") — build refuses to fabricate a value")
    return value, lineno


def _count_audit_rounds(plan_dir: Path, phase_lines, phase_id: str) -> int:
    """Count fingerprinted phase-candidate audits in the append-only journal.

    Historical design/closed-phase audit blocks predate the candidate fingerprint
    protocol and must not consume a current item's repair budget.  The journal
    fingerprint is the distinguishing carrier: D14 candidate audits require it,
    while legacy blocks/events do not.  The phase Markdown still participates as
    an integrity bound — a journal event without a matching audit block is ignored
    here and remains an audit/lint defect rather than silently spending budget.
    """
    block_count = sum(
        1 for ln in phase_lines
        if (match := _AUDIT_BLOCK_HEADER_RE.match(ln.strip())) and match.group(1) == phase_id)
    if block_count == 0:
        return 0

    journal_path = Path(plan_dir) / "journal.jsonl"
    if not journal_path.is_file():
        return 0
    fingerprinted = 0
    for raw in journal_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if (event.get("command") == "plan-audit"
                and event.get("item_id") == phase_id
                and event.get("result") in {"audit-green", "audit-attention", "audit-red"}
                and isinstance(event.get("fingerprint"), str)
                and event["fingerprint"]):
            fingerprinted += 1
    return min(block_count, fingerprinted)


def _has_audit_cap_remediation_grant(plan_dir: Path, item_id: str) -> bool:
    """Accept only a recorded direct-close remediation, never chat prose."""
    for path in sorted((Path(plan_dir) / "decisions").glob("D*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        parts = text.split("---", 2)
        if len(parts) != 3:
            continue
        fields = dict(line.split(":", 1) for line in parts[1].splitlines() if ":" in line)
        body = parts[2]
        if (fields.get("status", "").strip() == "accepted"
                and fields.get("item", "").strip() == item_id
                and "AUDIT-CAP" in body
                and "P5.6 обязан закрыть" in body
                and "третьего Audit P5" in body):
            return True
        normalized_body = " ".join(body.split())
        recovery_clause = re.search(
            r"повторить исходные Validation для (?P<items>.+?) только в fresh native roots",
            normalized_body,
        )
        if (fields.get("status", "").strip() == "accepted"
                and "AUDIT-CAP" in normalized_body
                and "provider-attested" in normalized_body
                and "новых terminal attempts" in normalized_body
                and recovery_clause is not None
                and item_id in set(re.findall(r"P\d+\.\d+", recovery_clause.group("items")))):
            return True
    return False


def _authority_request(item_id: str, protected_transition):
    """Validate the narrow request shape for a protected plan transition.

    Ordinary item execution never supplies this value: its authority is the checked item
    carrier.  A validator for an explicitly protected branch may supply the three facts
    it is asking the plan to prove.  The facts are *not* authority themselves; the
    Decision Log resolver below must still find the matching committed grant.
    """
    if protected_transition is None:
        return None
    if not isinstance(protected_transition, dict):
        raise TaskContractBuildError(item_id, "authority", "protected_transition must be a mapping")
    expected = {"gate_id", "branch", "scope"}
    if set(protected_transition) != expected:
        raise TaskContractBuildError(
            item_id, "authority",
            "protected_transition must contain exactly gate_id, branch and scope")
    request = {key: protected_transition[key] for key in expected}
    if any(not isinstance(value, str) or not value.strip() for value in request.values()):
        raise TaskContractBuildError(item_id, "authority",
                                     "protected_transition values must be non-empty strings")
    if not _OWNER_GRANT_RE.fullmatch(f"[OWNER-GRANT:{request['gate_id']}]"):
        raise TaskContractBuildError(item_id, "authority", "gate_id has an illegal form")
    return {key: value.strip() for key, value in request.items()}


def _decision_number(value: str):
    match = re.fullmatch(r"D(\d+)", (value or "").strip())
    return int(match.group(1)) if match else None


def _has_contiguous_decision_identities(rows) -> bool:
    """Whether the whole Decision Log is the one checked, append-only carrier.

    A protected grant is meaningful only when its ``D#`` is an identity in the
    plan's actual Decision Log, rather than a syntactically valid row pasted into
    the table.  The plan protocol's log is append-only ``D1`` … ``Dn``: reject a
    gap, duplicate, malformed ID, or reordered old decision here.  This is a
    resolver-local authority check, deliberately not a new plan-wide lint rule;
    ordinary Task Contract builds do not need an owner grant.
    """
    identities = [_decision_number(row.get("D#", "")) for row, _lineno in rows]
    return identities == list(range(1, len(identities) + 1))


def _owner_message_matches(plan_dir: Path, reference: str, request: dict) -> bool:
    """Validate the explicit Layer-0 repository-owner message a grant cites.

    The compact reference is confined to one committed ``brief/*.md`` file.  Its
    referenced line must independently restate the gate, branch and finite scope and
    declare repository-owner provenance.  Copying an owner identity into a Decision
    Log row is therefore insufficient to mint authority.
    """
    reference_match = _OWNER_MESSAGE_REF_RE.fullmatch(reference or "")
    if reference_match is None:
        return False
    message_path = plan_dir / "brief" / reference_match.group("filename")
    try:
        if not message_path.is_file() or message_path.is_symlink():
            return False
        records = [_OWNER_MESSAGE_RECORD_RE.fullmatch(line.strip())
                   for line in message_path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError):
        return False
    matches = [record for record in records
               if record is not None
               and record.group("message_id") == reference_match.group("message_id")]
    return (len(matches) == 1
            and matches[0].group("gate_id") == request["gate_id"]
            and matches[0].group("branch") == request["branch"]
            and matches[0].group("scope") == request["scope"])


def _resolve_authority(plan_lint, plan_lines, plan_dir: Path, item_id: str,
                       phase_path: Path, implementation_rules: str,
                       protected_transition):
    """Derive authority only from committed plan-native carriers.

    The routine path is backed by the item block that `build()` already parsed.  A
    protected branch additionally needs one exact Decision Log carrier: marker, branch,
    finite scope, and an explicit repository-owner message reference must parse and bind
    together.  A later revocation wins.  An invalid or absent grant returns an ungranted
    owner gate so `pre_mutation()` emits the frozen `AUTHORITY_BOUNDARY` code instead of
    inventing a new bypass code.
    """
    item_carrier_path = phase_path.parent / f"{item_id}.md"
    item_carrier = f"{item_carrier_path.relative_to(plan_dir).as_posix()}:{item_id}"
    request = _authority_request(item_id, protected_transition)
    if request is None:
        return "routine", True, item_carrier

    marker = f"[OWNER-GRANT:{request['gate_id']}]"
    # The item must itself declare this exact protected transition.  A caller cannot
    # redirect a valid grant to another item/branch merely by supplying kwargs.
    if marker not in implementation_rules:
        return "owner-gate", False, item_carrier

    from task import plan_decisions
    try:
        decisions = plan_decisions.load_decisions(plan_dir)
    except plan_decisions.DecisionError:
        return "owner-gate", False, item_carrier
    rows = [({"D#": decision.identifier, "Решение": decision.decision_text}, 1)
            for decision in decisions]
    if not _has_contiguous_decision_identities(rows):
        return "owner-gate", False, item_carrier

    grant_rows = []
    revocations = []
    for row, lineno in rows:
        decision_id = _decision_number(row.get("D#", ""))
        decision = (row.get("Решение", "") or "").strip()
        if decision_id is None:
            continue
        if marker in decision:
            grant_rows.append((decision_id, lineno, decision))
        if request["gate_id"] in _OWNER_REVOKE_RE.findall(decision):
            revocations.append(decision_id)

    # Count every exact gate marker before parsing.  A malformed duplicate is still an
    # ambiguity, not a harmless line the resolver may silently skip.
    if len(grant_rows) != 1:
        return "owner-gate", False, item_carrier
    decision_id, lineno, decision = grant_rows[0]
    record = _OWNER_GRANT_RECORD_RE.fullmatch(decision)
    if (record is None
            or record.group("gate_id") != request["gate_id"]
            or record.group("branch") != request["branch"]
            or record.group("scope") != request["scope"]
            or not _owner_message_matches(plan_dir, record.group("owner_message"), request)
            or any(revocation > decision_id for revocation in revocations)):
        return "owner-gate", False, item_carrier
    return "owner-gate", True, f"decisions/D{decision_id}:{lineno} {marker}"


# D78/2026.07.24-AGENT-RELIABILITY P2.10 — closed literal set of §3 Routing route-column headers `plan-protocol` §9
# Back-compat declares VALID today: the canon form plus exactly the two legacy spellings
# measured live on the fleet (`findings/14` M4.1). Preference order matters (canon first);
# no fuzzy/normalized/regex match — a header outside this tuple is an unrecognized table,
# never a guess (Implementation Rules (2)).
_ROUTING_HEADER_CANON = "Model class/effort"
_ROUTING_HEADER_CANDIDATES = (_ROUTING_HEADER_CANON, "Model/effort", "Model/Effort")
_EXECUTABLE_ROUTING_COLUMNS = (
    "Batch", "Items", "Model class/effort", "Exec", "Review", "Почему",
)
_EXECUTABLE_ROUTING_EXEC_VALUES = frozenset(("plan-exec", "manual", "plan-design"))
_EXECUTABLE_ROUTING_REVIEW_VALUES = frozenset(("full", "light", "none"))

# Default location of the committed provider routing carrier this module reads
# `mappings.*.class_selectors` from (D78 Implementation Rules (1) — one name-to-class
# carrier, never a second table in this module). Package-relative, same convention
# `command_render.mapping_from_catalog` already uses for its own sibling config
# (`Path(__file__).resolve().parents[N] / "configs/..."`) — never cwd/env discovery
# (`command_catalog`'s own module docstring bans that for the loader this calls).
_DEFAULT_ROUTING_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "command-routing.json"
_REVIEW_ORDER = ("none", "light", "full")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _model_class_name_map(routing_metadata: dict) -> dict:
    """`{model-name: {classes it is bound to}}` built fresh from every provider's
    `mappings.<provider>.class_selectors` (committed `command-routing.json`, read via
    `command_catalog.load_routing_metadata` by the caller — this function never opens a
    file itself). A name bound to more than one class is ambiguous by construction of the
    fleet-wide carrier; `_resolve_model_class` below refuses it rather than picking
    either winner (D78: "имя ... встречающееся в двух разных классах, даёт тот же
    типизированный отказ")."""
    name_to_classes: dict = {}
    for provider in routing_metadata.get("mappings", {}).values():
        for model_class, names in provider.get("class_selectors", {}).items():
            for name in names:
                name_to_classes.setdefault(name, set()).add(model_class)
    return name_to_classes


def _resolve_model_class(token: str, name_to_classes: dict, item_id: str, raw_cell: str) -> str:
    """Route-column model token → frozen `MODEL_CLASS_ORDER` class. Already a class name
    (the canon form this plan's own §3 uses) → returned as-is. A provider model name (the
    FOREMAN §3 form, e.g. `opus`) → looked up through the committed carrier ONLY — this
    module never grows its own name table (D78 Implementation Rules (1), D6). Unknown or
    ambiguous (bound to two classes at once) → typed refusal naming the offending cell,
    never a guessed class."""
    if token in MODEL_CLASS_ORDER:
        return token
    classes = name_to_classes.get(token)
    if not classes or len(classes) != 1:
        raise TaskContractBuildError(
            item_id, "Routing",
            f"route cell {raw_cell!r}: model token {token!r} is neither a class "
            f"{MODEL_CLASS_ORDER} nor an unambiguous name in command-routing.json "
            f"class_selectors (resolved classes: {sorted(classes) if classes else []})")
    return next(iter(classes))


def _routing_digest(plan_dir: Path, items: tuple[str, ...]) -> tuple[str, str]:
    """Return the two immutable inputs a batch receipt must bind.

    The Routing table remains the only authority.  Item specs are included only
    as an invalidation boundary: editing a member's contract invalidates an old
    continuation receipt without manufacturing a second routing carrier.
    """
    from task import plan_layout

    plan_bytes = (plan_dir / "plan.md").read_bytes()
    spec_bytes = b"".join(
        plan_layout.carrier_path(plan_dir, "item-spec", item_id=item).read_bytes()
        for item in items
    )
    return hashlib.sha256(plan_bytes).hexdigest(), hashlib.sha256(spec_bytes).hexdigest()


def executable_routing_table(plan_dir: Path | str) -> dict:
    """Return the sole executable ``§3 Routing`` table for a v2 plan.

    A Routing section may contain explanatory or provider-mapping tables.  They
    are not executable Routing merely because they have pipe-delimited rows.
    The exact six-column header bounds the one executable table.  A second
    matching header is ambiguity, never a later table to silently prefer.
    """
    from task import plan_lint

    plan_dir = Path(plan_dir)
    lines = plan_lint._read_lines(plan_dir / "plan.md") or []
    _index, body, start = plan_lint._find_section(lines, _ROUTING_HEADER_RE)
    if body is None:
        raise TaskContractBuildError(
            "routing", "Routing", "no `## 3. Routing` section found in plan.md")

    def cells(raw: str) -> tuple[str, ...]:
        value = raw.strip()
        if value.startswith("|"):
            value = value[1:]
        if value.endswith("|"):
            value = value[:-1]
        return tuple(cell.strip() for cell in value.split("|"))

    matches: list[tuple[int, list[tuple[dict[str, object], int]]]] = []
    for index, raw in enumerate(body):
        if not raw.strip().startswith("|") or cells(raw) != _EXECUTABLE_ROUTING_COLUMNS:
            continue
        separator_index = index + 1
        if separator_index >= len(body):
            raise TaskContractBuildError(
                "routing", "Routing", f"line {start + index}: executable table has no separator")
        separator = cells(body[separator_index])
        if (len(separator) != len(_EXECUTABLE_ROUTING_COLUMNS)
                or not all(re.fullmatch(r":?-{2,}:?", cell) for cell in separator)):
            raise TaskContractBuildError(
                "routing", "Routing", f"line {start + index}: executable table has an invalid separator")
        rows: list[tuple[dict[str, object], int]] = []
        row_index = separator_index + 1
        while row_index < len(body) and body[row_index].strip().startswith("|"):
            values = cells(body[row_index])
            if len(values) != len(_EXECUTABLE_ROUTING_COLUMNS):
                raise TaskContractBuildError(
                    "routing", "Routing", f"line {start + row_index}: executable table must have exactly six columns")
            row = dict(zip(_EXECUTABLE_ROUTING_COLUMNS, values))
            items = plan_lint._routing_items(row["Items"].strip().strip("`"))
            if not items:
                raise TaskContractBuildError(
                    "routing", "Routing", f"line {start + row_index}: invalid Items form")
            row["_items"] = tuple(items)
            rows.append((row, start + row_index))
            row_index += 1
        matches.append((start + index, rows))

    if not matches:
        raise TaskContractBuildError(
            "routing", "Routing",
            "no executable table with exact header `Batch | Items | Model class/effort | Exec | Review | Почему`")
    if len(matches) != 1:
        lines = ", ".join(str(line) for line, _rows in matches)
        raise TaskContractBuildError(
            "routing", "Routing", f"duplicate executable Routing tables at lines {lines}")
    header_line, rows = matches[0]
    if not rows:
        raise TaskContractBuildError(
            "routing", "Routing", "executable Routing table may not be empty")
    owners: set[str] = set()
    for row, line in rows:
        for item_id in row["_items"]:
            if item_id in owners:
                raise TaskContractBuildError(
                    item_id, "Routing", f"line {line}: item is assigned more than once")
            owners.add(item_id)
    digest_payload = "\n".join(
        ["|".join(_EXECUTABLE_ROUTING_COLUMNS)]
        + ["|".join(row[column] for column in _EXECUTABLE_ROUTING_COLUMNS) for row, _line in rows]
    )
    return {
        "headers": _EXECUTABLE_ROUTING_COLUMNS,
        "header_line": header_line,
        "rows": tuple(rows),
        "digest": hashlib.sha256(digest_payload.encode("utf-8")).hexdigest(),
    }


def compile_batch_routing(plan_dir, *, routing_config_path=None) -> dict:
    """Compile Routing once into item and batch projections.

    This compiler accepts only the exact executable v2 table.  Historical
    item-route spellings remain isolated in ``build()``'s legacy resolver and
    never acquire an inferred execution group.
    """
    from task import command_catalog, plan_lint

    plan_dir = Path(plan_dir)
    table = executable_routing_table(plan_dir)
    rows = table["rows"]
    route_header = _ROUTING_HEADER_CANON

    metadata = command_catalog.load_routing_metadata(
        routing_config_path or _DEFAULT_ROUTING_CONFIG_PATH)
    names = _model_class_name_map(metadata)

    def parse_route(raw: str, item: str) -> tuple[str, str]:
        model, sep, effort = (raw or "").partition("/")
        model, effort = model.strip(), effort.strip()
        if not sep or not model or effort not in EFFORT_ORDER:
            raise TaskContractBuildError(item, "Routing", f"route cell {raw!r} does not parse as '<model>/<effort>'")
        return _resolve_model_class(model, names, item, raw), effort

    item_rows: dict[str, dict] = {}
    groups: dict[str, list[dict]] = {}
    for row, line in rows:
        items = row["_items"]
        batch = (row.get("Batch") or "solo").strip()
        if not batch or not plan_lint._ROUTING_BATCH_RE.fullmatch(batch):
            raise TaskContractBuildError("routing", "Routing", f"line {line}: invalid Batch {batch!r}")
        exec_mode = (row.get("Exec") or "").strip()
        if exec_mode not in _EXECUTABLE_ROUTING_EXEC_VALUES:
            raise TaskContractBuildError("routing", "Routing", f"line {line}: invalid Exec {exec_mode!r}")
        review = (row.get("Review") or "").strip()
        if review not in _EXECUTABLE_ROUTING_REVIEW_VALUES:
            raise TaskContractBuildError("routing", "Routing", f"line {line}: invalid Review {review!r}")
        batches = [batch] * len(items)
        for item, item_batch in zip(items, batches):
            if item in item_rows:
                raise TaskContractBuildError(item, "Routing", "item is assigned more than once")
            model_class, effort = parse_route(row.get(route_header, ""), item)
            batch_key = f"solo:{item}" if item_batch.lower() == "solo" else item_batch
            entry = {"item_id": item, "batch": item_batch, "batch_key": batch_key, "route": {
                "model_class": model_class, "effort": effort},
                "exec": exec_mode, "review": review, "line": line}
            item_rows[item] = entry
            groups.setdefault(batch_key, []).append(entry)

    compiled = {}
    for batch_key, members in groups.items():
        batch = members[0]["batch"]
        members.sort(key=lambda entry: (entry["item_id"].split(".")[0], int(entry["item_id"].split(".")[1])))
        items = tuple(entry["item_id"] for entry in members)
        phases = {item.split(".")[0] for item in items}
        execs = {entry["exec"] for entry in members}
        if batch.lower() == "solo":
            if len(members) != 1:
                # Legacy projections are split above, so this is a new-plan error.
                raise TaskContractBuildError("routing", "Routing", "Batch solo may contain one item")
        elif len(members) < 2 or len(phases) != 1 or len(execs) != 1:
            raise TaskContractBuildError("routing", "Routing", f"Batch {batch!r} is not a phase-local execution unit")
        numbers = [int(item.split(".")[1]) for item in items]
        if batch.lower() != "solo" and numbers != list(range(numbers[0], numbers[-1] + 1)):
            raise TaskContractBuildError("routing", "Routing", f"Batch {batch!r} is not adjacent")
        route = {"model_class": max((entry["route"]["model_class"] for entry in members), key=MODEL_CLASS_ORDER.index),
                 "effort": max((entry["route"]["effort"] for entry in members), key=EFFORT_ORDER.index)}
        review = max((entry["review"] for entry in members), key=lambda value: _REVIEW_ORDER.index(value)
                     if value in _REVIEW_ORDER else len(_REVIEW_ORDER))
        routing_digest, spec_digest = _routing_digest(plan_dir, items)
        compiled[batch_key] = {"batch_id": batch, "items": items, "route": route,
                           "exec": next(iter(execs)), "review": review,
                           "routing_digest": routing_digest, "spec_digest": spec_digest}
    return {"items": item_rows, "batches": compiled, "routing_digest": table["digest"]}


def normalize_batch_request(request) -> tuple[str, ...]:
    """Normalize the closed item/range request grammar without accepting prose."""
    from task import plan_lint

    tokens = (request,) if isinstance(request, str) else tuple(request or ())
    expanded = []
    for token in tokens:
        if not isinstance(token, str):
            raise ValueError("BATCH_AMBIGUOUS: item request must contain strings")
        items = plan_lint._routing_items(token.strip().strip("`"))
        if not items:
            raise ValueError(f"BATCH_AMBIGUOUS: invalid request {token!r}")
        expanded.extend(items)
    if not expanded or len(set(expanded)) != len(expanded):
        raise ValueError("BATCH_AMBIGUOUS: request is empty or repeats an item")
    return tuple(expanded)


def build_batch_receipt(batch: dict, *, completed_prefix=(), handoff_digest=None) -> dict:
    """Create the optional durable continuation checkpoint for one batch."""
    prefix = tuple(completed_prefix)
    items = tuple(batch["items"])
    if items[:len(prefix)] != prefix:
        raise ValueError("BATCH_STALE: completed prefix is not a batch prefix")
    if handoff_digest is not None and not _SHA256_RE.fullmatch(handoff_digest):
        raise ValueError("BATCH_STALE: handoff digest must be SHA-256")
    return {"schema_version": "batch-receipt/v1", "batch_id": batch["batch_id"],
            "membership": list(items),
            "invocation_digest": hashlib.sha256("\n".join(items).encode()).hexdigest(),
            "completed_prefix": list(prefix), "routing_digest": batch["routing_digest"],
            "spec_digest": batch["spec_digest"], "handoff_digest": handoff_digest,
            "stop_disposition": "continue"}


def validate_batch_receipt(receipt: dict) -> None:
    required = {"schema_version", "batch_id", "membership", "invocation_digest", "completed_prefix",
                "routing_digest", "spec_digest", "handoff_digest", "stop_disposition"}
    if not isinstance(receipt, dict) or set(receipt) != required or receipt.get("schema_version") != "batch-receipt/v1":
        raise ValueError("BATCH_STALE: malformed receipt")
    members, prefix = receipt["membership"], receipt["completed_prefix"]
    if (not isinstance(receipt["batch_id"], str) or not members or not all(isinstance(item, str) for item in members)
            or members[:len(prefix)] != prefix or receipt["stop_disposition"] != "continue"):
        raise ValueError("BATCH_STALE: malformed receipt")
    if receipt["invocation_digest"] != hashlib.sha256("\n".join(members).encode()).hexdigest():
        raise ValueError("BATCH_STALE: invocation digest mismatch")
    if any(not isinstance(receipt[key], str) or not _SHA256_RE.fullmatch(receipt[key])
           for key in ("invocation_digest", "routing_digest", "spec_digest")):
        raise ValueError("BATCH_STALE: malformed receipt digest")
    if receipt["handoff_digest"] is not None and not _SHA256_RE.fullmatch(receipt["handoff_digest"]):
        raise ValueError("BATCH_STALE: malformed handoff digest")


def admit_batch(plan_dir, request, *, receipt=None, routing_config_path=None) -> dict:
    """Return the sole pre-mutation batch verdict; this function never mutates state."""
    try:
        requested = normalize_batch_request(request)
    except ValueError:
        return {"verdict": "BATCH_AMBIGUOUS", "batch": None, "requested": [], "canonical": None}
    compiled = compile_batch_routing(plan_dir, routing_config_path=routing_config_path)
    owners = [compiled["items"].get(item, {}).get("batch_key") for item in requested]
    if not all(owners) or len(set(owners)) != 1:
        return {"verdict": "BATCH_AMBIGUOUS", "batch": None, "requested": list(requested), "canonical": None}
    batch = compiled["batches"][owners[0]]
    exact = tuple(batch["items"])
    if requested == exact:
        return {"verdict": "ALLOW", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    if batch["batch_id"].lower() == "solo":
        return {"verdict": "BATCH_REQUIRED", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    if receipt is None:
        return {"verdict": "BATCH_REQUIRED", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    try:
        validate_batch_receipt(receipt)
    except ValueError:
        return {"verdict": "BATCH_STALE", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    if (receipt["batch_id"] != batch["batch_id"] or receipt["membership"] != list(exact)
            or receipt["routing_digest"] != batch["routing_digest"] or receipt["spec_digest"] != batch["spec_digest"]):
        return {"verdict": "BATCH_STALE", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    suffix = exact[len(receipt["completed_prefix"]):]
    if requested != suffix:
        return {"verdict": "BATCH_REQUIRED", "batch": batch, "requested": list(requested), "canonical": list(suffix)}
    return {"verdict": "ALLOW", "batch": batch, "requested": list(requested), "canonical": list(suffix)}


def _find_routing_row(plan_lint_mod, plan_lines, item_id: str, routing_metadata: dict):
    """Reuses `plan_lint`'s own generic table parser (`_find_section`/
    `_parse_table` — already the SSOT for Meta/Status Board/Phase Status tables) over the
    `## 3. Routing` section instead of a second parser. Returns `(model_class, effort)` —
    both already frozen-ladder members — or raises `TaskContractBuildError` naming the
    item, field `"Routing"` and the concrete cause (D78: no fabricated empty pair ever
    reaches `build()`'s caller, no unrecognized form is silently guessed at).

    An `Items` cell that is a comma list covering this item (`P8.5, P8.6` — the shape that
    blocked 7 live fleet items, `research/25` §1) gets a DIAGNOSTIC refusal naming the cell,
    its line and both legal forms; it stays a refusal — the list is not a legal form (D124,
    P8.10). Every other unrecognized cell keeps the historical blind text."""
    _, body, start = plan_lint_mod._find_section(plan_lines, _ROUTING_HEADER_RE)
    if body is None:
        raise TaskContractBuildError(item_id, "Routing", "no `## 3. Routing` section found in plan.md")
    headers, rows, _ = plan_lint_mod._parse_table(body, start)
    if headers is None:
        raise TaskContractBuildError(item_id, "Routing", "`## 3. Routing` section carries no table")
    header = next((candidate for candidate in _ROUTING_HEADER_CANDIDATES if candidate in headers), None)
    if header is None:
        raise TaskContractBuildError(
            item_id, "Routing",
            f"no recognized route-column header among {headers!r}; supported (closed set): "
            f"{_ROUTING_HEADER_CANDIDATES!r}")

    phase_token = item_id.split(".")[0]
    try:
        item_n = int(item_id.split(".")[1])
    except (IndexError, ValueError):
        item_n = None
    name_to_classes = _model_class_name_map(routing_metadata)

    def _resolve(raw_cell: str):
        model_token, sep, effort = raw_cell.partition("/")
        model_token, effort = model_token.strip(), effort.strip()
        if not sep or not model_token or not effort:
            raise TaskContractBuildError(
                item_id, "Routing", f"route cell {raw_cell!r} does not parse as '<model>/<effort>'")
        model_class = _resolve_model_class(model_token, name_to_classes, item_id, raw_cell)
        if effort not in EFFORT_ORDER:
            raise TaskContractBuildError(
                item_id, "Routing",
                f"route cell {raw_cell!r}: effort {effort!r} is outside the frozen ladder {EFFORT_ORDER}")
        return model_class, effort

    for row, _lineno in rows:
        cell = (row.get("Items", "") or "").strip().strip("`")
        if cell == item_id:
            return _resolve(row.get(header, ""))
        m = _ROUTING_RANGE_RE.match(cell)
        if m and item_n is not None and m.group(1) == phase_token == m.group(3):
            lo, hi = int(m.group(2)), int(m.group(4))
            if lo <= item_n <= hi:
                return _resolve(row.get(header, ""))

    def _token_covers(token: str) -> bool:
        """The same two matchers the loop above uses, applied to ONE token of a comma
        list — for DIAGNOSIS ONLY. A covering token never yields a route (the list stays
        illegal, D124: «отказ остаётся отказом»); it only proves the refusal is about the
        cell's FORM, not about a missing row."""
        if token == item_id:
            return True
        match = _ROUTING_RANGE_RE.match(token)
        return bool(match and item_n is not None and match.group(1) == phase_token == match.group(3)
                    and int(match.group(2)) <= item_n <= int(match.group(4)))

    range_form = f"{phase_token}.a–{phase_token}.b"
    for row, lineno in rows:
        cell = (row.get("Items", "") or "").strip().strip("`")
        # Narrow by construction (Code Guidance): a comma AND a token that covers this item.
        # Any other unparsed cell keeps the blind text below — a diagnostic that guessed the
        # cause on a foreign shape would lie about the fix.
        if "," not in cell or not any(_token_covers(t.strip().strip("`")) for t in cell.split(",")):
            continue
        raise TaskContractBuildError(
            item_id, "Routing",
            f"§3 Routing row {cell!r} (line {lineno}) is a comma list — an illegal `Items` "
            f"cell form; legal forms (closed set, plan-protocol §9): {item_id!r} (a single item) "
            f"or {range_form!r} (a single-phase range). Split the row per item; the batch "
            f"belongs in the `Batch` column.")
    raise TaskContractBuildError(item_id, "Routing", "no §3 Routing row found for this item")


def build(plan_dir, item_id, *, actual_route=None, capabilities=(), bundle_privacy=None,
         protected_transition=None,
         next_form="exec-items", next_context=None,
         next_origin="approved-goal", next_changed_by=None, carrier=None,
         routing_config_path=None) -> dict:
    """Task Contract v1 producer (2026.07.24-AGENT-RELIABILITY P2.6, F1) — compiles `phases/Pn.md` + `plan.md`
    §3/§0 fields for one item into the exact 15-key schema
    `task-contract-v1.schema.json` declares. Full field-mapping table:
    `plans/2026.07.24-AGENT-RELIABILITY/findings/P2.6-contract-mapping.md`.

    Reuses `task.plan_lint`'s own field parser (`parse_phase_md`/`parse_plan_md`,
    plus its generic `_find_section`/`_parse_table` table reader for §3 Routing)
    via a LAZY import — the same circular-import pattern `evaluate_finding`
    already uses for `review_policy` (`plan_lint` imports `task_contract` at
    module level; `task_contract` importing `plan_lint` back at module level
    would be circular). Never a second parser of item fields (Code Guidance,
    anti-duplicate-SSOT).

    Deterministic by default: two calls over the same committed tree produce
    byte-identical JSON (`content_hash` included) — `actual_route` is NOT
    captured live unless the caller supplies one, since a bare CLI invocation
    must be repeatable across processes/sessions.

    Anti-padding (Implementation Rules (2)): an item field that is empty
    (the canonical `"—"` placeholder) where the schema requires a value
    raises `TaskContractBuildError` naming the field and item — never a
    fabricated placeholder dressed up as data.

    `protected_transition` — an optional exact request (`gate_id`, `branch`, `scope`) for
    a branch that the item itself declares as owner-gated. It never grants authority by
    itself: `_resolve_authority` verifies a later Decision Log marker. The former
    `authority_*` kwargs are deliberately absent, so a caller cannot restore a foreign
    D-number or fabricate an allow result.

    `routing_config_path` (2026.07.24-AGENT-RELIABILITY P2.10, D78) — the committed routing carrier
    `_find_routing_row`/`_resolve_model_class` read `mappings.*.class_selectors` from,
    via `command_catalog.load_routing_metadata` (never a second name table in this
    module). Defaults to this package's own `configs/command-routing.json`
    (`_DEFAULT_ROUTING_CONFIG_PATH`, derived from `__file__` — the same
    package-relative convention `command_render.mapping_from_catalog` already uses for
    its sibling config); a caller MAY override it, but never supplies cwd/env instead.
    """
    from task import plan_lint  # lazy — avoids a plan_lint↔task_contract circular import
    from task import plan_layout
    from task import route_evidence  # lazy — same reasoning, route assembly only
    from task import review_policy  # lazy — reuse of loop_budget constants only
    from task import command_catalog  # lazy — same reasoning, class_selectors carrier only

    plan_dir = Path(plan_dir)
    phase_token = item_id.split(".")[0]
    diag = plan_lint.Diagnostics()
    layout = plan_layout.layout_version(plan_dir)
    if next_context is None:
        next_context = "continue-root" if layout == "v2" else "same-session — item"
    plan_meta, _ = plan_lint.parse_plan_md(plan_layout.plan_core_path(plan_dir), diag)
    # `parse_plan_md` resolves v2 Version/Status/Last Updated from the owner
    # projection. Keep this compiler on that single path rather than reopening
    # plan.md and accidentally restoring the legacy monolith as a source.
    for field in ("Version", "Status", "Last Updated"):
        if not plan_meta or field not in plan_meta:
            raise TaskContractBuildError(item_id, "Meta", f"нет поля {field!r} в владельческом виде")
    phase_path = plan_layout.phase_path(plan_dir, phase_token)
    phase = plan_lint.parse_phase_md(phase_path, phase_token, diag, layout=layout)
    occurrences = phase["items"].get(item_id) if phase else None
    if not occurrences:
        raise TaskContractBuildError(item_id, "item", f"no item block found in {phase_path}")
    fields = occurrences[0]["fields"]

    def field_text(name):
        value, _ = fields.get(name, ("", None))
        return (value or "").strip()

    _require_field(item_id, fields, "Intent")
    scope_included, scope_included_ln = _require_field(item_id, fields, "Scope Included")
    scope_excluded, scope_excluded_ln = _require_field(item_id, fields, "Scope Excluded")
    impl_rules_text = field_text("Implementation Rules")
    impl_rules_ln = fields.get("Implementation Rules", ("", None))[1]
    code_guidance_text = field_text("Code Guidance")
    code_guidance_ln = fields.get("Code Guidance", ("", None))[1]
    inputs_text = field_text("Inputs")
    required_reads_text = field_text("Required Reads")
    validation_text, _ = _require_field(item_id, fields, "Validation")
    deliverables, _ = _require_field(item_id, fields, "Deliverables")

    outcome = field_text("Intent")
    non_goals = _split_nonempty(scope_excluded, _SCOPE_CLAUSE_SPLIT_RE)

    must = []
    for clause in _split_nonempty(scope_included, _SCOPE_CLAUSE_SPLIT_RE):
        must.append({"id": f"M{len(must) + 1}", "requirement": clause,
                    "source_ref": f"phases/{phase_token}.md:{scope_included_ln}"})
    for clause in _marker_clauses(impl_rules_text, _IMPL_RULE_SPLIT_RE):
        must.append({"id": f"M{len(must) + 1}", "requirement": clause,
                    "source_ref": f"phases/{phase_token}.md:{impl_rules_ln}"})
    if not must:
        raise TaskContractBuildError(item_id, "Scope Included", "no requirement clause found")

    never = []
    for clause in non_goals:
        never.append({"id": f"N{len(never) + 1}", "prohibition": clause,
                     "source_ref": f"phases/{phase_token}.md:{scope_excluded_ln}"})
    for clause in _anti_clauses(code_guidance_text):
        never.append({"id": f"N{len(never) + 1}", "prohibition": clause,
                     "source_ref": f"phases/{phase_token}.md:{code_guidance_ln}"})
    if not never:
        raise TaskContractBuildError(item_id, "Scope Excluded", "no prohibition clause found")

    evidence = []
    execution_inputs = []
    for clause in _split_nonempty(inputs_text, _INPUTS_SPLIT_RE):
        path = _first_backtick_or_text(clause)
        evidence.append({"id": f"E{len(evidence) + 1}", "path": path,
                         "proof_class": "unknown", "algorithm": "doc-citation"})
        if _BACKTICK_RE.search(clause) and not is_external_path(path):
            execution_inputs.append({"path": path, "kind": "committed", "producer": None})
    required_reads_ids = []
    for clause in _marker_clauses(required_reads_text, _REQUIRED_READS_SPLIT_RE):
        path = _first_backtick_or_text(clause)
        eid = f"E{len(evidence) + 1}"
        evidence.append({"id": eid, "path": path, "proof_class": "unknown",
                         "algorithm": "doc-citation"})
        required_reads_ids.append(eid)
        if _BACKTICK_RE.search(clause) and not is_external_path(path):
            execution_inputs.append({"path": path, "kind": "committed", "producer": None})
    if not evidence:
        raise TaskContractBuildError(item_id, "Required Reads", "no evidence entry found")

    public_acceptance = []
    for clause in _split_nonempty(validation_text, _INPUTS_SPLIT_RE):
        eid = f"E{len(evidence) + 1}"
        evidence.append({"id": eid, "path": clause, "proof_class": "cross-checked",
                         "algorithm": "shell-command"})
        path_tokens = plan_lint.PORTABILITY_PATH_RE.findall(clause)
        scope = "internal" if any(is_external_path(tok) for tok in path_tokens) else "public"
        public_acceptance.append({"id": f"A{len(public_acceptance) + 1}", "predicate": deliverables,
                                  "scope": scope, "check": clause, "evidence_ref": eid})
    if not public_acceptance:
        raise TaskContractBuildError(item_id, "Validation", "no check clause found")

    plan_lines = plan_lint._read_lines(plan_dir / "plan.md") or []
    routing_metadata = command_catalog.load_routing_metadata(
        routing_config_path or _DEFAULT_ROUTING_CONFIG_PATH)
    # The canonical executable header may follow a non-executable mapping
    # table.  Ask the compiler first; legacy spellings retain their isolated
    # resolver only when the canonical table is absent altogether.
    try:
        compiled = compile_batch_routing(plan_dir, routing_config_path=routing_config_path)
    except TaskContractBuildError as exc:
        if "no executable table with exact header" not in str(exc):
            raise
        routing = _find_routing_row(plan_lint, plan_lines, item_id, routing_metadata)
    else:
        try:
            routing = compiled["items"][item_id]["route"]
        except KeyError as exc:
            raise TaskContractBuildError(item_id, "Routing", "no §3 Routing row found for this item") from exc
        routing = (routing["model_class"], routing["effort"])
    required_route = {"model_class": routing[0], "effort": routing[1]}
    if actual_route is None:
        actual_route = route_evidence.capture_actual(
            None, None, source="self-attested", ts="1970-01-01T00:00:00Z")
    route = route_evidence.build_task_contract_route(required_route, actual_route, capabilities)

    tier = "committed-bundle" if plan_lint._plan_declares_committed_bundle_tier(plan_dir) \
        else "brief-acceptance"
    if bundle_privacy is None:
        bundle_privacy = {"minimized": True, "excluded_classes": []}

    plan_id = plan_dir.name
    if carrier is None:
        carrier = f"task:plan-exec {plan_id} {item_id}"
    claude_render = f"/task:plan-exec {plan_id} {item_id}"
    codex_render = f"$ task:plan-exec {plan_id} {item_id}"

    phase_lines = plan_lint._read_lines(phase_path) or []
    observed_rounds = _count_audit_rounds(plan_dir, phase_lines, phase_token)
    audit_cap_remediation = _has_audit_cap_remediation_grant(plan_dir, item_id)
    authority_class, authority_granted, authority_granted_by = _resolve_authority(
        plan_lint, plan_lines, plan_dir, item_id, phase_path, impl_rules_text,
        protected_transition)

    contract = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": f"{plan_id.lower()}-{item_id.lower().replace('.', '-')}",
        "version": {"revision": 1, "content_hash": "0" * 64, "supersedes": None},
        "goal": {"outcome": outcome, "non_goals": non_goals},
        "must": must,
        "never": never,
        "done": {"public_acceptance": public_acceptance},
        "authority": {
            "class": authority_class,
            "granted": authority_granted,
            "granted_by": authority_granted_by,
            "auto_allowed": ["write the item's declared Files", "run the item's Validation",
                            "close the item with the two-commit topology"],
            "stop_boundaries": ["tag/push/release", "fleet rollout", "consumer repositories",
                               "FOREMAN outward parts"],
            "loop_budget": {"audit_rounds_max": review_policy.AUDIT_ROUNDS_MAX,
                           "same_finding_max": review_policy.SAME_FINDING_MAX},
            "observed_rounds": observed_rounds,
            "audit_cap_remediation": audit_cap_remediation,
        },
        "next": {"form": next_form, "carrier": carrier, "context": next_context,
                "origin": next_origin, "changed_by": next_changed_by},
        "route": route,
        "evidence": evidence,
        "portability": {
            "tier": tier,
            "execution_inputs": execution_inputs,
            "provenance_only": [],
            "privacy": bundle_privacy,
            "semantic_carrier": "task:plan-exec",
            "provider_renderers": {"claude": claude_render, "codex": codex_render},
        },
        "conflicts": [],
        "slice": {"subagent_keys": list(SLICE_SUBAGENT_KEYS),
                 "root_only_keys": list(SLICE_ROOT_ONLY_KEYS)},
        "cold_start": {"plan_id": plan_id, "item_id": item_id, "reads": required_reads_ids,
                      "carrier": carrier},
    }
    contract["version"]["content_hash"] = content_hash(contract)
    return contract


# --------------------------------------------------------------------------
# bundle_lint() — evidence-bundle privacy/minimization predicate (2026.07.24-AGENT-RELIABILITY P2.6, F2/F4).
# --------------------------------------------------------------------------

_SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"sk-[A-Za-z0-9]{20,}"),
    re.compile(rb"(?i)(?:api|secret)[_-]?key[\"']?\s*[:=]\s*[\"'][A-Za-z0-9/+=_-]{16,}"),
)
_CHAIN_OF_THOUGHT_PATTERNS = (
    re.compile(rb"<thinking>"),
    re.compile(rb"<scratchpad>"),
    re.compile(rb"(?i)chain[- ]of[- ]thought"),
)
_TOOL_PAYLOAD_PATTERNS = (
    re.compile(rb'"tool_use"'),
    re.compile(rb'"tool_result"'),
    re.compile(rb"<tool_call>"),
)
_RAW_TRANSCRIPT_PATTERNS = (
    re.compile(rb'"role"\s*:\s*"(?:user|assistant)"'),
    re.compile(rb"(?m)^(?:Human|Assistant|User|System):\s"),
)
_CONTENT_CLASS_PATTERNS = (
    ("secrets", _SECRET_PATTERNS),
    ("chain-of-thought", _CHAIN_OF_THOUGHT_PATTERNS),
    ("tool-payloads", _TOOL_PAYLOAD_PATTERNS),
    ("raw-transcript-bodies", _RAW_TRANSCRIPT_PATTERNS),
)
# A single stray "Human:"-shaped line is not a transcript — require repetition
# before calling it a raw conversational body (avoids a false positive on a
# doc that merely quotes one line of dialogue).
_RAW_TRANSCRIPT_MIN_HITS = 3


def _scan_content_classes(data: bytes) -> set:
    found = set()
    for class_name, patterns in _CONTENT_CLASS_PATTERNS:
        for pattern in patterns:
            hits = len(pattern.findall(data))
            if hits == 0:
                continue
            if class_name == "raw-transcript-bodies" and hits < _RAW_TRANSCRIPT_MIN_HITS:
                continue
            found.add(class_name)
            break
    return found


def bundle_lint(bundle_dir, *, manifest_path, verifier_path, declared_privacy) -> str | None:
    """plan-portability-v1.md §Bundle requirements (F2/F4) — COMPUTES, never
    reads, the declaration: minimization is the actual bundle file set against
    the manifest's own declared file list; content classes are found by
    signature scan over the ACTUAL bytes on disk (secrets/chain-of-thought/
    tool-payloads/raw-transcript-bodies), never by trusting
    `declared_privacy` as ground truth (that was exactly F2/F4: the fields
    were self-declared and self-read by the same generator).

    New reason codes (2026.07.24-AGENT-RELIABILITY P2.6 — not pre-declared by 2026.07.24-AGENT-RELIABILITY P2.1's frozen
    `state-transition-cases.json::new_reason_codes`; this item introduces
    them directly, same discipline as that file's own entries):

      * `BUNDLE_ARTIFACT_MISSING` — distinct_from `PORTABILITY_INPUT_MISSING`
        (that fires on an absent EXECUTION INPUT path already inside a
        compiled contract; this fires on the bundle's own internal manifest
        or verifier file being absent on disk — a different object, checked
        before any Task Contract exists).
      * `BUNDLE_PRIVACY_MISMATCH` — distinct_from `PORTABILITY_TIER_MISCLASSIFIED`
        (that fires on the TIER assignment against the classification rule;
        this fires on the computed content-class scan disagreeing with the
        item's declared `privacy` block — never about tier).

    `manifest_path` — a JSON file `{"files": [<bundle-relative path>, ...]}`
    declaring the bundle's exact expected member set (this item's own minimal
    manifest contract — no existing generic manifest schema is reusable
    across the fleet's several bundle-specific formats, e.g. 2026.07.24-AGENT-RELIABILITY P0.1's
    `manifests/bundle-manifest.json` vs 2026.07.24-AGENT-RELIABILITY P2.5's `result-manifest.json`).
    `verifier_path` — existence-checked only (never executed: running an
    arbitrary committed script from inside a library predicate is its own
    hazard and outside this item's Scope).

    Existing extension points surveyed first (D23): `is_external_path` (a
    path-STRING test, reused nowhere here — bundle_lint scans byte CONTENT,
    a different object) and `plan-portability-v1.md`'s bundle-requirements
    prose (stated but never executable before this function). Alternatives
    considered: (a) trust the declared `privacy` block as-is — rejected,
    exactly F4's defect; (b) hash-only manifest check without content-class
    scanning — rejected, leaves secrets/raw-bulk undetected even when file
    counts match. Named consumers: 2026.07.24-AGENT-RELIABILITY P2.7 (write-site), 2026.07.24-AGENT-RELIABILITY P2.8 (P2.5 bundle
    rerun). SemVer: new public function, additive to `task_contract`'s
    surface.
    """
    bundle_dir = Path(bundle_dir)
    manifest_path = Path(manifest_path)
    verifier_path = Path(verifier_path)
    if not manifest_path.is_file() or not verifier_path.is_file():
        return BUNDLE_ARTIFACT_MISSING

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared_set = {entry["path"] if isinstance(entry, dict) else entry
                    for entry in manifest["files"]}
    exempt = {manifest_path.resolve(), verifier_path.resolve()}
    actual_set = {str(p.relative_to(bundle_dir)) for p in bundle_dir.rglob("*")
                 if p.is_file() and p.resolve() not in exempt}
    minimized = actual_set == declared_set

    found_classes = set()
    for rel in actual_set:
        found_classes |= _scan_content_classes((bundle_dir / rel).read_bytes())

    declared_excluded = set(declared_privacy["excluded_classes"])
    violated = found_classes & declared_excluded
    if declared_privacy["minimized"] != minimized or violated:
        return BUNDLE_PRIVACY_MISMATCH
    return None


def canonical_payload(contract: dict) -> dict:
    """The hashed payload: the contract minus its own declared hash
    (task-contract-v1.md §Version, content_hash is recomputed, never trusted as written)."""
    payload = copy.deepcopy(contract)
    payload.get("version", {}).pop("content_hash", None)
    return payload


def content_hash(contract: dict) -> str:
    blob = json.dumps(canonical_payload(contract), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _rank(order: tuple, value: str) -> int:
    return order.index(value)


def _rank_or_none(order: tuple, value) -> int | None:
    """D78/2026.07.24-AGENT-RELIABILITY P2.10 route-ladder guard: `None` (never an `IndexError`/`ValueError`) when
    `value` is outside `order`. Used ONLY by `pre_mutation`'s route check below — the
    `CARRIER_PRECEDENCE` conflict-resolution use of `_rank` above is unrelated scope
    (D78/`findings/14` measured the route axes specifically) and stays untouched. An
    out-of-ladder value never crashes the predicate.  The caller distinguishes a
    malformed required route from missing actual provider evidence below."""
    return order.index(value) if value in order else None


def classify_tier(work: dict) -> str:
    """plan-portability-v1.md §Classification rule (D26) — `tier(work)`.

    `work` carries the four признаки: `sessions` (`"single"`/`"multi"`), `risk`
    (`"low"`/`"high"`), `handoff` (bool), `audit` (bool)."""
    if (work.get("sessions") == "multi" or work.get("risk") == "high"
            or work.get("handoff") or work.get("audit")):
        return "committed-bundle"
    return "brief-acceptance"


def is_external_path(path: str) -> bool:
    """task-contract-v1.md §Portability — string test over a path ALREADY known to be an
    execution input (role decided elsewhere). Not the D47 role test."""
    return path.startswith(_EXTERNAL_PREFIXES) or any(s in path for s in _EXTERNAL_SUBSTRINGS)


def portability_lint(portability: dict, *, work: dict | None = None) -> str | None:
    """plan-portability-v1.md §Classification rule + §Lint predicate — ordered check over
    an already-compiled `portability` block. Returns `None` (allow) or a typed reason code:
    `PORTABILITY_TIER_MISCLASSIFIED` (2026.07.24-AGENT-RELIABILITY P2.1, new — `artifacts/P2.1/state-transition-cases.json`
    `new_reason_codes`) · `PORTABILITY_INPUT_MISSING` / `PORTABILITY_EXTERNAL_INPUT`
    (2026.07.24-AGENT-RELIABILITY P0.2, `task-contract-v1.md` §Pre-mutation predicate #5-6, reused verbatim).

    Order, exactly as declared in plan-portability-v1.md §Classification rule:
    (1) tier contradicts the rule for the declared `work` · (2) `committed-bundle` with no
    `execution_inputs` · (3) a path listed as both execution input and provenance ·
    (4) a host-bound input · (5) a `produced-by-predecessor` input without a producer."""
    tier = portability["tier"]
    if work is not None and classify_tier(work) != tier:
        return "PORTABILITY_TIER_MISCLASSIFIED"

    execution_inputs = portability["execution_inputs"]
    if tier == "committed-bundle" and not execution_inputs:
        return "PORTABILITY_INPUT_MISSING"

    provenance_only = set(portability["provenance_only"])
    for entry in execution_inputs:
        path = entry["path"]
        if path in provenance_only:
            return "PORTABILITY_TIER_MISCLASSIFIED"
        if is_external_path(path):
            return "PORTABILITY_EXTERNAL_INPUT"
        if entry["kind"] == "produced-by-predecessor" and not entry["producer"]:
            return "PORTABILITY_INPUT_MISSING"

    return None


def pre_mutation(contract: dict, *, work: dict | None = None) -> str | None:
    """task-contract-v1.md §Pre-mutation predicate — ordered, first failure wins.
    Returns `None` (allow) or a typed reason code.

    `work` — optional признаки for the portability tier-classification sub-check (rank
    5-6 of the frozen table); omitted when the contract's own declared tier is trusted
    as-is (e.g. re-checking an already-classified contract)."""
    if contract["version"]["content_hash"] != content_hash(contract):
        return "VERSION_HASH_MISMATCH"

    for conflict in contract["conflicts"]:
        if conflict["resolution"] == "unknown":
            return "CONFLICT_UNRESOLVED"
    for conflict in contract["conflicts"]:
        winner = _rank(CARRIER_PRECEDENCE, conflict["winner"]["carrier_class"])
        loser = _rank(CARRIER_PRECEDENCE, conflict["loser"]["carrier_class"])
        if winner >= loser:
            return "CONFLICT_PRECEDENCE_VIOLATION"

    nxt = contract["next"]
    if nxt["origin"] == "diagnostic":
        return "NEXT_CHANGED_WITHOUT_TRANSITION"
    if nxt["origin"] == "typed-finding" and nxt["changed_by"] is None:
        return "NEXT_CHANGED_WITHOUT_TRANSITION"
    if nxt["origin"] == "approved-goal" and nxt["changed_by"] is not None:
        return "NEXT_CHANGED_WITHOUT_TRANSITION"

    portability_code = portability_lint(contract["portability"], work=work)
    if portability_code:
        return portability_code

    route = contract["route"]
    required_class_rank = _rank_or_none(MODEL_CLASS_ORDER, route["required"]["model_class"])
    actual_class_rank = _rank_or_none(MODEL_CLASS_ORDER, route["actual"]["model_class"])
    if required_class_rank is None:
        return "ROUTE_UNDERSHOOT"
    if actual_class_rank is None:
        return "ROUTE-UNVERIFIABLE"
    if actual_class_rank < required_class_rank:
        return "ROUTE_UNDERSHOOT"
    required_effort_rank = _rank_or_none(EFFORT_ORDER, route["required"]["effort"])
    actual_effort_rank = _rank_or_none(EFFORT_ORDER, route["actual"]["effort"])
    if required_effort_rank is None:
        return "ROUTE_UNDERSHOOT"
    if actual_effort_rank is None:
        return "ROUTE-UNVERIFIABLE"
    if actual_effort_rank < required_effort_rank:
        return "ROUTE_UNDERSHOOT"
    for capability in route["capabilities"]:
        if capability["support"] not in ("native", "adapted"):
            return "CAPABILITY_UNSUPPORTED"

    authority = contract["authority"]
    # `audit_rounds_max` is the total audit budget, not the number of repairs that
    # may follow it.  Once the final allowed audit has been observed there is no
    # remaining repair round: GREEN proceeds to phase close, while non-GREEN is an
    # incident/owner decision.  Using `>` here admitted one extra repair and a
    # third audit despite the declared two-audit cap.
    if (authority["observed_rounds"] >= authority["loop_budget"]["audit_rounds_max"]
            and not authority.get("audit_cap_remediation", False)):
        return "LOOP_BUDGET_EXCEEDED"
    if authority["class"] == "owner-gate" and not authority["granted"]:
        return "AUTHORITY_BOUNDARY"

    subagent = set(contract["slice"]["subagent_keys"])
    root_only = set(contract["slice"]["root_only_keys"])
    if subagent & root_only:
        return "SLICE_INCOMPLETE"
    if subagent | root_only != SLICE_PARTITION_KEYS:
        return "SLICE_INCOMPLETE"
    if not SLICE_SUBAGENT_REQUIRED <= subagent:
        return "SLICE_INCOMPLETE"
    if not SLICE_ROOT_ONLY_REQUIRED <= root_only:
        return "SLICE_INCOMPLETE"

    evidence_ids = {item["id"] for item in contract["evidence"]}
    cold_start = contract["cold_start"]
    if not set(cold_start["reads"]) <= evidence_ids:
        return "COLD_START_INCOMPLETE"
    if cold_start["carrier"] != nxt["carrier"]:
        return "COLD_START_INCOMPLETE"

    return None


def pre_final(contract: dict) -> str | None:
    """task-contract-v1.md §Pre-final predicate — ordered, first failure wins.
    Returns `None` (allow) or a typed reason code. Caller is responsible for the `n/a`
    branch (task-contract-v1.md: evaluated only when pre-mutation allowed)."""
    acceptance = contract["done"]["public_acceptance"]
    if not any(entry["scope"] == "public" for entry in acceptance):
        return "ACCEPTANCE_NOT_PUBLIC"

    by_id = {item["id"]: item for item in contract["evidence"]}
    for entry in acceptance:
        if entry["evidence_ref"] not in by_id:
            return "EVIDENCE_REF_UNKNOWN"

    for entry in acceptance:
        if entry["scope"] != "public":
            continue
        proof_class = by_id[entry["evidence_ref"]]["proof_class"]
        if proof_class not in DETERMINISTIC_PROOF_CLASSES:
            return "EVIDENCE_PROOF_CLASS_INSUFFICIENT"

    return None


def evaluate(contract: dict, *, work: dict | None = None) -> dict:
    """Run both boundaries in the canonical order and return a compact typed result —
    the shape a plan command reports verbatim (journal/handoff/subagent slice, 2026.07.24-AGENT-RELIABILITY P2.2
    Code Guidance): `{"pre_mutation": "allow"|"block:<CODE>", "pre_final":
    "allow"|"block:<CODE>"|"n/a", "content_hash": <sha256>}`."""
    mutation_code = pre_mutation(contract, work=work)
    if mutation_code is None:
        final_code = pre_final(contract)
        final = "allow" if final_code is None else f"block:{final_code}"
    else:
        final = "n/a"
    return {
        "pre_mutation": "allow" if mutation_code is None else f"block:{mutation_code}",
        "pre_final": final,
        "content_hash": content_hash(contract),
    }


# --------------------------------------------------------------------------
# CLI — `python3 -m task.task_contract check --contract <path> [--work <path>]`
#     · `python3 -m task.task_contract build --plan-dir <dir> --item <Pn.m>`
# --------------------------------------------------------------------------

def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Task Contract v1 compiler — evaluate pre-mutation/pre-final.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", help="evaluate a compiled contract JSON file")
    check.add_argument("--contract", required=True, help="path to a Task Contract v1 JSON payload")
    check.add_argument("--work", default=None,
                       help="optional JSON {sessions,risk,handoff,audit} for the portability "
                            "tier-classification sub-check")
    build_cmd = sub.add_parser("build", help="compile one item's Task Contract v1 JSON")
    build_cmd.add_argument("--plan-dir", required=True, help="plans/<PLAN-ID>")
    build_cmd.add_argument("--item", required=True, help="Pn.m")
    args = parser.parse_args(argv)

    if args.cmd == "build":
        contract = build(args.plan_dir, args.item)
        print(json.dumps(contract, ensure_ascii=False, sort_keys=True))
        return 0

    if args.cmd != "check":  # pragma: no cover - argparse already gates choices
        return 1
    contract = _load_json(args.contract)
    work = _load_json(args.work) if args.work else None
    result = evaluate(contract, work=work)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["pre_mutation"] == "allow" else 1



# --------------------------------------------------------------------------
# Review/loop-budget policy hook (2026.07.24-AGENT-RELIABILITY P2.3) — the one extension point
# `root/contracts/risk-review-loop-budget-v1.md`'s Contribution gate names:
# this compiler owns the pre-mutation/pre-final boundaries above and nothing
# about what happens to an item BETWEEN them when a typed finding is raised
# against it. `task.review_policy` owns that lifecycle; this function is the
# only place this module knows the module exists — a lazy import, so
# `pre_mutation`/`pre_final`/`evaluate` above stay untouched and this
# compiler's own test suite never needs `review_policy` importable.
# --------------------------------------------------------------------------

def evaluate_finding(state: str, finding: dict, *, budget=None, profile: str) -> dict:
    """Delegates one `typed-finding` event to `task.review_policy.review_transition`
    (2026.07.24-AGENT-RELIABILITY P2.3). `budget` defaults to a fresh `LoopBudget` when the caller tracks no
    cross-finding state of its own; passing the same `LoopBudget` across calls is
    what lets `same_finding_max` count occurrences across an item's fix rounds."""
    from task.review_policy import LoopBudget, review_transition
    return review_transition(state, finding, budget=budget or LoopBudget(), profile=profile)


if __name__ == "__main__":
    import sys
    sys.exit(main())
