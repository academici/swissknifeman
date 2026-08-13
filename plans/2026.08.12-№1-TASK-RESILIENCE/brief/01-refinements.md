# Уточнения владельца

## 2026-08-12 — коррекция формы плана

Владелец отверг преждевременно закрытый однофазный v1-план. Требуется:

- план остаётся в активном `plans/2026.08.12-№1-TASK-RESILIENCE/` до конца release/rollout;
- `Layout v2` задаётся явно;
- каждая фаза и каждый item имеют свой отдельный детальный carrier;
- прежде написанная реализация — лишь candidate, который заново проходит пофазную приёмку;
- тег и rollout не выполняются до закрытия видимого активного плана.

Созданный до уточнения локальный тег `v0.12.0` удалён; rollout не запускался.

## 2026-08-12 — обязательный RAG и Layout v1 retirement

- Обязательный Perplexity Web нельзя считать выполненным при пустом/недоступном ответе или
  заменять базовым поиском; нужен повтор, а до успеха план остаётся `rag-pending`.
- Из Task удаляется именно execution layout v1 (не все unrelated контракты с суффиксом `v1`).
- Все активные v1 планы в repository и зарегистрированных проектах мигрируются в v2 до удаления
  reader/command/migrator path; архивные v1 остаются inert history.
- После ремонта `perplexity-web-mcp` формирование этого плана продолжается, а прежние fallback
  результаты не используются как замена обязательного Perplexity evidence.

## 2026-08-12 — обязательные execution batches

- До коррекции план не отвечал, какие items исполняются `solo`, а какие одной сессией.
- Сначала исправляется сама схема/шаблон/lint/handoff, чтобы `Batch` больше нельзя было забыть;
  только затем мигрируется этот план.
- Нельзя атомизировать ради атомизации: adjacent items группируются при реальной экономии
  повторного чтения, setup и Validation, сохраняя per-item commits/gates.
- `solo` используется только с конкретной hard/economy boundary; Batch всегда виден в команде
  следующего исполнения и не пересекает phase audit/close.

## 2026-08-12 — orchestration negation lint roadmap

- Включить `roadmap/2026.08.12-task-orchestration-negation-lint.md` в активный план после
  repo-grounded анализа.
- Явное «оркестрация не заявлена/не требуется» не должно считаться positive declaration.
- Настоящий `scriptPath`/multi-agent positive и positive после отрицания остаются gated.
- Не переписывать пострадавший Agelto plan эвфемизмами; исправить общий parser и parity.

## 2026-08-12 — autonomous conflict resolution

- Владелец просит разрешать все локальные конфликты автономно и доводить авторизованный scope до terminal result.
- P1.1 repair выбирает минимальную обратимую правку Validation carrier; product scope и public/frozen contracts не расширяются.

## 2026-08-12 — P1.2 full-fleet admission boundary

- Владелец разрешил узкий redesign migrator/linter compatibility для P1.2 через
  `plan_migrate.py`, `plan_lint_checks/parsing.py` и Task tests.
- После этого решения read-only rehearsal всех 15 targets показал, что проблема
  не сводится к Routing: 9/15 targets доходят до output lint, 0/15 проходят его.
- Выбор политики для missing/unknown journal, noncanonical decisions, empty phases,
  terminal-state projection, read-budget, stale handoff и controlled in-place write не входит в
  прежний exact action. P1.2 не объявляется DoR без нового owner decision.

## 2026-08-12 — owner response: phase decomposition

- Владелец выбрал `authorize-phase-redesign` в `DR-P1.2-full-fleet-migration-policy`.
- Узкая Routing compatibility остаётся отдельным item; policy/dry-run, external apply/zero-live
  и reader retirement получают разные acceptance/rollback boundaries.
- Авторизация покрывает 15 exact `migration_order` targets; registry-row deletion и semantic repair
  invalid candidates вне этого списка остаются explicit authority gates, если они ещё есть
  в fresh inventory.

## 2026-08-12 — P1.5 repair-forward design

- Владелец запустил `$ task:plan-design 2026.08.12-№1-TASK-RESILIENCE P1.5`
  после начала retirement implementation.
- Фактический gate показал, что P1.5 должен охватить не только runtime
  branches, но и весь shared v1-shaped fixture fleet, terminal-bundle admission boundary,
  generated provider parity и release-visible CHANGELOG.
- Закрытые P1.1–P1.4 specs/bundles не переписываются под новый
  filesystem; live re-resolution ограничивается nonterminal executable items.

## 2026-08-12 — owner escalation: repeated executor restarts

- Владелец потребовал зафиксировать в плане полный incident по поводу
  семи рестартов P1.5 и довести работу без новых запусков.
- `findings/10-P1-execution-restart-incident.md` хранит exact count, chronology,
  impact, root cause и обязательные prevention controls.
- До конца текущей owner-сессии действует zero-restart invariant:
  route/protocol deviation фиксируется, но чинится прямо в этом процессе.

## 2026-08-12 — P3 batch continuation

Владелец уточнил, что P3.1–P3.3 должны исполняться как один уже объявленный
`B-P3-CONTINUE`, а не как отдельные одиночные запуски. P3.1 уже терминален; после ремонта
portable Inputs/DoR P3.2 handoff обязан адресовать весь оставшийся suffix `P3.2-P3.3` по
D10 и `roadmap.md`. RAG:— (owner-grounded: уточнение владельца 2026-08-12; repo-grounded: D10,
`roadmap.md`).

## 2026-08-13 — owner mandate: resolve P4.2 in the current session

- Владелец запретил парковать P4.2 на terminal `Blocked` и потребовал
  разрешить конфликт автономно в текущей сессии и вернуть результат.
- Immediate projections canonical command sources переносятся в P4.2: owning renderer,
  Codex adapters/locks, Claude golden fixtures и operator reference. P5.3 сохраняет
  final aggregate parity/registry/docs sweep, но не принимает stale outputs от раннего producer.
