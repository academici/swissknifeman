# Roadmap исполнения — 2026.07.19-DUAL-PROVIDER

<!-- Собран после полной детализации P0–P7. Отвечает на «какую команду дальше?» без
     повторного анализа всего плана. Живой документ: finish/design audit, закрытие фазы
     или re-design обновляют таблицу и Update Log. Roadmap не переопределяет Routing §3.
     Порядок строго phase-first: P0→P1→P2→P3→P4→P5→P6→P7. До finish + GREEN design
     audit исполнение любого item запрещено. -->

**Обновлён:** 2026-07-21 · **Соответствует plan.md:** v1.4.30

> **Статус exec:** P0–P5 terminal. Independent P5 audit attempt 2 записал literal
> GREEN в `4470af7`, поэтому stale audit pointer снят и P6 entry gate открыт.
> P6.1–P6.2 focused-green. Текущий шаг — P6.3 на fresh `plan-sol-xhigh` в clean
> worktree от cumulative `codex/p6-integration`; item останавливается только на принятии
> подготовленного exact analytics contract. P7+, live self-host, FOREMAN, fleet и push
> остаются закрыты.

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
| P1.5 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | committed synthetic protected-path proof; no live owner-state inputs |
| P1.6 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | docs ownership/validation + append-only exact P1.2–P1.4 commit map after P1.5 |
| P2.1 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ D75 core proposal/ADR | shared artifact kernel committed against approved additive contract |
| P2.2 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | — | fail-closed drift/apply state machine committed after terminal P2.1 API |
| P2.3 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/high | — | immutable capability-aware catalog committed after P2.2 |
| P2.4 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | synthetic dry/doctor/conformance gate committed; phase is terminal pending independent audit |
| P2.5 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | — | D76 contract-required RED remediation committed; phase reclosed pending fresh audit |
| P3.1 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/high | ✅ publication contract | frozen identity/install/ownership semantics до adapters |
| P3.2 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | deterministic Claude compatibility projection после P3.1 |
| P3.3 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | — | native Codex plugin/cache contract; D83 restored stale core cache/lock with catalog regression |
| P3.4 | solo | plan-run (manual) — 🟢 D80 bundle | gpt-5.6-terra/high | — | one same-seam repair: unmanaged selected target, managed-byte drift and corrupt-lock provenance all fail closed before write |
| P3.5 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | independent whole-inventory parity/no-write rerun passed after D83; terminal validation/close complete, next G03 audit then P1–P3 PR |
| P4.1 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/xhigh | ✅ D84 command/routing contract | frozen semantic tiers/invocation |
| P4.2 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ task contribution | complete Codex adapter/catalog against frozen P4.1 |
| P4.3 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | Claude command/plugin bytes preserved by independent golden |
| P4.4 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/high | ✅ plan-protocol canon contribution | neutral routing/Next/capability canon and dual invocation |
| P4.5 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | independent command/plan parity, generated docs and terminal close complete; G04 GREEN |
| P5.1 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/high | ✅ D85 harness/security contract | frozen security/profile boundary |
| P5.2 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ harness contribution | security projections против frozen contract |
| P5.3 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ always-on context budget | lifecycle/trust/context activation |
| P5.4 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | — | MCP/agent packs; audit repair preserves valid P2 identities |
| P5.5 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | independent harness parity/doctor/docs gate |
| P5.6 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/xhigh | ✅ D86 instruction freeze | public semantic parity/provenance contract |
| P5.7 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ D87 additive carrier | instruction renderer/conformance against frozen D86 |
| P6.1 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | — | mAInd provider deploy loop против frozen P1/P2/P5 contracts |
| P6.2 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | — | provider context/trust/instructions and exact 30-row provisioner matrix focused-green |
| P6.3 | solo | plan-run (manual) | gpt-5.6-sol/xhigh | ✅ analytics contract/privacy/migration | owner-gated schema/storage freeze; отдельный design item |
| P6.4 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ shared-core/analyst contribution | multi-package readers/store migration после frozen P6.3 |
| P6.5 | solo | plan-exec | gpt-5.6-terra/medium | — | integrated conformance + durable pre-restart checkpoint |
| P6.6 | solo | plan-exec (NEW SESSION) | gpt-5.6-terra/medium | — | mandatory cold restart; нельзя объединять с P6.5 |
| P7.1 | solo | plan-exec | gpt-5.6-terra/medium | — | generated docs + independent exact-set после GREEN P6.6 |
| P7.2 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ D# на live apply после isolated GREEN | isolated→rollback→live self-host; security/release full review |
| P7.3 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ D# на exact bootstrap cleanup inventory | guarded destructive cleanup и release manifest; отдельный rollback boundary |
| P7.4 | solo | plan-run (manual, NEW SESSION) | gpt-5.6-sol/xhigh | ✅ literal GREEN + explicit owner D# | cold adversarial audit; только GREEN+owner D# открывает reconcile |

