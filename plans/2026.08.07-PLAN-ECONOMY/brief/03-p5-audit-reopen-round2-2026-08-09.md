# 2026-08-09 — RED-аудит P5, заход 2: повторный реопен по §3

**Вход владельца:** `$ task:plan-design 2026.08.07-PLAN-ECONOMY P5` в режиме реопена по
четырём шагам, не детализации. Первым источником служит последний блок
`phases/P5/P5.md` → `## Audit P5 — 2026-08-09` с `Заход: 2`.

**Обязательный результат:**

1. Ввести один semantic-outcome reducer для auto-answer/response и сверить один исход в
   item state, `pending_groups()`, `unresolved_for_phase()`, owner-gate projection и phase join.
   Auto-answer, переклассифицированный в `authorization`, остаётся pending/blocked.
2. Считать 2–5 substantive options отдельно от обязательных `escalate`/`reject`; добавить
   регрессии обеих допустимых границ и контрпример без substantive options.
3. Сделать request/resolve projection failure idempotently retryable: ошибка не публикует
   continuation, а повтор того же decision доводит queue, journal и generated views до одного
   состояния. Оба пути покрываются отдельными regression tests.
4. Расширить executable acceptance P5.5 producer/error-сценариями, повторить detached validation,
   обновить terminal evidence/Known Deviations и переписать протухший handoff.

**Границы:** не менять frozen `decision-request` v1/`authority-frame` v1 и owner hash D143;
не менять P4 fingerprint/packet/`same_return_max`, reader-contract carrier paths, P6,
`packages/artifex` и P5.1–P5.3. Fixtures/schema/acceptance не ослаблять; исходную красноту новых
regression tests доказать воспроизводимым test-only commit до исправления.
