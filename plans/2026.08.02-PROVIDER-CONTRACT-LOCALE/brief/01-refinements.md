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