## Solo-обоснование и отсутствие batches/workflows

Все 45 item идут `solo`. В каждой фазе terminal Deliverable предыдущего item является
Inputs следующего, поэтому merge-criterion plan-protocol для batch/workflow не выполняется:
внутрифазных независимых scopes N≥3 нет. Contract/security/canon/release items имеют
`Review=full` и owner/commit boundaries; conformance items намеренно отделены от авторов
implementation. P5.6→P5.7 — contract→prescribed implementation, поэтому их нельзя
объединять; P6.5→P6.6 и P7.3→P7.4 дополнительно разделены обязательным NEW SESSION.

## D82 — phase-first execution map for P4–P6

Перед каждой фазой выполняется ровно один bounded entry pack: committed predecessor/gate
check, independent expected-inventory и protected-path snapshot, temp-root convention и
targeted seam-test map. Это read-only preflight, не ранний full validation. Каждый item
сохраняет two-commit close topology, но до terminal item запускает только contract-authored
targeted/static/temp-root negative probes. После первого owning-seam blocker successor
становится `🔴 Blocked`; один bounded same-seam scan собирает только подтверждённые причины
в minimal repair, затем targeted regressions выполняются один раз. Полный package
validation, docs/release assessment, phase close и fresh Sol/xhigh audit — один раз на
terminal tree фазы. Полные правила и exact probes: `research/20-p4-phase-first-execution-playbook.md`
и `research/20-p5-p6-phase-first-execution-playbook.md`.

| Фаза | Последовательные lanes и early gate | Terminal gate и PR checkpoint |
|:--|:--|:--|
| P4 | **NEW SESSION** только после committed G03 и P1–P3 review PR. `P4.1 → P4.2 → P4.3 → P4.4`; probes: exact command ID/routing inventory, P3 descriptor/cache refusal, Claude golden/two-run, затем one cross-projection routing/invocation integration gate before P4.5. | P4.5 independent parity/docs report → one task+skiller validation, registry/docs/protected delta/plan-lint → close → Sol/xhigh audit → G04. Open/update P4-only PR only after audit evidence; no P5/live/FOREMAN/fleet scope. |
| P5 | `P5.1 → (P5.2 → P5.3 → P5.4 shared harness lane) → P5.5 → (P5.6 → P5.7 instruction lane)`. Each writer proves its listed negative/ownership/temp-root seam before successor; one dual-provider cross-seam render/check/apply/check gate follows P5.4. | After P5.7: one harness validation, final independent P5.5 inventory + P5.7 instruction parity, generated operator references/protected delta/plan-lint → close → Sol/xhigh audit. Then prepare P4–P5 review PR only, with item commits, frozen D#s and temp-only evidence. |
| P6 | `(P6.1 → P6.2 deploy/provision lane) → (P6.3 → P6.4 analytics lane) → P6.5 → P6.6`. P6.1/P6.2 and P6.4 run their exact fail-closed integration matrices before successors; P6.5 is the single full integrated checkpoint gate. **P6.6 is a mandatory NEW SESSION** reading disk checkpoint before mAInd recall and runs no code repair. | After GREEN P6.6: close → one fresh Sol/xhigh audit from disk/checkpoint evidence, without rerunning P6.5. Then prepare/update P6 review PR on the P4–P5 checkpoint; separate temp-only provision, analytics migration and read-only checkpoint evidence; P7/self-host, FOREMAN and fleet stay excluded. |

## Готовый launch-block текущего шага

### P6.3 — provider-neutral analytics contract

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | command.filesystem-read · command.filesystem-write · command.git-read |
| Context | same-session — owner-gated design item |
| Суть | Prepare the complete P6.3 analytics recommendation and exact contract text, then stop once for the frozen-contract owner decision. |

```text
$ task:plan-run 2026.07.19-DUAL-PROVIDER P6.3
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
