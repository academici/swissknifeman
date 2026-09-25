<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-audit.md
Canonical SHA-256: sha256:03aec4d7e720de6c50f4c10b7d2ecf8d596cca9077d8b6940e096a255be06f83
Adapter: task.cursor-command/1.0.17
-->
## Native Cursor launch-block — required only at a real user-facing boundary

This generated runtime is the Cursor provider projection. Render only the Cursor-native launch;
never copy Claude slash syntax or Codex `$ task:` as the executable invocation.

At a fresh-session boundary print `**Native Cursor command:**` and a fenced `bash` block which
explicitly pins the repository workspace, mapped model, and autonomy flags:

```bash
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps 'task:<command> <arguments>'
```

`auto` never substitutes a fixed frontier or implementation pin. Current Cursor mapping: economy=composer-2.5-fast, implementation=composer-2.5, frontier=claude-opus-5-thinking-high.

---
disable-model-invocation: true
description: "Read-only Task design or phase audit; phase audit needs owner-bound consent."
argument-hint: "<PLAN-ID> <Pn|design>"
model: opus
effort: xhigh
---
Invocation payload: `$ARGUMENTS`.

Read `runtime/plan-protocol/references/common-principles.md` and
`runtime/plan-protocol/references/review-mode.md` from the configured Task package root.
The full schema canon and snippets are on-demand references, not mandatory review context.

Audit is adversarial and read-only over product work. Read the declared assurance, the Task Contract's
sole exact executable Routing compiler result, and prior terminal evidence; compare only the changed-risk delta.
For `design`, first run `scripts/plan-work.py design-gate --plan-dir <dir>`. Require a completed
`finalize-design --finish` and audit the returned current fingerprint across every declared phase,
item, dependency and execution-sheet row. Persist the audit journal event with that fingerprint
using the existing `--fingerprint` field. A changed design input makes the verdict stale; after
correction, repeat finish and the design audit. GREEN is the only result that opens plan execution.
Before phase audit, consume one accepted, unsuperseded `audit-admission/v2` decision whose bounded
residual-risk question, target phase, material candidate fingerprint, audit run, owner-message
provenance, and scope digest all match. Foreign, stale, ambiguous, or already consumed consent does
not admit a run. Legacy `required`/`auto`/`light`, risk prose, integration seams, missing assurance,
or an agent-authored grant are advisory only. Without matching consent, preserve a bounded
recommendation and leave GREEN evidence eligible for direct close; missing or RED acceptance
returns owning repair.
Persist the runtime candidate snapshot with
a GREEN verdict. A post-GREEN mismatch is `audit-impact/v1`: gate-rebind, delta, justified full,
evidence gathering, or owner review—never bare stale/full. This classification scopes native repair
and evidence; it does not authorize another audit. Fresh deterministic evidence is reused.
Before GREEN, regenerate audit-owned carriers once, rebuild the candidate and persist
`task.plan_evidence.audit_finalization()` with the exact `phase_close_gate` admission; product
paths must remain byte-identical between the product and closure anchors.

Use `task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput(audit=True))` as advice: at most one deterministic audit-owned bookkeeping
repair is allowed. A product defect returns one exact owning continuation; it does not trigger a
second audit, full replay, product write, or fresh root merely because this command is an audit.
Material risk selects one independent review path. Persist the semantic Next through `plan_delivery`.
One consent admits one bounded run; its in-progress journal event reserves it and its terminal event
consumes it. A repeat needs a new question, candidate/run-bound consent, and material hypothesis.

Audit does not bypass terminal admission: an applicable lease can only emit `waiting-owner` or its
typed continuation until a fresh terminal receipt and exact final fragment exist.

Persist a product finding as audit-attention (or audit-red) with decision action
`return-owning-continuation`, evidence IDs, reason_code, scope_class=<owning item>,
recovered=false, terminal=false,
and exact exec-items/run-items owning continuation. Reviewer completion leaves the phase open.
