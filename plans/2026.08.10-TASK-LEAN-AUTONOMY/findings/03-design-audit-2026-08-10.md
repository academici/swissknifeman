# Design audit — 2026.08.10-TASK-LEAN-AUTONOMY

**Date:** 2026-08-10 · **Mode:** pre-execution review of the whole plan ·
**Executor:** required semantic route `frontier/xhigh` (`task:plan-audit design`); the running
session did not export an independently attestable selector/effort pair.

## Audit design — 2026-08-10

**Вердикт: RED**

**Заход: 1-й.** Earlier `plan-audit` journal records for `design`: 0.

The plan is not executable yet. F1 is a literal admission blocker: the Task Contract compiler
cannot resolve Routing for any of the four items. F2–F10 are additional readiness, provenance,
context-budget, portability, and cold-start defects that must be reconciled before a fresh
independent design audit.

### Tree anchor and deterministic checks

The audit inspected committed anchor `c1a6ba3e9e0ce2878d0e6e3669305f42368e1aef` plus the
current dirty worktree. The target plan has no tracked files at that anchor; this is finding F10,
not a green committed-tree claim. No package implementation, generated provider product, release,
tag, push, or foreign plan state was changed.

- `python3 packages/task/scripts/plan-lint.py
  plans/2026.08.10-TASK-LEAN-AUTONOMY` →
  **0 ERROR / 0 WARN (on `c1a6ba3e` + worktree)**.
- `python3 packages/task/scripts/plan-lint.py --conflicts` →
  **0 mismatches / 0 warnings**.
- `python3 packages/task/scripts/verify-plan-citations.py
  plans/2026.08.10-TASK-LEAN-AUTONOMY --strict` → **5 local citations inspected / 0 findings**.
  This is not used as proof of external claims.
- `plan-views.py state --all --check`, `status --check`, `decisions --check`, and
  `bundle --all --check` → byte-current (**4 item states, 1 status view, 4 decision views,
  4 bundles**). After the audit journal append, status and bundles were regenerated through the
  owning generator before this report was written.
- `PYTHONPATH=packages/task/lib python3 -m task.task_contract build --plan-dir
  plans/2026.08.10-TASK-LEAN-AUTONOMY --item <Pn.m>` → **0/4 buildable**; every item returns
  `TaskContractBuildError: <Pn.m>: Routing: no §3 Routing row found for this item`.
- Generated bundle sizes are P0.1 **31,168**, P0.2 **80,813**, P1.1 **50,233**, and P1.2
  **194,396 estimated tokens**. Their repeated-path counts are respectively **3, 6, 6, 4**.
- `bash packages/task/scripts/validate.sh` → exit 0, **750 tests / 1 skip**, `validate: OK`.
  Its repository-wide plan scan retained **252 warnings**, all reported against archived plans;
  the targeted plan remains 0 ERROR / 0 WARN.

## Findings

### F1 · Blocker · confidence high · issue · `plan.md:55` · PROMOTE-CANDIDATE

**The only Routing row uses the illegal cross-phase range `P0.1–P1.2`, so all four Task
Contracts are unbuildable.**

The v2 Routing grammar allows one item or one range whose endpoints belong to the same phase.
The current cell crosses P0→P1. The deterministic compiler therefore matches neither P0 nor P1
and returns `no §3 Routing row found` for P0.1, P0.2, P1.1, and P1.2. `plan-lint` remains green,
so this is also a false-negative gap between the structural gate and the execution compiler.

**Constitution rule:** worktree-local `plan-protocol` §5: `Items` is exactly one `Pn.m` or one
same-phase range; routing must be unambiguous before mutation. The v2 executor must be able to
build its Task Contract.

**failure_scenario:** S1 is launched from the roadmap, P0.1 reaches pre-mutation admission, and
the compiler refuses before any legal item work. Bypassing the compiler would discard the very
strict initial contract the plan is intended to preserve.

**Repair contract:** split Routing into same-phase or per-item rows, carry the intended S1/S2
grouping in the canonical Batch/roadmap carriers, and require successful Task Contract builds for
all four items in the next finish gate. Add a linter regression so a cross-phase range cannot
again produce `plan-lint: OK` while the compiler rejects every routed item.

### F2 · Major · confidence high · issue · `phases/P0/P0.1.md:12`

**The item Validation fields are mostly prose categories, and P0.1/P0.2/P1.1 omit their affected
package validation commands.**

