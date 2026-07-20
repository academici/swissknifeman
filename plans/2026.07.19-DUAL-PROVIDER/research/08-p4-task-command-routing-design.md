# P4 design synthesis — task-command parity и provider-neutral routing

**Дата:** 2026-07-19

**Основание:** `brief/00-brief.md`, `brief/01-refinements.md`,
`research/01-target-architecture-options.md`, `research/02-sequence-and-boundaries.md`,
`research/07-p3-dual-skill-publication-design.md`, `phases/P3.md`, draft
`root/contracts/provider-{capability,config}-contract.md` и D4/D11/D19–D23 `plan.md`.
Новых внешних утверждений этот синтез не вводит; exact Codex projection и model selectors
замораживаются P4.1 только против terminal P0/P1/P3 evidence.

## Целевая граница

P4 оставляет `packages/task/commands/*.md` единственным semantic command inventory и
добавляет versioned provider-command/routing contract. Контракт отделяет четыре вещи:

1. stable command ID и workflow intent;
2. provider-neutral minimum model class и effort;
3. требуемые capabilities и lifecycle/plan semantics;
4. provider projection: имя/путь adapter'а, invocation rendering, native model selector и
   diagnostics.

Рекомендуемый routing vocabulary — три упорядоченных model class
`economy < implementation < frontier`; effort остаётся независимой осью
`low < medium < high < xhigh`. Provider mapping является явной versioned projection:
semantic source не содержит Claude/Codex marketing model names, а отсутствие пригодного
mapping даёт fail-closed diagnostic, не молчаливый downgrade. Конкретные selector'ы каждого
provider не фиксируются этим design synthesis и требуют P4.1 conformance/owner gate.

Claude projection сохраняет существующие slash-command IDs, frontmatter pins и bodies
через compatibility golden. Codex projection поставляется P3 publication pipeline как thin
generated skills/adapters, с observed owner invocation `$ task:…`; `$ ` — UI prefix, а
`task:<id>` — stable semantic identity. Adapter может менять provider-native wrapper,
instructions и launch syntax, но не intent, gates, status literals или acceptance semantics.

## Рассмотренные альтернативы

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Оставить Claude model names/frontmatter общим contract | минимальный diff | привязывает общий routing к одному provider; Codex вынужден угадывать эквивалент | отклонить |
| Два независимых набора command markdown | provider-native с первого дня | второй semantic canon, drift plan rules и fixes | отклонить |
| Semantic command inventory + deterministic projections | один intent, native invocation/model mapping, exhaustive parity | нужен frozen contract и compatibility fixtures | принять |
| Один generic lowest-common-denominator prompt | простая доставка | теряет native skills, model pins, lifecycle/orchestration | отклонить |
| Runtime auto-pick «лучшая доступная модель» | меньше config | недетерминированный downgrade и нерепродуцируемый audit | отклонить; mapping explicit/fail-closed |

## Command/routing contract outline

Contract P4.1 должен заморозить:

- stable IDs всего inventory и source path каждого command;
- command kind (`intent`/`plan-protocol`/`management`), semantic inputs/outputs и aliases;
- minimum `model_class`, independent `effort`, allowed overshoot и forbidden undershoot;
- capability requirements, including filesystem write, MCP, orchestration/subagent and
  package publication dependencies;
- provider projection identity, native invocation rendering and generated target;
- distinction between semantic command ID, UI invocation prefix and display label;
- plan literals/statuses/16 item fields/Next forms as semantic payload, not wrapper text;
- no-mapping/unsupported-capability/undershoot/ambiguous-command diagnostic codes;
- backward-compatibility, versioning, golden examples and owner approval record.

## Item sequence

P4.1 freezes the contract and mapping evidence. P4.2 adds the neutral catalog/parser and
Codex generated skill adapters through the P2/P3 artifact pipeline. P4.3 makes Claude a
named projection and proves byte/semantic compatibility. P4.4 migrates the plan protocol,
launch-block rendering and routing gate to neutral classes while retaining provider-native
invocations. P4.5 derives an independent inventory and proves two-provider parity,
undershoot/fail-closed behavior and operator documentation. All items touch the same
contract/catalog/golden surface and consume the preceding deliverable; workflow criterion
does not fire.

## Compatibility и fail-closed invariants

- Legacy project/config without provider selection continues to expose the current Claude
  command surface only; Codex does not appear implicitly.
- Semantic command ID is stable across providers; `/task:plan-design` and `$ task:plan-design`
  are provider projections, not two commands.
- Missing/unknown provider mapping or capability blocks invocation with a structured
  diagnostic; it never downgrades model class/effort.
- Provider overshoot is reportable and allowed by contract; undershoot is forbidden before
  work begins.
- Codex adapters are generated thin outputs and cannot become canonical replacements for
  `packages/task/commands` or `packages/skiller/skills/general/plan-protocol`.
- Claude compatibility is checked independently from the new renderer; expected fixtures are
  not regenerated from actual output.
- Dry-run/check/parity tests use temp or generated targets and do not edit current root
  `.agents/skills`, `plans/2026.07.18-FOREMAN` or fleet projects.

## Pre-mortem P4

| Отказ | Ранний сигнал | Mitigation | Owner/item |
|:--|:--|:--|:--|
| Neutral tiers secretly mirror Claude names | contract examples require `sonnet`/`opus` in semantic records | stable class enum + provider mapping table + schema rejection | P4.1 |
| Codex adapter drifts from task body | duplicated prose or hand-written SKILL bodies | thin generated wrapper, source hash/lock and semantic parity test | P4.2/P4.5 |
| Claude users lose command/model behavior | generated Claude command differs from pre-change fixture | independent pre-refactor golden + byte/field parity gate | P4.3 |
| Plan executor runs below required tier | missing/ambiguous mapping defaults to available model | fail-closed routing gate + negative undershoot/unknown mapping cases | P4.4/P4.5 |
| Launch-block syntax works in one surface only | literal `/task:…` or `$ task:…` embedded as universal semantic data | provider invocation renderer; semantic ID tested separately | P4.4/P4.5 |
| Parity test greens on two incomplete projections | expected set derived from renderer output | independent inventory reader from canonical commands/contract | P4.5 |
| Design pass mutates bootstrap/fleet artifacts | root `.agents/skills` or FOREMAN/fleet diff appears | declared Files + protected-path snapshot and no-write gate | P4.2–P4.5 |

## Verification

- Repo-grounding: cold-start plan artifacts, P3 handoff/design and owner refinement were
  read; package code was not executed.
- External: no new external capability claim was made. P4.1 must consume terminal P0/P1/P3
  first-party evidence before freezing provider selectors and invocation fields.
- Непроверенное → ПОВТОРНЫЙ ПРОХОД: exact frozen contracts, generated publication APIs and
  provider selector values do not exist until predecessor execution; they are hard entry
  gates in P4.1–P4.5.
- `[POSSIBLE-DEFECT]`: the current plan-protocol `Next` enum and examples encode Claude slash
  syntax. P4.4 must separate semantic Next form from rendered invocation without weakening
  current lint/back-compat behavior.
