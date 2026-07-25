# Roadmap исполнения — 2026.07.24-AGENT-RELIABILITY

**Обновлён:** 2026-07-25 · **Соответствует plan.md:** v1.7.0 (acting provider — Claude, D32/D33)

Этот roadmap — cold-recovery console. При живом root supervisor владелец не
перезапускает команды: root после каждого green close/audit автоматически
берёт следующий ready item и делегирует его свежему subagent из committed
`plan.md`/`handoff.md`. Последовательные зависимости идут по одному. Native
blocks ниже нужны для нового процесса/session recovery и всегда начинают
`NEW SESSION`. Поэтому таблицы разделяют `Plan context` (canonical enum
`same-session — item` для root supervisory cycle) и native `Context`
(`NEW SESSION` при recovery). `command.subagents` обязателен для каждого
carrier (D22/D33); acting provider — Claude Code: preflight проверяет
`packages/task/configs/command-routing.json` (`claude.command.subagents =
native`) и доступность Agent tool в сессии. Любое несовпадение
fail-closed до mutation без solo fallback.

**Pre-exec boundary:** historical cap `2/2` и exceptional slot B (attempt 3)
исчерпаны, все три verdict — RED. Owner authority C (D32) закрыла repair
F1–F3 и разрешает ровно один новый independent design audit A1 (`0/1`,
Claude frontier/xhigh: `/task:plan-audit 2026.07.24-AGENT-RELIABILITY design`).
Ни один item ниже, включая P0.1, не исполняется до literal GREEN A1 И
отдельного explicit Owner execution approval `G-EXEC`. Любой non-GREEN
возвращает Owner decision без автоматического repair/audit.

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
| P0.1 | solo | task:plan-exec | implementation/medium → Claude sonnet/medium | A0 literal GREEN + отдельный explicit Owner `G-EXEC` | Нельзя объединить: immutable integrity + item-owned semantic proof-class report должны стать отдельным committed anchor до contract design |
| P0.2 | solo | task:plan-run | frontier/high → Claude opus/high | — | Нельзя объединить: frozen Task Contract, Review=full |
| P0.3 | solo | task:plan-run | frontier/high → Claude opus/high | G0 — approve bank/grader/baseline hashes and floors | Нельзя объединить: frozen Acceptance + реальный Owner decision в конце |
| P0.4 | solo | task:plan-run | implementation/high → Claude sonnet/high | G0 precondition from P0.3, not a new stop | Нельзя объединить: первая live behavior mutation, hook rollback |
| P1.1 | solo | task:plan-run | frontier/high → Claude opus/high | — | Нельзя объединить: identity/ownership freeze, Review=full |
| P1.2 | solo | task:plan-run | implementation/high → Claude sonnet/high | — | Нельзя объединить: 13 bilingual private sources + 26 root projections + core publication form one versioned generator transaction, Review=full |
| P1.3 | solo | task:plan-run | implementation/high → Claude sonnet/high | — | Нельзя объединить: task/harness effective catalog changes after P1.2 |
| P1.4 | solo | task:plan-exec | implementation/medium → Claude sonnet/medium | — | Нельзя объединить: terminal cold conformance independently proves 13 private source/projection closures and 12 installed-bundle dedups |
| P2.1 | solo | task:plan-run | frontier/high → Claude opus/high | — | Нельзя объединить: state/authority contract freeze, Review=full |
| P2.2 | solo | task:plan-run | implementation/high → Claude sonnet/high | — | Нельзя объединить: central compiler/root dispatch seam, Review=full |
| P2.3 | solo | task:plan-run | implementation/high → Claude sonnet/high | — | Нельзя объединить: audit/reopen/cap enforcement must be isolated from compiler |
| P2.4 | solo | task:plan-run | implementation/high → Claude sonnet/high | — | Нельзя объединить: actual route evidence has separate fail-closed boundary |
| P2.5 | solo | task:plan-exec | implementation/medium → Claude sonnet/medium | — | Нельзя объединить: terminal immutable-bank proof after all P2 code |
| P3.1 | solo | task:plan-run | implementation/high → Claude sonnet/high | — | Нельзя объединить: cross-provider trace schema/version, Review=full |
| P3.2 | solo | task:plan-run | implementation/high → Claude sonnet/high | — | Нельзя объединить: metric arithmetic consumes frozen trace |
| P3.3 | solo | task:plan-run | implementation/high → Claude sonnet/high | — | Нельзя объединить: behavioral release gate consumes trace+metrics |
| P3.4 | solo | task:plan-run | implementation/high → Claude sonnet/high | — | Нельзя объединить: disposable worktree, native trials and rollback |
| P3.5 | solo | task:plan-run | frontier/xhigh → Claude opus/xhigh | — | Нельзя объединить: fresh independent terminal audit |
| P4.1 | solo | task:plan-run | frontier/high → Claude opus/high | — | Нельзя объединить: open accept/reject/unknown architecture verdict |
| P4.2 | solo | task:plan-exec | implementation/medium → Claude sonnet/medium | — | Нельзя объединить: lower-route one-package doctor after P4.1 |
| P4.3 | solo | task:plan-run | frontier/high → Claude opus/high | G1 — fleet/consumer/FOREMAN/tag/push/release go or hold | Нельзя объединить: final synthesis and external authority boundary |

