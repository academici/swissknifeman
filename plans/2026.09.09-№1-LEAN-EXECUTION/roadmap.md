# Roadmap исполнения — 2026.09.09-№1-LEAN-EXECUTION

<!-- Живая execution map, не второй план. Routing §3, item specs, owner gates и material-review
     triggers остаются авторитетными; фактический handoff пересчитывает readiness и Context. -->

**Обновлён:** 2026-09-09 · **Соответствует plan.md:** v1.0.2 · **Design:** pass 3/3 + bounded
F1–F4 remediation + owner P7 correction · **Статус:** ready for grouped P1.1–P1.3 execution under D13.

## Правило группировки

- Sequence is `P1 → P2 → P3 → P4 → P5 → P6 → P7`; no batch crosses a phase close boundary.
- `plan.md §3 Routing` owns Batch, route, Exec and Review. This roadmap renders, but never
  overrides, those declarations.
- Adjacent items keep separate validation, product commit and close evidence inside one admitted
  suffix. A later handoff derives the remaining suffix from durable state.
- Every `plan-run` launch requires `skills.repository`, filesystem read/write and git read/write.
  Item-specific provider or package tools are admitted only after their item preflight.
- P1 starts in a fresh root because this design root is terminal. P2–P7 phase
  starts use a fresh root when the preceding low-route phase-close root cannot satisfy the next
  route (`capability-missing`). P6.2–P6.4 continue in the already frontier/high P6.1 root.
- No launch below authorizes tag, push, release, deployment or consumer-project rollout.

## Карта исполнения

| Items | Batch | Exec | Model class/Effort | Review | Gate | Reuse / boundary |
|:--|:--|:--|:--|:--|:--|:--|
| P1.1–P1.3 | B-P1-ECONOMY | plan-run | implementation/high | full | D13 owner continuation; scoped plan lint green | one input→batch→continuity chain; shared Task compiler/renderer validation |
| P2.1–P2.3 | B-P2-CONTINUE | plan-run | implementation/high | full | terminal P1 close | one repair/readiness lifecycle, then narrow archive dependency removal |
| P3.1–P3.4 | B-P3-ASSURANCE | plan-run | implementation/high max | full | terminal P2 close; owner only for third full audit | one candidate lineage and shared routing/gate/receipt/anchor fixtures |
| P4.1–P4.2 | B-P4-TERMINAL | plan-run | implementation/high | full | terminal P3 close | Task policy then thin Harness adapters and bounded provider proof |
| P5.1–P5.3 | B-P5-GAPS | plan-run | implementation/high max | full | terminal P4 close; later owner D# only for a new template family | description/workflow evidence plus exact Laravel isolation; shared Skiller registry/docs validation |
| P6.1 | solo | plan-run | frontier/high | full | terminal P5 close; repository mutation forbidden | native source/case/baseline freeze is an epistemic hard boundary |
| P6.2–P6.4 | B-P6-CODEX | plan-run | frontier/high max | full | terminal P6.1; D12 deterministic reducer gate | evaluator→one verdict→qualification; one candidate maximum |
| P7.1 | solo | plan-run | implementation/high | none | terminal P6 close; D13 + P3 assurance outputs | one vertical whole-plan design-completion circuit breaker; deterministic close without audit |

## Native launch-blocks

The persisted handoff now names B-P1-ECONOMY directly. Later projections remain dormant until their
predecessor phase closes and the handoff names their current suffix.

### B-P1-ECONOMY — complete input, batch admission and continuity

| Параметр | Значение |
|:--|:--|
| Batch | B-P1-ECONOMY |
| Model class | implementation |
| Model | gpt-5.6-terra |
| Effort | high |
| Thinking | high |
| Review | full |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root: design-root-terminal |
| Суть | Execute P1.1–P1.3 as one admitted adjacent suffix with per-item close gates |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P1.1-P1.3'
```

### B-P2-CONTINUE — bounded repair and readiness lifecycle

| Параметр | Значение |
|:--|:--|
| Batch | B-P2-CONTINUE |
| Model class | implementation |
| Model | gpt-5.6-terra |
| Effort | high |
| Thinking | high |
| Review | full |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root: capability-missing |
| Суть | Execute P2.1–P2.3 through one reducer/readiness context and archive validation |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P2.1-P2.3'
```

### B-P3-ASSURANCE — proportional assurance and evidence reuse

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
| Суть | Execute P3.1–P3.4 over one candidate identity and shared validation fixtures |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P3.1-P3.4'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P4.1-P4.2'
```

### B-P5-GAPS — description debt, workflow-fleet evidence and Laravel isolation

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
| Суть | Produce two deterministic field reports and one exact Laravel isolation contract without foreign-tree mutation |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P5.1-P5.3'
```

### solo — P6.1 native source and baseline freeze

| Параметр | Значение |
|:--|:--|
| Batch | solo |
| Model class | frontier |
| Model | gpt-5.6-sol |
| Effort | high |
| Thinking | high |
| Review | full |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root: capability-missing |
| Суть | Freeze observed Codex source/case/baseline evidence without product mutation |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P6.1'
```

### B-P6-CODEX — evaluator, one verdict and qualification

| Параметр | Значение |
|:--|:--|
| Batch | B-P6-CODEX |
| Model class | frontier |
| Model | gpt-5.6-sol |
| Effort | high |
| Thinking | high |
| Review | full |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | continue-root |
| Суть | Continue from terminal P6.1 with P6.2–P6.4; D12 admits at most one declared change |

**Native Codex command (same authoritative root):**

```text
$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P6.2-P6.4
```

### solo — P7.1 whole-plan design completion circuit breaker

| Параметр | Значение |
|:--|:--|
| Batch | solo |
| Model class | implementation |
| Model | gpt-5.6-terra |
| Effort | high |
| Thinking | high |
| Review | none |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | cold-start-root: capability-missing |
| Суть | Implement and qualify one deterministic ATTENTION-remediation→execution continuation; close P7 without a separate audit |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.09-№1-LEAN-EXECUTION P7.1'
```

## Decision and authority gates

| Gate | Kind | Exact effect |
|:--|:--|:--|
| Third full audit in one evidence lineage | owner authority | Blocks only that third full audit; delta and gate-rebind remain available. |
| New workflow template family or mandatory stage-matrix change from P5.2 | owner D# | Blocks template mutation; the report-only verdict may close without it. |
| D12 in P6.3 | deterministic D11 reducer record, not owner approval | `change` plus complete valid D11 evidence admits only the predeclared canonical mutation; `retain` or `insufficient` admits no delivery mutation. |
| Repeat whole-plan design audit after bounded ATTENTION remediation | D13 now; P7.1 deterministic policy later | No automatic repeat from remediation/bookkeeping. A new audit requires a concrete new material boundary or explicit owner request. |
| Tag, push, release, deployment or consumer rollout | owner authority outside this plan | Blocks every external/release side effect; local plan execution and qualification remain allowed. |

## Current handoff

The current action is exactly B-P1-ECONOMY P1.1–P1.3 using the native command sealed above. D13
ends the repeat whole-plan design-audit loop without rewriting the ATTENTION verdict. No
intermediate audit, design pass or single-item launch is scheduled.
