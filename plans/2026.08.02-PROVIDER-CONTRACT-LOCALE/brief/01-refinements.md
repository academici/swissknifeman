# Refinements

## 2026-08-14 — P3.2–P3.3 design refinement

Владелец явно запросил `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE
P3.2-P3.3`. Заход ограничен исполняемостью двух оставшихся runtime-item'ов P3:
сохранить замороженные P1/P2 semantics, устранить их read-budget дефекты, закрепить
воспроизведённый Harness relative-target regression и вернуть управление отдельному
`p3-runtime` execution root. Реализация, provider/fleet writes и изменение frozen contracts
в этот design-заход не входят.

## 2026-08-15 — P4 readiness reconciliation

Владелец явно запустил `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P4`
после nonterminal P4.1 block-candidate. Заход ограничен исполняемостью уже принятой
шестипунктной P4: согласовать Routing с per-cwd roadmap, снять read-budget и
stage-aware producer-edge дефекты, сохранить frozen P1/P2/P3 semantics и P4.1 execution
evidence, затем вернуть владельцу отдельный routed resume только P4.1. Product
implementation, consumer/fleet writes и пересмотр frozen locale/authoring contracts в этот
design-заход не входят.

## 2026-08-15 — P4.4 round-2 recovery refinement

Владелец явно запустил `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.4`
после второго committed `FIX_REQUIRED` checkpoint `p4.4-task-plan-1`. Заход ограничен
восстановлением исполняемости того же P4.4 scope: не продолжать запрещённый третий review,
сохранить failed evidence append-only, закрыть complete-literal / authoring-review /
false-RU-overlay gaps новым material checkpoint и вернуть владельцу отдельный routed resume.
Frozen locale/authoring contracts, semantic command IDs, helper API, generated targets и
consumer/fleet/trust/credential writes в этот design-заход не входят.

## 2026-08-15 — P4.4 owner-approved post-round-2 contract revision

Durable response `P4.4-task-plan-2-round-2-owner-choice` выбрал `contract-revision` после
второго `FIX_REQUIRED` replacement checkpoint. Заход должен учесть уже committed fixes и
pass content-review evidence, не запускать новый product-repair loop и не считать ранний
handoff на P4.5 доказательством закрытия P4.4. Разрешён один immutable closure-checkpoint
для exact committed P4.4 delta; его `FIX_REQUIRED` снова требует явного решения владельца.
Frozen contracts, generated-target ownership и оставшиеся package-cwd rows не ослабляются.

## 2026-08-16 — P6.3 public health schema carrier

После доказанного отсутствия точной evidence-set wrapper-схемы в публичных CLI-документах
владелец выбрал `admit_public_schema_carrier` для
`DR-P6.3-PUBLIC-HEALTH-SCHEMA-1`. Исполняемость P6.3 восстанавливается отдельным frozen
plan-local carrier: одно bounded чтение owning P6.2 interface разрешено только для его
проектирования, а runtime-exporter продолжает работать исключительно через публичный mAInd
CLI. Изменения mAInd, provider/fleet repair и ослабление non-green семантики не разрешены.

## 2026-08-16 — P6 required/optional release membership

После P6 audit владелец выбрал `define_optional_project_membership` для
`DR-P6-BRAIN-OPTIONALITY-1`. Brain остаётся optional integration: его отсутствие или non-green
состояние не должно блокировать package runtime/fleet release, но обязано оставаться видимым в
exact-set health evidence. Решение реализуется generic sealed membership carrier без hardcode
имени/ID и без изменения P6.2 package runtime или public mAInd evidence-set schema. Required
projects и global P5/source/privacy/semantic blockers не ослабляются.

## 2026-08-16 — P7.1 replay admission refinement

Владелец явно запустил `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.1`
после того, как первый execution корректно остановился до provider-вызова: три принятые P4.3
`semantic.skill`-строки не были связаны с точным capability/workflow/grader/ablation набором, а
P2 fixture является только `structure-only`. Заход ограничен одним frozen P7.1 admission carrier,
D-записью и исполняемым рефайном того же item. P2/P4/P5/P6 не переоткрываются; одобренный пустой
P5 WAL, provider/fleet state, product code и release authority не меняются.

## 2026-08-17 — P7.3 owner-approved bounded redesign

Владелец явно выбрал `redesign-bounded-inputs` и `revise-acceptance` для двух durable
decision requests P7.3. Item сохраняет тот же operations/docs/release-manifest scope, но читает
компактный contract synthesis вместо дублированных полных контрактов и больших generated/docs
targets. Непустой точный blocker-set больше не делает корректную сборку manifest невозможной:
manifest обязан воспроизвести blockers и иметь `releasable=false`; это не исключение, не release
authority и не разрешение tag/push/publish, fleet rollout или provider repair.

## 2026-08-17 — P7 RED-audit forward recovery

Владелец явно запустил `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P7`
из P7.4 RED handoff. Заход маршрутизирует F1–F6 через их реальных владельцев без ослабления D88
или D89: локальный verifier/candidate seam получает adjacent chain P7.5–P7.6, generated
bookkeeping чинится у владельцев в design-root, а fleet rollout и live provider efficacy остаются
внешними deferred gates. Старый P7.4 RED не переписывается и не переоткрывается; после P7.6
последовательный P7.7 выполняет один bounded delta audit, не второй whole-plan audit.

## 2026-08-17 — P7.5 frozen-crosswalk return

Владелец явно запустил `$ task:plan-design
2026.08.02-PROVIDER-CONTRACT-LOCALE P7.5` после того, как execution воспроизвёл
противоречие: immutable P7.4 crosswalk содержит D1–D89, current decisions
содержат D1–D90, а P7.5 Validation требует текущий exact-set GREEN, хотя
сам carrier не входит в P7.5 Files и назначен P7.7. Design-root не изменил
ТЗ: обязательный isolated return reviewer вернул schema-invalid verdict,
а deterministic reducer запретил продолжение. Точные evidence и условие
возобновления зафиксированы в
`findings/P7.5-plan-design-return-review-2026-08-17.md`; product implementation, audit
baseline, contracts и release authority не менялись.
