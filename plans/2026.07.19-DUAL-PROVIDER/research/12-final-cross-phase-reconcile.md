# Final cross-phase reconcile — design pass 3/3 + post-audit remediation

**Дата:** 2026-07-19  
**Основание:** `brief/00-brief.md`, `brief/01-refinements.md`, `plan.md`, `roadmap.md`,
`phases/P0.md`–`phases/P7.md`, `research/00-user-intent-traceability.md`,
`research/01-target-architecture-options.md`, `research/02-sequence-and-boundaries.md`,
`research/11-p7-self-host-release-design.md`, `research/13-instruction-contract-remediation.md`
и findings/journal records, на которые они ссылаются.

## Contract chain

| Фаза | Потребляет | Производит | Reconcile verdict |
|:--|:--|:--|:--|
| P0 | brief + repo/provider evidence | capability/artifact/migration-gate contracts, glossary/scenarios, ADR | первый producer; package runtime вне границы |
| P1 | terminal/frozen P0 outputs | config contract, core provider/resolver API, compatibility matrix | P0 outputs перечислены как hard entry gate |
| P2 | terminal P1.4 + P0/P1 contracts/API/evidence | artifact/render/lock/catalog kernel + conformance | P3–P6 consumers имеют producer-before-consumer |
| P3 | terminal P2.4 + publication inputs | skill-publication contract, dual adapters/distribution/parity | P4/P7 читают exact P3 artifacts |
| P4 | terminal P3.5 + command/routing inputs | command-routing contract, dual command projections, plan gates/parity | P5–P7 и будущий FOREMAN reconcile имеют один routing source |
| P5 | terminal P4.5 + harness/current instruction evidence | harness contract/profiles/security/hooks/MCP/agents conformance + frozen instruction contract + common catalog/root-package projections/conformance | P6 получает harness adapters и уже спроектированный instruction plan/check/apply/repair API |
| P6 | terminal P5.7 + deploy/analytics inputs | provider deploy/sync including root/package instruction repair, analytics contract/store/readers, instruction-aware cold checkpoint | P6.5/P6.6 — фактические restart carriers; P7 стартует только после terminal GREEN P6.6 |
| P7 | terminal GREEN P6.6 + frozen P0–P6 bundle | generated docs, self-host instruction parity/drift/repair evidence, guarded cleanup, release audit/gate | только проверяет P5/P6 mechanism; GREEN + owner D# открывает отдельный FOREMAN reconcile |

Cross-phase skips не найдены. P1 contract уточнён: D13–D15 являются локальными design
constraints, а не фиктивным output P0. Coupling hotspots D9 — provider IDs/capabilities,
config precedence, artifact provenance, command routing и analytics schema — имеют по
одному owner/contract carrier до downstream implementation. RAG:— (repo-grounded:
`plan.md` D9/D13–D18/D20–D40, `phases/P0.md`–`phases/P7.md`)

Post-audit hotspot common instructions получает P5.6 contract, P5.7
implementation/conformance, P6.2 deploy/repair и P6.5/P6.6 durability; P7 не является
первым producer. RAG:— (repo-grounded: `plan.md` D45–D50,
`research/13-instruction-contract-remediation.md`)

## Required Reads и producer order

Structural sweep классифицирует каждый backticked Required Read как одно из двух:
существующий authoring/source path либо Deliverable более раннего item. Исправлены:

1. P4.4: пять реальных `*-template.md` paths отделены от
   `code-guidance-patterns.md`; прежние `snippets/plan.md` и аналоги не существовали.
2. P7.3: prose «artifact named by terminal P2.4» и «P3–P6 terminal reports» заменены
   конечными ordered paths.
3. P7.4: phase/FOREMAN reads развёрнуты в конечные path sets с read-only boundary.

Future paths допустимы только когда их producer стоит раньше: P0.1→P0.2 artifacts,
P0/P1 contracts, P2 conformance, P3–P6 terminal reports и P7 evidence проходят этот gate.
RAG:— (repo-grounded: item `Files`/`Required Reads` в `phases/P0.md`–`phases/P7.md`)

