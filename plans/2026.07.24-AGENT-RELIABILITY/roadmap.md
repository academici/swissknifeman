# Roadmap исполнения — 2026.07.24-AGENT-RELIABILITY

**Обновлён:** 2026-07-25 · **Соответствует plan.md:** v1.10.0 (neutral Routing SSOT; acting provider не назначен — native Codex-блоки суть recovery-проекции; bounded A3 repair и Owner authority E — D50–D55)

Этот roadmap — cold-recovery console. При живом root supervisor владелец не
перезапускает команды: root после каждого green close/audit автоматически
берёт следующий ready item и делегирует его свежему subagent из committed
`plan.md`/`handoff.md`. Последовательные зависимости идут по одному. Native
blocks ниже нужны для нового процесса/session recovery и всегда начинают
`NEW SESSION`. Поэтому таблицы разделяют `Plan context` (canonical enum
`same-session — item` для root supervisory cycle) и native `Context`
(`NEW SESSION` при recovery). `command.subagents` обязателен для каждого
carrier (D22); provider mapping проверяется в cold-start preflight как
`native`/`adapted`. Любое несовпадение fail-closed до mutation без solo
fallback. D33 остаётся историческим Claude assignment; D35 его supersedes.

**Exec boundary (действует с v1.10.0, Owner authority E / D50):** `G-EXEC`
**выдан** для self-host — P0–P3 исполняются без отдельного человеческого гейта,
старт с P0.1 по `handoff.md`. G0 (заморозка Acceptance после P0.3) принимает
агент D-записью. За владельцем остаётся ровно **G1** в P4.3: tag/push/release,
fleet и 17 подключённых проектов, запись в consumer-репозитории, продолжение
`2026.07.18-FOREMAN`. Персональное рационирование audit-слотов снято: шесть
исторических design-вердиктов (cap `2/2`, exceptional attempt 3, A1, A2, A3)
остаются literal RED как факты, а дальше действует канон plan-protocol «два
аудита на фазу, третий → решение», и вердикт выносит агент. Открытый названный
долг (три находки A2, A1 F11, зеркальная `Consumed`-строка ECO-OPT,
Claude-проекция `workflow-craft`, read-only измерение Claude enabled-set) старт
не блокирует и ведётся в `handoff.md`.

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
`/root`. The 22 Codex blocks remain mandatory local recovery projections
under root `AGENTS.md`; Claude renders the adjacent semantic `Next` through
this table instead of copying a Codex shell command. All execution-required
historical evidence is committed under `artifacts/source-evidence/`; origin
profiles, `tmp/`, foreign repositories and mAInd are never evidence inputs.

## Карта исполнения

