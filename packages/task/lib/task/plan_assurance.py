"""Phase assurance and post-audit impact policy.

This module is intentionally the single policy owner for ``phase-assurance/v1``
and ``audit-impact/v1``.  It accepts only a candidate rebuilt by Task (or a test
fixture with the same shape); commands and close gates do not make independent
risk decisions from Routing review depth, item count, or a bare hash mismatch.
"""
from __future__ import annotations

import re
from pathlib import Path

from task import plan_status


IMPACTS = frozenset(("isolated", "internal-integration", "public-contract", "security-external"))
AUDIT_INTENTS = frozenset(("auto", "required", "direct-close-eligible", "legacy-light"))
IMPACT_CLASSES = frozenset((
    "unrelated-worktree", "audit-bookkeeping", "local-material", "wide-material",
    "unclassifiable",
))
_HEADER = "> **Phase Assurance | v1.**"
_FIELD_RE = re.compile(r"^>\s*(Impact|Integration Seams|Live or Irreversible|Audit Intent|Rationale):\s*(.*?)\s*$")
_SEAM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_NO_BASELINE = object()
_LEGACY_AUDIT_INTENT_NORMALIZATIONS = {"light": "legacy-light"}
_LEGACY_LIVE_NORMALIZATIONS = {"none; repository edits are reversible": "no"}


