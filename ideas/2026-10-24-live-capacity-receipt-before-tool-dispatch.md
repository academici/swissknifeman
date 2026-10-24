# Live capacity gate: данные после завершения ответа не подходят для допуска tools

Статус: подтверждены ошибки task-local helper, его тестов и координации;
в проверенном установленном тракте не найден доказанный live input receipt.
Owning provider/transport component ещё нужно установить. Кодовый дефект SKM
или Grok этим расследованием не доказан. Реализация по этой записи не выполнялась.

Запись подготовлена в ветке `review/machine-workspace-hooks-20261024` по прямому
поручению владельца. Это постановка на отдельную доработку, не разрешение
перезапустить остановленный consumer run или признать review пройденным.

## Проблема и её практическое последствие

В Agelto при исполнении PROCESS-CORE обязательное независимое review P1.5
остановилось на предпусковой проверке запаса контекста. Политика consumer-плана
требует доказать capacity **до зависимого чтения исходников**, а helper искал
текущий API input usage в executor stream. На момент первого tool call нужной
записи в этом stream ещё не было. Она появилась позже, в завершённом stream.

Получилась причинная зависимость, которую нельзя исправить обычным retry:

1. Перед чтением кода требуется current-request input receipt.
2. Helper читает carrier, ещё не содержащий эту запись.
3. Gate правильно возвращает unknown и не допускает чтение.
4. После завершения ответа carrier уже содержит usage.
5. Проверка helper на завершённом carrier проходит, но не доказывает его работу
   в точке допуска следующего живого запроса.

Оператор несколько раз подготовил продолжение, не проверив весь этот порядок
событий. Два последних продолжения не продвинули coverage. Их остановка была
вызвана недоступностью доказательства, а не установленным исчерпанием физического
окна модели. Новые запуски затем были прекращены до устранения причины.

Результат для пользователя: P1 не закрыта, следующие пункты не исполняются,
несмотря на готовые продуктовые изменения и зелёные проверки предыдущих пунктов.
Техническое восстановление потребовало ручной работы и объяснений владельцу.

## Контекст и сохранённые границы

- Consumer: Agelto, native Planner PLAN1, PROCESS-CORE, фаза P1.
- Owning independent reviewer: `grok/grok-4.7/high`, `model_class=frontier`.
  Route не заменяли моделью оператора; nested review/advisor/fallback не включали.
- Review run: `cnd-20261024T173235Z-88f430`.
- P1.1/P1.2 были завершены ранее; в этой работе P1.3/P1.4 завершены коммитами
  `31cdf6621ef00abad21a99164ce60a5cd1bcd7d4` и
  `66e8f023c136edc48fccedba0fc2ff8fd0299a00`.
- Продуктовый candidate при остановке: `66e8f023c136edc48fccedba0fc2ff8fd0299a00`.
  Локальный main безопасно fast-forward до него; исходные 22 unrelated удаления
  `research/` сохранены. Push/publish не выполнялись.
- После P1.4 реально прошли `make core-test-up`, `make core-test-env`,
  `make core-test-install`, `make core-test-unit`, `make core-quality`,
  `make core-test-regression`. Это evidence реализации, не замена review P1.5.
- P1.5 остаётся blocked; canonical review/manual V1 pass/finish не записаны.
  P1.6 и P2 не запускались. Активных/orphaned runs при финальной сверке нет.
- Исправлять SKM/installed bundles и менять машину в consumer-сессии не разрешалось.
  Менялись только разрешённые invocation/helpers/постановка и evidence consumer-плана.

## Отдельный предшествующий сбой: неполное review

Первый reviewer вернул body с verdict pass и запросил coordinator registration.
Проверка V1 установила, что он прочитал name-status/stat и часть enum/codec,
но не полный actual diff и не значительную часть fixture/server/HTTP/proxy/
fake-LLM/egress implementation и assertions P1.3. Сам body также раскрывал
неполное покрытие. Поэтому его не материализовали как canonical pass.

