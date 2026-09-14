# Аудит скиллов, стартового контекста и доведения Task до результата

Дата: 2026-09-14. Исполнитель аудита: текущий root, GPT-6 Astra.
Статус: аудит завершён; реализация выполнена по последующему поручению владельца.
Текущий результат, проверки и оставшаяся полевая валидация: [implementation.md](implementation.md).
Ниже сохранены исходные выводы и рекомендации на момент baseline; они не описывают
нынешнее состояние уже исправленных файлов.
Область: весь canonical каталог Skiller, все 11 команд Task, настройки и локальные
скиллы Edufy/FlexCRM/CoreX, пять незавершённых roadmap-записей за сегодня.
AM из первоначальной формулировки не включён: уточнённый запрос перечисляет три проекта.

## Вердикт

Проблема подтверждается в двух независимых плоскостях:

1. Стартовый список перегружен глобальными plugin defaults, повторными поставками
   и дополнительным каталогом в AGENTS.md. Сокращение описаний ухудшает различимость
   триггеров, особенно когда ограничения стоят в конце длинного description.
2. В прочитанных правилах есть конкретные противоречия: повторное согласование уже
   разрешённой разработки, clean-tree как условие мелкой правки, жёсткие универсальные
   test/process defaults, неоднозначная граница между окончанием ответа и новой сессией.

Предупреждение не означает, что Codex прочитал тела всех скиллов или исчерпал весь контекст.
И причинность «именно сокращение описаний вызвало конкретную остановку» не доказана:
парные model replay и трассы выбора скиллов в инцидентных сессиях не выполнялись.
Удалять полезные domain/risk знания только потому, что модель сильнее, оснований нет.
Убирать повторение, лишние defaults и ложные gates — основания есть.

Исполнителем следующей реализации выбираю **Astra в текущем контексте**: основная сложность —
согласовать смысл нескольких противоречащих источников и проверить consumer delivery.
Уже собранный контекст делает смену исполнителя сейчас лишним расходом. Это решение
об организации работы, не утверждение о доказанном превосходстве Astra над Sol.
Sol подходит для последующих ограниченных механических изменений после фиксации контракта;
отдельного обязательного model handoff или параллельного workflow не требуется.

## Доказательства и пределы охвата

- [inventory.json](inventory.json): SHA-256, происхождение, описания, размеры и
  найденные нормативные формулировки для всех **232** canonical SKILL.md; локальные
  project/user/system и включённые Swissknifeman plugin candidates; хеши roadmap.
- [skills-matrix.md](skills-matrix.md): рекомендация для **каждого** из 232 скиллов.
- [collect.py](collect.py): воспроизводимый read-only сбор; пишет только эти два отчёта.
- [Сценарии отказа и приёмки](scenarios.md): конкретные последовательности и ожидаемый результат.

Все canonical тела прошли автоматический скрининг, все описания — каталогизацию.
Содержательное чтение сосредоточено на активных конфликтующих семействах и Task:
anti-drift, context-economy, plan-protocol, TDD/testing/review, PHP architecture/style,
package contribution, VueUse, local orchestrator, bootstrap/runbook и генераторы.
Это не заявление о ручном построчном ревью всех 163 тысяч слов корпуса, всех snippets,
scripts и API-примеров. Для неприоритетных специализированных скиллов результат —
«сохранить предметно», а не голословное «проверен и безопасен».

Проверены реальные cwd и dirty baseline до записей. Существовавшие изменения
CHANGELOG, Task parser/tests и roadmap принадлежат другой работе и не изменялись.
Статические сравнения с каноном показывают различие байтов, но не объявляют корректные
project-specific проекции устаревшими только по несовпадению хеша.

## Что означает предупреждение

