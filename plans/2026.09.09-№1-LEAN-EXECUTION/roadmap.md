# Roadmap исполнения — 2026.09.09-№1-LEAN-EXECUTION

<!-- Живая execution map, не второй план. Routing §3, item specs, owner gates и material-review
     triggers остаются авторитетными; фактический handoff пересчитывает readiness и Context. -->

**Обновлён:** 2026-09-10 · **Соответствует plan.md:** v1.0.3 · **Design:** pass 3/3 +
D14 P7 redesign · **Статус:** P1/P2 terminal; P7.1 is the owner-prioritized next item before P3.

## Правило группировки

- Sequence is `P1 → P2 → P7 → P3 → P4 → P5`; no batch crosses a phase-close boundary.
- `plan.md §3 Routing` owns Batch, route, Exec and Review; this roadmap never overrides it.
- P7 is solo because it is a priority Task-core correction before later assurance work.
- P3.1–P3.2 remain one adjacent batch; P3.4 is a solo closure boundary because retired P3.3 leaves
  a concrete batch gap. P6.1–P6.4 were also unstarted and are retired by D14.
- Every `plan-run` requires repository skill, filesystem read/write and git read/write. No launch
  authorizes tag, push, release, deployment or consumer-project rollout.

## Карта исполнения

| Items | Batch | Exec | Model class/Effort | Review | Gate | Reuse / boundary |
|:--|:--|:--|:--|:--|:--|:--|
| P1.1–P1.3 | B-P1-ECONOMY | terminal | implementation/high | full | closed | admission/batch/continuity delivered |
| P2.1–P2.3 | B-P2-CONTINUE | terminal | implementation/high | full | closed with recorded deviations | repair/readiness/archive delivered; P2 audit cost is P7 evidence |
| P7.1 | solo | plan-run | implementation/high | light | D14; exact P7 DoR and byte budget | one deletion-led lifecycle slice before P3 |
| P3.1–P3.2 | B-P3-ASSURANCE | plan-run | implementation/high max | full | terminal P7 close; owner only for third full audit | one candidate/impact context; P7 owns normal validation selection |
| P3.4 | solo | plan-run | implementation/high | full | terminal B-P3-ASSURANCE close | evidence topology and finalization at a concrete batch boundary |
| P4.1–P4.2 | B-P4-TERMINAL | plan-run | implementation/high | full | terminal P3 close | Task policy then Harness adapters and bounded provider proof |
| P5.1–P5.3 | B-P5-GAPS | plan-run | implementation/high max | full | terminal P4 close; owner D# for a new template family | description/workflow evidence and Laravel isolation share registry/docs qualification |

## Native launch-blocks

### solo — P7.1 lean Task control loop

| Параметр | Значение |
|:--|:--|
| Batch | solo |
| Model class | implementation |
| Model | gpt-5.6-terra |
| Effort | high |
| Thinking | high |
| Review | light |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root: design-root-terminal |
| Суть | Consolidate and qualify the lean normal Task lifecycle before P3 |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P7.1'
```

### B-P3-ASSURANCE — proportional assurance and evidence topology

| Параметр | Значение |
|:--|:--|
| Batch | B-P3-ASSURANCE |
| Model class | implementation |
| Model | gpt-5.6-terra |
| Effort | high |
| Thinking | high |
| Review | full |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root: capability-missing |
| Суть | Execute adjacent P3.1–P3.2 over P7 lifecycle output and one candidate identity |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P3.1 P3.2'
```

### solo — P3.4 evidence graph and finalization

| Параметр | Значение |
|:--|:--|
| Batch | solo |
| Model class | implementation |
| Model | gpt-5.6-terra |
| Effort | high |
| Thinking | high |
| Review | full |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | continue-root |
| Суть | Close the evidence graph after the P3.1–P3.2 assurance batch |

**Same-session command:**

```text
$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P3.4
```

### B-P4-TERMINAL — terminal admission and provider adapters

| Параметр | Значение |
|:--|:--|
| Batch | B-P4-TERMINAL |
| Model class | implementation |
| Model | gpt-5.6-terra |
| Effort | high |
| Thinking | high |
| Review | full |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root: capability-missing |
| Суть | Land Task terminal policy before Harness translations and bounded provider proof |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P4.1 P4.2'
```

### B-P5-GAPS — description debt, workflow evidence and Laravel isolation

| Параметр | Значение |
|:--|:--|
| Batch | B-P5-GAPS |
| Model class | implementation |
| Model | gpt-5.6-terra |
| Effort | high |
| Thinking | high |
| Review | full |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root: capability-missing |
| Суть | Produce bounded cross-package field outputs without foreign-tree mutation |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P5.1 P5.2 P5.3'
```

## Decision and authority gates

| Gate | Kind | Exact effect |
|:--|:--|:--|
| Third full audit in one evidence lineage | owner authority | Blocks only that third full audit; delta and gate-rebind remain available. |
| New workflow template family or mandatory stage-matrix change from P5.2 | owner D# | Blocks template mutation; report-only verdict may close. |
| Security/auth, destructive migration, irreversible external action, payment/accounting, concurrency/shared state, public API/schema or low-confidence impact | P7 deterministic widening | Selects affected integration/full validation and at most one independent review path. |
| Tag, push, release, deployment or consumer rollout | owner authority outside this plan | Blocks every external/release side effect. |

## Current handoff

The current action is exactly solo P7.1 in a fresh implementation/high root. D14 retires P3.3 and
P6; no design audit or intermediate phase is scheduled before the priority fix.
