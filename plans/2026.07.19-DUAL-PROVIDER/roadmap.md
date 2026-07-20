# Roadmap исполнения — 2026.07.19-DUAL-PROVIDER

<!-- Собран после полной детализации P0–P7. Отвечает на «какую команду дальше?» без
     повторного анализа всего плана. Живой документ: finish/design audit, закрытие фазы
     или re-design обновляют таблицу и Update Log. Roadmap не переопределяет Routing §3.
     Порядок строго phase-first: P0→P1→P2→P3→P4→P5→P6→P7. До finish + GREEN design
     audit исполнение любого item запрещено. -->

**Обновлён:** 2026-07-20 · **Соответствует plan.md:** v1.4.3

> **Статус exec:** P0 закрыта и audit attempt 3 завершён literal GREEN на `245bb56`;
> G01 открыт, P1 закрыта после D70/D73 и terminal P1.3/P1.4 evidence.
> Следующий шаг — independent P1 audit для G02; P2.1 остаётся закрыт до literal GREEN.
> D71 исполнил D65/D68 reconciliation сейчас: `main` — active execution root, retained stash
> `72505e4d8bef2a58f4ed555cc5b6014450aee3a9` сохраняет recovery point, unrelated owner dirt
> возвращён unstaged. Это не открывает FOREMAN/fleet/live authority и не снимает P1.2 owner gate.
> Исполнительские модели — только current ChatGPT/Codex family: Terra для prescribed
> implementation, Sol для design/contracts/audit. GPT-5.6 Luna не используется на этом
> public-contract/release critical path. RAG:✅ 2026-07-19
> (`findings/P7-openai-model-routing-2026-07-19.md`).
> D69: explicit fresh process на каждом manual item; inherited root xhigh не используется
> как routine fallback. Каждая terminal phase получает fresh independent Sol/xhigh audit;
> regression возвращается в owning phase по D58 до продолжения roadmap.

## Карта исполнения

| Item | Batch | Запуск | Model/Thinking | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P0.1 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | historical narrow inventory закрыт; command-surface интерпретация корректируется отдельным P0.5 |
| P0.5 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | terminal correction evidence пяти explicit roots; не переписывает P0.1 |
| P0.2 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/high | ✅ D53 | vocabulary/scenarios и distinction Command Surface / Task Command заморожены |
| P0.3 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/xhigh | ✅ D55 | capability/artifact contracts v1.0.0 + ADR accepted |
| P0.4 | solo | plan-run/plan-close repair — 🟢 | gpt-5.6-sol/high; repair gpt-5.6-sol/xhigh | ✅ D59; D60 contract-neutral repair | exact structural G11 revalidation green; frozen contract unchanged |
| P0.6 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ D63-B · D64-A · D65-A → D71 timing/target | sealed clean-tree lint/evidence replay закрыт; D71 reconciled delivery into main without product-semantic expansion |
| P0.7 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ D67/D68 mechanical authority | sealed D65 manifest/derived policy applied in D71; package/main/P1 product semantics не менялись |
| P1.1 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/xhigh | ✅ D70 | frozen provider-config v1.0.0; exact F1–F6 candidate accepted |
| P1.2 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ D73 shared-core contribution | immutable core API committed in exact item scope |
| P1.3 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | — | precedence/diagnostics и carrier adapters committed |
| P1.4 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | compatibility/no-write gate committed |
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

Все 42 item идут `solo`. В каждой фазе terminal Deliverable предыдущего item является
Inputs следующего, поэтому merge-criterion plan-protocol для batch/workflow не выполняется:
внутрифазных независимых scopes N≥3 нет. Contract/security/canon/release items имеют
`Review=full` и owner/commit boundaries; conformance items намеренно отделены от авторов
implementation. P5.6→P5.7 — contract→prescribed implementation, поэтому их нельзя
объединять; P6.5→P6.6 и P7.3→P7.4 дополнительно разделены обязательным NEW SESSION.

## Готовый launch-block текущего шага

### S-P1 audit — independent G02 gate

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | xhigh |
| Context | NEW SESSION — шаг-не-item |
| Суть | Независимо проверить terminal P1 для G02 до P2.1. |

```text
/task:plan-audit 2026.07.19-DUAL-PROVIDER P1

Прочитай plan.md, phases/P1.md, handoff.md, journal.jsonl, P1 contracts и compatibility matrix.
Проведи independent G02 audit terminal P1.1–P1.4. Не запускай P2.1, не меняй live config,
FOREMAN, fleet или unrelated owner-owned dirt.
```

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| P0.2 | весь vocabulary + domain scenarios; terminal P0.5 anchor; Command Surface 32 / Task Command 11 как разные scopes | P0.3 contract authoring |
| P0.3 | capability/artifact contracts + ADR | P0.4 и все downstream contracts |
| P0.4 | migration/FOREMAN/fleet safety gates | P1 entry |
| P0.6 | D63-B exact prerequisite/isolation · D64-A sealed path-only anchor · D65-A → D71 execution target/timing | выполнено; D71 сделал main active root, P0 close/audit и P1 entry остаются gated G01 |
| P0.7 | D67 exceptional audit attempt 3 · D68 exact reconciliation classifications/derived policy | D71 applied sealed policy; frozen contracts и historical D65 exact eight не меняются |
| P1.1 | provider-config contract — D70 выполнен | P1.2–P1.4 |
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
- Repo-grounding: 42/42 Routing rows, 12 `plan-exec` + 30 `manual`; instruction carrier
  и contract/read/owner-gate reconcile — `research/12-final-cross-phase-reconcile.md`,
  `research/13-instruction-contract-remediation.md`.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: account availability Sol/Terra; runtime fail closed,
  downgrade запрещён.
- Обходки/[POSSIBLE-DEFECT]: numbering P0.5 отражает новый carrier без renumber существующих
  journal IDs; фактический порядок задают D52 и эта execution map. D51 supersedes недостаточный D49 только в части
  schema-invalid row 11; audit-r3 F1 не меняет contract/D51/canon, а закрывает missing
  directory-ID enforcement. Evidence — `findings/journal-same-plan-remediation-verification-2026-07-20.md`.
  Audit r4 остаётся pre-exec gate.