Текущая [документация OpenAI](https://learn.chatgpt.com/docs/build-skills) описывает
metadata-first загрузку: сначала имя, описание и путь, тело — при выборе скилла.
У стартового списка отдельный бюджет: до 2% окна модели, с fallback 8 000 символов,
когда окно неизвестно. Сначала сокращаются описания; при ещё большем наборе возможны
пропуски. **Именно приведённое пользователем предупреждение говорит, что все скиллы
ещё видимы**, а не что часть уже исключена. Одноимённые скиллы не объединяются.

Опция `allow_implicit_invocation: false` управляет автоматическим выбором;
она не является доказательством удаления записи из resident listing. Для отключения
есть `skills.config.enabled=false` и plugin enablement; provider поведение проверяется
на реальной установке. Описания должны начинаться с отличительного trigger/границы.
Источник проверен 2026-09-14; установленный CLI: `codex-cli 0.154.0`.

[OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
отдельно предупреждает о чувствительности Astra к неясным и конфликтующим инструкциям.
Это поддерживает направление аудита, но не заменяет воспроизведение наших инцидентов.

## Стартовая поверхность трёх проектов

| Статический замер | Edufy | FlexCRM | CoreX |
|---|---:|---:|---:|
| Включённые Swissknifeman plugins после global + project config | 10 | 17 | 10 |
| Локальные `.agents/skills/*/SKILL.md` | 2 | 14 | 90 |
| Кандидаты discovery, включая найденные user/system | 103 | 137 | 191 |
| Группы одинаковых имён | 0 | 1 | 70 |
| Символов в исходных descriptions | 20 886 | 31 034 | 37 665 |
| Proxy списка с именами/описаниями/абсолютными путями, символов | 33 244 | 47 358 | 59 641 |
| Размер корневого AGENTS.md, байт | 20 419 | 24 220 | 3 787 |

**Это filesystem/config inventory, не полученный из провайдера effective skills/list.**
Учтены plugin manifests и наблюдаемые migrated-command skills. Исключён недискаверимый
`task/runtime/plan-protocol/SKILL.md`: простой рекурсивный подсчёт ошибочно считал его дублем.
User/system содержит восемь файлов, включая `review-agent`, видимость которого в данной
сессии не аттестована. Curated plugins, plugin trust, inherited launch overrides и активный
session snapshot полностью не реконструировались. Поэтому числа не называются точным
размером prompt или фактическим расходом токенов.

Proxy рассчитан с полными путями; CLI может применять aliases и иное оформление.
Его нельзя напрямую сравнивать с предполагаемым окном модели и объявлять точный процент
превышения. Для implementation acceptance нужен captured native prompt/listing того же route.

### F1 — Major: global plugins расширяют каждый проект

`~/.codex/config.toml` включает architect, devops, PHP, quality, system, Laravel auth/data/testing,
core и task. Локальная конфигурация FlexCRM добавляет frontend, но не отключает inherited
architect/system. В Edufy `.swissknife.json` говорит `codex.enabled=false`, однако глобальный
Codex runtime всё равно имеет включённые плагины. Это разные уровни конфигурации.

**Исправить:** сделать project selection явным для полного набора managed plugins,
включая `enabled=false` для inherited невыбранных. Глобально оставить действительно личный
минимум. Не переписывать глобальные defaults до сохранения нужного набора в каждом затронутом
проекте; не менять остальные проекты побочным эффектом аудита трёх roots.

### F2 — Major: CoreX получает два источника одной capability

70 имён одновременно найдены в local skill copies и plugin projection. Из 79 локальных
скиллов с однозначным соответствием канону 76 байт-в-байт совпадают; отличаются
ecosystem-mcp, ecosystem-setup и plan-protocol. У Task повторяются все 11 native adapters.
Это уже измеренное дублирование, а не предположение о «слишком умной модели».

**Исправить:** одна managed доставка одной identity в одном provider root. Сначала выбрать
существующий intended channel CoreX по ownership/lock; сохранить уникальные OSS/package
capabilities локального набора. Затем убрать только доказанные управляемые дубли штатным
publisher. Изменённый local skill требует сравнения смысла; удаление по имени запрещено.
Проверить также три `source-command-plan-*` auto-migration адаптера Task: они предлагают
те же audit/design/close операции вторым набором имён. Нужен один Codex command surface,
сохранив Claude команды и явные совместимые aliases вне лишнего resident discovery.

### F3 — Major: каталог повторяется в AGENTS.md

В Edufy корневой hub содержит 70 bullet descriptions. Владелец:
[`hub.py`](../../packages/skiller/lib/skiller/hub.py), `build_hub_markdown()` и
`target_form()` (строки 389 и 436): краткая форма по умолчанию выбирается для Claude,
а обычному AGENTS.md достаётся полная. Это не сокращается skills-list budget провайдера.

**Исправить:** краткий hub для Codex при подтверждённом native discovery; полный индекс
оставить on-demand документом. Если capability отсутствует в native listing, сохранить
короткий адресный указатель, а не копировать весь каталог. Использовать существующий
механизм `unconfirmed`, не создавать второй discovery control plane.

### F4 — Major: зелёный budget не измеряет всю проблему

`packages/skiller/bin/skiller budget --check-core` → **431 / 750, 9/9, OK**.
Это полезный CORE gate, но не native first-turn gate проекта. Дополнительно
[`budget.py`](../../packages/skiller/lib/skiller/budget.py), `_listing_entry_chars()`
(строка 430), считает name+description+when_to_use без file path; `measure_listing_budget()`
оперирует переданным набором, не всем реально унаследованным runtime.

**Исправить:** расширить существующий provider-aware отчёт effective inputs и происхождением,
разделять raw listing, реально rendered listing, AGENTS/hub, activated bodies и usage.
Не поднимать лимит CORE и не выдавать model-independent 8 000 за точный текущий лимит.
Порог rollout — минимум 25–30% запаса до **измеренного** listing cap на выбранных routes;
при неизвестном cap показывать unknown и fallback estimate, а не фиктивный GREEN.

### F5 — Major: явные повторные approval gates в скиллах

- [`tdd-discipline`](../../packages/skiller/skills/quality/tdd-discipline/SKILL.md), 61–69:
  до кода требует подтверждать интерфейс, набор тестов и одобрять план. Это конфликтует
  с уже разрешённой прямой разработкой. Оставить один вопрос только о реально недостающем
  продуктовом решении; test-first не должен принудительно включаться от слова integration.
- [`anti-drift`](../../packages/skiller/skills/general/anti-drift/SKILL.md), 29–32, 63–70:
  ambiguity → ASK, новый abstraction → ASK, «только названные файлы» и обязательный
  dependent-package gate чрезмерны для разрешённого исправления. В конце того же файла
  остались ссылки «exit session after hard threshold» и Plan→Clear→Execute, противоречащие
  исправленному continue-root в основной части. Исправить весь смысловой кластер, включая snippets.
- [`package-contribution-protocol`](../../packages/skiller/skills/architect/package-contribution-protocol/SKILL.md):
  смешивает bugfix и новое обобщение, 2+ потребителя и Rule of Three, запрет любого изменения
  Contracts без major и собственное разрешение совместимых minor API additions.
  Сохранить защиту несогласованного расширения чужого API; разрешённый package bugfix не
  требует автоматически proposal issue → ADR → повторного разрешения.
- [`task:fix`](../../packages/task/commands/fix.md), 20: «Дерево чистое» расходится с
  [`task:dev`](../../packages/task/commands/dev.md) и plan lifecycle. Заменить на baseline
  ownership/composition, сохраняя чужие изменения. Удалить недоказанный слоган «экономия 5–50×».

Это findings по текстам, не доказательство, что каждый из этих скиллов был активирован
в конкретной инцидентной сессии.

### F6 — Major: quality advice превращается в acceptance без решения проекта

[`test-strategy`](../../packages/skiller/skills/quality/test-strategy/SKILL.md) задаёт
70/20/10, coverage 90/80/60/40, запрещает E2E без unit coverage той же логики и mock stdlib.
[`code-review`](../../packages/skiller/skills/quality/code-review/SKILL.md) смешивает
проверку diff с процессом команды/SLA и требованием дробить PR по размеру.
[`artifact-review`](../../packages/skiller/skills/quality/artifact-review/SKILL.md) направляет
plan/spec в plan-audit и называет skill-conformance конституцией ревью.

**Исправить:** примеры стратегии отдельно от принятых repo требований. Конкретный finding
обосновывается поведением/риском/согласованным контрактом; непринятый вкусовой default скилла
не становится blocker. Независимое ревью сохраняется для реального public API/security/
concurrency риска. Внешний read-only обзор документа не должен незаметно включать phase audit.
[`diagnosing-bugs`](../../packages/skiller/skills/quality/diagnosing-bugs/SKILL.md) также
нуждается в допустимом пути для статически доказуемой ошибки, когда live repro недоступен.

### F7 — Major: локальные правила могут быть сильнее и старее канона

FlexCRM local `complex-task-orchestrator` требует декомпозиции по слоям; Task рекомендует
вертикальные результаты. Корневой AGENTS.md содержит старый headline «без Filament», но
composer.json включает `filament/filament` и `axioma-studio/azguard-filament`.
Nuxt отсутствует в корневом package.json, хотя включён frontend-nuxt: кандидат на отключение
после проверки вложенных app roots. **Filament отключать по старому headline нельзя.**
В FlexCRM также одновременно присутствуют local и plugin `laravel-best-practices`, тогда
как канон сам рекомендует в Boost-проекте использовать одну версионную поставку.

**Исправить:** сначала `.ai`/другие объявленные source carriers проекта, затем их генератор;
не редактировать AGENTS/projections вручную. Применять context-specific override локальных
инвариантов, но не считать любой local текст достоверным описанием текущего runtime.
`skills-ssot` необходимо согласовать с реальным multi-source ownership: он сейчас
универсально предписывает Boost регенерацию AGENTS, тогда как tooling runbook ограничивает
роль Boost в экосистеме. Не запускать `boost:update` как универсальное лечение.

### F8 — Major: Task имеет правильную философию, но неоднозначный последний шаг

`plan-run` и `plan-exec` уже требуют close + successor в том же root. Проблема не лечится
ещё одним длинным параграфом «будь автономен». Нужен один результат выбора следующего действия
на существующей границе continuity/delivery, которым пользуются adapters и final renderer.

**Правило:** достижение результата → необходимые проверки → inline close → проверить
готовность и разрешённость successor → продолжить либо назвать реальную границу и следующий
шаг. Next — навигация, не автоматическая новая authority. Окончание ответа, закрытие item,
закрытие фазы и создание новой сессии — четыре разных события.

Не добавлять новый mandatory receipt/schema на каждую фразу. Переиспользовать
`plan_continuity`, `plan_delivery`, `terminal_admission` и общий provider renderer.
Пока adapter не установлен/не применяется, инструкция не превращается в перехват финального
сообщения. `terminal_admission.evaluate()` возвращает `NOT_APPLICABLE` без lease, а при
не-terminal continuity проверяет continuation до сравнения terminal fragment; один только
вызов `required_final_message()` не доказывает end-to-end enforcement.

## F9 — Major: личный autonomy skill тоже может создавать процессный долг

Прочитан `~/.codex/skills/owner-autonomy/SKILL.md`. Его общая установка на продолжение полезна,
но пункт `Resolve without escalation`, 4 предлагает после запрета повторного открытия фазы
продолжать через successor/remediation phase или новый plan. Это расходится с текущей
Task philosophy: сначала repair owning seam в существующей authority, а не обход audit cap
новой формой плана. Рекомендация — заменить именно этот пункт; не удалять полезное
правило «продолжать уже разрешённую работу».

`~/.agents/skills/find-skills/SKILL.md` срабатывает даже на обычное «как сделать X» и
предлагает leaderboard/установку дополнительных скиллов. Для минимального default это
неподходящий trigger. Оставить явные запросы поиска/установки; installs/stars не считать
доказательством полезности или безопасности содержимого.

| Найденный user/system skill | Рекомендация |
|---|---|
| owner-autonomy | Сохранить; исправить remediation-plan shortcut и убрать дубли общих инструкций после проверки поведения. |
| find-skills | Только явный поиск/установка; не расширять набор в ответ на обычную разработку. |
| openai-docs | Сохранить для конкретных OpenAI/Codex вопросов; это не blanket startup read. Длинное описание учитывать в native budget. |
| imagegen | Предметная image capability; не менять в рамках PHP default чистки без наблюдаемого лишнего invocation. |
| plugin-creator | Явный plugin authoring; не development default. |
| skill-creator | Явный skill authoring; не вызывать автоматически из задачи оптимизации кода. |
| skill-installer | Явная установка; сохранить возможность, не включать как регулярный этап разработки. |
| review-agent | Файл найден, в объявленном каталоге текущего root не наблюдается; до native discovery не считать активной нагрузкой. |

Curated `deep-research`, `plugin-management`, `openai-docs`/system adapters не являются
Skiller corpus: оценены границы применения, не проводился полный аудит их scripts и
инструментов. Их подключение должно входить в native W1, а не выводиться из наличия cache.

## Судьба всех сегодняшних roadmap-записей

| Carrier | Что подтверждено сейчас | Рекомендация |
|---|---|---|
| [Exec alias](../../roadmap/archive/2026.09.14-task-plan-run-exec-alias-admission.md) | Два независимых enum по-прежнему исключают plan-run: `task_contract.py` (`_EXECUTABLE_ROUTING_EXEC_VALUES`), `plan_lint_checks/engine.py:12`. Текущий FlexCRM routing уже компилируется; исторический live отказ не повторился на его изменённом состоянии. | Один semantic resolver с сохранением исходного command/route evidence; synthetic plan-run fixture плюс lint/build/adapters. |
| [Owner continuity](../../roadmap/2026.09.14-owner-session-continuity-regression.md) | Канон уже запрещает обычный restart; incident показывает ошибочную интерпретацию stale handoff. | Свежий typed Next из post-close состояния, не чтение legacy handoff как authority; тот же общий delivery seam. |
| [Dirty worktree](../../roadmap/2026.09.14-task-owned-dirty-worktree-continuity.md) | Carrier прямо сообщает `visible-non-gating`; в command guidance есть противоположное «Дерево чистое». | Diff происхождение и semantic overlap, локальная композиция; owner boundary только при доказанном неразрешимом конфликте. |
| [Terminal emission](../../roadmap/2026.09.14-task-terminal-command-emission-regression.md) | Receipt builder и optional lease не обеспечивают универсальный final transport. Предложение «любой final с successor → launch» конфликтует с continuity carrier. | Объединить с owner continuity, различать паузу в чате и просьбу новой сессии; требовать launch лишь при реальной соответствующей границе. |
| [Unicode bundle](../../roadmap/2026.09.14-task-unicode-cross-plan-bundle-regression.md) | Два focused regression tests GREEN; source `plan_weight.py`/`plan_bundle.py` совпадают с текущим Task cache 0.16.2. | Не повторять реализацию. Проверить конкретный CoreX loaded runtime, regeneration bundle и независимый CONSUMER-DOMAIN gate; затем зафиксировать delivery и архивировать carrier. |

Roadmap source files не перемещались: это аудит рекомендаций, не присвоение/закрытие
реализации чужого задания. Их SHA сохранены. Архивный final-launch carrier от 13 сентября
объясняет прежнее намерение, но не считается доказательством исправления регрессии 14-го.

## Как проредить каталог

Полная построчная диспозиция — [232 строки матрицы](skills-matrix.md). Приоритеты:

1. **Убрать из default, сохранить возможность:** mcp-advisor, query-craft, gh-review,
   compact-responses; system bucket; обзорный engineering; процессы команды/OSS governance,
   интервью/проектирование; специализированные business/Blender/voice навыки. Это не
   утверждение, что все эти buckets сейчас включены в трёх проектах.
2. **Объединить resident entry:** named-arguments + naming в PHP style;
   DI/patterns в references Laravel architecture; шесть Docker subskills в references
   одного Docker entry; testing-safety-report в обычный completion report.
   Сохранить реальные проектные конвенции, а не заменить всё общим «пиши хороший код».
3. **Сократить activated body:** VueUse каталог (T1 estimate 10 838) → предметный index/reference;
   plan-protocol (9 136) → короткий role-specific executor entry и адресные layout/authoring
   references. Это экономия после активации, не снижение listing за счёт числа строк тела.
4. **Сохранить необычные failure знания:** isolation, outbox/idempotency, keyset pagination,
   namespace safety, production-readiness, framework-version gotchas. Удаление таких скиллов
   требует negative-control regressions, а не мнения «модель наверняка знает».

Кандидат CORE — четыре коротких identity: anti-drift (после переписывания), context-economy,
verify-claims, session-handoff. Plan protocol остаётся доступным через явный Task execution.
Это изменение default policy, а не немедленное удаление пяти файлов. Проверить requires,
core manifests, standalone vendor, connect, миграцию старых setups и provider parity.

Бакеты имеют смысл, если меняют подключаемый набор. Предлагаемый следующий разрез:
`php-style`, `laravel-architecture`, `laravel-runtime-safety`; `quality-testing`,
`quality-review`, `quality-process`; `architect-design`, `architect-agent`,
`architect-security`; `devops-runtime`, `devops-setup`. Это проектные предложения,
не команда создать все buckets сразу. Начать с quality/architect, где измерены лишние gates;
после pilot оставить только разделения, реально уменьшающие набор в трёх проектах.
Перенос больших тел в десятки новых discoverable skills при подключении их всех ухудшит listing.

Для первых 60–90 символов description поставить отличительный триггер/границу:
`Explicit TDD work: ...`, `Team review process setup: ...`, `Nuxt app configuration: ...`.
Это тестовая зона устойчивости при сокращении, не заявление о фиксированном лимите Codex.
Не оставлять `explicit only`, `only if enabled`, `not a phase audit` в отрезаемом хвосте.
Не менять faithful vendor copy без фиксации upstream provenance: wrapper/adapter либо
явно сопровождаемый fork с соответствующим upstream.json.

## Порядок реализации с конкретной приёмкой

Обычное ограниченное задание; master plan сейчас не нужен. Эти W обозначают порядок работы
аудита, не executable Pn.m и не дополнительную схему Task.

| Работа | Владелец исходников | Готовность |
|---|---|---|
| W1. Правдивый runtime baseline | Skiller existing budget/publication; project configs | Native inventory/startup capture на трёх cwd и используемых routes; hashes/versions, warning и body activations отдельно; без исправления чужого проекта. |
| W2. Устранить доставочные дубли и полный hub | Skiller `hub.py`, selection/publisher; `.ai` и provider config потребителей | CoreX без двойных managed identities, уникальные local skills сохранены; Edufy Codex hub краткий; выбранные plugins не дополняются невыбранными global silently. |
| W3. Исправить конфликтные правила | Canonical Skiller skills, Task `fix.md`, project sources | TDD не спрашивает повторное согласование; dirty baseline композиционен; severity не навязывает необоснованные gates; project instructions соответствуют стеку. |
| W4. Alias + единый Next/final contract | Task routing compiler/lint, continuity/delivery/render; plan-protocol | Alias fixture GREEN; все сценарии таблицы ниже проходят в Codex/Claude; нет replay закрытого item/отдельного close/самовольного расширения scope. |
| W5. Проверить уже существующий Unicode repair | Task release/runtime delivery и CoreX plan owner | Source/cache/consumer/session различены; два regression tests GREEN, bundle regenerated при разрешённых prerequisites; roadmap закрыт только по delivery evidence. |
| W6. Минимальные profiles и body diet | Skiller core-policy/buckets/registry и vendor provenance | На парных задачах warning исчезает с запасом; нужные skills выбираются; нет ухудшения acceptance, лишних approvals/restarts; уменьшение usage заявляется только при provider telemetry. |
| W7. Закрыть доставку | Каждый owning package и три consumer source roots | Affected package qualification, штатная regeneration + --check, provider parity, root CHANGELOG [Unreleased], docs и release-visible delivery evidence. |

W3 и alias-часть W4 можно выполнять до полной очистки поставки: это независимые доказанные
дефекты. Сначала исправить общий источник, затем обновлять consumer projections, чтобы новый
sync не вернул старые правила. Не выдавать текущие cache bytes за опубликованный tagged release.

**Pilot:** одинаковые исходные snapshots, задачи и routes до/после; обычный bugfix, PHP feature,
Vue feature, рискованный DB/queue кейс, два соседних plan items, запрошенная пауза/новая сессия.
Измерять success по acceptance, ошибочные вопросы владельцу, ненужные restarts, выбранные/прочитанные
skills, tool calls, wall time, input/output usage если доступно. Сначала один парный прогон
каждого сценария; спорное отличие перепроверить, не делать статистический вывод из одной пары.
Обязательные negative controls — isolation/auth/authority/foreign edit/неидемпотентный retry.
Не вводить вечный дорогостоящий audit после каждого item ради проверки этой оптимизации.

## Проверка этого аудита и следующий шаг

- `python3 tasks/2026.09.14-skills-and-task-audit/collect.py`: 232 записи, три проекта,
  происхождение и размеры собраны; tool output и inventory согласованы.
- `skiller budget --check-core`: GREEN 431/750; scope ограничен CORE.
- Два существующих Unicode regression tests: GREEN, 2 tests, 0.006 s.
- Текущий FlexCRM `compile_batch_routing`: PASS; исторический alias defect подтверждён
  исходными enum и synthetic routing row: `TaskContractBuildError: routing: Routing:
  line 1: invalid Exec 'plan-run'`, а не приписан неизменному live проекту.
- Package runtime/skills/configs не изменялись этим аудитом; полная package/fleet qualification
  не запускалась и не объявляется зелёной. Проверка Markdown links и diff записана в [verification.md](verification.md).

Документация продукта не требует обновления: поведение ещё не изменено. В `docs/reference.md`
добавлена только provenance запись использованных текущих первичных источников.

**Рекомендация следующего шага:** реализация Astra по этому заданию, начиная с W1/W2 и W3,
согласовать общий Next contract из scenarios.md перед W4. Исполнять в текущем root, если
контекст сохранён. Отдельный launch, повторный аудит, master plan и переключение на Sol
не являются условиями начала этой реализации. Текущий запрос на аудит этим завершён;
изменение рабочих подключений и поведения вынесено в явные проверяемые рекомендации.
