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
