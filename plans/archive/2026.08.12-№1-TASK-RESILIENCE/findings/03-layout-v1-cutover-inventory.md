---
item: P1.1
date: 2026-08-12
file: phases/P1/P1.1.md
rule_or_contract_locus: task-contract-v1 pre-final public acceptance
defect_class: acceptance-failure
gate: return-loop-v1
qualification: unqualifiable
missing_carrier_reason: terminal return fingerprint does not exist before the required pre-escalation evidence write
---
# Layout v1 cutover inventory — 2026-08-12

## Verdict

The registered fleet is not ready for Layout v1 reader removal. The generated inventory contains
active v1 migration targets and fail-closed blockers; P1.2 must migrate the ordered `v1-active`
set, while P1.3 must not remove the reader until every `invalid` entry is repaired, every
`unreachable` registered root becomes reachable and classified, and a fresh inventory proves zero
live v1 consumers.

Machine-readable evidence and the exact migration order are in
`../artifacts/P1/active-layout-inventory-v1.json`. Validate the committed snapshot with:

```bash
python3 plans/2026.08.12-№1-TASK-RESILIENCE/artifacts/P1/validate-active-layout-inventory.py
```

The producer-only materialization form is the same command with `--write`; it must be followed by
the validation form above and review of the resulting diff.

## Inventory boundary

- Authorities: the current repository, worktree-local `packages/skiller/bin/skiller list`, and
  worktree-local `packages/maind/bin/maind projects list --json`.
- Dedupe key: resolved absolute project path. Duplicate registry rows remain represented through
  each root's `sources`, but a root is scanned once.
- Executable candidates: only direct `plans/<ID>/plan.md` children of a registered root.
- Archive candidates: descendants below a direct `plans/archive` or `plans/archives` container;
  they are recorded as inert history and never enter `migration_order`.
- Symlink boundary: a symlinked candidate or plans directory, or a path resolving outside its
  registered root, is `invalid`; the scanner does not traverse it.
- Layout verdict: the current `task.plan_layout` resolver checks declaration/tree agreement;
  legacy v1 additionally must carry at least one `phases/Pn.md` file.

## Cutover blockers

- `unreachable`: stale mAInd registry paths under temporary directories. They must be made
  reachable and classified or removed from the authoritative registry before P1.3.
- `invalid`: `dterema/plans/2026.07.24-LEAD-FORMS-AND-CTA` and
  `vaulter/plans/VLT-MUT` declare legacy-by-absence but have no legacy phase carrier. The latter
  also matches its repository's exact `Active` identifier; it is therefore a live fail-closed
  blocker rather than an archive inference. The corex root's archived `COREX-CORE` entry is a
  symlink; the scanner preserves that lexical path, records it as invalid and does not traverse it.
- `v1-active`: migrate strictly in the artifact's sorted `migration_order`; do not infer priority
  from filesystem enumeration or registry duplication.

## Evidence integrity notes

- The initial documented preflight form `maind health --cwd <path>` is incompatible with the
  current CLI, whose `--cwd` is boolean. `packages/maind/bin/maind health` resolved the current
  repository and completed green; the failed invocation was not counted as green.
- В предыдущем attempt `codex doctor --json` не дал observable terminal result; в repair-заходе
  2026-08-12 команда завершилась `overallStatus=ok`, поэтом дефект больше не влияет
  на validation trust.
- The registered skill catalog pointed at removed Task cache `0.11.1`; canonical worktree content
  and installed cache `0.12.0` exist. Execution used the canonical worktree projection.
- Current journal helpers require keyword-only `derive_run_id` arguments, and `plan-views state`
  requires an explicit item selector. The plan-run projection examples omit those details; the
  failed local calls were repaired and recorded as nonterminal `local-repair` evidence.
- P1.1 pre-final returned `block:ACCEPTANCE_NOT_PUBLIC`: the compiler treated the sole Validation
  clause as internal because its JSON check redirects to `>/dev/null`. A fresh isolated reviewer
  returned `JUSTIFIED`; `task.plan_blocking.evaluate()` returned `terminal-block` with
  `BLOCK_CONFIRMED`. This finding records pre-escalation return evidence as `unqualifiable` because
  the journal-derived terminal fingerprint does not exist until after the terminal event.
- D13 устранила этот acceptance-only дефект: JSON-команда сохранена, но больше не
  подавляет stdout. `task_contract.evaluate()` после регенерации bundle вернул
  `pre_mutation=allow` и `pre_final=allow` на provider-thread-state route `frontier/high`.
- Первый validation repair-заход зафиксировал дрейф fleet snapshot: в registered Agelto plan
  появился новый generated `P6.closed.md`, а текущий plan получил repair carriers. Это
  локальный snapshot drift; inventory пересобирается owning-скриптом и исходная
  Validation повторяется.

## Provenance

The retirement ordering is governed by D7. External rationale is not re-derived here; the
verified source synthesis and official URLs remain in
`02-rag-resilience-and-schema-cutover-2026-08-12.md`.
