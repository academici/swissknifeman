# P1 design reconciliation — read budget and preflight

**Дата:** 2026-08-11
**Тип:** repo-grounded design evidence

## Read-budget defect

`2026.08.10-TASK-LEAN-AUTONOMY P1.1` закрыл package runtime/docs scope, но его handoff и
`findings/P1.1-runtime-alignment.md` сохранили material deviation: layout-v2 plan не имел
plan-owned `root/contracts/read-budget-v1.md`. Task admission загружает этот exact path и не
имеет числового fallback. До активации P1.2 обычный plan-lint не диагностировал отсутствие,
поскольку execution-only gate применяется только к активной фазе.

Решение D15 потребляет frozen donor contract v1.1.0 без изменения смысла. Это plan-design
carrier, а не ретроактивное расширение sealed P1.1 Files. После materialization обязательны
direct `plan-weight item` checks для P1.1/P1.2, bundle regeneration и plan-lint.

## Environment preflight

- `pwd` и repository root совпали; unrelated dirty paths существовали до этого design-захода и
  не входят в target-plan scope.
- `codex doctor --json` вернул `overallStatus=ok`, approval `Never`, unrestricted filesystem и
  network-enabled sandbox. Он показывает configured default `gpt-5.6-terra`, но не является
  независимой аттестацией active session selector/effort; semantic `plan-design` route остаётся
  `gpt-5.6-sol/high` с этой явно записанной границей evidence.
- Codex-native `.codex/hooks.json` разрешился в читаемый `.codex/hooks/lifecycle.py`; synthetic
  `SessionStart/context.observer` вернул exit 0, поэтому exit 127/path defect не наблюдался.
- `packages/maind/bin/maind health --cwd` прошёл все project checks.
- `packages/harness/bin/harness doctor` сообщил missing/stale global Claude hooks, а settings
  audit — 7 недоступных Claude hook paths. Это не зелёная Claude telemetry проверка. Для P1.2
  missing optional run-report остаётся D13 `coverage-limited`, но required journal identity и
  acceptance evidence не ослабляются.
- Все шесть D9+D13 URL отсутствуют в committed `HEAD:docs/reference.md`; существующий dirty
  `docs/reference.md` не читается как authority и не изменяется этим планом. После D15 P1.2
  остаётся structural waiting до отдельного owner commit.

RAG:— (repo-grounded: observed command output 2026-08-11, D9, D13,
`packages/task/lib/task/plan_admission.py`).