В D29 разрешили единственный оставшийся targeted closure, semantic round 2 of 2:
дочитать недостающий range и полные изменённые symbols/dependencies/assertions,
сохранив исходный отчёт. Полный raw diff имеет 1 251 431 bytes / 28 194 строки,
подготовлен в 236 bounded chunks; дополнительно полные тела изменённых файлов —
486 610 bytes / 63 chunks. Эти размеры описывают workload, не token window.

Подтверждённый checkpoint closure содержит чтение и assessment `patch-001/002`;
следующий chunk — `patch-003`. Остальной coverage не следует считать выполненным.
Частичные выводы первоначального review и новый checkpoint нужно сохранять,
не регенерируя код и не выдавая partial review за complete.

## Хронология отказов

Все времена ниже — UTC 2026-10-24. Technical continuations относятся к тому же
item/run и сохранённому targeted round 2; новый независимый review round и
обнуление бюджетов не объявлялись.

| Время | Наблюдение | Действие и предел доказательства |
| --- | --- | --- |
| 17:37:47 | Initial review остановлен `MANUAL_REGISTRATION_PENDING` | Coordinator нашёл coverage gap; V1 не пройден |
| 17:52:50 | Targeted closure продолжил собственную Grok session | Новая actual capacity проверялась отдельно |
| 17:56:15 | `CAPACITY_RESERVE`: slack 7807 недостаточен для следующего chunk и post-chunk gate | Сохранены `patch-001/002`, чтение `patch-003` не начато |
| 18:00:25 | Native `SESSION_FRESH / idle_expired` | Поддержанное fresh continuation, без reset candidate/coverage/budgets |
| 18:02:11 | Helper заблокировал работу: live `signals.json` отсутствует, compactionCount неизвестен | Зависимые coverage reads не начаты |
| 18:12:40 | После изменения helper возобновлена собственная session | Предыдущие тесты всё ещё не проверяли first-tool usage availability |
| 18:13:50 | `ENVIRONMENT_BLOCKED`: в newest executor stream нет assistant usage | Current I неизвестен, зависимые reads не начаты |
| 18:22:10 | Bounded end-to-end diagnosis завершён | Подтверждённого live I carrier не найдено, readiness прежних retry отозвана |

Первая проблема helper: он требовал post-turn `signals.json` во время живого tool.
В наблюдаемой fresh session файл появился/обновился в 18:02:07.433 сразу после
native `turn_ended` 18:02:07. Helper обращался к нему раньше, в 18:00:47.
Отсутствие файла в этот момент не доказывало ни нулевую compaction, ни отказ доступа.

Следующая правка разрешала отсутствие signals только при положительном receipt
доставки/истории/trim, оставляя compactionCount null. Однако другая зависимость
helper всё ещё требовала assistant usage из текущего executor stream. Именно она
оказалась недоступной в точке первого tool следующего продолжения.

## Точное причинное доказательство последнего отказа

Полная корреляция сохранена в `asof-correlation.json`: own session, promptId,
API stream start, toolCallId, native timestamps и наблюдение самого helper.
Здесь важен порядок публикации, а не факт существования файлов после завершения.

| Событие | Время / значение |
| --- | --- |
| Current native turn started | 18:12:42.454 |
| Native first tool started | 18:12:57.572 |
| Helper observation | 18:12:57.887387: current assistant usage отсутствует |
| Completed first request usage | `input_tokens=83086`, disjoint cache read `107648`, cache creation `0` |
| Retrospective inclusive I | `83086 + 107648 = 190734` |
| Live typed ToolCall metadata | `totalTokens=191146`, `requestTrimmedTokens=0` |
| Earlier correlated thought metadata | `totalTokens=199786` |

Последнее завершённое usage позволяет разобрать тот запрос задним числом.
Оно не было доступно helper в 18:12:57.887 и не доказывает first-tool admission.
Также оно не является measurement следующего API request.

Live `totalTokens` нельзя принять за I или его строгую верхнюю границу только
по имени поля и близости чисел. Первичная гарантия его семантики не установлена.
Корреляцию с **API request**, а не только session/user turn, также должен явно
обеспечивать адаптер. Поля session/prompt/stream/tool полезны для этого, но их
область уникальности нельзя угадывать.

