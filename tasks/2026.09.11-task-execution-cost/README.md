# Task: убрать лишние проверки и завершать пункт в одной сессии

**Статус:** локальная реализация и квалификация завершены; установка в consumer-проекты не выполнялась.
**Дата:** 2026-09-11. **Проверенная база:** `d56e90e3`, с исходными незакоммиченными
изменениями владельца в `docs/reference.md` и `roadmap/README.md`.
**Формат:** одна ограниченная задача с последовательными шагами, без нового executable master plan.

## Результат для владельца

Один пункт должен давать законченный результат: реализация → достаточные проверки → закрытие
в текущей сессии. Повторная проверка требует изменённого входа, конкретного сбоя или нового
непокрытого риска. Зелёный результат сам по себе не запускает следующую проверку.

Проблема подтвердилась кодом, а не только поведением модели: Task одновременно
обещал лёгкий lifecycle и сохранял обязательные audit-переходы. Эти противоречия исправлены
в runtime и канонических инструкциях. Части реализации выполнены Sol/high; сравнительного
измерения моделей здесь нет, поэтому обещать ускорение от выбора модели нельзя.

Формальный многофазный план сейчас не нужен: причины связаны одним lifecycle, точки изменения
известны, миграция обратима. Ни повторный аудит этого отчёта, ни дизайн нового control plane
не являются предварительным условием реализации.

## Источники задачи и разрешённые противоречия

Исходные записи сохранены байт-в-байт в [source-roadmap/](source-roadmap/):

| Запись | Что переносится в задание | Что уточнено |
|:--|:--|:--|
| [Инцидент 10 сентября](source-roadmap/2026.09.10-№1-audit-escalation-regression.md) | Legacy `required` не должен навязывать audit зелёной фазе | Одного предположения агента о риске недостаточно для назначения phase audit |
| [Completion-first](source-roadmap/2026.09.11-plan-run-completion-first-regression.md) | Закрытие текущего пункта выполняется в той же сессии | Утверждение «после P1.4 обязательно audit P1» — историческое; новый Next зависит от действующего admission |
| [Политика согласия](source-roadmap/2026.09.11-owner-consented-risk-based-audit-policy.md) | Direct-close по умолчанию; отдельный audit требует остаточного риска и адресного согласия | Предложенный JSON — эскиз, а не готовая схема; отсутствие согласия не делает RED acceptance зелёным |

Само архивирование означало консолидацию задания; результат последующей реализации описан
ниже. Ссылки и формулировки внутри исходных записей отражают момент инцидента.

## Выполнено 2026-09-11

| Причина | Изменение и доказательство |
|:--|:--|
| F1: автоматический audit | `plan_assurance` и `plan_gates`: GREEN → direct-close; legacy intent — advisory. Missing/RED evidence → текущий owning repair, не audit. Candidate восстанавливается существующим механизмом. |
| F1/F6: адресное согласие | Новый небольшой `audit_admission` использует существующие accepted decisions, owner-message/grant и journal. Согласие связано с phase/candidate/run и конкретным остаточным вопросом; завершённый run потребляет grant. На обычном пути никаких новых записей не требуется. |
| F2/F5: лишняя глубина и повторы | Канон plan-protocol, task-development-philosophy и команды: проверки по риску; актуальное evidence переиспользуется; bookkeeping не требует повторной product validation; нет default full review. |
| F3: незавершённый handoff | `plan_delivery` запрещает Next на close/повтор того же GREEN item, проверяет готовность successor и требует допустимого закрытия полностью GREEN-фазы перед handoff. Честный Blocked и незавершённая фаза не превращаются в бесконечное требование closure. |
| F4: связанный lifecycle | Реальный fixture с git и subprocess проходит product change → одна validation → item journal → phase closure carrier → next bundle → delivery receipt и один commit в той же session/run. Это интеграционный тест runtime, не полный запуск модели на consumer-плане. |

Обязательное acceptance не отменено. Неразрешённый исторический RED/ATTENTION audit
не маскируется новым default: нужен соответствующий GREEN repair. Старые terminal journal rows
без run ID остаются читаемыми для совместимости, но не разрешают запуск нового live audit.
Проверка owner-message повторно использует доверительную модель репозитория; криптографической
аутентификации владельца этим изменением не добавлено.

