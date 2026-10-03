"""Deterministic closure digest for a terminal layout-v2 phase."""
from __future__ import annotations

import re
from pathlib import Path

from task import plan_decisions, plan_layout, plan_projection


class ClosureError(ValueError):
    """A phase closure cannot safely be generated or checked."""


_ITEM_HEADER = re.compile(r"^###\s+(P\d+\.\d+)\s+—\s+(.+?)\s*$", re.MULTILINE)
_FIELD = re.compile(r"^\*\*([^*]+):\*\*\s*(.*)$", re.MULTILINE)
_CONTRACT_START = re.compile(r"^>\s*\*\*Phase Contract", re.MULTILINE | re.IGNORECASE)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ClosureError(f"media closure is not readable: {path}") from exc


def _phase_contract(phase_path: Path) -> str:
    lines = _read(phase_path).splitlines()
    start = next((index for index, line in enumerate(lines)
                  if _CONTRACT_START.match(line)), None)
    if start is None:
        raise ClosureError(f"{phase_path}: no contract-phase block")
    block = []
    for line in lines[start:]:
        if not line.startswith(">"):
            break
        block.append(line[1:].lstrip())
    return "\n".join(block).strip()


def _item_facts(spec_path: Path) -> tuple[str, str, str, str]:
    text = _read(spec_path)
    header = _ITEM_HEADER.search(text)
    if header is None:
        raise ClosureError(f"{spec_path}: no canonical header item")
    fields = {match.group(1): match.group(2).strip() for match in _FIELD.finditer(text)}
    deliverables = fields.get("Deliverables")
    if not deliverables:
        raise ClosureError(f"{spec_path}: no Deliverables")
    state_path = spec_path.with_name(spec_path.stem + ".state.md")
    state = {match.group(1): match.group(2).strip() for match in _FIELD.finditer(_read(state_path))}
    return header.group(1), header.group(2), deliverables, state.get("Known Deviations", "—")


def render_closure(plan_dir, phase_id: str) -> str:
    """Build a deterministic digest for one declared terminal phase."""
    plan_dir = Path(plan_dir)
    if plan_layout.layout_version(plan_dir) != "v2":
        raise ClosureError("closure digest exists only for Layout v2")
    if not plan_layout.is_terminal_phase(plan_dir, phase_id):
        raise ClosureError(f"{phase_id}: closure is built only for the terminal phase")
    phase_path = plan_layout.phase_path(plan_dir, phase_id)
    contract = _phase_contract(phase_path)
    facts = [_item_facts(path) for path in plan_layout.item_spec_paths(plan_dir, phase_id)]
    if not facts:
        raise ClosureError(f"{phase_path}: has no terminal phase item-spec files")
    try:
        decisions = tuple(decision for decision in plan_decisions.load_decisions(plan_dir)
                          if any(item.startswith(f"{phase_id}.") for item in decision.items))
    except plan_decisions.DecisionError as exc:
        raise ClosureError(str(exc)) from exc
    input_paths = [phase_path]
    for item_id, _title, _deliverables, _deviations in facts:
        spec_path = plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)
        input_paths.extend((spec_path, spec_path.with_name(spec_path.stem + ".state.md")))
    input_paths.extend(decision.path for decision in decisions)
    digest = plan_projection.inputs_sha256(input_paths, root=plan_dir)
    status = plan_layout.phase_statuses(plan_dir)[phase_id]
    from task import phase_findings, plan_gates
    resolution_path = phase_findings.receipt_path(plan_dir, phase_id)
    resolution_section = None
    if resolution_path.is_file():
        candidate = plan_gates.phase_candidate_fingerprint(plan_dir, phase_id)
        proof = phase_findings.acceptance(plan_dir, phase_id, candidate["snapshot"])
        if not proof["allow"] or not phase_findings.closed_green(plan_dir, phase_id):
            raise ClosureError(f"PHASE_FINDINGS_UNRESOLVED: {proof}")
        input_paths.append(resolution_path)
        digest = plan_projection.inputs_sha256(input_paths, root=plan_dir)
        resolution_section = ("## Resolved Review Findings\n\n"
            f"Current phase acceptance: GREEN. Historical RED review/item outcomes remain unchanged.\n\n"
            f"Checked resolution: [evidence](../../closure/{resolution_path.name}), SHA-256 `{proof['sha256']}`.\n"
            f"Resolved review items: {', '.join(proof['review_items'])}.\n"
            "The Known Deviations below quote historical item results; their findings are resolved by this evidence.")
    metadata = plan_projection.metadata_block(
        projection="phase-closure", projection_version="v1", source_scope=f"phase {phase_id} + item states + decisions",
        through=f"{phase_id}: {status}", inputs_sha256_value=digest,
        generated_by="task plan-views closure")
    produced = "\n".join(f"- {item_id} — {title}: {deliverables}"
                           for item_id, title, deliverables, _deviations in facts)
    deviations = "\n".join(f"- {item_id}: {value}" for item_id, _title, _deliverables, value in facts
                             if value not in ("", "—")) or "- —"
    links = "\n".join(f"- [{decision.identifier}](../../decisions/{decision.path.name})"
                      for decision in decisions) or "- —"
    body = "\n\n".join(("## Phase Contract\n\n" + contract,
                           "## Produced\n\n" + produced,
                           "## Known Deviations\n\n" + deviations,
                           "## Solutions\n\n" + links))
    if resolution_section:
        body += "\n\n" + resolution_section
    return plan_projection.rendered_file(metadata=metadata, title=f"Closing phase {phase_id}", body=body)


def build_closure(plan_dir, phase_id: str, *, check=False) -> Path:
    """Write or freshness-check the generated closure digest."""
    plan_dir = Path(plan_dir)
    try:
        target = plan_layout.carrier_path(plan_dir, "phase-closure", phase_id=phase_id)
    except plan_layout.PlanLayoutError as exc:
        raise ClosureError(str(exc)) from exc
    try:
        plan_projection.write_or_check(target, render_closure(plan_dir, phase_id), check=check)
    except plan_projection.ProjectionError as exc:
        raise ClosureError(str(exc)) from exc
    return target
