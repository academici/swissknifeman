# Exceptional design audit — 2026.07.24-AGENT-RELIABILITY — attempt 3

**Date:** 2026-07-25
**Mode:** fresh cold-context adversarial pre-execution design audit
**Verdict: RED**

`AUDIT-CAP: historical 2/2 exhausted; exceptional 1/1 consumed`.

This verdict ends the exceptional audit session. It does not authorize P0.1,
plan repair, another redesign pass, or another audit.

## Anchor and deterministic checks

- Audited commit:
  `f299d6c91fe1de5b3d301496e0858834a2511ebc`
  (`docs(plan): ограничить authority после design audit`).
- Effective session: `gpt-5.6-sol/xhigh`, approval `never`, sandbox
  `danger-full-access`, repository cwd correct.
- `codex doctor --json`: overall `ok`; every effective global/project hook
  command existed and was executable; synthetic SessionStart, PreToolUse and
  SubagentStop probes returned `0`.
- `./packages/maind/bin/maind health --cwd --json`: project scope connected,
  memory roundtrip and both MCP paths green.
- Immutable source-evidence verifier modes `verify`, `map-state`,
  `verify-results`, and `verify-claim-inventory`: exit `0` (20 manifest
  entries, seven journals, five minimized cases, eight claim ranges).
  `git diff 0436d7c5..HEAD` and the working-tree diff for the bundle were empty.
- Package validation was green: task `228` tests, skiller `418`, harness `412`,
  analyst `211`, and maind `490`; `git diff --check` returned `0`.
- Scoped plan-lint before audit writes:
  `OK (1 plan, 0 errors, 0 warnings)`.
- The pre-existing archive moves and `tmp/` are unrelated user-owned state and
  were preserved.

There was no environment blocker affecting this verdict.

## Findings

### F1 — Four generated-scope gates depend on an undefined item baseline

- **Severity:** Blocker
- **Label:** issue
- **Items:** P1.2, P1.3, P2.2, P2.3
- **Evidence:** `phases/P1.md:57,76`; `phases/P2.md:59,78`; repository-wide
  search outside immutable evidence found no definition or producer for
  `ITEM_BASE_SHA`.
- **Failure scenario:** all four item validations call
  `assert_generated_scope.py --baseline "$ITEM_BASE_SHA"`. Neither the item
  contracts, roadmap recovery carriers, task commands, nor plan protocol
  freezes or exports that value. A cold executor therefore cannot run the
  literal validation deterministically: it must either pass an empty value or
  invent which commit is the item baseline. The guard is load-bearing for
  private-bucket leakage, target completeness, version/tree consistency,
  undeclared generated drift, and no-op regeneration.
- **Impact:** the repaired F2 publication transaction cannot reach an honest
  deterministic GREEN without improvising outside its frozen specification.

### F2 — Two items require reading artifacts that do not exist until the same item creates them

- **Severity:** Blocker
- **Label:** issue
- **Items:** P2.3, P3.4
- **Evidence:** `phases/P2.md:74-75` lists the absent
  `packages/task/lib/task/review_policy.py` in both P2.3 Files and Required
  Reads, with no predecessor producing it. `phases/P3.md:91-92` likewise lists
  absent `artifacts/P3.4/canary-cases.json` in both P3.4 Files and Required
  Reads.
- **Failure scenario:** Required Reads are cold-start prerequisites and must be
  consumed before mutation. These two prerequisites can only appear after the
  item begins authoring its own Files, so the declared execution order is
  impossible as written.
- **Impact:** the review-loop enforcement item and disposable-worktree canary
  are not execution-ready even though their downstream intent is otherwise
  specified.

### F3 — P1.1 can close without validating its exact 13-source bootstrap map

- **Severity:** Major
- **Label:** issue
- **Item:** P1.1
- **Evidence:** `phases/P1.md:34,36-39`. The exact
  `repository-bootstrap-map.json` is a required deliverable and P1.2 input, but
  P1.1 Validation only compiles two scripts, builds the effective inventory and
  remediation map, validates those two JSON files, and runs plan-lint. It does
  not parse, schema-check, count, or semantically validate the bootstrap map,
  and the named inventory command has no bootstrap-map output argument.
- **Failure scenario:** malformed, incomplete, or wrongly resolved seed
  ownership can pass every declared P1.1 command and be discovered only after
  the publication mutation item starts.
- **Impact:** the exact 13-source/26-target ownership freeze is described but
  is not itself a deterministic P1.1 acceptance gate.

## Repaired threads that passed this audit

The historical RED findings remain historical facts; this audit does not
relabel them. The Pass 4 redesign did substantively close their original
structural gaps:

- **Historical F1:** P0.1 now keeps the committed verifier's claims narrow and
  assigns semantic proof to a new stdlib verifier, closed proof classes,
  explicit algorithms/inputs, mutation tests, and a deterministic report.
  Excluded raw-rollout dedup/classifier quantities remain
  `pinned-not-recomputable` or `unknown`.
- **Historical F2:** P1 now names all 13 migration seeds and bilingual private
  canonical targets, source-only publication semantics, the sole
  `registry.py`→`publication.py` producer, 26 thin root targets, combined
  version/tree lock, consumer vendor/connect rejection, and P1.4 cold
  exactly-once closure. Current source seams can host that design.
- Authority is correct throughout v1.6.1: every exceptional verdict stops;
  audit GREEN would still have required separate Owner `G-EXEC`.
- Structural sweep: 21/21 item headings contain all 16 required fields;
  roadmap rows and native recovery carriers are 21/21; all are explicitly solo
  and dependency-ordered. No undeclared parallel workflow is required.
- Predecessor-produced Required Reads are otherwise reachable, Files are
  explicit, model/effort routing matches the roadmap, and Owner gates remain
  limited to A0, G-EXEC, G0, and G1.

Those positives do not override the three execution-readiness findings above.

## Terminal Owner boundary

`AUDIT-CAP: historical 2/2 exhausted; exceptional 1/1 consumed`.

| Parameter | Value |
|:--|:--|
| Native model | `gpt-5.6-sol` |
| Reasoning effort | `xhigh` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |
| Purpose | Owner decision only: stop the plan or explicitly grant new bounded repair/audit authority |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access 'NEW SESSION Owner decision boundary for 2026.07.24-AGENT-RELIABILITY after exceptional independent design audit attempt 3 RED. AUDIT-CAP: historical 2/2 exhausted; exceptional 1/1 consumed. Do not execute P0.1, repair the plan, modify packages/runtime/docs, or start another audit. Read AGENTS.md, CLAUDE.md, plans/2026.07.24-AGENT-RELIABILITY/brief/01-refinements.md, findings/08-design-audit-red-attempt-2.md, findings/09-design-audit-exceptional-attempt-3.md, plan.md, phases/P1.md, phases/P2.md, phases/P3.md, roadmap.md, handoff.md, and journal.jsonl. Present Dmitry Vostrikov only the terminal choice: stop/kill the plan, or explicitly grant a new bounded authority that names the permitted repair scope and any later independent audit. Record no implementation, fleet, consumer, FOREMAN, release, tag, push, or further audit action without that explicit Owner decision.'
```
