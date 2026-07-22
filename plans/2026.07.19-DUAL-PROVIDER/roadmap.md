# Roadmap исполнения — 2026.07.19-DUAL-PROVIDER

<!-- Собран после полной детализации P0–P7. Отвечает на «какую команду дальше?» без
     повторного анализа всего плана. Живой документ: finish/design audit, закрытие фазы
     или re-design обновляют таблицу и Update Log. Roadmap не переопределяет Routing §3.
     Порядок строго phase-first: P0→P1→P2→P3→P4→P5→P6→P7. До finish + GREEN design
     audit исполнение любого item запрещено. -->

**Обновлён:** 2026-07-22 · **Соответствует plan.md:** v1.4.42

> **Статус exec:** D103 reopens only the sequential P2.6→P5.8→P6.7→P6.8 remediation.
> D104 and terminal P2.6 are complete; P5.8 and P5 close are complete pending fresh P5 audit. P7.2 remains
> blocked, while P7.3+, FOREMAN, fleet and push stay closed.

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
| P2.6 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ D104 exact additive P2 API/contract | D105 seal/dispatch repair and final independent audit complete; no live root write |
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
| P5.8 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | D104 consumed via P2.6 | native Codex lifecycle fragment/handler and P5 phase close complete; fresh P5 audit remains |
| P6.1 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | — | mAInd provider deploy loop против frozen P1/P2/P5 contracts |
| P6.2 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | — | provider context/trust/instructions and exact 30-row provisioner matrix focused-green |
| P6.3 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/xhigh | ✅ analytics contract/privacy/migration | owner-gated schema/storage freeze completed |
| P6.4 | solo | plan-run (manual) — 🟢 | gpt-5.6-terra/high | ✅ shared-core/analyst contribution | multi-package readers/store migration completed after frozen P6.3 |
| P6.5 | solo | plan-exec — 🟢 | gpt-5.6-terra/medium | — | integrated conformance + durable pre-restart checkpoint |
| P6.6 | solo | plan-exec (NEW SESSION) — 🟢 | gpt-5.6-terra/medium | — | mandatory cold restart; нельзя объединять с P6.5 |
| P6.7 | solo | plan-run (manual) — ⬜ | gpt-5.6-terra/high | D104 consumed via P2.6 | P6-owned native composition/deploy integration; temporary roots only |
| P6.8 | solo | plan-exec — ⬜ | gpt-5.6-terra/medium | — | independent temporary-root and live no-write proof; no apply |
| P7.1 | solo | plan-run (manual) — 🟢 | gpt-5.6-sol/xhigh | ✅ D99 | terminal generated docs/exact-set |
| P7.2 | solo | plan-run (manual) — 🔴 | gpt-5.6-terra/high | ✅ D# on live apply after rerun | blocked until P2.6→P6.8 and fresh P6 audit are GREEN |
| P7.3 | solo | plan-run (manual) | gpt-5.6-terra/high | ✅ D# на exact bootstrap cleanup inventory | guarded destructive cleanup и release manifest; отдельный rollback boundary |
| P7.4 | solo | plan-run (manual, NEW SESSION) | gpt-5.6-sol/xhigh | ✅ literal GREEN + explicit owner D# | cold adversarial audit; только GREEN+owner D# открывает reconcile |

## Solo-обоснование и отсутствие batches/workflows

Все 49 item идут `solo`. В каждой фазе terminal Deliverable предыдущего item является
Inputs следующего, поэтому merge-criterion plan-protocol для batch/workflow не выполняется:
внутрифазных независимых scopes N≥3 нет. Contract/security/canon/release items имеют
`Review=full` и owner/commit boundaries; conformance items намеренно отделены от авторов
implementation. P5.6→P5.7 — contract→prescribed implementation, поэтому их нельзя
объединять; P6.5→P6.6 и P7.3→P7.4 дополнительно разделены обязательным NEW SESSION.

## P7 session-by-session execution process