P0.1 names one exact budget command but leaves Harness compatibility/projection checks as prose;
P0.2 and P1.1 name test classes and a CLI reproduction without runnable invocations. Only P1.2
mentions all three package validation scripts, after the earlier items would already have closed.
The repository requires each affected package validation command before handoff.

**Constitution rule:** `plan-protocol` §3 requires runnable Validation commands;
root `AGENTS.md:46` requires the affected package validation command before handoff.

**failure_scenario:** two executors choose different subsets behind “focused tests”, close an
item without `packages/<owner>/scripts/validate.sh`, and hand a green-looking state to the next
item although provider projections or package invariants are red.

**Repair contract:** give every item an exact copy-pastable command list, including the owning
package `scripts/validate.sh`, generator `--check` commands, and the narrow reproducer that proves
its deliverable. Keep manual inspection as an additional check, not the sole acceptance predicate.

### F3 · Major · confidence high · issue · `roadmap.md:13`

**The two one-session causal groups conflict with mandatory package-cwd instruction routing.**

S1 combines Harness-owned P0.1 with a P0.2 item that writes both Skiller and Task. S2 ends in a
P1.2 item allowed to revisit Harness, Skiller, and Task. The roadmap nevertheless launches each
group as one `continue-root` `plan-run` series. Root `AGENTS.md:91` requires a restart with
`codex -C packages/<name>` before work inside each package, so one root cannot truthfully inherit
all three package rule stacks as currently specified.

**Constitution rule:** root package-scope routing is part of the repository conformance
constitution; `plan-protocol` §7 requires commands to read repository instructions root→cwd and
fail closed on missing applicable rules.

**failure_scenario:** the S1 executor stays at repository root to preserve the promised one-session
flow, edits package sources without the package-local instruction stack, and produces changes that
cannot be accepted under the repository's own launch contract.

**Repair contract:** either split the affected work into package-scoped items/sessions with an
explicit integration continuation, or define a repository-approved orchestration carrier whose
children start at the exact package cwd and return bounded evidence. Do not waive package guides
to preserve a session-count target.

### F4 · Major · confidence high · issue · `phases/P1/P1.2.md:8`

**The write boundary for runtime discovery and stabilization is not sealed.**

P1.1 permits all of `packages/task/lib/task/**`, `packages/task/scripts/**`, focused tests, and
conditional docs/schema “where ownership is found”. P1.2 then permits “scoped fixes in P0/P1
owners”, “relevant” docs, and “accepted roadmap records”. Those phrases do not name a finite write
set or a deterministic authority step for admitting another file. This contradicts the plan's own
strict-initial-contract premise.

**Constitution rule:** `plan-protocol` §3 says `Files` bounds writes; v2 readiness requires concrete
files before execution. Brief `00-brief.md:5–8` preserves strict scope/boundaries before adaptive
work begins.

**failure_scenario:** a canary reveals a plausible adjacent defect and P1.2 edits any earlier
package/document/roadmap under the phrase “scoped fixes”, turning bounded local repair into silent
scope expansion and making the item commit impossible to audit against `Files`.

**Repair contract:** enumerate the maximum mutable paths for P1.1/P1.2, define the exact admission
carrier for any newly discovered file, and route a change outside that set to a named owner/design
decision rather than absorbing it into stabilization.

### F5 · Major · confidence high · issue · `phases/P1/P1.md:33`

**The terminal meaning of `GO/ADJUST` is undefined.**

The phase says it ends with either GO or ADJUST and that ADJUST records residual work without a
new design/audit loop. P1.2 promises a terminal plan handoff only “if acceptance holds”, but no
carrier maps ADJUST to a canonical item/phase status, exact semantic Next, owner decision, or
forward remediation item.

**Constitution rule:** `plan-protocol` §§4 and 6 require one of six statuses plus an exact Next;
the brief's success criterion requires an accepted change, not merely a recorded non-GO verdict.

**failure_scenario:** field evidence returns ADJUST. One executor closes P1.2 as 🟠 and archives a
plan whose acceptance failed; another leaves it open with no executable successor. Both follow
some of the prose, and neither has a canonical state transition.

**Repair contract:** define GO and ADJUST transitions explicitly. GO may expose plan closure only
when acceptance is green. ADJUST must state whether the item remains nonterminal or closes with a
named forward-remediation Next/owner gate; it must not silently become successful terminality.

### F6 · Major · confidence high · issue · `plan.md:19`

