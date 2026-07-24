# Roadmap исполнения — 2026.07.24-AGENT-RELIABILITY

**Обновлён:** 2026-07-24 · **Соответствует plan.md:** v1.5.0

Этот roadmap — cold-recovery console. При живом root supervisor владелец не
перезапускает команды: root после каждого green close/audit автоматически
берёт следующий ready item и делегирует его свежему subagent из committed
`plan.md`/`handoff.md`. Последовательные зависимости идут по одному. Native
blocks ниже нужны для нового процесса/session recovery и всегда начинают
`NEW SESSION`. Поэтому таблицы разделяют `Plan context` (canonical enum
`same-session — item` для root supervisory cycle) и native `Context`
(`NEW SESSION` при recovery). `command.subagents` обязателен для каждого
carrier по D22; cold-start preflight проверяет
`packages/task/configs/command-routing.json` (`codex.command.subagents =
native`) и live `codex doctor --json` (`multi_agent` enabled). Любое
несовпадение fail-closed до mutation без solo fallback.

## Provider-neutral carrier и deterministic rendering

Canonical SSOT — `plan.md` Routing, item specs и semantic `Next` lines.
Таблица ниже — проверенная projection из
`packages/task/configs/command-routing.json`; provider меняет selector и
invocation prefix, но не PLAN-ID, item, effort, capabilities, plan context,
Required Reads или authority gate.

| Semantic datum | Claude renderer | Codex renderer |
|:--|:--|:--|
| `implementation` | `sonnet` | `gpt-5.6-terra` |
| `frontier` | `opus` | `gpt-5.6-sol` |
| effort | exact `low/medium/high/xhigh` | exact `low/medium/high/xhigh` |
| `exec-items: task:plan-exec <ID> <item>` | `/task:plan-exec <ID> <item>` | `$ task:plan-exec <ID> <item>` |
| `run-items: task:plan-run <ID> <item>` | `/task:plan-run <ID> <item>` | `$ task:plan-run <ID> <item>` |
| `command.subagents` | `native` | `native` + live `multi_agent` preflight |

All canonical paths are repository-relative and visible to either provider.
`plans/<ID>/root/` is the plan's long-lived artifact directory, not OS
`/root`. The 21 Codex blocks remain mandatory local recovery projections
under root `AGENTS.md`; Claude renders the adjacent semantic `Next` through
this table instead of copying a Codex shell command. All execution-required
historical evidence is committed under `artifacts/source-evidence/`; origin
profiles, `tmp/`, foreign repositories and mAInd are never evidence inputs.

## Карта исполнения

| Item | Batch | Запуск | Model/Thinking | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1 | solo | task:plan-exec | implementation/medium → gpt-5.6-terra/medium | — | Нельзя объединить: baseline должен быть отдельным committed anchor до contract design |
| P0.2 | solo | task:plan-run | frontier/high → gpt-5.6-sol/high | — | Нельзя объединить: frozen Task Contract, Review=full |
| P0.3 | solo | task:plan-run | frontier/high → gpt-5.6-sol/high | G0 — approve bank/grader/baseline hashes and floors | Нельзя объединить: frozen Acceptance + реальный Owner decision в конце |
| P0.4 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | G0 precondition from P0.3, not a new stop | Нельзя объединить: первая live behavior mutation, hook rollback |
| P1.1 | solo | task:plan-run | frontier/high → gpt-5.6-sol/high | — | Нельзя объединить: identity/ownership freeze, Review=full |
| P1.2 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | — | Нельзя объединить: skiller/root/core publication correctness, Review=full |
| P1.3 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | — | Нельзя объединить: task/harness effective catalog changes after P1.2 |
| P1.4 | solo | task:plan-exec | implementation/medium → gpt-5.6-terra/medium | — | Нельзя объединить: terminal installed-runtime conformance must independently test P1.2/P1.3 |
| P2.1 | solo | task:plan-run | frontier/high → gpt-5.6-sol/high | — | Нельзя объединить: state/authority contract freeze, Review=full |
| P2.2 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | — | Нельзя объединить: central compiler/root dispatch seam, Review=full |
| P2.3 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | — | Нельзя объединить: audit/reopen/cap enforcement must be isolated from compiler |
| P2.4 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | — | Нельзя объединить: actual route evidence has separate fail-closed boundary |
| P2.5 | solo | task:plan-exec | implementation/medium → gpt-5.6-terra/medium | — | Нельзя объединить: terminal immutable-bank proof after all P2 code |
| P3.1 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | — | Нельзя объединить: cross-provider trace schema/version, Review=full |
| P3.2 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | — | Нельзя объединить: metric arithmetic consumes frozen trace |
| P3.3 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | — | Нельзя объединить: behavioral release gate consumes trace+metrics |
| P3.4 | solo | task:plan-run | implementation/high → gpt-5.6-terra/high | — | Нельзя объединить: disposable worktree, native trials and rollback |
| P3.5 | solo | task:plan-run | frontier/xhigh → gpt-5.6-sol/xhigh | — | Нельзя объединить: fresh independent terminal audit |
| P4.1 | solo | task:plan-run | frontier/high → gpt-5.6-sol/high | — | Нельзя объединить: open accept/reject/unknown architecture verdict |
| P4.2 | solo | task:plan-exec | implementation/medium → gpt-5.6-terra/medium | — | Нельзя объединить: lower-route one-package doctor after P4.1 |
| P4.3 | solo | task:plan-run | frontier/high → gpt-5.6-sol/high | G1 — fleet/consumer/FOREMAN/tag/push/release go or hold | Нельзя объединить: final synthesis and external authority boundary |

