# Post-D74 audit remediation and producer→consumer reconcile

## Sources and boundary

- `brief/09-post-d74-audit-remediation.md` — exact owner scope and anti-scope.
- `plan.md` → latest `## Audit design — 2026-08-04` — F1–F3 and required verification.
- `research/20-p3.4-successor-contract-design.md` and D74 — frozen successor objective.
- Current P1.6, P2.6, P3.4, P4.1–P4.5 and P5.1 specifications — executable carrier graph.

This synthesis is plan-only. It changes no terminal item record, frozen contract byte, product,
package, provider, fleet, Brain, generated, documentation or release state. RAG:— (repo-grounded:
the named plan carriers and current worktree).

## F1 — concrete admission ownership

The grant and admission are deliberately different objects:

| Carrier | Producer | Meaning | Consumer |
|:--|:--|:--|:--|
| `artifacts/P1/p3-smoke-dispatch-grant-v1.json` | P1.6 | D74-bounded maxima, allowlists and scope; no concrete run/slice/attempt/replay usage | P2.6 admission builder and validators |
| `artifacts/P2/p3-smoke-slice-manifest-v1.json` | P2.6 | terminal P3.4 slice identity and frozen execution inputs | P2.6 admission builder |
| `artifacts/P2/p3-smoke-replay-v1.jsonl` | P2.6 | strict durable tail and replay-derived usage for the concrete smoke attempt | P2.6 admission builder and dispatch verifier |
| `artifacts/P2/p3-smoke-dispatch-admission-v1.json` | P2.6 | concrete manifest+grant+replay projection with plan/item/run/slice/attempt/idempotency identities and hashes | P2.6 `dispatch`, P3.4 smoke, P4 assurance, P5 lineage |

P2.6 is the sole instance producer because only that item has terminal compiler/store/replay
semantics. P1.6 remains the schema/grant producer. The exact builder is
`artifacts/P2/build-p3-smoke-admission.py --manifest … --grant … --replay … --output …`; it accepts
explicit paths only. `dispatch --run-id p3-smoke-v1 --admission …` consumes the resulting carrier.
Passing the grant path as admission must return `ADMISSION_SCHEMA_INVALID` before durable intent or
provider activity. This preserves D74: P3 still cannot mint authority or budget values. RAG:—
(repo-grounded: audit F1, D74 and the repaired P1.6/P2.6/P3.4 specifications).

## F2 — assurance and trial propagation

| Producer | Consumer obligation | Exact closure |
|:--|:--|:--|
| P1.6 six-contract set and grant | P4.1 | reads contract/cases/validator/grant; freezes grant≠admission, stale replay/usage and pre/post admission/intent/activity rows |
| P2.6 admission plus `dispatch.py`/`test_dispatch.py` | P4.2 | owns crash/reconcile repairs in `dispatch.py`; verifies no stale/grant-shaped admission can append intent or rerun activity |
| P1.6/P2.6/P3.4 security boundary | P4.4 | includes `dispatch.py`/`test_dispatch.py`; attacks identity/hash/scope/provider/route/tool/validation/budget/usage widening and grant substitution |
| P4.1–P4.4 evidence | P4.5 | aggregate assurance refuses missing admission/dispatch rows or grant/admission conflation |
| P4.5 assurance plus P1/P2 lineage | P5.1 | consumes exactly six contracts and the P2 admission hash through admission-aware P4 assurance; the smoke grant is never a business admission |

The P4 phase contract now names the concrete admission and six-contract cases, and the P5 phase
contract names the terminal six-contract set. P4.1, P4.2, P4.4, P4.5 and P5.1 carry exact paths and
deterministic validators rather than relying only on aggregate hashes. RAG:— (repo-grounded: audit
F2 and repaired phase specifications).

## Full producer→consumer order

The executable order remains 34 items and does not reopen another historical item:

`P1.6 schema+grant+six-contract aggregate → close P1 → P2.6 manifest+replay+concrete admission+
provider-free dispatch → close P2 → P3.4 bounded provider activity/smoke → close P3 → P4.1 exact
fault bank → P4.2 dispatch-aware recovery → P4.3 worktree integration → P4.4 admission-aware
security → P4.5 assurance aggregate → P5.1 six-contract trial freeze → P5.2–P6.4`.

Every absent Required Read introduced by this remediation is produced by an earlier item in that
order. Semantic ownership is unique: P1.6 owns schema/grant, P2.6 owns the concrete instance and
provider-neutral dispatch, P3.4 owns provider activity only, P4 owns assurance/repairs, and P5 owns
trial selection/economics. The feasible set is therefore non-empty without changing D74 or frozen
P1.1–P1.5 outputs. RAG:— (repo-grounded: repaired Files/Required Reads/Rules/Validation fields).

## F3 and readiness verdict

P4–P6 Phase Handoffs now state current facts: P0 is terminal; P1–P3 are forward-reopened only through
P1.6/P2.6/P3.4; P4–P6 are unexecuted; the current step is a fresh cold design audit whose literal
GREEN is required before P1.6. No old authoring-next command or claim that all P0–P3 outputs are
absent remains.

DoR remains satisfied: 34 items, 16 fields each, exact per-item Routing, zero skeleton or
clarification markers, no new owner question, no orchestration group, and no terminal item/status/
Completion Notes mutation. External fact classes were not added; all remediation verdicts are
repo-grounded. The next valid action is `task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR design`.
