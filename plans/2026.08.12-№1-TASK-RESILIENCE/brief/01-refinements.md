# Уточнения владельца

## 2026-08-13 — постархивное P7-продолжение

- Владелец вызвал `$ task:plan-design 2026.08.12-№1-TASK-RESILIENCE P7` и тем самым
  авторизовал вернуть архивный план в active-path только для текущего working-tree candidate и
  `artifacts/roadmap-snapshots`.
- Требуется подготовить исполнимые items для отдельных свежих сессий; текущий design root ничего
  из product scope не исполняет.
- После terminal P7, phase audit и close план должен быть снова перенесён в `plans/archive/`;
  до полного закрытия он остаётся активным.
- P0–P6, теги `v0.13.0`/`v0.13.1`/`v0.13.2`, push/GitHub release и completed rollout не
  переоткрываются и не получают новую authorization.

## 2026-08-13 — owner response: exact v0.13.2 after v0.13.1 validation RED

- Владелец запустил exact action-ref `$ task:plan-design 2026.08.12-№1-TASK-RESILIENCE P6.2`
  из DecisionRequest `P6-audit-v0131-validation-boundary-2026-08-13` и тем самым выбрал
  option `repair-and-patch-release-v0.13.2`.
- Новый release candidate обязан быть отдельным committed SHA с byte-fresh P6.2 spec/bundle/state;
  все release gates повторяются в clean detached worktree ровно на этом SHA без overlay.
- После зелёных gates выпускается только новый локальный annotated `v0.13.2`; tag objects и peeled
  commits `v0.13.0`/`v0.13.1` не удаляются, не двигаются и не перезаписываются.
- P6.3/P6.4 evidence, push, GitHub release, registered rollout и P0–P5 остаются вне scope.

## 2026-08-13 — owner response: P6 fingerprint repair and patch release

- Владелец запустил exact action-ref `$ task:plan-design 2026.08.12-№1-TASK-RESILIENCE P6.2`
  из DecisionRequest `P6-audit-frozen-release-boundary-2026-08-13`.
- Выбран вариант `repair-and-patch-release`: исправить deterministic tracked-tree/glob
  fingerprint, повторно квалифицировать candidate и выпустить patch `v0.13.1`.
- `v0.13.0`, P6.3/P6.4 evidence, push/GitHub release и P0–P5 не трогаются.

## 2026-08-13 — effective-route incident before P6.2

- Владелец повторно запустил exact native `task:plan-design` route, но agent ложно принял
  `codex doctor --json` config за effective route и отказал в P6.2.
- Снача исправить общий Codex plan-command routing gate, затем сразу довести P6.2 до DoR.
- Product fix должен войти в `v0.13.0`; tag на прежний P6.1 target больше недопустим.

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

## 2026-08-13 — P5.2 design-item recovery

- Владелец запустил `$ task:plan-design 2026.08.12-№1-TASK-RESILIENCE P5.2` для
  восстановления executable ТЗ и digest-qualified bundle без ручной подмены
  generated carrier.
- Удалённая roadmap-запись `2026.08.10-audit-before-close-phase-gate.md` остаётся
  historical Git evidence; Required Reads ссылаются только на существующие current
  carriers.
- P5.2 ограничен candidate fingerprint/audit policy/close gate/terminal closure seam;
  return-loop `plan_returns.py`, полная spec→product→closure topology и provider projection в него
  не входят.

## 2026-08-13 — owner refinement: audit должен быть audit-fixer

- После завершения ограниченной по объёму фазы её audit должен по горячим следам
  сам исправлять все безопасные in-scope отклонения, а не выдавать отдельные
  design/dev запуски и ещё один audit.
- `🟠 Done with deviations` или найденная во время audit проблема — это вход в repair,
  а не разрешение сохранить долг или поставить block из-за сложности.
- Аудитор остаётся свежим независимым root относительно исполнителя, но после
  находки он же становится owning fixer: группирует симптомы по root seam,
  чинит, повторяет исходные validation и строит новый candidate в том же root.
- Штатная остановка допустима только на доказанной authority/safety или
  public/frozen-contract границе. Объём тестов, несколько файлов, generator drift,
  грязное дерево или сама сложность решения не являются terminal evidence.
- Программный audit cap остаётся только аварийной защитой; обычный путь
  больше не создаёт audit → repair-run → audit → owner loop.
