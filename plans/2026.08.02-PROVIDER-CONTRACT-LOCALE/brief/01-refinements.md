# Refinements

## 2026-08-14 — P3.2–P3.3 design refinement

Владелец явно запросил `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE
P3.2-P3.3`. Заход ограничен исполняемостью двух оставшихся runtime-item'ов P3:
сохранить замороженные P1/P2 semantics, устранить их read-budget дефекты, закрепить
воспроизведённый Harness relative-target regression и вернуть управление отдельному
`p3-runtime` execution root. Реализация, provider/fleet writes и изменение frozen contracts
в этот design-заход не входят.