## Готовые native Codex NEW SESSION launch-blocks (historical projections)

> **D33:** acting provider — Claude Code. Блоки ниже — исторические
> Codex-projections авторинг-провайдера, их НЕ копировать. Claude-запуск
> рендерится из semantic carrier по таблице выше: `/model` (opus|sonnet) +
> `/effort` по Routing §3 → `/task:plan-exec <ID> <item>` или
> `/task:plan-run <ID> <item>` в НОВОЙ сессии из корня репо.

### P0.1 — verify immutable integrity + semantic closure

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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="medium"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P0.1. Read AGENTS.md, CLAUDE.md and task:task-plan-exec completely; run the canonical cold-start preflight and plan-lint. Verify both gates are committed: the sole exceptional design audit under D29 has literal GREEN and Dmitry Vostrikov has separately granted explicit G-EXEC authority to execute P0.1 after that verdict; otherwise do no writes and return the Owner execution boundary. Read plan.md, roadmap.md, handoff.md, the exceptional audit finding, phases/P0.md and P0.1 Required Reads. Root delegates only P0.1 to a fresh grounded subagent. Keep artifacts/source-evidence byte-identical; run all four immutable verifier modes, then implement the P0.1-owned source-evidence semantic contract/verifier/tests/report. Recompute only facts derivable from committed inputs and label excluded raw-session dedup/classifier claims pinned-not-recomputable or unknown, never verified. Never scan tmp, profiles, mAInd or foreign repositories; do not mutate packages/hooks/consumers/FOREMAN. Close only after bundle diff is empty and tests are green, then continue according to roadmap.'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.1. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, findings/08-design-audit-red-attempt-2.md, phases/P1.md and P1.1 Required Reads; verify terminal P0. Root delegates P1.1 to a fresh grounded subagent. Freeze identity/ownership/capability, D27 versions, exact D28 12 deletions and D31 13-record repository-bootstrap map: pinned migration seed hashes, private canonical RU/EN targets, two provider targets, publication.py generator, root-bootstrap@0.1.0 and combined lock. Prove build_registry indexes private skills while normal publication and consumer vendor/connect selection exclude them. Do not edit runtime sources; close and continue.'
```

### P1.2 — 13 private canonical skills + root/core publication

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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.2. Read AGENTS.md, CLAUDE.md, packages/skiller/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P1.md and P1.2 Required Reads; verify committed P1.1. Root delegates only P1.2 to a fresh grounded subagent. Materialize exactly 13 private repository-bootstrap SKILL.ru.md sources from pinned seeds, generate/stamp their EN canons, and test that registry indexes them but normal bucket/core/marketplaces and consumer vendor/connect selection exclude them. Version first: skiller/core/skm 0.4.1 and root-bootstrap 0.1.0. Extend the existing publication.py seam; registry.py must generate exactly 13 thin Claude plus 13 thin Codex root pointers and one combined source/rendered lock, never full copied bodies or skillset.py output; skillset.py may only enforce source-only consumer rejection. Regenerate the complete owned tree, prove registry --check no-op/unaffected units byte-identical, then delete exact six core root collisions after proof. Validate scope, close, continue.'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="medium"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.4. Read AGENTS.md, CLAUDE.md and task:task-plan-exec completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P1.md and P1.4 Required Reads; verify P1.2/P1.3 committed green. Root delegates P1.4 to a fresh grounded subagent. In explicit stdlib temporary roots, materialize each provider root projection, cold-install only normal repository marketplace bundles, discover/activate/resolve and behavior-smoke. Require 13 repository-bootstrap IDs exactly once from thin roots with canonical path/hash/version matching the lock and zero private marketplace entries; require six core plus six task IDs exactly once from installed bundles with all 12 duplicate roots absent. Do not write live fleet/cache; close through task-plan-exec and continue.'
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
| A0 | до G-EXEC | единственный exceptional independent design audit under D29; любой verdict завершает audit session | repair/audit beyond exceptional 1/1 |
| G-EXEC | после A0 GREEN, до P0.1 | explicit Owner execution approval; option B его не подразумевает | все 21 items |
| G0 | после P0.3 | exact bank/grader/baseline hashes and metric floors | P0.4–P4 |
| G1 | после P4.3 packet | exact external targets/actions: fleet, consumers, FOREMAN, tag, push, release — либо hold | external work outside this plan |