## Готовые native Codex NEW SESSION launch-blocks

### P0.1 — verify committed manifests, corpus и baseline

**Next:** exec-items: task:plan-exec 2026.07.24-AGENT-RELIABILITY P0.1

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `medium` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `medium` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="medium"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P0.1. Read AGENTS.md, CLAUDE.md and the task:task-plan-exec skill completely; run pwd, git status --short, codex doctor --json, effective hook command integrity, ./packages/maind/bin/maind health --cwd --json, python3 plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/verify_source_bundle.py verify --root plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence, and python3 packages/task/scripts/plan-lint.py plans/2026.07.24-AGENT-RELIABILITY. Read plan.md, roadmap.md, handoff.md, phases/P0.md and P0.1 Required Reads. Root supervises and delegates P0.1 to a fresh subagent grounded from committed plan/handoff. Execute only P0.1 from committed bundle inputs; never scan tmp, profiles, mAInd or foreign repositories for evidence; preserve unrelated diffs; do not mutate packages/hooks/consumers/FOREMAN. Close through task-plan-exec and automatically continue according to roadmap only after green.'
```

### P0.2 — Task Contract v1

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P0.2

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-sol` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P0.2. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight from AGENTS.md. Read plan.md, roadmap.md, handoff.md, phases/P0.md and P0.2 Required Reads; verify committed P0.1 green. Root delegates only P0.2 to a fresh grounded subagent under frontier/high. Produce and close Task Contract v1; no package or hook mutation. Continue automatically to P0.3 after green.'
```

### P0.3 — Acceptance v1 и G0

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P0.3

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-sol` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P0.3. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P0.md and P0.3 Required Reads; verify committed P0.1/P0.2 green. Root delegates P0.3 to a fresh grounded subagent. Freeze exact bank/grader/baseline hashes and proposed floors, then stop at G0 for Dmitry Vostrikov approval. Do not execute P0.4 or mutate behavior before an explicit Owner D#.'
```

### P0.4 — hook lifecycle

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P0.4

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P0.4. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P0.md and P0.4 Required Reads. Verify an explicit Owner D# approves the exact P0.3 hashes/floors; if absent, do no writes. Root delegates P0.4 to a fresh grounded subagent. Repair only self-host hook owners/files, prove cold/live paths and rollback, preserve cached compatibility until restart proof, then close and continue automatically.'
```

### P1.1 — identity/ownership freeze

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P1.1

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-sol` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.1. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P1.md and P1.1 Required Reads; verify terminal P0. Root delegates P1.1 to a fresh grounded subagent. Freeze identity/ownership/capability plus the D27 version/generated-tree ledger and exact D28 12-directory deletion map; approve the per-publication-unit skiller version seam, but do not edit runtime sources. Close and continue automatically.'
```