В own signals обнаруживалось `contextWindowTokens=500000`. Происхождение и
семантика значения как actual runtime window не установлены, поэтому W оставлен
unknown. Это значение, каталог моделей, bytes входа, старое окно другой сессии
и self-report модели не принимались как capacity proof.

Проверенные доступные пути: persisted session/turn `usage`, own session history,
typed updates и локальный `trace --local`. Подходящего input/cache receipt,
положительно доступного перед первым dependent tool, они не дали. Trace не
загружался удалённо; другие сессии при финальном bounded диагнозе не исследовались.
Вывод ограничен проверенным установленным трактом, не всеми версиями Grok
или всеми возможными provider APIs.

## Почему тесты ошибочно разрешили continuation

Десять no-model checks проверили отдельные полезные условия: отсутствие signals
не становится count 0; отсутствующий contract/trim receipt, trimming, compaction
marker, foreign turn, loop gap и reserve boundary должны блокировать работу.
Но fixture подставляла **completed assistant usage** в синтетический live prefix.

Получилось ложноположительное доказательство readiness: компонент проверки
delivery был протестирован, а end-to-end admission всё ещё зависел от данных,
публикуемых позже. Повтор проверки уже завершённой own session тоже не проверял
доступность measurement на новом first tool. Это наши ошибки helper/test design
и координации, которые нельзя перекладывать на SKM или provider.

Исправление должно сначала воспроизвести исходный отказ на точной временной
границе. Тест, который пишет usage до tool dispatch, хотя реальный путь пишет
его после turn end, проверяет выдуманный порядок и непригоден для приёмки.

## Capacity policy и границы обобщения

Требование consumer-плана: при actual окне W нужен запас
`I + 4096 + max(120000, ceil(W / 4)) <= W`.
Это принятая политика конкретного исполнения; SKM не должен навязывать её числа
всем проектам или providers.

При неизвестном W D26 допускает строго проверяемый equivalent carrier:
успешно admitted request B даёт нижнюю границу W при доказанной применимости
к текущему runtime. Проверка `I + 4096 + R(B) <= B`, где
`R(x)=max(120000, ceil(x/4))`, достаточна благодаря монотонности `x-R(x)`.
В сохранённой калибровке B=428682. Применимость требует actual текущих
identity/build/fingerprint/config/delivery и верной input/cache семантики.
Старый PASS или B из другой сессии сами по себе этой применимости не доказывают.

Этот механизм не устраняет необходимость получить **current I**, либо доказанную
консервативную верхнюю границу current I. Когда такого live receipt нет, менять
арифметику, брать aggregate usage или считать unknown равным нулю нельзя.
Безопасная остановка правильна; ложный preflight pass и повтор без устранения
источника unknown — нет.

## Классификация и предполагаемые владельцы

| Область | Что установлено | Куда направить работу |
| --- | --- | --- |
| Consumer helper | Требование post-turn файла во время live tool; позднее — требование ещё не опубликованного assistant usage | Исправлять контракт producer/consumer и lifecycle tests, не очередной путь к файлу |
| Координация | Component tests и replay завершённого stream выданы за live readiness; последовали бесполезные continuations | Causal admission evidence и progress fingerprint перед retry |
| Исполнитель review | Неполный diff/scope при verdict pass; первоначальный broad metadata search | Проверяемый coverage contract и bounded own-session locator |
| План/интеграция | Strong live gate принят без доказанной возможности provider transport поставить нужные данные вовремя | Проверять совместимость policy и фактических capabilities до admission |
| SKM runtime | Есть normalised completed usage и session controls; они не доказывают live pre-tool capability | Проверить adapter boundary/публикацию/причину отказа; кодовый дефект пока не установлен |
| Provider transport | Live metadata есть, но строгая input/cache семантика и своевременный receipt не найдены | Установить owning producer; не утверждать provider bug без воспроизведения |