> D103 temporarily blocks this console at P7.2. No P7 command is runnable until P2.6,
> P5.8, P6.7, P6.8 and a fresh P6 audit are terminal GREEN; this section does not authorize
> their execution or P7.3+.

P7 исполняется четырьмя независимыми внешними Codex-процессами: каждый item получает
собственную shell-команду и точный route из `plan.md` §3. После GREEN item executor
обязан закончить final response следующим полным launch-block из этого раздела и не
запускать successor самостоятельно.

Переход между terminal items:

1. Завершить текущий Codex process. `/clear`, compaction и продолжение текущего чата
   не заменяют обязательную новую сессию.
2. Запустить точную shell-команду следующего item. `resume --last` и chat summary
   не использовать; новый процесс читает plan/phase/handoff с диска.
3. До writes executor печатает observed model/effort, branch/worktree, `approval_policy=never`,
   `sandbox=unrestricted`, проходит hook probe, `maind health --cwd --strict` и target plan-lint.
   Route mismatch или RED strict-health останавливают writes и дают bounded repair launch-block.
4. Один writer работает в `/home/vostrikov/projects/packages/swissknifeman` на
   cumulative `codex/provider-project-sync`. Dirty root, закрытые predecessor phases, FOREMAN,
   fleet, unrelated projects и push не трогаются; generic subagents не создаются.
5. Owner gate внутри P7.1/P7.2/P7.3/P7.4 не завершает сессию: executor сначала готовит
   exact inventory/evidence/D#, печатает одну copy-paste approval-строку и после ответа
   владельца завершает тот же item в той же сессии.

### P7.1 — capability manifest, production gates и generated provider docs

| Параметр | Значение |
|:--|:--|
| Semantic command | `run-items: task:plan-run 2026.07.19-DUAL-PROVIDER P7.1` |
| Model / Effort | `gpt-5.6-sol` / `xhigh` |
| Context | mandatory fresh Codex process; no resume/chat carry-over |
| Owner gate | Exact D# на candidate manifest hash/catalog set и additive core/public seam до production switch. |
| Переход | Только GREEN P7.1 открывает P7.2; final response печатает launch P7.2. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman --no-alt-screen \
  -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' \
  -a never -s danger-full-access \
  'Выполни $ task:plan-run 2026.07.19-DUAL-PROVIDER P7.1 в новой сессии. Начни с research/22-p7-capability-manifest-remediation.md и findings/P7.1-capability-manifest-gap-2026-07-22.md. Собери exact manifest candidate + shared-core contribution review; до production switch выдай один exact Owner D# и approval-строку, затем продолжи тот же item после ответа. Только P7.1; frozen semantics, closed predecessor deliverables, P7.2+, live provider outputs, FOREMAN, fleet, dirty root и push не трогать. До writes проверь effective route, hooks, strict mAInd health и plan-lint. Один writer, branch codex/provider-project-sync. После GREEN не запускай successor: закончи exact P7.2 launch-block из roadmap.md.'
```

### P7.2 — isolated и live self-host E2E

| Параметр | Значение |
|:--|:--|
| Semantic command | `run-items: task:plan-run 2026.07.19-DUAL-PROVIDER P7.2` |
| Model / Effort | `gpt-5.6-terra` / `high` |
| Context | mandatory fresh Codex process; no resume/chat carry-over |
| Owner gate | Exact D# на live path/action set только после isolated GREEN + rollback rehearsal. |
| Переход | Только terminal GREEN P7.2 открывает P7.3; final response печатает launch P7.3. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman --no-alt-screen \
  -m gpt-5.6-terra -c 'model_reasoning_effort="high"' \
  -a never -s danger-full-access \
  'Выполни $ task:plan-run 2026.07.19-DUAL-PROVIDER P7.2 в новой сессии. Сначала isolated Claude-only, Codex-only и dual-provider matrix с rollback; до доказанного GREEN live state не менять. На owner gate выдай exact D#, exact path/action inventory и одну approval-строку; не спрашивай заранее. Не исправляй package source в evidence item. Только P7.2; закрытые predecessor phases, P7.3+, FOREMAN, fleet и push не трогать. После GREEN не запускай successor: закончи exact P7.3 launch-block из roadmap.md.'
```

