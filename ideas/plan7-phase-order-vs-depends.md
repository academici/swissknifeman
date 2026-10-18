# PLAN7: порядок P2 → P1 противоречит зависимостям плана

- Что произошло: `orch conduct run --items P2.1 P2.2 P2.3` → `CLAIM_BLOCKED DEPENDENCY_NOT_READY: phase P2 waits for phase P1`.
  До этого: `PHASE_NOT_DETAILED` (P2 был skeleton) — выполнен `planner design-done PLAN7 P2` (check 0/0).
- Причина: в `phase.json` P2 объявлена зависимость от P1; промт владельца задаёт порядок P2 → P1.
- Сделано: ничего не обходил (зависимости не правил).
- Варианты: (a) идти по плану P1 → P2 → P3 → P4 (P1.2 трогает живое состояние машины: стоп conduct, бэкап tar);
  (b) снять зависимость P2→P1 решением владельца, если P2 не требует единой папки машины.