Канонические источники изменены в `packages/task/commands/` и `packages/skiller/skills/`;
provider projections, runtime skill и lock-файлы обновлены генераторами. Обновлены root
CHANGELOG и существующая документация Task. Нового master plan, telemetry-сервиса,
универсального validation cache или второго terminal guard не создавалось.

### Приёмка и границы

- Финальная Task qualification: `bash packages/task/scripts/validate.sh` — **1046 tests,
  OK (skipped=1), 13.911 s**; plan-lint conflicts — 0. Пропущен fixture реального плана,
  которого больше нет по ожидаемому live-пути; это не проверка архивного/fleet состояния.
- Skiller qualification: `bash packages/skiller/scripts/validate.sh` — **654 tests, OK**;
  проверены 233 skills, registry и Codex publication consumer acceptance. Имеющиеся discovery/
  skill warnings (173) не устранены этой задачей; CORE budget — 431/750 tokens.
- Provider renderer `--check` и registry `--check` — GREEN. Агрегированная документация
  `pnpm docs:build` — exit 0, 7.71 s; предупреждения npm config и bundle >500 kB остаются.
  Первый результат сборки потерялся при сокращении контекста; приведён результат повторного
  запуска, не восстановленный по наличию файлов.
- Интеграционная lifecycle trace: **1 product validation, 0 phase audits**, item и phase terminal
  events в одной session/run; stale spec отклоняется. Тесты delivery отдельно сохраняют
  допустимые Blocked/deviation handoff и GREEN item при другом blocked item фазы.
- Один read-only native smoke: Codex CLI 0.154.0, `gpt-5.6-sol/high`, `-a never`,
  `-s danger-full-access`, изолированный cwd `/tmp/task-execution-smoke.VIwq36`,
  `--ignore-user-config --ephemeral`. Thread: `01a08f61-a95e-7cc0-ae72-e3890de8a63a`.
  Модель прочла сгенерированные команды и правильно описала direct-close legacy GREEN,
  reuse неизменной validation и отдельный audit только с адресным consent. Неоднозначное
  выражение про передачу RED «владельцу» привело к уточнению канона: ремонт остаётся у
  текущего исполнителя, owner нужен только для реальной authority/product decision.
  Это интерпретационный smoke, **не исполнение живого плана и не перехват native final**.
- Runtime этого smoke сообщил input_tokens=32423, cached_input_tokens=24576,
  output_tokens=713, reasoning_output_tokens=304. Это один образец, не расход всей задачи;
  сопоставимого замера «до/после» и доказанного процента экономии нет.

### Что остаётся при поставке

Локальная правка завершена; повторный аудит не является следующим шагом. Installed plugins
в Agelto и других проектах, релиз, commit/push не выполнялись. При поставке обновить consumer
штатным owning tool и на его следующем обычном пункте наблюдать число validation/audit/handoff.
Не запускать ради этого отдельный полный цикл аудитов. Поведение Claude и полного native
Codex plan-run на живом consumer ещё не проверено; provider parity подтверждена генерацией
и тестами контрактов, а не двумя полевыми запусками. При новом воспроизводимом сбое исправлять
конкретную ветку, без автоматического расширения процесса.

## Delivery 2026-09-11

Поставлено без запуска consumer-планов и без production deploy:

- Релиз: Task **0.13.4**, публикационные units **core 0.13.2** и **general 0.13.2**;
  umbrella **v0.15.2** — commit `b9045b66`, merge commit `2f13589b`, PR
  [#150](https://github.com/academici/swissknifeman/pull/150), annotated tag и
  [GitHub Release v0.15.2](https://github.com/academici/swissknifeman/releases/tag/v0.15.2).
- Release checks: `bash packages/task/scripts/validate.sh` — 1046 tests OK (1 skipped),
  `bash packages/skiller/scripts/validate.sh` — 654 tests OK; provider renderer and registry
  `--check` — OK. Existing docs build evidence from this task was reused.
- PR CI не является зелёным по независимой baseline-причине: тот же `origin/main` не проходит
  `docs/status.md` status-check (две неизвестные capability labels), Ruff находит старые unused
  imports в `core`/`harness`, а harness fixture ожидает Claude CLI в runner. Эти пути не входят
  в релизный diff; Task CI не стартовал, поскольку validate останавливается на harness. Причина
  и граница зафиксированы в [PR #150](https://github.com/academici/swissknifeman/pull/150).

`packages/skiller/bin/skiller update --all` выполнил сохранённые connect/vendor/sync каналы и
локальные provider selections. Для physical vendor-копий проверен SHA-256 `plan-protocol`:
`388429ed1bf6c47ddde7ced751ba5609eb4acd42eb7b8938cf8756a14264caec`; для существующих Codex
bundles проверены manifest versions Task 0.13.4/Core 0.13.2. Connect-проекты, где bundle не
создаётся, указывают на опубликованный worktree `.../swissknifeman` и включают `task`.

| Статус | Проекты |
|:--|:--|
| Обновлён и подтверждён | Brain, Agelto, Axioma Studio, Diabox, Dterema, Edufy, FlexCRM, Memster, Azguard, Chatom, CoreX, erp-sdk, Loqum, perplexity-web-mcp, swissknifeman, Vaulter, vintera/cms, sibintek-insiders, Sova |
| Уже актуален | Нет: все доступные записи были штатно переприменены и проверены на текущий source/version. |
| Заблокирован без перезаписи | dterema/app, botkit, vintera/vintera, agentools — `SPUB_OWNERSHIP_CONFLICT`: Codex marketplace bundle содержит неуправляемые либо изменённые файлы. До явной reconciliation/repair эти четыре сохраняют Task 0.13.3/Core 0.13.1 (для dterema/app, botkit и vintera/vintera подтверждено manifest); agentools также оставлен нетронутым из-за modified managed artifacts. |

Существующие пользовательские правки `docs/reference.md` и `roadmap/README.md` в umbrella
worktree не включались ни в релизный commit, ни в эту поставку.

## Подтверждённые причины до исправления

Разделы ниже сохраняют исходную диагностику и спецификацию как историю и критерии регрессии,
а не очередь на повторную реализацию. Описания прежнего поведения относятся к проверенной базе.

### F1 — высокий приоритет: direct-close реализован как исключение

В [plan_assurance.py](../../packages/task/lib/task/plan_assurance.py), `evaluate()`:

- `required`, обычный `auto` с integration и несколько `legacy-light` items приводят к audit;
- отсутствующий/невалидный assurance также превращается в audit;
- отсутствие candidate превращается в `gather-evidence`, но `_decision()` рендерит его как
  `audit-phase` с командой `task:plan-audit`;
- `parse()` разрешает `direct-close-eligible` только для isolated, без seams и live effects.

В [plan_gates.py](../../packages/task/lib/task/plan_gates.py), `phase_close_gate()`, это
материализуется в `PHASE_AUDIT_MISSING`, запрещающий закрытие. `phase_audit_policy()` не строит
candidate при вызове без `candidate_snapshot`. Это воспроизводит форму исходного инцидента.

### F2 — высокий приоритет: правила глубины проверки противоречат друг другу

[plan_lifecycle.select()](../../packages/task/lib/task/plan_lifecycle.py) для обычного изменения
выбирает `focused`, `review=none`, `continue-root`, один commit. Но
[plan-protocol §5](../../packages/skiller/skills/general/plan-protocol/SKILL.md) говорит
`default/doubt Review is full`, а §4 требует audit для integration/legacy-сценариев.
[task-development-philosophy](../../packages/skiller/skills/repository-bootstrap/task-development-philosophy/SKILL.md)
всё ещё рекомендует первый full audit для material phase baseline.

Это подтверждённый конфликт инструкций. Его вклад в конкретные часы работы пока не измерен.
Ещё одна общая инструкция «экономить токены» не исправит конфликт источников.

### F3 — высокий приоритет: delivery проверяет handoff, но не выбирает весь Next за агента

В [plan_delivery.py](../../packages/task/lib/task/plan_delivery.py), `_handoff()`, Next читается
из уже написанного `handoff.md`. Есть запрет повторного `plan-run/plan-exec` закрытого item,
но в этой проверке отсутствует `plan-close` того же item. Нет вызова phase assurance в этом
пути; один только renderer не доказывает готовность фазового successor.

`build_terminal_receipt()` уже запрещает final для незакрытого item. Поэтому утверждение
исходной записи «нет предфинального guard» слишком широкое: guard есть, но его необходимо
связать с правильным продолжением работы и воспроизвести поведение на уровне invocation.

### F4 — высокий приоритет: автоматическое завершение нельзя доказать тестом selector

[plan_lifecycle.py](../../packages/task/lib/task/plan_lifecycle.py) прямо является advisory
selector, а не execution engine. Возврат `continue-root` не выполняет journal/close/views.
[terminal_admission.evaluate()](../../packages/task/lib/task/terminal_admission.py) уже проверяет
terminal receipt и continuity, но без применимого lease возвращает `NOT_APPLICABLE`.

Нельзя добавить ещё один `completion_readiness` рядом и назвать это end-to-end исправлением.
Нужно исправить существующий путь команды и проверить transcript/adapter. Нельзя заявлять
перехват всех нативных final-ответов там, где provider transport его не обеспечивает.

### F5 — средний приоритет: «все Validation» не определяет повторное использование результатов

[plan-exec.md](../../packages/task/commands/plan-exec.md) требует `Run every declared Validation
carrier`. [terminal_policy.py](../../packages/task/lib/task/terminal_policy.py) хранит
`spec_sha256` и строки `carrier/status/evidence_ids`; сами эти строки не являются полным
cache key из product inputs, test/tool/config и environment.

Нельзя ни требовать повторного запуска зелёной команды на каждом lifecycle-переходе, ни объявлять
любой старый `evidence_id` достаточным доказательством. Требуется короткое правило: проверить
один раз на релевантных входах, повторять только после их изменения или при live boundary.
Наличие универсального исполняющего validation cache этим аудитом не установлено; не создавать
такой сервис без необходимости для конкретной регрессии.

### F6 — средний приоритет: новые предложения сами рискуют увеличить стоимость

Новый guard, отдельный recommendation outcome, новая система telemetry и дополнительная consent
схема сразу во всех consumers могут повторить исходную проблему. В
[task_contract.py](../../packages/task/lib/task/task_contract.py) уже есть owner-message/grant
проверки; в `plan_continuity`, `terminal_admission`, `review_policy` — continuity и retry policy.
Сначала расширять владельца существующей ответственности. Не создавать обязательные записи
риска/согласия для обычного direct-close и не добавлять ежедневный полный preflight.

## Воспроизведённая база и границы доказательств

Диагностический вызов существующих fixtures из `test_plan_assurance` дал:

| Candidate | Action | Next | Phase close |
|:--|:--|:--|:--|
| Один GREEN, internal-integration, `required` | audit-required | audit-phase | PHASE_AUDIT_MISSING |
| Один GREEN, internal-integration, `auto` | audit-required | audit-phase | PHASE_AUDIT_MISSING |
| Два GREEN, internal-integration, `light` | audit-required | audit-phase | PHASE_AUDIT_MISSING |
| GREEN isolated, direct-close-eligible | direct-close | close | allow |
| Вызов facade без snapshot | gather-evidence | audit-phase | candidate unresolved |

Проверка неизменённого runtime:

```bash
PYTHONPATH=packages/task/lib:packages/task/tests python3 -m unittest \
  test_plan_assurance test_plan_lifecycle test_plan_delivery \
  test_terminal_admission test_plan_continuity
```

Результат: **58 tests, OK, 0.247 s**. Это baseline, не приёмка новой политики: часть тестов
явно ожидает навязанный audit. Число часов и токенов внешних Agelto runs заново не измерялось;
их transcript не проверялся. Сведения о них — свидетельства владельца в архивных записях.

Минимальное воспроизведение F1 из корня репозитория (временная fixture удаляется автоматически):

```bash
PYTHONPATH=packages/task/lib:packages/task/tests python3 - <<'PY'
from test_plan_assurance import PhaseAssuranceTests, candidate
from task import plan_assurance, plan_gates
fixture = PhaseAssuranceTests()
try:
    plan = fixture.plan(impact="internal-integration", seams="migration", intent="required")
    snapshot = candidate()
    print(plan_assurance.evaluate(plan, "P1", candidate=snapshot))
    print(plan_gates.phase_close_gate(
        plan, "P1", candidate_snapshot=snapshot,
        candidate_fingerprint=plan_gates._candidate_snapshot_fingerprint(snapshot)))
finally:
    fixture.doCleanups()
PY
```

## Исходные шаги реализации (выполнены в локальном scope)

### 1. Убрать автоматический phase audit, сохранить честное acceptance

Владельцы: `plan_assurance.py`, `plan_gates.py`; синхронно §4 plan-protocol и команды
`plan-audit.md`, `plan-close.md`, `plan-exec.md`.

1. Direct-close — default для фазы с достаточным GREEN item evidence. `required/auto/light`,
   количество items и сама integration-граница не являются audit admission.
2. Legacy intent читать совместимо, сообщать advisory migration hint. Не переписывать старые
   journal events. Отсутствие старого assurance не заменять запросом audit.
3. Отделить ошибки evidence/неготовый item от выбора audit: missing candidate → собрать
   candidate существующим `phase_candidate_fingerprint`; RED/missing acceptance → owning repair.
   `audit_required=false` сам по себе **не** означает `close_allowed=true`.
4. Для запрошенного phase audit проверять конкретные target, вопрос, evidence gap и адресное
   owner consent, связанное с material candidate и текущим audit run. Опираясь на existing
   decisions/journal, выбрать минимальное расширение. Пример `audit-admission/v2` в архиве
   недостаточен: в нём ещё нет полноценной привязки к diff/run и одноразового потребления.
5. Не считать текст, написанный агентом «owner granted», самостоятельным доказательством
   согласия. Переиспользовать существующую проверку происхождения owner message/decision.
6. Истёкшее/чужое/уже использованное согласие не создаёт audit Next. Повторный audit требует
   нового согласия. Локальное исправление найденного дефекта не требует этого согласия.
7. Непокрытый обязательный safety/acceptance gate остаётся обязательным даже без audit consent;
   advisory recommendation не превращать в скрытый gate.

### 2. Довести closure в текущем invocation и вычислить действительный Next

Владельцы: `commands/plan-run.md`, `commands/plan-exec.md`, `plan_delivery.py`, существующие
`plan_continuity.py`/`terminal_admission.py`; `command_render.py` только для provider syntax.

1. GREEN объявленных gates → evidence/journal → изменённые views → item close в текущей сессии.
   Если это последний item и допустим direct-close, закрыть и фазу перед Next.
2. Не выводить пользовательский launch для `plan-close` текущего результата или повторного
   `plan-run` текущего item. Standalone явно запрошенный `plan-close` остаётся поддержанным.
3. Рассчитывать/валидировать Next из состояния после closure, dependencies и результата
   assurance. Один reducer должен владеть решением; renderer только переводит его в синтаксис.
4. Phase closure carrier сохранить: он нужен downstream. Убрать его зависимость от лишнего
   audit, а не сам файл. Для legacy GREEN-фазы штатный direct-close должен создавать `Pn.closed`
   и разрешать сборку следующего bundle без изменения исторической product evidence.
5. Использовать имеющиеся terminal guard и continuity; новое persisted состояние добавлять
   только если без него невозможно выразить воспроизведённую ветку. `closure-pending` может
   быть локальным описанием оставшейся работы.
6. Явный stop владельца, недостающая authority и доказанная невозможность продолжения дают
   честный checkpoint. Нехватка контекста сохраняет продолжение, но не выдаётся за completion.

### 3. Снизить повторную работу внутри item

Владельцы: §4–5 plan-protocol, `task-development-philosophy`, `commands/plan-exec.md`,
`commands/plan-run.md`, `plan_lifecycle.py`; существующий `review_policy.py` при необходимости.

1. Убрать `default/doubt Review is full`. Обычный низкий риск → self-check и affected tests;
   bounded integration → необходимая package/integration проверка; независимый review — по
   конкретному item risk или прямому требованию владельца. Не заменять full скрытым full review.
2. Сохранить явно заданные acceptance/security/release gates. Избыточный старый carrier
   корректировать прозрачно по существующим правилам изменения контракта, не молча пропускать.
3. Declared Validation означает наличие актуального доказательства, не повтор команды при
   каждом `review → close → delivery`. Уже выполненные проверки использовать при неизменных
   релевантных product/test/tool/config inputs и условиях окружения; иначе один affected rerun.
4. Closure/bookkeeping-only diff → одна регенерация и структурная проверка; он не инвалидирует
   независимое product evidence. Live check повторяется на своей live boundary.
5. После успешной приёмки не запускать ещё один review «для уверенности». Найденный дефект
   исправлять в его owning scope, затем проверять изменённый участок. Повтор того же сбоя
   меняет диагностическую тактику по существующей retry policy, а не создаёт новый full audit.
6. Для контрольного запуска записать в существующий отчёт время implementation/checks/closure,
   количество полных повторов и owner handoff; токены — только если runtime их отдаёт.
   Новая telemetry-служба и обязательная схема отчёта не нужны.

### 4. Квалифицировать один раз и доставить согласованные источники

Обновить существующие unit/integration fixtures, затем добавить одну связанную regression trace:

| Сценарий | Обязательный результат |
|:--|:--|
| GREEN legacy required → phase close → next bundle | Нет audit Next, есть `Pn.closed`, нет ложного `unresolvable_entry` |
| Много GREEN integration items без отдельного evidence gap | Тот же direct-close |
| Риск без согласия, acceptance GREEN | Только ограниченная recommendation, без audit launch |
| RED/missing acceptance без согласия | Owning repair, никакого фиктивного GREEN close |
| Адресное согласие на конкретный material candidate | Один bounded audit; чужое/устаревшее/повторное согласие не допускается |
| Один plan-run, review GREEN | Closure в текущем invocation, Next не повторяет current item/close |
| Неизменный product при bookkeeping change | Product checks не повторяются; изменённый test/config/product требует affected rerun |
| Нет provider interception/lease | Честное ограничение, без заявления о гарантированном перехвате final |

Проверять поведение и число запусков в trace, не только строки `select()` и наличие слов в
Markdown. Unit fixtures не доказывают поведение модели: отдельно выполнить один ограниченный
ручной provider transcript для исходного симптома; зафиксировать, какой provider реально проверен.
Не объявлять обе платформы проверенными по одному Codex run.

После правок канона регенерировать owning tools:

```bash
python3 packages/task/scripts/render-provider-commands.py --write --repair-owned --root .
bash packages/skiller/bin/skiller registry
python3 packages/task/scripts/render-provider-commands.py --check --root .
bash packages/skiller/bin/skiller registry --check
bash packages/task/scripts/validate.sh
bash packages/skiller/scripts/validate.sh
```

Внутри реализации запускать affected tests, перечисленные выше, плюс затронутые tests
review/routing/journal/projection. Полную qualification выполнять после последнего содержательного
изменения; не повторять все suites после одной правки отчёта. Fleet/архивные планы не проверять
в этой задаче; реальные изменяемые consumer plans проверяются через `--plan PATH`.

Обновить root `CHANGELOG.md` `[Unreleased]`, существующую документацию Task и этот статус
реализации. Сгенерированные файлы вручную не править. Установка в Agelto и закрытие его live
плана — отдельная поставка: исправление этого репозитория само по себе не меняет installed plugin.

## Когда остановить проверки

Готово, когда перечисленные регрессии и affected qualification зелёные, доказано сохранение
обязательного acceptance, provider outputs согласованы, а ограниченный transcript показывает
один item invocation с closure и без лишнего audit. Дальше передать результат. Второй аудит
этой реализации не является автоматическим условием завершения.

Доказательство экономии сначала поведенческое: **0** повторов неизменной product validation
только из-за lifecycle-перехода, **0** owner handoff на closure текущего item, **0** автоматически
назначенных phase audits на обычном GREEN пути. Универсальный лимит минут или обещание процента
ускорения без замера не устанавливать. Долгая необходимая проверка сама по себе не равна циклу.

## Внешняя проверка подхода

Perplexity был доступен и вызван обычным `search`, но не вернул результат до прекращения
ожидания. Его синтез здесь не используется. Прямым web search/open 2026-09-11 проверены:

- [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents):
  простые композиции, явный компромисс стоимости/задержки, условия остановки; evaluator-optimizer
  оправдан при измеримой пользе. Статья 2024 года отмечает изменение tooling; здесь используется
  принцип проектирования, не описание текущего API.
- [Google SRE — Reliable Product Launches at Scale](https://sre.google/sre-book/reliable-product-launches/):
  упрощённый путь для типичных запусков и соразмерный процесс.

Вывод для Task — наш инженерный выбор: нативный агент владеет локальным циклом
implement/test/fix; Task добавляет durable scope, handoff и конкретные межшаговые ограничения.
Эти источники не доказывают, что модель безошибочна, и не предписывают нашу consent schema.

## Архивная целостность

SHA-256 исходных файлов до перемещения:

```text
53cbe62607ac739946d59681e3e9b27f19017f06e0e786935894464a609daa42  2026.09.10-№1-audit-escalation-regression.md
d19eed7515306667ca637bf7149633d8ab1c37939c9adaa2860086e7c1826e8e  2026.09.11-plan-run-completion-first-regression.md
41b062e7ab58a51f0f31c879ed139e73fba5d0b9bdfdb796c6e4835811d26e2f  2026.09.11-owner-consented-risk-based-audit-policy.md
```