**Meta declares `Design Passes 1/1`, but the journal-derived Update Log contains no literal
`Design pass 1/1` completion record.**

Before this audit, the only authoring row said that the plan was created and fully detailed. The
new audit row records this RED verdict. Neither identifies the pass number, what the pass covered,
what it did not reach, or the next pass focus. No owner decision shrinks or substitutes the budget.

**Constitution rule:** `task:plan-audit design` checklist §5 requires `k >= N` to be evidenced by
Update Log rows named `Design pass …`; plan-protocol §1 requires authoring provenance in Meta,
Update Log, and journal.

**failure_scenario:** a cold owner accepts `1/1` from Meta without being able to distinguish a
fresh full design sweep from bootstrap authoring in one context. The design-budget gate becomes
an assertion rather than evidence.

**Repair contract:** append forward-only design provenance through the journal with a literal
`Design pass 1/1` close, coverage/gaps, and next-focus statement; regenerate status instead of
hand-editing it. If the remediation itself is a new pass, update the denominator honestly.

### F7 · Major · confidence high · issue · `decisions/D1-strict-contract-adaptive-execution.md:1`

**D1–D6 omit decision-level actor/model provenance and do not link their load-bearing evidence
back to the findings/research layer.**

All six records carry id/date/status/items/supersession metadata, but none identifies the actor or
model that authored/accepted the decision. D1–D4 end with only `RAG:✅ 2026-08-10`; they do not
name `findings/02-external-rag.md` or a specific verified fact. D5/D6 use broad owner/repository
descriptions without an exact source carrier. Phase prose claims the owner accepted D1–D6 through
the brief, but the records do not preserve that authority provenance.

**Constitution rule:** `plan-layout-v2` “Decisions” requires actor/model provenance and evidence
marker per decision; `task:plan-audit design` checklist §3 requires D-records to reference the
knowledge layers so the chain is reconstructible without chat.

**failure_scenario:** after context loss, an executor cannot tell whether a tolerance was an owner
choice or a model synthesis and cannot reopen the exact external/repository basis. A later
supersession then rests on an untraceable accepted premise.

**Repair contract:** add the canonical decision provenance fields and exact evidence paths/anchors
to D1–D6, use `[UNVERIFIED]` where evidence is genuinely absent, regenerate decision views, and
retain the existing accepted meaning unless a new owner decision changes it.

### F8 · Major · confidence high · issue · `roadmap.md:18`

**The roadmap's “ready launch-blocks” are semantic sketches, not complete provider-neutral plus
native launch blocks.**

Both S1 and S2 tables stop after `Суть`; they have no `Команда` row. The following code blocks
contain `run-items: task:plan-run …`, which is a semantic Next form, not an executable Codex
invocation pinned to cwd/model/effort/approval/sandbox. The package-cwd conflict in F3 also means a
correct native cwd cannot yet be derived.

**Constitution rule:** `task:plan-audit design` checklist §6 requires ready launch blocks for every
batch/group; `plan-protocol` §6 and root launch-and-hook-integrity require the provider-neutral
carrier alongside a native pinned launch block.

**failure_scenario:** the owner copies the advertised block into a shell and gets no command, or
launches a default `gpt-5.6-terra/medium` session without the required high effort and package cwd.

**Repair contract:** after resolving F1/F3, render complete neutral and native blocks for each
actual executable group, including exact cwd, `gpt-5.6-terra/high`, `-a never`,
`-s danger-full-access`, semantic Next, canonical Context, and copy-pastable command.

### F9 · Major · confidence high · issue · `bundles/P1.2.json:1` · PROMOTE-CANDIDATE

**The mandatory executor bundles are not minimized; P1.2 alone carries 194,396 estimated tokens
and rereads four paths twice.**

P1.2 imports the whole 111,651-token `CHANGELOG.md`, 21,939-token `docs/reference.md`, two foreign
plan journals/handoffs, the local journal/status, and five roadmap documents before doing field
analysis. Across the four generated bundles, 3/6/6/4 paths are repeated. The plan is specifically
intended to reduce repeated context reads, yet its final canary starts with the largest repeated
input surface.

**Constitution rule:** `plan-protocol` §§2 and 7 require ordered digest-qualified and portable
execution inputs; the v2 bundle contract is the exact executor path. Brief
`00-brief.md:21–30` and `01-refinements.md:7` make compact context and fewer repeated reads part of
acceptance.

