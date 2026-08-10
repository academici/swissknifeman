# Design audit — 2026.08.02-PROVIDER-CONTRACT-LOCALE

**Date:** 2026-08-10 · **Mode:** pre-execution review of the whole plan ·
**Executor:** gpt-5.6-sol under the required frontier/xhigh route (`task:plan-audit design`);
the runtime did not export the active effort value

## Audit design — 2026-08-10

**Вердикт: RED**

**Заход: 8-й.** `journal.jsonl` contains seven earlier `plan-audit` records for `design`; the
2026-08-10 skills-audit integration is a material design pass after the earlier GREEN.

**AUDIT-CAP: design — 8-й заход, решение за владельцем.** The audit does not assign another
automatic remediation or audit command. The owner must explicitly choose a bounded design repair
followed by an exceptional fresh audit, or terminate/re-scope the plan. Accepting the current plan
with deviations is not an executable option while F26 keeps the mandatory v2 executor carrier
unbuildable.

### Tree anchor and deterministic checks

The audit inspected `3b8ef9842ac82878a16a67007f7d6f7f780a3cd6` plus the current dirty
worktree. The dirty state is itself finding F29; no package, provider, fleet, Brain, generated
product or release state was changed.

- `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE
  --baseline HEAD` → `OK (1 plan, 0 errors, 0 warnings; new: 0)`:
  **0 ERROR / 0 WARN (on 3b8ef984 + worktree)**.
- `python3 packages/task/scripts/plan-lint.py --conflicts` →
  `OK (0 mismatches, 0 warnings)`.
- `python3 packages/task/scripts/verify-plan-citations.py
  plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --strict` → 0 findings, but the checker reports
  **0 machine citations inspected**; this is not used as proof of the external design claims.
- `python3 packages/task/scripts/plan-views.py bundle --plan-dir
  plans/2026.08.02-PROVIDER-CONTRACT-LOCALE --item <Pn.m> --stdout` for every routed item →
  **30/30 non-zero**, each with `ERROR: unresolvable_entry: ...`.
- Status, decision and all 30 item-state projections were byte-current before the journal append.
  Bundle production/check is non-green by F26 and is not reported as skipped success.

The literal RED follows F26: the exact v2 executor path cannot be materialized for even P0.1.
The green linter is a false negative for this pre-execution state, not evidence that the plan is
executable.

## Findings

### F26 · Blocker · confidence high · issue · `phases/P0/P0.1.md:7` · PROMOTE-CANDIDATE

**All 30 v2 item bundles are unbuildable because every `Inputs` field starts with a narrative
declaration that resolves to no carrier.**

The v2 plan-protocol executor path is exactly plan core → phase context → item spec →
`bundles/<Pn.m>.json` → item state. `plan_bundle.model()` resolves every `Inputs` and
`Required Reads` declaration to files or decision records and raises `unresolvable_entry` when a
declaration resolves to neither (`packages/task/lib/task/plan_bundle.py:188–200`). The first
failure is P0.1 `current git HEAD/worktree`; the same exhaustive invocation fails for every item,
ending with P7.4 `Terminal P7.1–P7.3 commits and artifacts`. `bundles/` currently contains zero
files.

`plan-lint` does not expose the failure because its v2 bundle gate considers only ready items in
active phases, then returns early when that set has no existing bundle
(`packages/task/lib/task/plan_gates.py:248–269`). All phases are `Not started`, so a reported
0/0 lint result coexists with 30/30 failed bundle renders.

**Constitution rule:** plan-protocol §2 v2 carrier contract and task:plan-audit design checklist
§6 require an executable roadmap/carrier chain; a mandatory reader input must be resolvable and
digest-qualified.

**failure_scenario:** after the supervisor pause is released, the P0.1 executor follows the
canonical v2 path and cannot obtain `bundles/P0.1.json`; generating it fails before any item work.
Every later item has the same defect. Execution either stops at item 1 or bypasses the canonical
input-integrity carrier and runs from unverifiable prose.

**Repair contract for an owner-authorized design pass:** normalize all 30 `Inputs` and `Required
Reads` into individually resolvable carrier declarations, regenerate all 30 bundles through
`plan-views.py bundle`, require byte-current `--check`, and add a pre-execution lint/test case that
cannot return green when the routed first item has no renderable bundle. Do not weaken the bundle
resolver or remove digest qualification.

### F27 · Major · confidence high · issue · `roadmap.md:71`

**The active v2 execution carrier still directs cold package sessions and P4 reviewers to v1 phase
paths that do not exist.**

