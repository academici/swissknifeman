# Roadmap исполнения — 2026.07.19-DUAL-PROVIDER

<!-- Собран после полной детализации P0–P7. Отвечает на «какую команду дальше?» без
     повторного анализа всего плана. Живой документ: finish/design audit, закрытие фазы
     или re-design обновляют таблицу и Update Log. Roadmap не переопределяет Routing §3.
     Порядок строго phase-first: P0→P1→P2→P3→P4→P5→P6→P7. До finish + GREEN design
     audit исполнение любого item запрещено. -->

**Обновлён:** 2026-07-20 · **Соответствует plan.md:** v1.3.0

> **Статус exec:** P0.1 и P0.5 🟢; остальные 38 items открыты. P0.5 terminal correction
> evidence разделяет umbrella Command Surface и Task Command subset; следующий шаг — новый
> P0.2 owner freeze.
> Historical audit r4 GREEN уже открыл исполнение P0.1; повторный whole-plan audit из-за
> локальной prerequisite correction не подменяет item-level full review и остаётся вне
> текущего Next.
> Исполнительские модели — только current ChatGPT/Codex family: Terra для prescribed
> implementation, Sol для design/contracts/audit. GPT-5.6 Luna не используется на этом
> public-contract/release critical path. RAG:✅ 2026-07-19
> (`findings/P7-openai-model-routing-2026-07-19.md`).

## Карта исполнения

| Item | Batch | Запуск | Model/Thinking | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P0.1 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | historical narrow inventory закрыт; command-surface интерпретация корректируется отдельным P0.5 |
| P0.5 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | terminal correction evidence пяти explicit roots; не переписывает P0.1 |
| P0.2 | solo | plan-run (manual) | gpt-5.6-sol/high | ✅ весь vocabulary/scenarios + Command Surface 32 / Task Command 11 | стартует только после terminal P0.5; owner approval ссылается на correction anchor |
| P0.3 | solo | plan-run (manual) | gpt-5.6-sol/xhigh | ✅ capability/artifact contracts + ADR | frozen public contracts; отдельный irreversible owner gate |
| P0.4 | solo | plan-run (manual) | gpt-5.6-sol/high | ✅ migration/FOREMAN/fleet gates | cross-plan safety gate после frozen P0.3, отдельно от contract authoring |
| P1.1 | solo | plan-run (manual) | gpt-5.6-sol/xhigh | ✅ provider-config contract | owner-gated public precedence/config freeze |
| P1.2 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ shared-core contribution | prescribed API после P1.1; public core boundary требует full review |
| P1.3 | solo | plan-run (manual) | gpt-5.6-terra/high | — | потребляет P1.2 symbols и реализует precedence/diagnostics |
| P1.4 | solo | plan-exec | gpt-5.6-terra/medium | — | independent compatibility/no-write gate после всей P1 implementation |
| P2.1 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ core proposal/ADR | shared artifact kernel; contribution gate и public API review |
| P2.2 | solo | plan-run (manual) | gpt-5.6-terra/high | — | drift/apply state machine зависит от terminal P2.1 API |
| P2.3 | solo | plan-run (manual) | gpt-5.6-sol/high | — | public catalog design после P2.2; открытое design decision D17 |
| P2.4 | solo | plan-exec | gpt-5.6-terra/medium | — | independent dry/doctor/conformance gate завершает P2 |
| P3.1 | solo | plan-run (manual) | gpt-5.6-sol/high | ✅ publication contract | frozen identity/install/ownership semantics до adapters |
| P3.2 | solo | plan-exec | gpt-5.6-terra/medium | — | deterministic Claude compatibility projection после P3.1 |
| P3.3 | solo | plan-run (manual) | gpt-5.6-terra/high | — | native Codex plugin/cache contract, зависит от P3.2 catalog/goldens |
| P3.4 | solo | plan-run (manual) | gpt-5.6-terra/high | — | providerizes mutation flows после обеих projections; partial-failure review |
| P3.5 | solo | plan-exec | gpt-5.6-terra/medium | — | independent whole-inventory parity/no-write gate |
| P4.1 | solo | plan-run (manual) | gpt-5.6-sol/xhigh | ✅ command/routing contract | frozen semantic tiers/invocation; отдельный public-contract gate |
| P4.2 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ task contribution | complete Codex adapter/catalog against frozen P4.1 |
| P4.3 | solo | plan-exec | gpt-5.6-terra/medium | — | independent Claude byte/literal compatibility gate |
| P4.4 | solo | plan-run (manual) | gpt-5.6-sol/high | ✅ plan-protocol canon contribution | canon-the-fleet-follows; нельзя объединять с compatibility или parity |
| P4.5 | solo | plan-exec | gpt-5.6-terra/medium | — | independent command/plan parity и generated docs gate |
| P5.1 | solo | plan-run (manual) | gpt-5.6-sol/high | ✅ harness/security contract | owner-gated security/profile boundary до provider outputs |
| P5.2 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ harness contribution | security projections против frozen contract; full review |
| P5.3 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ always-on context budget | lifecycle/trust/context activation после P5.2; budget gate владельца |
| P5.4 | solo | plan-run (manual) | gpt-5.6-terra/high | — | MCP/agent packs зависят от P5.3 lifecycle mappings |
| P5.5 | solo | plan-exec | gpt-5.6-terra/medium | — | independent harness parity/doctor/docs gate |
| P5.6 | solo | plan-run (manual) | gpt-5.6-sol/xhigh | ✅ instruction contract/source/managed-boundary freeze | public semantic parity/provenance contract; отдельный irreversible owner gate |
| P5.7 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ harness contribution | prescribed catalog/renderer/conformance после frozen P5.6; full review |
| P6.1 | solo | plan-run (manual) | gpt-5.6-terra/high | — | mAInd provider deploy loop против frozen P1/P2/P5 contracts |
| P6.2 | solo | plan-run (manual) | gpt-5.6-terra/high | — | onboard/sync/security consumes P6.1 provider result shape |
| P6.3 | solo | plan-run (manual) | gpt-5.6-sol/xhigh | ✅ analytics contract/privacy/migration | owner-gated schema/storage freeze; отдельный design item |
| P6.4 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ shared-core/analyst contribution | multi-package readers/store migration после frozen P6.3 |
| P6.5 | solo | plan-exec | gpt-5.6-terra/medium | — | integrated conformance + durable pre-restart checkpoint |
| P6.6 | solo | plan-exec (NEW SESSION) | gpt-5.6-terra/medium | — | mandatory cold restart; нельзя объединять с P6.5 |
| P7.1 | solo | plan-exec | gpt-5.6-terra/medium | — | generated docs + independent exact-set после GREEN P6.6 |
| P7.2 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ D# на live apply после isolated GREEN | isolated→rollback→live self-host; security/release full review |
| P7.3 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ D# на exact bootstrap cleanup inventory | guarded destructive cleanup и release manifest; отдельный rollback boundary |
| P7.4 | solo | plan-run (manual, NEW SESSION) | gpt-5.6-sol/xhigh | ✅ literal GREEN + explicit owner D# | cold adversarial audit; только GREEN+owner D# открывает reconcile |

