<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:6c420f5f37689d7d76abae710f281ae09fa891a5a86f97ffd9a58c95e682b3cf
Adapter: task.cursor-command/1.0.17
-->
## Native Cursor launch-block — required only at a real user-facing boundary

This generated runtime is the Cursor provider projection. Render only the Cursor-native launch;
never copy Claude slash syntax or Codex `$ task:` as the executable invocation.

At a fresh-session boundary print `**Native Cursor command:**` and a fenced `bash` block which
explicitly pins the repository workspace, mapped model, and autonomy flags:

```bash
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps 'task:<command> <arguments>'
```

`auto` never substitutes a fixed frontier or implementation pin. Current Cursor mapping: economy=composer-2.5-fast, implementation=composer-2.5, frontier=claude-opus-5-thinking-high.

---
disable-model-invocation: true
description: "Run manual Task items under the current attested session route."
argument-hint: "[PLAN-ID] [Pn.m ...]"
---
Выполни «$ARGUMENTS» через canonical `task:plan-exec` lifecycle, но сохрани текущую
provider-attested route и carrier `task:plan-run`. Не переключай модель вручную. Нормальный
low-risk выбор выражается один раз:
`task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())`. Durable старт связывает маршрут
с `route-run-receipt/v1`; не создавай второй route contract в prompt.

1. Вызови `scripts/plan-work.py prepare` один раз с `--command plan-run`. Он владеет recovery,
   batch/route/authority admission, evidence graph, generated carriers, durable start и единым
   execution snapshot. Повторный запуск продолжает тот же durable run.
   Для явно разрешённого отдельного повтора terminal solo item передай
   `--repeat-admission <plan-owned JSON>`: owner decision несёт exact marker
   `[REPEAT-ADMISSION:<digest>]`; контракт строит `task.plan_repeat.build()`.
   Он связывает историю, текущий GREEN дизайн и новую run identity; стандартные
   route/authority/input gates сохраняются. Без grant terminal item не переисполняй.
2. Реализуй только Scope Included. Выбирай порядок чтения и работы самостоятельно. Для обычной
   обратимой работы достаточно self-check и affected tests. Расширяй validation или независимое
   review только из-за конкретного риска либо явного требования владельца.
3. Сохрани GREEN evidence и terminal journal event, затем один раз вызови
   `scripts/plan-work.py finalize`. Runtime обновит затронутые views, следующий ready bundle и
   delivery receipt. Не повторяй preflight и не перечитывай полные carriers без именованной
   неоднозначности.
4. Продолжай разрешённую работу в этой сессии. Остановись только на реальной owner/external
   boundary, недостающем решении или исчерпанном контексте. Один scoped commit — штатный путь.

Не выдумывай evidence и не обходи security/auth, payments, destructive/irreversible, public
contract или shared-state boundaries. Existing dirty changes принадлежат владельцу.

В финале обычного same-session local closure дай краткий результат и точный semantic Next из
receipt. Byte-exact shared final fragment нужен только когда его требует terminal lease,
cross-session/provider handoff, owner/external wait или release/public boundary.
