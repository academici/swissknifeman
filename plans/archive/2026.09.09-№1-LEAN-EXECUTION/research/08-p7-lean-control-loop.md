# P7 lean Task control-loop synthesis

## Sources

- `findings/15-lean-lifecycle-overhead-2026-09-10.md`
- `findings/16-p7-design-preflight-2026-09-10.md`
- `brief/01-refinements.md` owner priority correction
- `packages/skiller/skills/repository-bootstrap/task-development-philosophy/SKILL.md`
- current Task runtime owners and canonical plan commands named below

The synthesis is repository-grounded (`RAG:—`). External testing/context guidance remains evidence
inside finding 15; P7 adds no new external fact class.

## Target lifecycle

The normal path is one bounded vertical loop:

```text
capture route/context once -> compile compact item/batch contract -> implement ->
select focused affected validation -> generate changed projections once ->
write one terminal update + one semantic Next -> one scoped commit
```

`task_contract`/`route_evidence` own admission, `plan_repair`/`plan_blocking` own failure recovery,
`plan_gates`/`review_policy` own changed-risk and review selection, `plan_projection` owns freshness,
`plan_continuity` owns actual context boundaries, and `plan_delivery` owns semantic Next plus native
rendering. A thin transient lifecycle function/CLI may compose these owners, but it must persist no
new schema or carrier and must delete more canonical command/canon bytes than it introduces.

## Change-impact matrix

| Change class | Validation | Review/context |
|:--|:--|:--|
| low-risk, package-local, high-confidence | exact focused checks only | no independent audit; continue current root if route/capacity permit |
| bounded internal integration | focused + affected package/integration seam | delta/light review only when declared by Routing |
| security/auth, destructive migration, irreversible external action, payment/accounting, concurrency/shared state, public API/schema, low-confidence impact | focused + affected package + required integration/full boundary | fail closed and select exactly one widened/independent review path |
| unrelated pre-existing fleet failure | record baseline delta, non-gating | gating only when ownership/dependency closure intersects the change |
| release/tag/deploy/consumer rollout | repository validation is insufficient authority | explicit owner gate remains mandatory |

Audit is read-only over product: it may repair at most one deterministic bookkeeping carrier owned
by the audit, but a product defect returns one exact continuation to the owning item. Fresh evidence
is reused; a second audit/full replay requires a new material hypothesis, never the audit's own
bookkeeping.

## Projection and delivery ownership

At the terminal boundary, compare declared projection inputs and build only changed state/status/
decision/bundle/closure outputs, once, in owner order. The command records one provider-neutral
semantic Next; `plan_delivery` validates and renders the active provider command. Route/session
evidence is captured once at admission and reused until `route_change_boundary()` proves change.
One product/bookkeeping commit is normal; a second commit is reserved for a real session or
ownership boundary.

## Retired overlap and stop conditions

- P3.3's proposed `validation-receipt/v2` and repeat-full schemas are deleted from the executable
  plan; P7 selects validation from current typed impact/evidence without another durable receipt.
- P6.1–P6.4 are deleted from the executable plan; their research remains historical evidence, not
  a prerequisite for simplifying the already measured Task commands.
- P3.4 consumes P7's lifecycle outcome and retains only distinct evidence-topology work.
- Stop when canonical five-command + plan-protocol bytes are `<= 105795`, low-risk and hard-risk
  fixtures pass, provider projections are regenerated from canonical inputs, Task/Skiller/docs
  gates are green, and no parallel lifecycle carrier exists.