**failure_scenario:** P1.2 spends most of its usable context on entire ledgers and duplicated
carriers, then needs a context-driven restart or shallow analysis before the actual canary and
stabilization work. The plan reproduces the context churn it is meant to remove.

**Repair contract:** replace whole ledgers with bounded selectors/history projections and the
`[Unreleased]` slice, remove duplicate declarations or fix the owning bundle generator where it
duplicates a single decision input, regenerate all bundles, and publish a measured post-fix token
budget in the finish evidence.

### F10 · Major · confidence high · issue · `plan.md:1`

**The complete plan and one load-bearing roadmap input are untracked, so this audit has no
reproducible committed plan anchor.**

`git ls-files plans/2026.08.10-TASK-LEAN-AUTONOMY` returns zero paths. The worktree also contains
untracked `roadmap/2026.08.10-plan-run-routing-blocked-terminal-loop.md`, which P1.1/P1.2 consume,
and a modified `docs/reference.md`, which is bundled into P1.2. Bundle hashes are byte-current only
for this mutable worktree snapshot.

**Constitution rule:** `plan-protocol` §§1 and 7 require repository files as truth and portable
inputs to be committed or predecessor-produced; root evidence-integrity forbids treating a dirty or
skipped check as committed green evidence.

**failure_scenario:** a cold launch from `c1a6ba3e` cannot see the plan at all. A later commit can
also differ from the bytes audited here, invalidating bundle digests and the RED remediation scope.

**Repair contract:** after design remediation, commit the stable plan, decision/evidence carriers,
accepted roadmap input, journal and generated views as an explicit plan bookkeeping change; then
rerun bundle/view/Task Contract/lint checks on that committed tree before the next audit. Preserve
all unrelated ARTIFEX and owner worktree changes.

## Brief trace — checked without uncovered thoughts

| Brief/refinement thought | Plan carrier(s) | Result |
|:--|:--|:--|
| Strict initial goal/scope/acceptance/authority frame | D1, P0.2, P1.1 | covered; executability defects F1/F2/F4 |
| Adaptive grouping and local repair | D1/D2, roadmap S1/S2 | covered; package-boundary defect F3 |
| Minimal always-on instructions and progressive disclosure | D4, P0.1 | covered |
| No status-only audit/reopen loops | D3, P0.2, P1.1 | covered |
| Material review trigger and verdict reuse | D3, P1.1 | covered |
| No new supervisor/cursor/lease/manifest control plane | both phase exclusions, D1 | covered |
| Preserve security/destructive/public/frozen/owner gates | P0.1/P0.2 rules, D2 | covered |
| Required Perplexity base-search stop | D6, P0.1/P0.2 | covered |
| Field canary over formal-green-only proof | D5, P1.2 | covered; terminal ambiguity F5 |
| Compact plan/few sessions/repeated reads | two phases/four items, roadmap | covered in intent; F3/F9 block the promised path |
| Accepted end-to-end change without ritual cycle | P1.2 deliverable and phase handoff | covered in intent; F5 leaves ADJUST unresolved |

No owner thought was found only in chat or entirely absent from a carrier. The defects are in the
executability and evidence quality of those carriers, not in top-level brief coverage.

## Other checks without findings

- **Phase contract direction is coherent:** P0 produces the reduced instruction/command semantics;
  P1 consumes terminal P0 semantics and adds the minimum runtime/canary layer. No producer/consumer
  cycle was found beyond the execution-carrier defects above.
- **Item set coverage is complete:** four item specs, four generated states, four bundles, and two
  roadmap ranges cover P0.1–P1.2 exactly once at the roadmap level.
- **DoR markers are closed:** no live `[NEEDS CLARIFICATION …]` marker was found; both phase
  contexts carry Included/Excluded scope, contract-first statements, and item indexes.
- **Open questions are empty:** the generated open-question view has no unresolved records.
- **Consequences discipline is not triggered:** D1–D6 have empty `supersedes` sets and do not
  textually cancel an earlier accepted decision, so no missing `**Consequences:**` finding applies.
- **External source provenance is present at repository level:** `findings/02-external-rag.md` and
  the current `docs/reference.md` record the cited primary sources. Their decision-level linkage is
  still defective under F7. This RED verdict itself rests only on repository/compiler evidence and
  does not require a new external-fact verdict.

## Verification and environment trust