### P1.2 — skiller/root/core publication

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P1.2

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.2. Read AGENTS.md, CLAUDE.md, packages/skiller/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P1.md and P1.2 Required Reads; verify committed P1.1. Root delegates P1.2 to a fresh grounded subagent. Implement only exact map records: add per-unit versions, bump skiller API plus core/skm to 0.4.1, regenerate their complete declared trees, prove the second check/no hidden manifest drift, then delete the exact six root core collisions after bundle/marketplace proof. Validate scope, close, continue.'
```

### P1.3 — task/harness projection and dedup

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P1.3

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.3. Read AGENTS.md, CLAUDE.md, packages/task/CLAUDE.md, packages/harness/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P1.md and P1.3 Required Reads; verify committed P1.2. Root delegates P1.3 to a fresh grounded subagent. Reuse existing command_render APIs through the thin worktree-local front; bump task to 0.3.1 and harness versions per D27, regenerate complete task locks/tree/marketplaces, prove a read-only second check, then delete all six exact root task collision directories and update AGENTS bootstrap ownership. Preserve task semantics and Claude compatibility; validate scope, close, continue.'
```

### P1.4 — effective-runtime conformance

**Next:** exec-items: task:plan-exec 2026.07.24-AGENT-RELIABILITY P1.4

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `medium` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `medium` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="medium"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.4. Read AGENTS.md, CLAUDE.md and task:task-plan-exec completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P1.md and P1.4 Required Reads; verify P1.2/P1.3 committed green. Root delegates P1.4 to a fresh grounded subagent. Cold-install generated repository marketplaces into explicit temporary roots and discover the actual effective runtime; require all six core and six task semantic IDs exactly once with the 12 root duplicates absent. Do not write live fleet/cache; close through task-plan-exec and continue.'
```

### P2.1 — state/authority contract

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.1

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-sol` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P2.1. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P2.md and P2.1 Required Reads; verify terminal P1. Root delegates P2.1 to a fresh grounded subagent. Freeze total state/authority/review/fresh-dispatch contracts and negative cases only; no package edits. Close and continue.'
```

### P2.2 — compiler and root dispatch

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.2

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P2.2. Read AGENTS.md, CLAUDE.md, packages/task/CLAUDE.md, packages/skiller/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P2.md and P2.2 Required Reads; verify committed P2.1. Root delegates P2.2 to a fresh grounded subagent. Implement the independently-green compiler/fresh-item dispatch and the sole canonical protocol/command edit. Version first: plan-protocol 2.12.0, skiller API plus general/core units 0.5.0, task 0.4.0; regenerate exact full owned trees/locks/marketplaces, prove second checks and scope guard. Do not depend on P2.3 or add duplicate prose logic; close and continue.'
```

### P2.3 — finding/review enforcement

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.3

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P2.3. Read AGENTS.md, CLAUDE.md, packages/task/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P2.md and P2.3 Required Reads; verify committed P2.2 independently green. Root delegates P2.3 to a fresh grounded subagent. Extend the frozen compiler policy hook with typed findings/reopen/third-event incident; do not edit P2.2 commands or plan-protocol. Bump task runtime publication to 0.5.0, regenerate its complete adapters/locks/golden plugin/marketplaces while command bodies stay unchanged, prove second check and scope guard, close and continue.'
```

### P2.4 — route/budget evidence

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.4

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P2.4. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P2.md and P2.4 Required Reads; verify committed P2.2/P2.3. Root delegates P2.4 to a fresh grounded subagent. Capture actual route evidence without inference, fail closed on unknown required axes, validate task/harness/analyst, close and continue.'
```

### P2.5 — historical scenario proof

**Next:** exec-items: task:plan-exec 2026.07.24-AGENT-RELIABILITY P2.5

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `medium` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `medium` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="medium"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P2.5. Read AGENTS.md, CLAUDE.md and task:task-plan-exec completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P2.md and P2.5 Required Reads; verify P2.2-P2.4 committed. Root delegates P2.5 to a fresh grounded subagent. Run the exact immutable bank, write only result artifacts, route failures without recursive repair, close through task-plan-exec and continue.'
```

### P3.1 — Unified Trace v1

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P3.1

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P3.1. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P3.md and P3.1 Required Reads; verify terminal P2. Root delegates P3.1 to a fresh grounded subagent. Implement the one analyst-owned trace schema plus thin provider readers and task linkage, no external collector/reasoning storage, validate, close and continue.'
```