## Solo-обоснование и отсутствие batches/workflows

Все 40 items идут `solo`. В каждой фазе terminal Deliverable предыдущего item является
Inputs следующего, поэтому merge-criterion plan-protocol для batch/workflow не выполняется:
внутрифазных независимых scopes N≥3 нет. Contract/security/canon/release items имеют
`Review=full` и owner/commit boundaries; conformance items намеренно отделены от авторов
implementation. P5.6→P5.7 — contract→prescribed implementation, поэтому их нельзя
объединять; P6.5→P6.6 и P7.3→P7.4 дополнительно разделены обязательным NEW SESSION.

## Готовый launch-block текущего owner gate

### S-P0.2 — vocabulary owner freeze

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | high — owner-approved vocabulary freeze |
| Context | continue (/clear) — ручной item |
| Суть | Зафиксировать P0.2 glossary и scenario matrix на terminal P0.5 evidence |

```
Выполнить P0.2 вручную в 2026.07.19-DUAL-PROVIDER на gpt-5.6-sol/high. Сначала прочитать plan.md, handoff.md, phases/P0.md и Required Reads P0.2 в указанном порядке. Использовать terminal findings/P0-command-surface-correction.md как evidence: Command Surface и Task Command — разные glossary entries, anchored counts не становятся frozen constants. Подготовить только P0.2 glossary/scenario scope и получить новый Approval Owner D# на весь набор. Не менять P0.1/P0.5 evidence, package code, FOREMAN, ACTIVE или fleet.
```

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| P0.2 | весь vocabulary + domain scenarios; terminal P0.5 anchor; Command Surface 32 / Task Command 11 как разные scopes | P0.3 contract authoring |
| P0.3 | capability/artifact contracts + ADR | P0.4 и все downstream contracts |
| P0.4 | migration/FOREMAN/fleet safety gates | P1 entry |
| P1.1 | provider-config contract | P1.2–P1.4 |
| P1.2 | contribution в shared core | P1.3–P1.4 |
| P2.1 | artifact-kernel proposal/ADR | P2.2–P2.4 |
| P3.1 | publication contract | P3.2–P3.5 |
| P4.1 | command/routing contract | P4.2–P4.5 |
| P4.2/P4.4 | contributions в task/plan-protocol canons | P4.3/P4.5 и downstream invocations |
| P5.1 | harness/security contract | P5.2–P5.5 |
| P5.2/P5.3 | harness contribution + always-on context budget | P5.4–P5.5 |
| P5.6 | common instruction semantics/source/markers/provenance/backcompat contract | P5.7 и P6/P7 instruction consumers |
| P5.7 | harness instruction contribution + semantic-parity conformance | P6.2 deploy/repair |
| P6.3 | analytics/privacy/migration contract | P6.4–P6.6 |
| P6.4 | shared core/analyst contribution | P6.5–P6.6 |
| P7.2 | live self-host apply после isolated GREEN | P7.3 |
| P7.3 | bootstrap cleanup inventory/actions | P7.4 |
| P7.4 | literal GREEN release verdict + explicit Approval Owner D# | только отдельный FOREMAN reconcile; fleet всё ещё закрыт |

## Проверка (verification status)

- RAG: official OpenAI model catalog + Terra model page, 2026-07-19 — Sol/Terra IDs,
  roles и efforts подтверждены; детали в `findings/P7-openai-model-routing-2026-07-19.md`.
- Repo-grounding: 40/40 Routing rows, 12 `plan-exec` + 28 `manual`; instruction carrier
  и contract/read/owner-gate reconcile — `research/12-final-cross-phase-reconcile.md`,
  `research/13-instruction-contract-remediation.md`.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: account availability Sol/Terra; runtime fail closed,
  downgrade запрещён.
- Обходки/[POSSIBLE-DEFECT]: numbering P0.5 отражает новый carrier без renumber существующих
  journal IDs; фактический порядок задают D52 и эта execution map. D51 supersedes недостаточный D49 только в части
  schema-invalid row 11; audit-r3 F1 не меняет contract/D51/canon, а закрывает missing
  directory-ID enforcement. Evidence — `findings/journal-same-plan-remediation-verification-2026-07-20.md`.
  Audit r4 остаётся pre-exec gate.