| Item | Batch | Запуск | Model/Thinking | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1 | solo | task:plan-exec | implementation/medium | — (`G-EXEC` выдан authority E, D50) | Нельзя объединить: immutable integrity + item-owned semantic proof-class report должны стать отдельным committed anchor до contract design |
| P0.2 | solo | task:plan-run | frontier/high | — | Нельзя объединить: frozen Task Contract, Review=full |
| P0.3 | solo | task:plan-run | frontier/high | G0 — принимает агент D-записью (D50): bank/grader/baseline hashes и floors §8 с квалификатором D53 | Нельзя объединить: frozen Acceptance — терминальный freeze фазы |
| P0.4 | solo | task:plan-run | implementation/high | G0 precondition from P0.3, not a new stop | Нельзя объединить: первая live behavior mutation, hook rollback |
| P1.1 | solo | task:plan-run | frontier/high | — | Нельзя объединить: identity/ownership freeze, Review=full |
| P1.2 | solo | task:plan-run | implementation/high | — | Нельзя объединить: 13 bilingual private sources + 26 root projections + core publication form one versioned generator transaction, Review=full |
| P1.3 | solo | task:plan-run | implementation/high | — | Нельзя объединить: task/harness effective catalog changes after P1.2 |
| P1.5 | solo | task:plan-run | implementation/high | — | Нельзя объединить: закрытие newly measured collisions (4 `architect` root-дубля, class-B `workflow-craft`, core↔donor детектор) — отдельная versioned generator transaction; **исполняется ПЕРЕД P1.4** (D41) |
| P1.4 | solo | task:plan-exec | implementation/medium | — | Нельзя объединить: terminal cold conformance independently proves class-A/B source/projection closures и catalog-wide uniqueness; **последний item фазы, стартует только после green P1.5** |
| P2.1 | solo | task:plan-run | frontier/high | — | Нельзя объединить: state/authority contract freeze, Review=full |
| P2.2 | solo | task:plan-run | implementation/high | — | Нельзя объединить: central compiler/root dispatch seam, Review=full |
| P2.3 | solo | task:plan-run | implementation/high | — | Нельзя объединить: audit/reopen/cap enforcement must be isolated from compiler |
| P2.4 | solo | task:plan-run | implementation/high | — | Нельзя объединить: actual route evidence has separate fail-closed boundary |
| P2.5 | solo | task:plan-exec | implementation/medium | — | Нельзя объединить: terminal immutable-bank proof after all P2 code |
| P3.1 | solo | task:plan-run | implementation/high | — | Нельзя объединить: cross-provider trace schema/version, Review=full |
| P3.2 | solo | task:plan-run | implementation/high | — | Нельзя объединить: metric arithmetic consumes frozen trace |
| P3.3 | solo | task:plan-run | implementation/high | — | Нельзя объединить: behavioral release gate consumes trace+metrics |
| P3.4 | solo | task:plan-run | implementation/high | — | Нельзя объединить: disposable worktree, native trials and rollback |
| P3.5 | solo | task:plan-run | frontier/xhigh | — | Нельзя объединить: fresh independent terminal audit |
| P4.1 | solo | task:plan-run | frontier/high | — | Нельзя объединить: open accept/reject/unknown architecture verdict |
| P4.2 | solo | task:plan-exec | implementation/medium | — | Нельзя объединить: lower-route one-package doctor after P4.1 |
| P4.3 | solo | task:plan-run | frontier/high | G1 — fleet/consumer/FOREMAN/tag/push/release go or hold | Нельзя объединить: final synthesis and external authority boundary |

## Готовые native Codex NEW SESSION recovery launch-blocks

