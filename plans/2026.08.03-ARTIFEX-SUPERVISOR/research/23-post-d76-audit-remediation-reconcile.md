# Post-D76 audit remediation and producer → consumer reconcile

## Sources and invariants

- `brief/10-post-d76-audit-remediation.md` — exact owner scope and anti-scope.
- `plan.md` → last `## Audit design — 2026-08-04` — F1–F3 failure scenarios.
- `findings/hooks-stale-source-precondition-2026-08-04.md` — current non-green hook state and
  worktree-local owning command surface.
- `research/20-p3.4-successor-contract-design.md`, D74 and the current open P1.6/P2.6/P3.4
  specifications — successor objective and frozen historical boundary.

All conclusions below are repo-grounded. No external fact class is introduced, no product item is
executed, and no terminal item/status/Completion Notes or P1.1–P1.5 byte is changed. RAG:—
(repo-grounded: the named current plan carriers).

## F1 — a task carrier distinct from the write-heavy parent item

P3.4 remains the implementation owner for `worker.py`, provider-aware CLI binding, lifecycle tests
and adapter aggregation. Its own `Files`/`Validation` therefore cannot be copied into a no-write
readiness manifest. The smoke gets two exact provider-specific child task identities instead:
`p3-smoke-codex-v1` and `p3-smoke-claude-code-v1`. They live in one frozen
`p3-smoke-task-set-v1.json`, with an empty write/tool allowlist, a temporary empty Git workspace,
one schema-only response, finite wall/byte/event/turn/token/cost maxima and minimized readiness
deliverables. The task-set hash is distinct from the P3.4 Task Contract/item hash.

P1.6 freezes the additive `dispatch-task-manifest-v1` form inside
`dispatch-admission-v1`, the exact smoke task set, and one D74-bound provider-specific grant per
task. P2.6 is the sole runtime instance producer:

`smoke task set → provider-specific dispatch manifests → verified grants → strict replay rows →
provider-specific admissions → admission index`.

P3.4 may select an admission only by exact task/provider ID from the index after its write-heavy
implementation/tests are complete. Each dispatch remains `max_slices=1`; neither one admission nor
one grant is reused for both providers. The P3.4 plan-item manifest is never an input to this chain.
Passing a grant, the P3.4 Task Contract, or a manifest for `item_id=P3.4` must refuse before intent
or process launch. This leaves frozen `slice-manifest-v1` unchanged: regular plan-item compilation
continues to use it, while the additive dispatch task is explicitly a child-activity carrier rather
than a false plan-item slice. RAG:— (repo-grounded: audit F1 and frozen
`root/contracts/slice-manifest-v1.md`).

## F2 — owner-bound business authority before provider dispatch

P5.1 remains no-provider experiment design and becomes the sole business admission producer. It
first freezes the catalog and `business-grant-request-v1.json`. A later Decision Log row must carry
the exact marker `[OWNER-GRANT:G-OWNER-P5-BUSINESS]` and bind the SHA-256 of both files, provider
set, controlled roots, maximum dispatch count, per-trial caps and expiry/revocation rule. Without
that row P5.1 cannot materialize grants/admissions or become terminal.

After the owner marker, P5.1 deterministically materializes:

- one business grant per catalogued candidate trial;
- one dispatch task manifest per P5.2 repository slice, P5.3 recovery/provider-failure call and
  P5.4 candidate battle wave;
- strict zero-or-replayed usage rows, one provider/run/slice/attempt identity per call;
- one admission per trial plus an immutable index mapping catalog ID to exact carrier paths/hashes.

P5.2–P5.4 may only select by predeclared catalog ID from that index. They cannot mint, widen,
refresh or reset grant/admission data locally. The incumbent side of a paired wave is not an
Artifex dispatch and therefore is pinned as baseline evidence rather than granted Artifex
authority. The existing `G-OWNER-P5.4-SINGLE` remains a separate verdict permission; it never
authorizes provider dispatch.

Negative acceptance is explicit: the P3 smoke task/grant/admission carries purpose
`provider-readiness-smoke`, D74, a temporary empty repo and smoke-only call count. P5 requires
purpose `business-trial`, the exact P5 business owner marker, controlled-root/task/catalog hashes
and per-trial call identity. Supplying any P3 carrier returns `BUSINESS_AUTHORITY_REQUIRED` or
`PURPOSE_MISMATCH` before intent/activity and leaves usage unchanged. RAG:— (repo-grounded: audit
F2, current P1.6/P3.4 exclusions and P5.1–P5.4 specs).

## F3 — explicit repair/recheck producer before security assurance

New P4.6 owns only the effective Codex hook prerequisite. Its exact order is P4.3 → P4.6 → P4.4,
even though the additive item ID follows the existing P4.5 identifier. It records the known
warning, runs the worktree-local Harness `--repair` command once, reruns the exact `--dry-run`,
and produces a minimized results JSON plus independent validator. It may not edit Harness/package
sources, accept `warning`, or substitute doctor/syntax/exit-code evidence. P4.4 reads the terminal
P4.6 result and still independently reruns the effective-hook command as part of the broader
security gate. The current design session performs neither command with `--repair`. RAG:—
(repo-grounded: hook finding and audit F3).

## Complete forward order and ownership

The topology grows from 34 to 35 plan items only because P4.6 is an executable repair/recheck
producer; smoke/business child task instances are frozen item-owned artifacts, not phantom plan
items or alternate status carriers.

`P1.6 contract + smoke task/grants → close P1 → P2.6 smoke manifest/replay/admissions + dispatch
seam → close P2 → P3.4 bounded provider implementation and admitted smoke → close P3 → P4.1 fault
bank → P4.2 recovery → P4.3 worktree lane → P4.6 hook repair/recheck → P4.4 security → P4.5
assurance → P5.1 catalog + owner-bound business grants/admissions → P5.2 live repository slices →
P5.3 recovery/provider-failure pilot → P5.4 five candidate admissions + paired economics → P6`.

Every new Required Read is either an existing source or produced by an earlier step in that order.
Semantic ownership is unique: P1.6 owns schemas and D74 smoke authority; P2.6 owns smoke runtime
instances; P3.4 owns provider lifecycle/activity; P4.6 owns effective-hook repair evidence; P5.1
owns business authority/instances; P5.2–P5.4 only consume them. No P3 carrier is a business grant,
and no doctor/syntax result is hook integrity.