Post-audit producer order:

1. `root/contracts/provider-instruction-contract.md` создаёт P5.6 до чтения P5.7/P6/P7.
2. `P5-instruction-conformance.md` создаёт P5.7 до P6.2/P6.5/P7 consumers.
3. P6.2 отдаёт provider-aware instruction plan/check/apply/repair до checkpoint P6.5.
4. P6.5 создаёт disk+mAInd checkpoint, P6.6 читает его в новой сессии; user-intent
   ссылка исправлена с P6.4 на P6.5–P6.6.
5. Package `AGENTS.md` — future live outputs P7.2; до него P5.7/P6.2 проверяют temp
   projections, поэтому P6.6/P7 reads имеют реальные predecessor gates.

RAG:— (repo-grounded: `phases/P5.md`–`phases/P7.md`)

## Routing, orchestration и owner gates

Routing покрывает 39/39 items построчно: 11 deterministic Terra/medium items имеют
`Exec = plan-exec`; 28 Sol или Terra/high+ items имеют `Exec = manual`. Contradictory
`plan-exec` при high/xhigh нет. Official OpenAI model pages повторно подтверждают
Sol/Terra roles и supported reasoning efforts. RAG:✅ 2026-07-19
(`findings/P7-openai-model-routing-2026-07-19.md`)

Во всех фазах intra-phase deliverable предыдущего item является input следующего;
N≥3 independent scopes нет, поэтому workflow criterion не срабатывает. P6.5→P6.6 и
P7.3→P7.4 дополнительно требуют NEW SESSION. P5.6→P5.7 не batch: первый
замораживает public contract/owner gate на Sol/xhigh, второй реализует prescribed
package change на Terra/high.

Owner gates сведены в `roadmap.md` и имеют item carriers. Pass 3 добавил недостающую
формализацию: P1.2/P6.4 contribution-review artifacts, P5.6 instruction contract owner D#,
P5.7 harness contribution review, P7.2 owner D# перед live apply и P7.3 owner D# перед
exact cleanup actions. P7.4 не может сам утвердить release: нужен
literal GREEN и отдельный Approval Owner D#.

## DoR и brief traceability

- Skeleton markers отсутствуют; все 8 фаз содержат Scope Included/Excluded, 16 полей
  каждого item, Code Guidance, deterministic Validation и честные future entry gates.
- Все phase design syntheses P0–P7 содержат pre-mortem; mitigations имеют item/Owner.
- `research/00-user-intent-traceability.md` покрывает один SSOT, два provider adapter'а,
  config/publication/task/harness/mAInd/analytics/docs/self-host, безопасную автономность,
  root/package instruction semantic parity, restart durability через P6.5/P6.6 и
  FOREMAN→fleet sequence.
- Open Questions отсутствуют; resolved forks закреплены D-log.
- Execution остаётся закрытым до нового adversarial design audit; это remediation не
  запускало plan-lint и не заявляет GREEN.

## Проверка (verification status)

- RAG: official OpenAI model catalog + Terra model page, 2 primary pages, 2026-07-19 — OK;
  confidence high. Docs MCP отсутствовал, применён official-domain fallback.
- Repo-grounding: cold-start set + managed-block/repo carrier recon + structural
  path/routing/item-schema sweeps. Plan-lint в post-audit remediation не запускался по
  прямому ограничению владельца; повторный audit обязан дать current anchored count.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: доступность `gpt-5.6-sol`/`gpt-5.6-terra` в аккаунте
  владельца — runtime gate, неизвестна из публичных docs; downgrade запрещён.
- Обходки/[POSSIBLE-DEFECT]: D41 остаётся историческим lint gap только для `finish` Next;
  после завершения finish текущий Next — канонический `plan-audit design`, workaround не активен.
  Historical audit row 11 содержит free-form `friction`, не входящий в текущий enum;
  D49 добавляет append-only canonical compensating row, но без нового anchored lint нельзя
  утверждать, что действующий lint принимает correction semantics.
