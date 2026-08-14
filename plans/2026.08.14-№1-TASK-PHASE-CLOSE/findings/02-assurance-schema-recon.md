# Recon — Phase Assurance schema and publication surface

**Источник:** read-only repository research, 2026-08-14.
**Evidence:** RAG:— (repo-grounded).

## Canonical payload

Handwritten block живёт в `## Phase Context`:

```text
> **Phase Assurance | v1.**
> Impact: isolated | internal-integration | public-contract | security-external
> Integration Seams: — | `<stable-seam-id>` · ...
> Live or Irreversible: no | yes
> Audit Intent: auto | required | direct-close-eligible
> Rationale: <nonblank checkable reason>
```

Нормализованный object: `schema_version`, `impact`, unique sorted `integration_seams`,
boolean `live_or_irreversible`, `audit_intent`, normalized nonblank `rationale`.

## Validation and compatibility

- Exactly one block, five exact ordered fields; duplicate/missing/unknown field, bad enum,
  blank rationale и malformed/duplicate seam id — typed Russian diagnostic.
- `direct-close-eligible` валиден только при `isolated`, пустых seams и `no`.
- Missing legacy block остаётся readable, но не даёт unaudited direct close.
- Matching GREEN audit имеет силу даже для legacy phase без assurance.

## Owner and generated surfaces

- Tiny stdlib owner: `packages/task/lib/task/phase_assurance.py`; он не импортирует
  gates/lint/policy. `plan_gates.py` и `plan_lint_checks/parsing.py` только потребляют его.
- Canonical command sources: `packages/task/commands/{plan-design,plan-audit,plan-close,plan-exec}.md`.
- Canon: `packages/skiller/skills/general/plan-protocol/{SKILL.md,references/plan-layout-v2.md,snippets/phase-template.md}`.
- Provider artifacts регенерируются `render-provider-commands.py`; registry projections —
  worktree-local `packages/skiller/bin/skiller registry`; aggregate docs — `scripts/docs-sync.sh`.