Generic `ENVIRONMENT_BLOCKED` дописывал совет проверить sandbox/дать `--allow-path`.
Здесь отсутствие usage не было доказанным permission failure. Этот hint не должен
превращаться в запрос расширения полномочий или действий владельца без причины.

## Минимальная постановка на доработку

Сначала выбрать owning boundary по фактической публикации: provider не отдаёт
usage вовремя, transport не передаёт уже доступный receipt или consumer читает
неподходящий carrier. Крайний итог может быть честным `unsupported` для данного
режима. Нельзя обещать, что одна правка generic stream parser создаст отсутствующие
provider данные.

Расширять существующие provider capability/evidence contracts, не строить новый
telemetry framework, dashboard или набор ad-hoc sidecar formats ради этого случая.
Provider-specific acquisition остаётся в адаптере; lifecycle и выбранная policy —
в conductor. Новый межпроцессный контракт, если он действительно нужен, типизировать
и валидировать существующими schema-механизмами.

Нужная capability — неизменяемый receipt текущего API request, положительно
доступный **до первого dependent tool dispatch**. В нём должны быть доказаны:

- Область измерения и корреляция: request, session, turn, actual model/build,
  effort/config, tool dispatch и точные времена измерения/публикации.
- Current input и cache inclusivity/disjointness; либо документированная строгая
  верхняя граница current input. Terminal/cumulative/spend counters отличать явно.
- Actual W или пределы применимости принятого equivalent proof; catalog/default
  window, пользовательское ограничение истории и measured runtime не смешивать.
- Идентичность полного delivered mandatory contract; trimming/compaction,
  preserved coverage и provenance. Отсутствующий файл остаётся unknown, не 0.

Capability/preflight должен отдельно отвечать, есть ли такая возможность и
проверена ли конкретная текущая сессия. `available=true` для executable и matching
provider/model/effort/class не равны current capacity pass. Если обязательный live
gate не поддержан, нужен точный отказ с missing premise и supported resume path.
Нельзя советовать очередной retry, guessed upgrade или permission grant.

Для bounded recovery сохранять candidate, receipts, partial review и semantic
round budget. После actual exhaustion поддержанное fresh context продолжает только
оставшийся coverage с новым own receipt. Ни новый run ID, ни смена session не
обнуляют correction/review counters. При повторе того же failure и отсутствии
изменений candidate/coverage/диагностики запуск не оправдан.

## Конечная приёмка без оплачиваемых model probes

Тестировать causal ordering настоящим producer/transport fixture или fake provider
через реальную adapter boundary. Нужны controlled barriers, чтобы helper/tool
попытался прочитать receipt **до разрешения turn completion**. Не использовать
sleep-based race и не подмешивать completed artifacts в live фазу.

| Сценарий | Ожидаемый результат |
| --- | --- |
| Initial/fresh request, current usage отсутствует, terminal usage появится позже | До dispatch unknown/unsupported; поздние данные не делают прежний admission pass |
| Подтверждённый current receipt опубликован до dispatch | Gate читает именно этот immutable receipt и допускает работу только при reserve pass |
| Same-session resume, есть usage прежнего request | Старое measurement не принимается за current I |
| Несколько requests в одном turn / одинаковый session ID | Receipt привязан к правильному API request; turn/session aggregate не подставляется |
| Receipt другого request/session/model/config | Отказ с конкретным mismatch |
| Partial/truncated/replaced receipt | Нет pass; читатель не видит полуопубликованный документ |
| `signals.json` отсутствует до turn end | Compaction остаётся unknown, если другой положительный carrier не доказал нужное свойство |
| Live `totalTokens` без semantic guarantee | Не используется как input или его upper bound |
| Current input с inclusive cache / с disjoint cache | Cache считается один раз по declared semantics |
| Неверная build/config equivalence или неполная delivery | Equivalent proof отвергнут |
| Trimming/compaction и утраченный mandatory contract/coverage | Отказ, сохранённый checkpoint; никакого silent green |
| Reserve на границе и сразу за ней | Один и тот же строгий предикат до/после continuation |
| Missing usage при доступных source paths | Диагноз telemetry, не рекомендация расширить sandbox |
| Повторный live отказ без прогресса | Нет автоматического нового model run; budgets и evidence сохранены |
| Полный review coverage отсутствует при verdict pass | Manual V1 не закрывается; telemetry pass не заменяет content review |

