<!-- plan-projection
projection: decision-current
projection_version: v1
source_scope: decisions/
through: 2026-08-10/D9
inputs_sha256: 29fd177f697c80375abc57196bde8eefd4aaa201173e6e48e86ce52f294479f0
generated_by: task plan-views decisions
-->

# Текущие решения

> Не править руками: это генерируемый вид.

| ID | Date | Status | Items | Решение |
|:--|:--|:--|:--|:--|
| D1 | 2026-08-10 | accepted | P0.2, P1.1, P1.2 | Task фиксирует строгий initial contract, а порядок, группировка и локальный repair во время исполнения являются адаптивными решениями owning-агента внутри tolerances. |
| D10 | 2026-08-11 | accepted | P1.1, P1.2 | Единственный real post-P1.1 canary — фактический запуск `task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2` от pre-mutation admission до pre-final, journal/state regeneration и handoff. Для двух условных событий scorecard использует закрытые значения: - `local_repair: observed` либо `local_repair: not-observed (no eligible local failure fingerprint in the P1.2 live run)`; - `material_review: observed` либо `material_review: not-observed (no D3 material trigger: scope/SHA/risk remained stable)`. Оба `not-observed` совместимы с GO, если соответствующее событие действительно не возникло и все остальные acceptance predicates green; replay не подменяет этот live window. P1.1 до возможного D9 waiting добавляет одну factual root `CHANGELOG.md` запись в `[Unreleased]` про уже реализованные release-visible instruction/command/docs изменения. Запись не утверждает GO и не удаляется при ADJUST. Если owning-package remediation после ADJUST меняет опубликованный смысл, её owner обновляет ту же root ledger запись до своего handoff. |
| D2 | 2026-08-10 | accepted | P0.2, P1.1 | Мелкий обратимый дефект в scope исправляется в той же owning-сессии. Повтор одного failure fingerprint вызывает смену тактики и максимум один scoped review; остановка обязательна только на material/authority boundary или при подтверждённом no-progress. |
| D3 | 2026-08-10 | accepted | P0.2, P1.1, P1.2 | После единственного pre-exec design audit новый аудит запускается только новым материальным триггером. Неизменившийся scope/SHA/risk переиспользует scoped verdict; minor/nit исправляется без re-audit. |
| D4 | 2026-08-10 | accepted | P0.1, P0.2 | Always-on инструкции содержат только устойчивые инварианты и маршрутизацию. Подробная процедура и edge cases живут в on-demand skill/reference; generated projections меняются только через канонический Harness/Skiller источник. |
| D5 | 2026-08-10 | accepted | P1.1, P1.2 | Focused deterministic checks остаются safety net; приёмка operating model требует живого canary и разбора фактической траектории. Новая exhaustive test matrix не создаётся. |
| D6 | 2026-08-10 | accepted | P0.1, P0.2 | Если задача явно требует Perplexity Web, проверяется базовый search. Его недоступность или функциональный отказ после одной узкой повторной попытки является owner-visible stop; другой web-инструмент не подменяет обязательный retrieval молча. |
| D7 | 2026-08-10 | accepted | P0.1, P0.2, P1.1, P1.2 | Четыре item'а сохраняются, но каждый имеет одного write-owner и exact cwd: P0.1 — Harness, P0.2 — Skiller, P1.1 — Task, P1.2 — repository root. Generated outputs другого уровня допустимы только как deterministic result named owner generator; item не поглощает source edits соседнего package. |
| D8 | 2026-08-10 | accepted | P1.2 | GO означает: все P1.2 acceptance predicates green, item закрывается `🟢 Done`, а Next ведёт к `close: task:plan-close 2026.08.10-TASK-LEAN-AUTONOMY P1`. ADJUST означает: хотя бы один predicate red/unknown, P1.2 остаётся `🟡 In progress`, через owner tool создаётся ровно один durable DecisionRequest с exact owning-package continuation, а handoff объявляет структурный `waiting: <decision-id resolved> → run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2`. |
| D9 | 2026-08-10 | accepted | P1.2 | `docs/reference.md` остаётся carrier'ом и write scope владельца существующего foreign diff, а не P1.2. До старта P1.2 repository owner/foreign-diff owner отдельно reconciles и commits строку, в которой присутствуют exact official URLs: - `https://www.prince2official.com/Prince2-News-and-Announcements/agile-progress-reporting-dashboards` - `https://github.github.com/spec-kit/concepts/spec-of-specs.html` P1.2 проверяет оба URL только в committed `HEAD:docs/reference.md`. Red prerequisite оставляет P1.2 `⬜ Not started` и публикует structural waiting Next; текущий dirty файл не читается как approval, не коммитится, не откатывается и не перезаписывается этим планом. |
