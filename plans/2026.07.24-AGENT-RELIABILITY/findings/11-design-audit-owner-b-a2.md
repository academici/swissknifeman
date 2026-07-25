# Design audit A2 — Owner option B — RED

**Date:** 2026-07-25  
**Audit target:** committed tree
`916acdb5e46322c102bd6c4b0f714ca3f7decc96` only  
**Mode:** fresh independent full-plan design audit; no repair; no execution  
**Verdict:** **RED**

`AUDIT-CAP: historical design 2/2 exhausted; exceptional attempt 3 1/1 consumed; Owner-B post-redesign A2 1/1 consumed.`

This verdict consumes the only Owner-B A2 slot. It does not authorize a
repair, another audit, P0.1, or any other plan item. Control returns to the
Owner.

## Scope and environment

The audit used a detached clean worktree pinned to the target SHA. Concurrent
uncommitted artifacts in the main worktree, including
`findings/10-design-audit-a1-attempt-4.md`, were excluded from evidence and
preserved.

Cold-start checks were green:

- effective audit route: `gpt-5.6-sol/xhigh`, approval `never`, sandbox
  `danger-full-access`, correct repository cwd;
- `codex doctor --json`: overall `ok`;
- registered hook commands existed and were executable; safe synthetic probes
  passed, and the live PreToolUse path rejected a destructive-pattern probe;
- `maind health --cwd --json`: connected to `project:swissknifeman`, memory
  roundtrip and both MCP paths green;
- immutable source-evidence verifier: 20 manifest entries, seven journals,
  five sanitized cases and eight claim ranges; all four verifier modes exited
  `0`;
- scoped lint at the audited SHA:
  `plan-lint: OK (1 plan, 0 errors, 0 warnings)`;
- `git diff --check 916acdb5^..916acdb5`: clean.

No environment defect affected the verdict.

## Findings

### F1 — The D36 baseline order conflicts with the canonical executor order

- **Severity:** Blocker
- **Label:** issue
- **Items:** P1.2, P1.3, P2.2, P2.3
- **Evidence:** `plan.md:191`; `phases/P1.md:55,74`;
  `phases/P2.md:57,76`; `roadmap.md:206,227,290,311`;
  `packages/task/commands/plan-exec.md:16-23,53-63`;
  `packages/task/commands/plan-run.md:9-10,31-32`.
- **Failure scenario:** D36 and every affected item/recovery carrier require
  `base-sha.txt` capture after Required Reads and before any other item-owned
  write. The canonical executor instead requires item/phase status writes and
  an `in-progress` journal append before entering Implementation Rules, where
  the capture command lives; `plan-run` imports that order verbatim. A literal
  cold executor cannot satisfy both contracts and must decide which
  load-bearing rule to violate. The helper's `--capture-or-verify` mode also
  treats an absent carrier plus clean owner paths as a new capture and has no
  explicit start/resume or predecessor-SHA binding, so a clean resume missing
  the carrier can silently establish a later `HEAD` as the generated-scope
  baseline.
- **Impact:** the exact diff-scope proof for four publication/compiler items is
  not execution-ready under the repository's own canonical command. A wrong
  baseline can omit earlier committed item changes from leakage,
  completeness, tuple/tree and undeclared-drift checks.

### F2 — The declared autonomous multi-session chain has no workflow carrier

- **Severity:** Blocker
- **Label:** issue
- **Items:** roadmap; phases P0–P4, explicitly P2
- **Evidence:**
  `packages/skiller/skills/general/plan-protocol/SKILL.md:466-480`;
  `roadmap.md:5-15,55-75`; `phases/P2.md:5-16`; the audited tree contains
  zero files under `plans/2026.07.24-AGENT-RELIABILITY/workflows/`.
- **Failure scenario:** the roadmap and P2 contract promise that a persistent
  root supervisor automatically delegates each next item, crosses sequential
  item boundaries and continues without Owner relay. Canon requires a workflow
  script and a handoff `scriptPath` when a phase declares a long autonomous
  chain carrying external state for longer than one executor session; manual
  item-by-item execution is then explicitly illegal. All 21 roadmap rows are
  `solo`, and the only carriers are per-item recovery commands with
  `command.subagents`; there is no durable orchestration identity, ordered
  workflow, or workflow resume path.
- **Impact:** after root context/session loss the promised autonomous chain can
  stop and fall back to Owner-mediated per-item recovery—the exact premature
  stop and carrier fragmentation contour this plan is intended to eliminate.
  The phase is not ready under the binary orchestration DoR gate.

### F3 — Authored research does not carry the required layer-1 provenance

- **Severity:** Major
- **Label:** issue
- **Items:** plan knowledge layer; consumers P0.1–P0.3 and P2
- **Evidence:**
  `packages/skiller/skills/general/plan-protocol/SKILL.md:1118-1138`;
  `research/01-root-cause-analysis.md:32-57,69-89`;
  `research/02-target-operating-model.md:3-24`;
  `research/03-metrics-and-experiment.md:3-21`. None of the three synthesis
  files references a `findings/` source or carries `[UNVERIFIED]` /
  `RAG:— (repo-grounded: …)`.
- **Failure scenario:** Research 01 presents observed incident facts and a
  causal synthesis, while Research 02/03 turn them into the operating model,
  corpus and metrics. Without direct layer-1 references or the required
  unverified/repo-grounded marker, a cold executor cannot reconstruct which
  raw telemetry/runtime/independent-review file supports each load-bearing
  statement or distinguish observation from authored proposal without
  redoing the authoring session's inference.
- **Impact:** the mandatory `brief → findings → research → decisions`
  provenance chain is not self-contained at the synthesis boundary. P0
  contract/corpus work can inherit an unsupported or misclassified premise.

## Repaired threads that passed

The historical findings remain historical facts; A2 does not relabel them.
The post-redesign contract did close two of the three specific attempt-3
threads:

- **D37 passed:** P2.3 `review_policy.py`/test and P3.4
  `canary-cases.json` are same-item Files/Deliverables, not Required Reads.
- **D38 passed:** P1.1 freezes the exact schema and record keys, sorted exact
  13-identity set, both seed path/hash records, bilingual canonical formulas,
  exact unique 26-target projection set, version/unit/generator/lock literals,
  explicit resolution, focused mutation cases and a deterministic
  `--check-bootstrap-map` validation.

Additional full-plan checks passed:

- 21/21 items have complete item fields, Routing rows, roadmap rows, semantic
  `Next`, `command.subagents` and native recovery blocks;
- zero `[NEEDS CLARIFICATION]` markers, wildcard Files or empty Code Guidance;
- all five phase contracts/handoffs exist;
- Required Reads producer reachability is complete after excluding explicitly
  same-item future-file mentions;
- provider/model mapping matches
  `packages/task/configs/command-routing.json`;
- the frozen brief, scope exclusions, authority gates, evaluation/canary
  contours, release/fleet boundaries and all-items-not-started state are
  preserved.

Those positives do not offset the execution-readiness and provenance defects
above.

## Terminal boundary

**RED.** A2 ends here. No item was executed and no repair was attempted.

`AUDIT-CAP: historical design 2/2 exhausted; exceptional attempt 3 1/1 consumed; Owner-B post-redesign A2 1/1 consumed.`

Only the Owner may now choose to stop/kill the plan or grant a new, explicit,
bounded authority. There is no implicit fix-forward or further-audit authority.