The package-slice prompt reads `phases/<Pn>.md`; P4 integration and reviewer carriers repeatedly
read `phases/P4.md` (`roadmap.md:95,124,142,165–168`). P0.3 Required Reads similarly require
`phases/P1.md` through `phases/P7.md` (`phases/P0/P0.3.md:9`), and the plan index advertises
`phases/P0.md … P7.md` (`index.md:10`). The live layout is
`phases/<Pn>/<Pn>.md` plus `phases/<Pn>/<Pn.m>.md`.

**Constitution rule:** plan-protocol §2 fixes the v2 phase/item carrier locations; root package
rules require fresh package-cwd sessions to receive the exact applicable specifications.

**failure_scenario:** a P3/P4/P6/P7 package child or P4 checkpoint reviewer copies the declared
prompt, fails to read the named phase carrier, and either stops or improvises from roadmap prose.
P0.3 also cannot complete its own Required Reads exactly, so the recovery contract may freeze
without the declared downstream phase inputs.

### F28 · Major · confidence high · issue · `plan.md:19`

**Meta claims `Design Passes 4/4`, but the Update Log has only two literal `design pass …`
completion rows and no explicit fourth-pass close.**

`status.md:109` records `design pass 1/3`; `status.md:118` records `design pass 3/3 finish`.
The 2026-08-10 entry at `status.md:131` says only that the skills audit was integrated; it does not
identify `design pass 4/4`, what was not reached, or the next pass focus. There is also no literal
pass-2 close row. No owner D-record authorizes the counter shortfall.

**Constitution rule:** task:plan-audit design checklist §5 requires `k >= N` to be evidenced by
Update Log rows named `Design pass …`; a shortfall without an owner D-record is Major.

**failure_scenario:** a cold auditor or owner accepts `4/4` from Meta while the journal cannot
distinguish the fourth bounded fresh pass from an incremental same-context edit. The design budget
and authoring provenance become assertions rather than auditable gates.

### F29 · Major · confidence high · issue · `handoff.md:14`

**The revised design advertised as the audit source is not committed at the audit anchor.**

The scoped worktree contains 41 modified tracked files for this plan/docs slice and ten untracked
load-bearing carriers, including `brief/01`, D55–D61, `findings/13` and `research/09`. The diff
against HEAD is 410 insertions/156 deletions before counting those untracked carriers. In contrast,
`handoff.md:14–32` presents that integration and those files as the current sources of truth.

**Constitution rule:** plan-protocol evidence and cold-start execution depend on committed,
re-readable carriers; root evidence-integrity requires claims to name their actual tree state.

**failure_scenario:** a new root launched from the recorded HEAD does not receive the owner
refinement or D55–D61, while bundles generated before/after an incidental worktree change receive
different digests. A later commit can also differ from the exact bytes this audit reviewed, making
the audit verdict non-reproducible.

### F30 · Minor · confidence high · issue · `handoff.md:10`

**The v2 handoff emits provider/context forms from the historical v1 protocol.**

The provider-neutral table uses free prose `cold start; identity distinct ...` instead of the v2
Context enum, while the native table at `handoff.md:75–77` uses
`NEW SESSION — audit step, not an item`. The v2 canon permits exactly `continue-root`,
`isolated-child-return`, or `cold-start-root`; a cold root must carry one canonical reason.

**Constitution rule:** plan-protocol §6 v2 launch contract and root launch-and-hook-integrity require
the provider-neutral form alongside the native launch block with a canonical Context value.

**failure_scenario:** a parser or cold owner cannot classify the handoff by the v2 enum/reason and
falls back to provider prose; automated routing can neither prove an allowed hard boundary nor
distinguish a root continuation from a fresh independent audit.

## Brief trace — checked without gaps

| Brief/refinement thought | Plan carrier(s) | Result |
|:--|:--|:--|
| Reliable hub; one semantic source of truth; independent provider state | P1.1–P1.3, P3.1–P3.3, P6.2, D15/D55/D57 | covered |
| Preserve local/ambiguous assets; classify before destructive recovery | P0.1–P0.4, P5.1–P5.4, D26–D29 | covered |
| Compact English canon plus three independently inherited locale surfaces | P2.1–P2.3, P4.1–P4.6, D17–D24 | covered |
| Minimum current-model Skill Core and progressive disclosure | P1.2, P2.3, P4.2–P4.3, D56 | covered |
| Additive Claude/Codex adapters and a third-provider seam | P1.2, P3.2, P7.1–P7.2, D57 | covered |
| Official docs → real-provider replay/ablation → regression locks | P2.3, P7.1–P7.2, D58/D61 | covered |
| Multi-label, provider-qualified measurements without heuristic deletion | P3.3, P6.2, P7.1/P7.4, D59–D60 | covered |
| Exact fleet evidence, rollback, health and release blockers | P0, P5, P6, P7, D26–D32/D47/D52 | covered |