- `pwd`, `git status --short`, `codex doctor --json`, worktree-local `maind health --cwd`, hook
  diagnostics, targeted plan lint/conflict/citation checks, generated-view checks, bundle metrics,
  and all four Task Contract builds were run.
- `maind health --cwd` was green. `codex doctor` was overall green and confirmed approval `Never`
  plus unrestricted filesystem, but reported the default for new unpinned launches as
  `gpt-5.6-terra`; it does not attest this already-running audit effort. Therefore the journal actor
  records the required semantic route `frontier/xhigh`, not a fabricated observed selector.
- `harness doctor` returned 0 but diagnosed a stale global run-report hook
  (`run-report.py`, `_lib.py`, `_usage.py`). The audit did not mutate global user configuration;
  P1.2 must not treat hook-derived telemetry as trustworthy until its own preflight is green or it
  explicitly relies only on journal/git evidence.
- The installed cached `core:plan-protocol` is stale relative to the repository SSOT:
  `df7b9cf1…` (v2.23.0, 1363 lines) versus `5ceaec0b…` (v2.24.0, 281 lines). This audit used the
  worktree-local canonical v2 skill and `references/plan-layout-v2.md`, as required by repository
  provenance rules.
- No implementation completion, package code correctness, or git history claim was audited in
  `design` mode. The Task Contract compiler was run only as the plan's deterministic admission
  gate.

### Что запускать

**Next:** design-finish: task:plan-design 2026.08.10-TASK-LEAN-AUTONOMY finish

**Provider-neutral plan-protocol launch block**

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | `cold-start-root` |
| Суть | reason=`owner-pause-no-resume`; bounded remediation of F1–F10, no P0/P1 execution |
| Команда | `$ task:plan-design 2026.08.10-TASK-LEAN-AUTONOMY finish` |

```text
$ task:plan-design 2026.08.10-TASK-LEAN-AUTONOMY finish

РЕЖИМ: whole-plan design-finish remediation, НЕ execution и НЕ phase reopen
ВХОД: plans/2026.08.10-TASK-LEAN-AUTONOMY/findings/03-design-audit-2026-08-10.md → блок `## Audit design — 2026-08-10`; прочитать ПЕРВЫМ
СКОУП: 1) split invalid cross-phase Routing and make 4/4 Task Contracts build 2) replace prose Validation with exact commands and per-item package validate 3) reconcile S1/S2 with package-cwd launches 4) seal P1.1/P1.2 Files and stabilization admission 5) define GO/ADJUST status+Next 6) restore literal design-pass journal provenance 7) add D1–D6 actor/model and evidence links 8) render complete neutral+native group launches 9) minimize/regenerate bundles with measured budget 10) commit reviewed carriers and rerun final gates
НЕ ТРОГАТЬ: не выполнять P0/P1; не менять package/product code; не ослаблять D1–D6 safety/authority/public semantics; не hand-edit generated state/status/decision/bundle views; не включать и не откатывать чужие изменения ARTIFEX/docs/roadmap вне явно принятого remediation scope
```

**Native Codex launch block**

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-sol | high | `cold-start-root` (`owner-pause-no-resume`) | Remediate F1–F10 through design-finish; no item execution | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.08.10-TASK-LEAN-AUTONOMY finish'` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.08.10-TASK-LEAN-AUTONOMY finish

РЕЖИМ: whole-plan design-finish remediation, НЕ execution и НЕ phase reopen
ВХОД: plans/2026.08.10-TASK-LEAN-AUTONOMY/findings/03-design-audit-2026-08-10.md → блок `## Audit design — 2026-08-10`; прочитать ПЕРВЫМ
СКОУП: 1) split invalid cross-phase Routing and make 4/4 Task Contracts build 2) replace prose Validation with exact commands and per-item package validate 3) reconcile S1/S2 with package-cwd launches 4) seal P1.1/P1.2 Files and stabilization admission 5) define GO/ADJUST status+Next 6) restore literal design-pass journal provenance 7) add D1–D6 actor/model and evidence links 8) render complete neutral+native group launches 9) minimize/regenerate bundles with measured budget 10) commit reviewed carriers and rerun final gates
НЕ ТРОГАТЬ: не выполнять P0/P1; не менять package/product code; не ослаблять D1–D6 safety/authority/public semantics; не hand-edit generated state/status/decision/bundle views; не включать и не откатывать чужие изменения ARTIFEX/docs/roadmap вне явно принятого remediation scope'
```
