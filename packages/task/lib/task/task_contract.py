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


def _count_audit_rounds(phase_lines, phase_id: str) -> int:
    """`authority.observed_rounds` — the audit-round cap counter
    (`risk-review-loop-budget-v1.md` §Loop budget, `audit_rounds_max`),
    reconstructed by counting `## Audit <phase_id>` block headers already
    committed in the phase file — the exact grep `plan-audit.md:52-54`'s own
    canon already performs, never a second parser. Distinct from
    `review_policy.LoopBudget.from_committed` (per-finding, not phase-level) —
    see `findings/P2.6-contract-mapping.md`."""
    count = 0
    for ln in phase_lines:
        m = _AUDIT_BLOCK_HEADER_RE.match(ln.strip())
        if m and m.group(1) == phase_id:
            count += 1
    return count


# D78/2026.07.24-AGENT-RELIABILITY P2.10 — closed literal set of §3 Routing route-column headers `plan-protocol` §9
# Back-compat declares VALID today: the canon form plus exactly the two legacy spellings
# measured live on the fleet (`findings/14` M4.1). Preference order matters (canon first);
# no fuzzy/normalized/regex match — a header outside this tuple is an unrecognized table,
# never a guess (Implementation Rules (2)).
_ROUTING_HEADER_CANON = "Model class/effort"
_ROUTING_HEADER_CANDIDATES = (_ROUTING_HEADER_CANON, "Model/effort", "Model/Effort")

# Default location of the committed provider routing carrier this module reads
# `mappings.*.class_selectors` from (D78 Implementation Rules (1) — one name-to-class
# carrier, never a second table in this module). Package-relative, same convention
# `command_render.mapping_from_catalog` already uses for its own sibling config
# (`Path(__file__).resolve().parents[N] / "configs/..."`) — never cwd/env discovery
# (`command_catalog`'s own module docstring bans that for the loader this calls).
_DEFAULT_ROUTING_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "command-routing.json"


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
         authority_class="routine", authority_granted=True,
         authority_granted_by="D50 (G-EXEC for self-host P0-P3)",
         next_form="exec-items", next_context="same-session — item",
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

    `routing_config_path` (2026.07.24-AGENT-RELIABILITY P2.10, D78) — the committed routing carrier
    `_find_routing_row`/`_resolve_model_class` read `mappings.*.class_selectors` from,
    via `command_catalog.load_routing_metadata` (never a second name table in this
    module). Defaults to this package's own `configs/command-routing.json`
    (`_DEFAULT_ROUTING_CONFIG_PATH`, derived from `__file__` — the same
    package-relative convention `command_render.mapping_from_catalog` already uses for
    its sibling config); a caller MAY override it, but never supplies cwd/env instead.
    """
    from task import plan_lint  # lazy — avoids a plan_lint↔task_contract circular import
    from task import route_evidence  # lazy — same reasoning, route assembly only
    from task import review_policy  # lazy — reuse of loop_budget constants only
    from task import command_catalog  # lazy — same reasoning, class_selectors carrier only

    plan_dir = Path(plan_dir)
    phase_token = item_id.split(".")[0]
    diag = plan_lint.Diagnostics()
    plan_lint.parse_plan_md(plan_dir / "plan.md", diag)  # populates diag only; not consulted here
    phase_path = plan_dir / "phases" / f"{phase_token}.md"
    phase = plan_lint.parse_phase_md(phase_path, phase_token, diag)
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
    routing = _find_routing_row(plan_lint, plan_lines, item_id, routing_metadata)
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
    observed_rounds = _count_audit_rounds(phase_lines, phase_token)

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
    out-of-ladder value on EITHER axis and EITHER side of the route (required or
    actual) is treated the same way `route_evidence.classify` already treats an
    unresolved actual — as an undershoot, never a crash — reusing the frozen
    `ROUTE_UNDERSHOOT` code rather than minting a new one (2026.07.24-AGENT-RELIABILITY P0.2 pre-mutation codes are
    frozen; D74 already established this precedent one layer up, in
    `route_evidence.dispatch_guard`)."""
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
    if (required_class_rank is None or actual_class_rank is None
            or actual_class_rank < required_class_rank):
        return "ROUTE_UNDERSHOOT"
    required_effort_rank = _rank_or_none(EFFORT_ORDER, route["required"]["effort"])
    actual_effort_rank = _rank_or_none(EFFORT_ORDER, route["actual"]["effort"])
    if (required_effort_rank is None or actual_effort_rank is None
            or actual_effort_rank < required_effort_rank):
        return "ROUTE_UNDERSHOOT"
    for capability in route["capabilities"]:
        if capability["support"] not in ("native", "adapted"):
            return "CAPABILITY_UNSUPPORTED"

    authority = contract["authority"]
    if authority["observed_rounds"] > authority["loop_budget"]["audit_rounds_max"]:
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