### P3.2 — reliability metrics

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P3.2

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P3.2. Read AGENTS.md, CLAUDE.md, packages/analyst/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P3.md and P3.2 Required Reads; verify committed P3.1. Root delegates P3.2 to a fresh grounded subagent. Implement denominator/provenance/completeness-aware metrics only from Unified Trace, validate, close and continue.'
```

### P3.3 — behavioral eval integration

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P3.3

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P3.3. Read AGENTS.md, CLAUDE.md, packages/skiller/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P3.md and P3.3 Required Reads; verify committed P3.1/P3.2. Root delegates P3.3 to a fresh grounded subagent. Adapt the immutable system bank without changing hashes/floors, validate skiller, close and continue.'
```

### P3.4 — disposable-worktree canary

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P3.4

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P3.4. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P3.md and P3.4 Required Reads; verify committed P3.1-P3.3. Root delegates P3.4 to a fresh grounded subagent. Use only task-specific CANARY_ROOT/CANARY_WT and codex -C with explicit native flags; never set HOME/CODEX_HOME or mutate global registries. Persist each detached case SHA+patch, rehearse clean switch rollback, refuse dirty cleanup, close only on exact evidence.'
```

### P3.5 — terminal reliability audit

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P3.5

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `xhigh` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-sol` |
| Thinking | `xhigh` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P3.5. Read AGENTS.md, CLAUDE.md and task:task-plan-run plus canonical plan-audit completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P3.md and P3.5 Required Reads. Root delegates the read-only terminal audit to a fresh grounded frontier/xhigh subagent. Recompute exact hashes/metrics/cold runtime/canary cleanup; write only canonical audit/bookkeeping. Return GREEN, REMEDIATE or ROLLBACK under existing cap and continue to P4 only on GREEN.'
```

### P4.1 — code-grounded hypothesis verdict

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P4.1

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-sol` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P4.1. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P4.md and P4.1 Required Reads; verify literal GREEN P3.5. Root delegates P4.1 to a fresh grounded subagent. Produce accept/reject/unknown code-grounded verdict artifacts only; do not implement accepted structural refactors. Close and continue.'
```

### P4.2 — effective source doctor

**Next:** exec-items: task:plan-exec 2026.07.24-AGENT-RELIABILITY P4.2

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `medium` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-terra` |
| Thinking | `medium` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="medium"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P4.2. Read AGENTS.md, CLAUDE.md, packages/skiller/CLAUDE.md and task:task-plan-exec completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P4.md and P4.2 Required Reads; verify P4.1 committed. Root delegates P4.2 to a fresh grounded subagent. Extend only the exact skiller read-only doctor Files, compose frozen P1/P3 outputs without duplicating ownership logic, prove no writes, close and continue.'
```

### P4.3 — docs and G1 Owner packet

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P4.3

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Plan context | `same-session — item` |
| Model | `gpt-5.6-sol` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P4.3. Read AGENTS.md, CLAUDE.md, release-discipline, docs-maintenance and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P4.md and P4.3 Required Reads; verify P4.1/P4.2 committed. Root delegates P4.3 to a fresh grounded subagent. Synchronize exact docs/changelog and build the measured self-host Owner packet. Run task renderer --check and skiller registry --check only; do not rewrite or re-version generated publications, and reopen the exact D27 owner on drift. Stop at G1; do not execute fleet/consumer/FOREMAN/tag/push/release.'
```

## Гейты владельца

| Gate | Где | Что утверждает | Блокирует |
|:--|:--|:--|:--|
| G0 | после P0.3 | exact bank/grader/baseline hashes and metric floors | P0.4–P4 |
| G1 | после P4.3 packet | exact external targets/actions: fleet, consumers, FOREMAN, tag, push, release — либо hold | external work outside this plan |