No owner thought was found only in chat or left without a carrier/rejection. The adversarial blind-
spot pass found no additional missing integration, migration, compatibility, documentation,
rollback, security or release domain beyond F26–F30.

## Other checks without findings

- **Knowledge layers are coherent.** `brief/00–01` → `findings/13` plus current repository facts →
  `research/00,09` → D55–D61 → the named item refinements. External claims are marked/adjudicated;
  rejected audit prescriptions remain rejected rather than silently entering scope.
- **Current official sources support the design direction.** Anthropic describes metadata-first,
  on-demand progressive disclosure and recommends moving detail out of the main skill; OpenAI
  recommends one focused job, explicit inputs/outputs and trigger tests and exposes a
  provider-specific implicit-invocation policy; the Agent Skills specification defines the shared
  `SKILL.md` plus optional resources without making provider invocation one shared semantic field.
  Sources re-opened 2026-08-10:
  `https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview`,
  `https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices`,
  `https://developers.openai.com/codex/skills`, and `https://agentskills.io/specification`.
- **Phase contracts are coherent.** P0 evidence/recovery gates feed P1/P2 frozen contracts; P3
  implements them; P4 migrates admitted locale/skill carriers; P5 reconciles consumers; P6 emits
  provider-qualified health; P7 performs real replay, locks regressions, prepares operations and
  audits the release candidate. No producer/consumer cycle or missing semantic phase was found.
- **Routing/roadmap set equality holds.** There are 30 item specs, 30 Routing entries and 30 roadmap
  rows. All are sequential/solo for predecessor, authority, live-state or release-risk reasons;
  model/effort entries agree with Routing. Owner gates correspond to contract freeze, exact live
  mutation sets, corpus admission, Brain recovery and final release authority.
- **Decision discipline holds.** D1–D61 are present without duplicates; open questions are empty.
  D24 and D43, the decisions that textually replace/supersede earlier accepted positions, carry
  inline `**Consequences:**`. D55–D61 do not silently supersede accepted provider semantics.
- **DoR markers are closed.** No live `[NEEDS CLARIFICATION]` marker was found in current phase/item
  specs; all eight phase contexts declare included/excluded scope and executable validations.

## Verification and environment trust

- RAG retrieval: three fresh Perplexity Web queries over official Anthropic, OpenAI and Agent Skills
  sources, followed by direct primary-page web reads — OK. No supplementary source changed the
  finding set.
- Repository verification: direct carrier reads, set/count checks, source inspection and commands
  above. No code/git completion verification was performed because `design` mode audits the plan,
  not implementation claims.
- Affected tooling validation: `bash packages/task/scripts/validate.sh` passed 750 tests with one
  skip and finished `validate: OK`; its repository-wide archive scan retained 252 historical
  warnings, while the targeted plan lint remained 0 errors/0 warnings.
- Workarounds: none introduced. The plan remains paused by
  `2026.08.03-ARTIFEX-SUPERVISOR`; this audit does not release it.
- Environment defect: the installed cached `core:plan-protocol` is stale relative to the repository
  SSOT (`df7b9cf1…`, 1363 lines versus `5ceaec0b…`, 281 lines). This audit followed the repository
  canonical v2 contract and discloses the cache drift. `codex doctor --json` confirmed
  `gpt-5.6-sol` but did not expose active effort, so xhigh is recorded as the required route rather
  than an independently observed runtime fact; worktree-local mAInd health and the absolute-target
  Codex hook dry-run were otherwise green/no-op.

### Что запускать

**AUDIT-CAP исчерпан — автоматическая команда не назначается.** Owner decision must name whether
to authorize one bounded repair of F26–F30 and an exceptional independent re-audit, or to terminate/
re-scope the plan. F26 cannot be waived as `Done with deviations` because it prevents P0.1 from
entering the mandatory v2 executor path.

**Provider-neutral plan-protocol launch block**

| Параметр | Значение |
|:--|:--|
| Model class | owner |
| Effort | high |
| Capabilities | plan-authority · remediation-scope-decision |
| Context | `cold-start-root` |
| Суть | reason=`owner-pause-no-resume`; decide bounded F26–F30 repair plus exceptional re-audit, or terminate/re-scope; do not start P0.1 |
| Команда | — |

**Native Codex launch block**

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| owner decision | high | `cold-start-root` (`owner-pause-no-resume`) | Decide the RED/AUDIT-CAP disposition; no automatic ninth audit | — |