### P7.3 — guarded bootstrap cleanup и release manifest

| Параметр | Значение |
|:--|:--|
| Semantic command | `run-items: task:plan-run 2026.07.19-DUAL-PROVIDER P7.3` |
| Model / Effort | `gpt-5.6-terra` / `high` |
| Context | mandatory fresh Codex process; no resume/chat carry-over |
| Owner gate | Exact D# на provenance-backed cleanup path/action inventory до первой mutation. |
| Переход | Только terminal GREEN P7.3 открывает fresh P7.4; final response печатает launch P7.4. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman --no-alt-screen \
  -m gpt-5.6-terra -c 'model_reasoning_effort="high"' \
  -a never -s danger-full-access \
  'Выполни $ task:plan-run 2026.07.19-DUAL-PROVIDER P7.3 в новой сессии. До cleanup mutation собери complete provenance table, replacement hashes, reversible actions и post-smoke plan; затем выдай exact D# и одну approval-строку. Unknown/user-owned/Claude compatibility carriers не удалять; generated outputs только через owning API/CLI. Только P7.3; закрытые predecessor phases, P7.4, FOREMAN, fleet, tag и push не трогать. После GREEN не запускай successor: закончи exact fresh P7.4 launch-block из roadmap.md.'
```

### P7.4 — fresh adversarial release audit

| Параметр | Значение |
|:--|:--|
| Semantic command | `run-items: task:plan-run 2026.07.19-DUAL-PROVIDER P7.4` |
| Model / Effort | `gpt-5.6-sol` / `xhigh` |
| Context | mandatory fresh Codex process; disk evidence first, no resume/chat summary |
| Owner gate | Literal GREEN audit плюс explicit release D#; ATTENTION/RED не открывает FOREMAN. |
| Переход | GREEN + owner D# открывает только `task:plan-close ... P7`; FOREMAN не исполняется. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman --no-alt-screen \
  -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' \
  -a never -s danger-full-access \
  'Выполни $ task:plan-run 2026.07.19-DUAL-PROVIDER P7.4 в новой сессии как independent adversarial audit. Сначала прочитай committed release manifest/P7 evidence с диска; не используй chat summary и не исправляй findings. Пересчитай independent exact sets/hashes, проверь actual Claude/Codex consumers, rollback, privacy и protected delta. Выдай literal GREEN|ATTENTION|RED; только GREEN получает exact owner D# и отдельный P7 close launch-block. Не запускай close самостоятельно. FOREMAN, fleet, package fixes, tag и push не трогать.'
```

### P7 phase close — только после GREEN P7.4 + owner D#

| Параметр | Значение |
|:--|:--|
| Semantic command | `close: task:plan-close 2026.07.19-DUAL-PROVIDER P7` |
| Model / Effort | `gpt-5.6-terra` / `low` |
| Context | mandatory fresh Codex process; plan-step only; no resume/chat carry-over |
| Переход | Reconcile status/journal/handoff once; package validators не повторять. Точный FOREMAN payload берётся из P7.4 evidence. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman --no-alt-screen \
  -m gpt-5.6-terra -c 'model_reasoning_effort="low"' \
  -a never -s danger-full-access \
  'Выполни $ task:plan-close 2026.07.19-DUAL-PROVIDER P7 только после committed literal GREEN P7.4 и exact owner D#. Только plan reconciliation; не повторяй P7 validators, не меняй package code, не исполняй FOREMAN/fleet и не push. В final выдай exact GREEN-gated FOREMAN reconcile launch-block из committed P7.4 evidence, но не запускай его.'
```

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

### P5 audit — D104 lifecycle contribution

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | xhigh |
| Capabilities | command.filesystem-read · command.filesystem-write · command.git-read |
| Context | cold-start — plan-step |
| Суть | Independently audit terminal P5 and the D104 P5.8 lifecycle fragment before P6.7. |

```text
$ task:plan-audit 2026.07.19-DUAL-PROVIDER P5
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