class AssuranceError(ValueError):
    """A named refusal that can be rendered by lint and close unchanged."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def parse(text: str) -> dict:
    """Parse exactly one handwritten Phase Assurance block from phase Markdown."""
    if not isinstance(text, str):
        raise AssuranceError("PHASE_ASSURANCE_INVALID", "carrier must be text")
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == _HEADER]
    if not starts:
        raise AssuranceError("PHASE_ASSURANCE_MISSING", "missing `Phase Assurance | v1`")
    if len(starts) != 1:
        raise AssuranceError("PHASE_ASSURANCE_DUPLICATE", "Phase Assurance | v1 declared more than once")
    values: dict[str, str] = {}
    for line in lines[starts[0] + 1:]:
        if not line.startswith(">"):
            break
        match = _FIELD_RE.fullmatch(line)
        if match is None:
            continue
        key, value = match.groups()
        if key in values:
            raise AssuranceError("PHASE_ASSURANCE_DUPLICATE_FIELD", f"field {key!r} repeated")
        values[key] = value.strip()
    required = ("Impact", "Integration Seams", "Live or Irreversible", "Audit Intent", "Rationale")
    missing = [field for field in required if field not in values]
    if missing:
        raise AssuranceError("PHASE_ASSURANCE_FIELD_MISSING", f"missing fields: {', '.join(missing)}")
    impact = values["Impact"]
    intent = _LEGACY_AUDIT_INTENT_NORMALIZATIONS.get(values["Audit Intent"], values["Audit Intent"])
    if impact not in IMPACTS:
        raise AssuranceError("PHASE_ASSURANCE_IMPACT_INVALID", f"Impact {impact!r} outside closed enum")
    if intent not in AUDIT_INTENTS:
        raise AssuranceError("PHASE_ASSURANCE_INTENT_INVALID", f"Audit Intent {intent!r} outside closed enum")
    live = _LEGACY_LIVE_NORMALIZATIONS.get(
        values["Live or Irreversible"], values["Live or Irreversible"])
    if live not in {"yes", "no"}:
        raise AssuranceError("PHASE_ASSURANCE_LIVE_INVALID", "Live or Irreversible awaits yes/no")
    raw_seams = values["Integration Seams"]
    seams = () if raw_seams == "—" else tuple(part.strip(" `") for part in raw_seams.split("·"))
    if any(not seam or not _SEAM_RE.fullmatch(seam) for seam in seams):
        raise AssuranceError("PHASE_ASSURANCE_SEAMS_INVALID", "Integration Seams awaits `—` or stable seam-id")
    if len(set(seams)) != len(seams):
        raise AssuranceError("PHASE_ASSURANCE_SEAMS_DUPLICATE", "Integration Seams should not be repeated")
    rationale = values["Rationale"]
    if not rationale or rationale == "—":
        raise AssuranceError("PHASE_ASSURANCE_RATIONALE_REQUIRED", "Rationale required")
    return {
        "schema_version": "phase-assurance/v1",
        "impact": impact,
        "integration_seams": seams,
        "live_or_irreversible": live == "yes",
        "audit_intent": intent,
        "rationale": rationale,
    }


def read(plan_dir: Path | str, phase_id: str) -> dict:
    path = Path(plan_dir) / "phases" / phase_id / f"{phase_id}.md"
    try:
        return parse(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AssuranceError("PHASE_ASSURANCE_CARRIER_MISSING", str(path)) from exc


def _decision(*, plan_dir: Path, phase_id: str, action: str, code: str,
              reasons: list[str], assurance: dict | None = None,
              impact: dict | None = None, audit_required: bool = False,
              close_allowed: bool = False, admission: dict | None = None,
              diagnostics: list[str] | None = None) -> dict:
    command = {
        "direct-close": "task:plan-close",
        "audit-required": "task:plan-audit",
        "gate-rebind": "task:plan-close",
        "delta": "task:plan-audit",
        "full": "task:plan-audit",
        "gather-evidence": "task:plan-close",
        "owning-repair": "task:plan-close",
        "owner-review": "task:plan-close",
    }[action]
    kind = "audit-phase" if audit_required else "close"
    return {
        "action": action,
        "audit_required": audit_required,
        "close_allowed": close_allowed,
        "code": code,
        "reasons": reasons,
        "assurance": assurance,
        "impact": impact,
        "audit_admission": admission,
        "diagnostics": diagnostics or [],
        "next_kind": kind,
        "next_exact": f"{kind}: {command} {plan_dir.name} {phase_id}",
    }


def classify_impact(*, baseline: dict | None, candidate: dict | None,
                    second_full_justification: dict | None = None) -> dict:
    """Return the complete `audit-impact/v1` classification, never a hash shortcut."""
    if not isinstance(candidate, dict):
        return _impact("unclassifiable", (), (), ("candidate-snapshot-missing",), "owner-review")
    if not isinstance(baseline, dict):
        return _impact("unclassifiable", (), (), ("trusted-baseline-missing",), "gather-evidence")
    required = {"phase_id", "terminal_item_heads", "declared_files", "product_tree_sha256"}
    if not required <= set(candidate) or not required <= set(baseline):
        return _impact("unclassifiable", (), (), ("candidate-snapshot-incomplete",), "owner-review")
    if candidate["phase_id"] != baseline["phase_id"]:
        return _impact("unclassifiable", (), (), ("phase-identity-changed",), "owner-review")
    material_fields = ("terminal_item_heads", "declared_files", "product_tree_sha256", "material_risks")
    changed = [field for field in material_fields if baseline.get(field) != candidate.get(field)]
    if not changed:
        return _impact("audit-bookkeeping", (), (), ("material-snapshot-unchanged",), "gate-rebind")
    before_heads = {row.get("item_id"): row for row in baseline.get("terminal_item_heads", []) if isinstance(row, dict)}
    after_heads = {row.get("item_id"): row for row in candidate.get("terminal_item_heads", []) if isinstance(row, dict)}
    affected = tuple(sorted(item for item in set(before_heads) | set(after_heads)
                            if before_heads.get(item) != after_heads.get(item)))
    if not affected and "product_tree_sha256" in changed:
        affected = tuple(sorted(after_heads))
    if not affected:
        return _impact("unclassifiable", (), (), tuple(f"changed:{field}" for field in changed), "owner-review")
    # A solitary proven product carrier is a bounded local delta, not a reason
    # to infer a second full audit.  Broadness begins only when multiple item
    # heads are affected (or a mandatory material surface says so).
    wide = ((len(affected) > 1 and len(affected) * 2 > max(len(after_heads), 1))
            or any(risk in {"public", "security", "live", "irreversible", "frozen"}
                   for risk in candidate.get("material_risks", [])))
    if wide:
        valid_second_full = isinstance(second_full_justification, dict) and bool(second_full_justification.get("reason"))
        return _impact("wide-material", affected, (), tuple(f"changed:{field}" for field in changed),
                       "full" if valid_second_full else "owner-review")
    return _impact("local-material", affected, (), tuple(f"changed:{field}" for field in changed), "delta")


def _impact(classification: str, affected_items: tuple[str, ...], affected_edges: tuple[str, ...],
            reasons: tuple[str, ...], continuation: str) -> dict:
    return {
        "schema_version": "audit-impact/v1",
        "classification": classification,
        "affected_items": list(affected_items),
        "affected_edges": list(affected_edges),
        "reasons": list(reasons),
        "continuation": continuation,
    }


def evaluate(plan_dir: Path | str, phase_id: str, *, candidate: dict | None,
             baseline: dict | None | object = _NO_BASELINE,
             second_full_justification: dict | None = None) -> dict:
    """Separate sufficient acceptance from an explicitly consented extra audit."""
    plan_dir = Path(plan_dir)
    diagnostics = []
    try:
        assurance = read(plan_dir, phase_id)
    except AssuranceError as exc:
        if exc.code == "PHASE_ASSURANCE_MISSING":
            assurance = {
                "schema_version": "phase-assurance/implicit-v1",
                "impact": "isolated",
                "integration_seams": (),
                "live_or_irreversible": False,
                "audit_intent": "direct-close-eligible",
                "rationale": "implicit isolated/reversible default",
            }
        else:
            assurance = None
            diagnostics.append(f"{exc.code}: Phase Assurance advisory; fix explicitly declared block")
    if assurance and assurance["audit_intent"] in {"required", "legacy-light", "auto"}:
        diagnostics.append("PHASE_AUDIT_INTENT_ADVISORY: legacy Audit Intent does not assign audit; default direct-close")
    heads = candidate.get("terminal_item_heads") if isinstance(candidate, dict) else None
    risks = candidate.get("material_risks") if isinstance(candidate, dict) else None
    if (not isinstance(candidate, dict) or candidate.get("phase_id") != phase_id
            or not isinstance(heads, list) or not heads or not isinstance(risks, list)
            or not all(isinstance(risk, str) for risk in risks)
            or not isinstance(candidate.get("declared_files"), list)
            or not isinstance(candidate.get("scope"), list)
            or not re.fullmatch(r"[0-9a-f]{64}", str(candidate.get("product_tree_sha256", "")))
            or any(not isinstance(row, dict) or not re.fullmatch(
                rf"{re.escape(phase_id)}\.\d+", str(row.get("item_id", ""))) for row in heads)
            or len({row["item_id"] for row in heads if isinstance(row, dict)}) != len(heads)):
        return _decision(plan_dir=plan_dir, phase_id=phase_id, action="gather-evidence",
                         code="PHASE_ASSURANCE_CANDIDATE_UNRESOLVED",
                         reasons=["runtime-candidate-unresolved"], assurance=assurance,
                         diagnostics=diagnostics)
    statuses = [row.get("status") for row in heads if isinstance(row, dict)]
    if len(statuses) != len(heads) or any(status != plan_status.STATUS_DONE for status in statuses):
        result = _decision(plan_dir=plan_dir, phase_id=phase_id, action="owning-repair",
                           code="PHASE_ACCEPTANCE_NON_GREEN", reasons=["non-green-terminal-item"],
                           assurance=assurance, diagnostics=diagnostics)
        item = next((row.get("item_id") for row in heads if isinstance(row, dict)
                     and row.get("status") != plan_status.STATUS_DONE), None)
        if isinstance(item, str) and re.fullmatch(rf"{re.escape(phase_id)}\.\d+", item):
            result.update(next_kind="run-items", next_exact=f"run-items: task:plan-run {plan_dir.name} {item}")
        return result
    impact = None
    if baseline is not _NO_BASELINE:
        impact = classify_impact(baseline=baseline, candidate=candidate,
                                 second_full_justification=second_full_justification)
    from task import audit_admission
    admission = audit_admission.evaluate(plan_dir, phase_id, candidate)
    if admission["allowed"]:
        return _decision(plan_dir=plan_dir, phase_id=phase_id, action="audit-required",
                         code="PHASE_AUDIT_OWNER_APPROVED",
                         reasons=[risk["bounded_question"] for risk in admission["record"]["residual_risks"]],
                         assurance=assurance, impact=impact, admission=admission,
                         audit_required=True, diagnostics=diagnostics)
    if risks:
        diagnostics.append("AUDIT_RECOMMENDATION: clarify the open question and address consent; material-risk does not assign itself audit")
    action = "gate-rebind" if impact and impact["classification"] == "audit-bookkeeping" else "direct-close"
    return _decision(plan_dir=plan_dir, phase_id=phase_id, action=action,
                     code="PHASE_DIRECT_CLOSE_ASSURED", reasons=["green-acceptance-no-approved-audit"],
                     assurance=assurance, impact=impact, admission=admission,
                     close_allowed=True, diagnostics=diagnostics)