Adoption criterion: causal тесты доказывают positive receipt до первого dependent
tool и все negative cases; точные capability limits отражены в preflight/status;
только после этого разрешено faithful continuation сохранённого consumer review.
Если provider не даёт нужного carrier, результат приёмки — корректный ранний
unsupported/refusal с причиной, а не фиктивный universal support.

## Исходники для проверки при реализации

На момент записи checkout SKM имеет HEAD
`979fcb3809f541588c848e9e7d456f4bdab7399c`. Это provenance чтения исходников,
не обещание одинакового состояния установленного consumer runtime.

- [conductor/process.py](../packages/orch/lib/orch/conductor/process.py):
  `_usage`, `parse_stream`, `RoleRun.usage_complete` нормализуют usage из captured
  stream. Здесь нельзя автоматически приписать данным pre-tool publication timing.
- [conductor/infrastructure/sessions.py](../packages/orch/lib/orch/conductor/infrastructure/sessions.py):
  session reuse и `max_idle_s` / `idle_expired`. Механизм fresh context работает,
  но не создаёт отсутствующий live receipt и не является capacity proof.
- [conductor/domain/report.py](../packages/orch/lib/orch/conductor/domain/report.py):
  `ENVIRONMENT_HINT`, `escalation_code`; отдельно проверить причинность подсказки.
- [Документация conductor](../packages/orch/docs/conductor.md): capability/route,
  session options, lifecycle и ручная регистрация evidence.

Эти места — точки проверки, не заранее назначенный root cause для code fix.

## Private evidence и точка продолжения

Raw traces, payloads и полные сессии в SKM ideas не копировать. Они могут содержать
consumer context. Consumer plan root разрешается штатным workspace project lookup:
проект `agelto`, план с названием `PROCESS-CORE` (native alias `PLAN1`
на момент инцидента).
Ниже пути относительно этого plan root, а не публичные переносимые ссылки.

- `artifacts/autopilot/p15-live-first-tool-diagnosis-20261024/report.txt`:
  финальный bounded диагноз; SHA256
  `0c3d9a385736f854a6525f55393f822ee65fd52a50f92de63d42cf62a64a8d3f`.
- В том же каталоге: `asof-correlation.json`, `updates-asof-first-tool.json`,
  `native-events-current-turn.json`, `current-process-memtrace.json`,
  `bounded-capability-check.json`, `trace-local-command-result.json`,
  `evidence-manifest.json`, `product-checkpoint-proof.json`, `DO-NOT-RETRY.txt`.
- `before/` там же: frozen stage-report, failed capacity receipt, helper versions,
  completed stream, initial review/targeted body и coverage-progress snapshots.
  Manifest позволяет проверить hashes; наличие completed stream не превращает его
  в as-of live measurement.
- `artifacts/autopilot/p15-targeted-closure-20261024/diagnosis.md`:
  доказательство первоначального V1 coverage gap и полная постановка closure.
- `artifacts/autopilot/p15-live-carrier-recovery-20261024/diagnosis.md`:
  первый helper fix и ограничения его десяти component checks.
- `autopilot-handoff.md`: native blocked state, binding, сохранённые бюджеты,
  checkpoint001/002 и запрет исполнения прежних resume-команд.

После исправления capability требуется actual текущий proof и продолжение
с `patch-003`, затем полное review coverage и coordinator V1 verification.
Настоящая готовность продукта, review completeness и capacity admission — разные
критерии; ни один из них не заменять другим.

Связанные идеи: [Grok session resume](2026-10-22-grok-session-resume-capability.md),
[автопилот и ограниченная стоимость](2026-10-22-autopilot-outcome-control-and-owner-stops.md),
[анализ обязан менять исполнение](2026-10-21-autopilot-analysis-must-change-execution.md).