Блоки ниже — current local recovery projections по root `AGENTS.md`.
Semantic `Next`/neutral Routing остаются SSOT; другой provider рендерит тот
же carrier через проверенную mapping table без изменения payload.

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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="medium"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P0.1. Read AGENTS.md, CLAUDE.md and task:task-plan-exec completely; run the canonical cold-start preflight and plan-lint. Execution authority: G-EXEC was granted by Owner authority E and is recorded as D50 in plan.md and in plan.md section 10 — verify that record is committed and that plan.md is at version 1.10.0 or later before writing anything; if D50 is absent from the committed tree, stop and return the Owner boundary instead of executing. The six historical RED design verdicts are facts and do not block this item. As the first action of this item, capture the plan rollback baseline artifacts/P0.1/pre-plan-sha.txt per D45 (idempotent on resume, validated as a 40-hex commit and ancestor of HEAD) and commit it with the item Files. Otherwise do no writes and return the Owner execution boundary. Read plan.md, roadmap.md, handoff.md, the A2 audit report, phases/P0.md and P0.1 Required Reads. Root delegates only P0.1 to a fresh grounded subagent. Keep artifacts/source-evidence byte-identical; run all four immutable verifier modes, then implement the P0.1-owned source-evidence semantic contract/verifier/tests/report. Recompute only facts derivable from committed inputs and label excluded raw-session dedup/classifier claims pinned-not-recomputable or unknown, never verified. Never scan tmp, profiles, mAInd or foreign repositories; do not mutate packages/hooks/consumers/FOREMAN. Close only after bundle diff is empty and tests are green, then continue according to roadmap.'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P0.4. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P0.md and P0.4 Required Reads. Verify the G0 freeze record D59 (agent-recorded, D50) and the exact P0.3 hashes/floors in bank-manifest.json; if that record is absent, do no writes. Root delegates P0.4 to a fresh grounded subagent. Repair only self-host hook owners/files, prove cold/live paths and rollback, preserve cached compatibility until restart proof, then close and continue automatically.'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.1. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, findings/08-design-audit-red-attempt-2.md, findings/09-design-audit-exceptional-attempt-3.md, phases/P1.md and P1.1 Required Reads; verify terminal P0. Root delegates P1.1 to a fresh grounded subagent. Freeze identity/ownership/capability, D27 versions, exact D28 12 deletions and D38 bootstrap-map schema: exact sorted 13 identity set, both seed path/hash records, canonical RU/EN formulas, globally unique exact 26 Claude/Codex targets, literal version/unit/generator/lock and explicit resolution. Add focused mutation tests for every dimension. Produce the D36 baseline helper/owner scope map with exclusive capture, idempotent resume reuse and fail-closed invalid/dirty cases while preserving all generated-scope checks. Prove build_registry indexes private skills while normal publication and consumer vendor/connect selection exclude them. Do not edit runtime sources; close and continue.'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.2. Read AGENTS.md, CLAUDE.md, packages/skiller/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P1.md and P1.2 Required Reads; verify committed P1.1. Root delegates only P1.2 to a fresh grounded subagent. After Required Reads and before any other item-owned write, run the exact D36 P1.2 baseline --capture-or-verify command from Implementation Rules; on resume reuse the existing carrier byte-for-byte, never recapture, and fail closed on owner dirt/invalid SHA. Materialize exactly 13 private repository-bootstrap SKILL.ru.md sources from pinned seeds, generate/stamp their EN canons, and test that registry indexes them but normal bucket/core/marketplaces and consumer vendor/connect selection exclude them. Version first: skiller/core/skm 0.4.1 and root-bootstrap 0.1.0. Extend the existing publication.py seam; registry.py must generate exactly 13 thin Claude plus 13 thin Codex root pointers and one combined source/rendered lock, never full copied bodies or skillset.py output; skillset.py may only enforce source-only consumer rejection. Regenerate the complete owned tree, prove registry --check no-op/unaffected units byte-identical, then delete exact six core root collisions after proof. Obtain ITEM_BASE_SHA only through baseline --verify-and-print, run unchanged-strength generated-scope validation, close, continue. Treat every seam produced by plan 2026.07.19-DUAL-PROVIDER as a low-trust input per D54: its terminal status is orange with an ATTENTION item and it introduced the hand-written root adapters outside the generator, so prove current behaviour with a characterization test here before changing it and never inherit green from that plan.'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.3. Read AGENTS.md, CLAUDE.md, packages/task/CLAUDE.md, packages/harness/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P1.md and P1.3 Required Reads; verify committed P1.2. Root delegates P1.3 to a fresh grounded subagent. After Required Reads and before any other item-owned write, run the exact D36 P1.3 baseline --capture-or-verify command from Implementation Rules; on resume reuse bytes and fail closed rather than recapturing. Reuse existing command_render APIs through the thin worktree-local front; bump task to 0.3.1 and harness versions per D27, regenerate complete task locks/tree/marketplaces, prove a read-only second check, then delete all six exact root task collision directories and update AGENTS bootstrap ownership. Obtain ITEM_BASE_SHA only through baseline --verify-and-print, preserve task semantics and Claude compatibility, run unchanged-strength generated-scope validation, close, continue. Treat every seam produced by plan 2026.07.19-DUAL-PROVIDER as a low-trust input per D54: its terminal status is orange with an ATTENTION item and it introduced the hand-written root adapters outside the generator, so prove current behaviour with a characterization test here before changing it and never inherit green from that plan.'
```

### P1.5 — newly measured collision closure (перед P1.4)

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P1.5

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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.5. Read AGENTS.md, CLAUDE.md, packages/skiller/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, findings/10-design-audit-a1-attempt-4.md F1, findings/12-effective-collision-remeasure.md, phases/P1.md and P1.5 Required Reads; verify committed green P1.2 and P1.3. This item executes BEFORE P1.4 per D41. Root delegates only P1.5 to a fresh grounded subagent. After Required Reads and before any other item-owned write, run the exact D36 P1.5 baseline --capture-or-verify command from Implementation Rules; on resume reuse the carrier byte-for-byte and fail closed on owner dirt or invalid SHA. Prove ownership by frontmatter identity equality for architecture, codebase-design, domain-modeling and package-contribution-protocol against the enabled architect bundle, then delete exactly those four .agents/skills directories with no suppression metadata. Add the class-B workflow-craft root-bootstrap record (public-bucket canonical source, Codex-only declared asymmetry, precondition no enabled unit serves it) in configs plus the P1.5 extension map; never touch the class-A 13 canonical sources, their 26 projections or repository-bootstrap-map.json bytes. Version first: skiller API 0.4.2 and repository-bootstrap 0.2.0, every other unit byte-identical. Extend only the existing publication.py root-bootstrap renderer through registry.py, emit the thin Codex projection and the combined 27-target lock, add the completeness check that each provider root set equals exactly the declared target set, and add the read-only core-versus-donor-bucket mutual exclusion diagnostic to doctor.py without reading or writing any live profile or cache. Regenerate the full owned tree and both repository marketplaces, prove registry --check is a no-op, obtain ITEM_BASE_SHA only through baseline --verify-and-print, run generated-scope with owner P1.5, write findings/P1.5-collision-closure.md, close and continue to P1.4. Treat every seam produced by plan 2026.07.19-DUAL-PROVIDER as a low-trust input per D54: its terminal status is orange with an ATTENTION item and it introduced the hand-written root adapters outside the generator, so prove current behaviour with a characterization test here before changing it and never inherit green from that plan.'
```

