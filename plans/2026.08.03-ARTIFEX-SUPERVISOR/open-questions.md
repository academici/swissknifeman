# Open Questions — 2026.08.03-ARTIFEX-SUPERVISOR

## OQ-P5.5-R2 — Replacement capability probes

**Статус:** Resolved → D112

The repository owner authorized `[OWNER-GRANT:G-OWNER-P5-G2B-PROBE-R2]` through D111, then D112
superseded only the Codex cap-enforcement semantics with the enforceable wrapper/usage contract in
`brief/27-p5.5-codex-r2-cap-contract-owner-refinement.md`. No wider schema, root, attempt, retry,
D105 or pilot authority was granted.

## OQ-P5.2-BRIDGE — Business execution bridge architecture

**Статус:** Resolved → D118 (package-owned; owner delegated the technical pick, see
`brief/32-p5.2-bridge-architecture-owner-delegation-2026-08-06.md`)

D117 voided D114 (package-owned bridge in `packages/artifex/lib/artifex/`), D115 (Claude
scoped-write prompt) and D116 (plan-local-only bridge in `run-pilot.py`) as executor
self-authorization — none of their `brief/29-31-*.md` carriers quote an actual owner message,
unlike every other owner-grant/owner-direction carrier in this plan. P5.2 therefore has no
approved bridge architecture.

Open technical question for the owner: should the business execution bridge live in the Artifex
package (`packages/artifex/lib/artifex/`, testable/reusable beyond this one pilot) or stay
plan-local-only inside `plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/run-pilot.py` (no package
mutation, exactly what D116 attempted)? Either way the contract must stay symmetric across both
providers (`codex-cli 0.146.0`, `Claude Code 2.1.222`) — one provider being the executor's own
runtime this session is a sequencing fact (that provider gets exercised/debugged first, the other
is validated separately afterward), not a design difference between the two provider mappings.

The one slice already attempted under void D114/D116 authority (`p5.2-slice-01-worktree-core`,
provider `codex`, `accepted:false`, `changed_paths:[]`, recorded in
`artifacts/P5/repository-pilot-results-v1.json`) is retained as a historical, non-authoritative
data point: the provider process completed (`OK`) but produced no repository delta, which is
consistent with the bridge/prompt construction being unresolved rather than a provider capability
failure. It is not reused as evidence without a fresh owner decision on this question.

**Follow-up, also resolved (2026-08-06):** implementing D118 exposed that the seam bytes belong to
the G2B generation by construction. The owner selected «Реопен P5.5» and «Гонять 2.1.222»
(`brief/33-p5.2-seam-ownership-owner-decision-2026-08-06.md`) → **D119** (P5.5 reopens as sole
producer, adopts the seam, re-freezes both manifests; P5.2 becomes a pure consumer) and **D120**
(the frozen `2.1.222 (Claude Code)` pin is honored via `SKM_CLAUDE_BIN`, not bumped). No question
remains open on this track.

## OQ-P5.2-NULL — What the 0/3-accepted pilot proved

**Статус:** Resolved → D121/D122

The first live P5.2 pilot returned `0/3 accepted` with the mechanics fully sound. The closing
handoff queued three options (fresh grant + retry / accept as terminal / reopen P5.5 to sharpen the
prompt) and one open question: *does P5.4's release-readiness adjudication require a positive P5.2
business-edit precedent, or is mechanical safety/reversibility sufficient?*

Both are resolved by the 2026-08-06 design pass. The question was mis-framed: the frozen admission
carries no task description at all, so the pilot measured the harness, not the candidate — a null
measurement, not a negative one (`findings/P5.2-task-description-gap-2026-08-06.md` F1–F4; external
corroboration in `findings/P5.2-external-harness-precedent-2026-08-06.md`). The owner selected
«Реопен P5.5 + новый грант на 3 строки» and «Поднять до 600000 ms в новых строках»
(`brief/34-p5.2-zero-accept-owner-decision-2026-08-06.md`) → **D121** (hash-verified catalog
resolution in the seam; P5.1/P5.5/P5.2 reopen) and **D122**
(`[OWNER-GRANT:G-OWNER-P5.2-RETRY]`, three replacement rows, `claude-code` wall `600000` ms).

Answer to the carried sub-question: P5.4 **does** require a real P5.2 result, because P5.3 and P5.4
consume the same carrier shape — without the fix their evidence would inherit the same gap. The
answer is therefore "fix the carrier and re-measure", not "waive the precedent".

Deferred, deliberately: the contract-level fix (adding `task.scenario` to
`business-dispatch-admission-v1`) is semantically better but forces a 14-admission re-mint and a
full P5.1 rewrite for no gain over hash-verified catalog resolution during the pilot — recorded as
a **P6 product-surface follow-up**, see `research/38-p5.2-zero-accept-root-cause-and-options.md` §4
Option 3.

## OQ-P5.4-ECONOMY — How the economic verdict can be adjudicated at all

**Статус:** Resolved → D123/D124/D125/D126/D127

P5.4's pre-intent gate stopped before its first dispatch on eight blockers
(`findings/P5.4-preflight-blockers-2026-08-06.md`), and the 2026-08-06 re-design pass found three
more (`findings/P5.4-metric-surface-gap-2026-08-06.md`): the candidate lane records provider usage
as booleans rather than integers (F9); no single provider fills all seven `economy-evidence-v1`
metric fields, so `GO` was unreachable in `parity` mode by construction (F10); and the codex
sandbox has no working compensating control on this kernel (F11).

The owner was shown each verified blocker with options and a recommendation, and selected all four
recommendations (`brief/35-p5.4-economic-adjudication-owner-decisions-2026-08-06.md`) →
**D123** (single-provider `claude-code` economic lane on a new additive `economy-evidence-v2`),
**D124** (the `baseline` lane is one headless single-shot provider invocation of the same slice
without the supervisor, coordinator envelope a structural zero), **D125**
(`[OWNER-GRANT:G-OWNER-P5.4-PAIRED-WAVES]`, ten rows, raised caps), **D126** (all five waves on
`claude-code`, codex excluded from P5.4) and **D127** (the five-item forward topology).

## OQ-P5.4-CODEX-SANDBOX — The codex sandbox versus the `network-disabled` guarantee

**Статус:** Decision pending (нужен владелец)

D126 removed codex from P5.4 rather than resolving this, and said so explicitly. The question
itself is unresolved and is now the plan's only open one.

Codex's own bubblewrap sandbox cannot acquire network-namespace capabilities in this nested
environment (`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`). The only verified
path to a working codex write is its documented `--dangerously-bypass-approvals-and-sandbox`,
which removes the `network-disabled` guarantee that is an explicit capability and a `SEC-WORKTREE`
`acceptance_ref` on every catalog row — on a host independently confirmed to have real outbound
network access. The obvious compensating control was tested first-party on 2026-08-06 and does not
work here either: `unshare -rn` and `unshare -n` both return `Operation not permitted`
(`findings/P5.4-metric-surface-gap-2026-08-06.md` F11). There is no third technical option to
propose.

What is blocked by leaving it open: the codex business lane stays unproven, so P6 may not claim it
as a shipped capability without its own evidence. What is NOT blocked: P5.4, whose waves are all
`claude-code` under D126, and provider parity, which is carried by terminal P3.3 and P5.3.

Owner decision needed, exactly one of: (a) accept the bypass with an explicit D# recording that
`network-disabled` is not enforced for those runs; (b) ship the product with a documented
single-provider business scope and codex marked `behind-gate`/`disabled` with the reason named;
(c) defer the codex business lane to a follow-up plan on a host where unprivileged namespaces are
available.
