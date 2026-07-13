# HANDOFF — 2026-07-13 — after P1.1

**Next:** /task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P1.2

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — текст ТЗ дословный, решения приняты (D5/D6), исполнителю решать нечего |
| Context | continue (/clear) — ручной item |
| Суть | `plan-lint --baseline`/`--gate` — детерминированный счёт новых ошибок (K), завершает разблокировку P1 |

````
/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P1.2 — cold-start reads: plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md (Context, Execution Rules, §3 Routing, D-лог) · plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P1.md (Phase Context + item P1.2 целиком, Completion Notes P1.1 для контекста реализации) · packages/task/lib/task/plan_lint.py (после P1.1 — Diagnostics/main) · packages/skiller/skills/general/plan-protocol/SKILL.ru.md §8 (после P1.1)
````

**Done:** P1.1 закрыт (коммит `4c03715`): `SKILL.ru.md` §8 несёт закрытый enum 8 форм
`handoff.Next` + канонический порядок закрытия item'а (lint ПОСЛЕ handoff, счёт с атрибуцией);
`plan_lint.py` — резолвер enum'а (таблица regex вместо жёсткой пары, m8/B1/N1/N2 закрыты),
actionable-текст ERROR скелет-item'а, `discover_plan_dirs` больше не линтит `plans/archive/`
как план — линтит её подкаталоги как архивные планы (N3/D14). Тесты 85→100 (+19), все зелёные.
`validate.sh` пакета `task`: ПРОВАЛ → OK. Регресс по 9 корням флота — ноль новых ERROR вне
`/archive/`; REGHUB 79→78 (как предсказано findings §3). Полные детали —
`phases/P1.md` P1.1 Completion Notes.

**Remaining:** P1.2 (детерминированный `--baseline`/`--gate` — 1 item) → P2 (4 items, canon
routing-gate/status-rule/Contracts/EN-регенерация; **opus/high, ЗАПУСК ВРУЧНУЮ** — `plan-exec`
по своему новому гейту (P2.1) обязан такие items отклонять) → P3 (4 items, команды plan-*) →
P4 (3 items, регресс по флоту + REGHUB эскалация + доки).

**Sources of truth:** `plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md` (Meta, Execution Rules, §3
Routing, D-лог) · `phases/P1.md` (P1.1 Completion Notes — детали фикса; P1.2 ТЗ) ·
`findings/P0-protocol-gap-recon.md` · SSOT-цели: `packages/skiller/skills/general/plan-protocol/SKILL.ru.md`,
`packages/task/lib/task/plan_lint.py`.

**Open risks:**
- Back-compat флота: любая следующая правка линтера (P1.2 добавляет `--baseline`/`--gate`,
  затрагивает только CLI-флаги и сравнение диагностик — риск ниже, чем у P1.1) — регресс-прогон
  по 9 корням обязателен в Validation P1.2 тоже.
- Фаза P2 требует РУЧНОГО запуска под opus/high (§3 Routing, Exec = manual) — до P2.1 (routing-
  гейт) `plan-exec` этот гейт ещё не умеет; не запускать P2.x через `plan-exec` по инерции.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там, отдельный.
- Внутри `plans/archive/` (swissknifeman: чисто; vaulter: VLT-CANON/VLT-REMED несут новые
  ERROR/WARNING, впервые пролинтованы) — вне Scope этого плана, архивные планы не переоткрываем.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: кросс-репо push-уведомление о bump'е контракта (роадмап, вне scope); миграция §3
  Routing 26 живых планов на канон-форму с колонкой Exec (back-compat: старые формы валидны).
- open_questions: развилки `plan.md` §Обсуждение (авто-делегация в Workflow, релакс ERROR→WARNING
  на скелетах) — обе отклонены D-логом, возражение владельца перебивает новым D# со `supersedes`.