### P1.4 — effective-runtime conformance (терминальный item, после P1.5)

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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="medium"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P1.4. Read AGENTS.md, CLAUDE.md and task:task-plan-exec completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P1.md and P1.4 Required Reads; verify P1.2, P1.3 and P1.5 committed green — P1.5 runs before this item per D41 and a missing findings/P1.5-collision-closure.md fails closed before any fixture work. Root delegates P1.4 to a fresh grounded subagent. First declare the fixture composition per D51: write artifacts/P1.4/fixture-unit-set.json listing, for each provider, ALL publishable units of that repository marketplace MINUS exactly the three donor buckets general, research and oss-dev (reason d42-donor-bucket), and fail closed if the file is missing, if the unit set does not equal that rule recomputed from the manifest, or if curated core and any donor end up enabled together. Narrowing beyond those three names is a failure, not a green run. In explicit stdlib temporary roots, materialize each provider root projection, cold-install exactly the declared fixture bundles, discover/activate/resolve and behavior-smoke; build the identity-to-carrier map from the generated publication catalog/lock, never by recursive globbing of source trees. Require 13 class-A repository-bootstrap IDs exactly once from thin roots plus the class-B workflow-craft Codex projection, with canonical path/hash/version matching the combined 27-target lock and zero private marketplace entries; require six core, six task and four architect IDs exactly once from installed bundles with all 16 measured duplicate roots absent — the expected exactly-once total is derived by the formula 13 + 1 + 6 + 6 + 4 = 30, not written as a bare literal. Verify catalog-wide: fail on ANY identity with two or more carriers and on ANY undeclared root directory in the declared fixture, not only on the enumerated ones. Then run the SEPARATE negative fixture with core plus a donor bucket enabled and require exactly nine named core-versus-donor D42 diagnostics with non-empty safe_owner_action (anti-drift, compact-responses, context-economy, mcp-advisor, plan-protocol, session-handoff, verify-claims, gh-review, query-craft) plus the class-B workflow-craft precondition error; silence there fails the item. Do not write live fleet/cache or any user profile; close through task-plan-exec and continue.'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P2.2. Read AGENTS.md, CLAUDE.md, packages/task/CLAUDE.md, packages/skiller/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P2.md and P2.2 Required Reads; verify committed P2.1. Root delegates P2.2 to a fresh grounded subagent. After Required Reads and before any other item-owned write, run the exact D36 P2.2 baseline --capture-or-verify command from Implementation Rules; on resume validate/reuse, never recapture. Implement the independently-green compiler/fresh-item dispatch and the sole canonical protocol/command edit. Version first: plan-protocol 2.12.0, skiller API plus general/core units 0.5.0, task 0.4.0; keep repository-bootstrap 0.2.0 byte-identical. Regenerate exact full owned trees/locks/marketplaces, prove second checks, obtain ITEM_BASE_SHA only through baseline --verify-and-print and run the generated-scope guard including its D47 foreign-commit attribution. Self-conformance per D47 is mandatory: the new tier rules must be applied to THIS plan inside the item — run plan-lint on plans/2026.07.24-AGENT-RELIABILITY and require zero errors before commit, classify brief tmp references as provenance rather than execution inputs, and fix either the plan text or the rule inside this item with a D-record instead of deferring the debt to P2.3. Notify the consumer plan 2026.07.25-ECO-OPT before close. Do not depend on P2.3 or add duplicate prose logic; close and continue.'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P2.3. Read AGENTS.md, CLAUDE.md, packages/task/CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P2.md and P2.3 Required Reads; verify committed P2.2 independently green. Root delegates P2.3 to a fresh grounded subagent. After Required Reads and before any other item-owned write, run the exact D36 P2.3 baseline --capture-or-verify command from Implementation Rules; on resume validate/reuse, never recapture. Only then author review_policy.py/test_review_policy.py as same-item Files, extend the frozen compiler policy hook with typed findings/reopen/third-event incident, and do not edit P2.2 commands or plan-protocol. Bump task runtime publication to 0.5.0, regenerate its complete adapters/locks/golden plugin/marketplaces while command bodies stay unchanged, prove second check, obtain ITEM_BASE_SHA only through baseline --verify-and-print and run unchanged-strength generated-scope guard, close and continue.'
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
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P3.4. Read AGENTS.md, CLAUDE.md and task:task-plan-run completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P3.md and P3.4 Required Reads; verify committed P3.1-P3.3. Root delegates P3.4 to a fresh grounded subagent. Complete predecessor reads first, then author/validate canary-cases.json as a same-item File; never treat it as a cold-start prerequisite. Read PRE_PLAN_SHA only from plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.1/pre-plan-sha.txt per D45 and validate it is a 40-hex commit and an ancestor of CANDIDATE_SHA before creating the worktree; never invent a pre-plan ref and never substitute CANDIDATE_SHA. Use only task-specific CANARY_ROOT/CANARY_WT and pin both routed axes by flag per D46 — Codex: -C plus -m and model_reasoning_effort=high; Claude form: claude -p with --model and --effort high; unknown actual effort fails the dispatch instead of running on a session default. Never set HOME/CODEX_HOME or mutate global registries. Persist each detached case SHA+patch and the applied provider/model/effort with its source, rehearse clean switch rollback to PRE_PLAN_SHA, refuse dirty cleanup, close only on exact evidence.'
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
| A0/A1/A2/A3 | historical | четыре персональных audit-слота CONSUMED RED (`findings/09`–`findings/11`, `findings/13`) + два исторических вердикта cap 2/2 (`findings/07`, `findings/08`); факты, не действующий механизм (D50) | ничего: рационирование снято, действует канон «два аудита на фазу» |
| Authority C/D/E | consumed / **действует E** | C (D32) и D (D39) — CONSUMED, их скоупы закрыты. **E (D50)** — стоячая делегация решений агенту: развилки, скоуп, пороги закрываются записью | E не блокирует ничего; C/D исторические |
| G-EXEC | **выдан** authority E (D50) | self-host P0–P3 исполняются без отдельного человеческого гейта | — (снят) |
| G0 | после P0.3 | **ПРИНЯТ 2026-07-25 записью D59** (агент, D50): exact bank/grader/baseline hashes и 14 floors заморожены, `bank-manifest.json content_hash=82d1e6a9997dc8de…` | — (снят; P0.4 разблокирован) |
| G1 | после P4.3 packet | exact external targets/actions: fleet, consumers, FOREMAN, tag, push, release — либо hold | external work outside this plan |
