# Семантика loop'ов: итеративное исполнение поверх скиллов

Как агент должен исполнять задачу **итеративно с проверкой на каждом круге**, не
заводя для этого отдельный реестр сущностей. Документ формулирует модель loop'а,
показывает, какими **существующими** скиллами она уже закрыта, и где проходит
граница между скиллом (policy: *что проверять и когда стоп*) и раннером
(механика: *сам цикл*).

Идея навеяна каталогом [loops.elorm.xyz](https://loops.elorm.xyz/loops) — набором
переиспользуемых «loop'ов» для AI-агентов. Полезен он не файловой организацией, а
компактной моделью исполнения, которую стоит взять как словарь, а не как структуру.

## Модель loop'а

Каждый loop задаёт пять полей плюс защиту от «накрутки»:

| Поле | Смысл |
|---|---|
| **Goal** | объективный результат («PR открыт, все CI-проверки зелёные») |
| **Run mode** | ручной (prompt-only) или по событию (hook) |
| **Max iterations** | верхний предел кругов (обычно 3–12) — страховка от зацикливания |
| **Between-iterations check** | команда, которой агент проверяет прогресс между кругами (`git log`, тест, линт) |
| **Exit condition** | объективное состояние = задача завершена |
| **Step 1** | что агент делает на каждом круге |

**Anti-gaming guardrails** (этого нет в обычных чеклистах, но именно это отличает
loop от «просто повтори»): нельзя менять саму проверку, чтобы она прошла; нельзя
пропускать верификацию; нельзя подделывать успех манипуляцией метрик. Exit
condition оценивается по выводу честной проверки, а не по утверждению агента.

## Раннер уже встроен — скиллы дают гейты, не цикл

Сам цикл исполнять не нужно изобретать в прозе скиллов: Claude Code уже даёт
раннер.

- **`/loop`** — self-paced или по интервалу; агент сам выдерживает темп, после
  каждого круга гоняет проверку и продолжает, только если exit condition не
  достигнут.
- **`/schedule`** — cron-агенты для повторяющихся задач (CI, аудит, sync).
- `ScheduleWakeup` — динамический темп внутри `/loop` для ожидания внешнего
  состояния.

Скиллы реестра дают **содержимое** loop'а: цель, что считать проверкой, при каком
сигнале остановиться. Раннер дают встроенные команды. Поэтому в реестре нет и не
нужен прозо-псевдораннер, продублированный в каждом скилле.

## Маппинг на существующие скиллы

Модель loop'а уже разложена по зрелым скиллам — каждый закрывает свою фазу:

| Фаза loop'а | Скилл | Что даёт |
|---|---|---|
| Pre-loop contract | [`general/task-brief-template`](https://github.com/academici/swissknifeman/blob/main/skills/general/task-brief-template/SKILL.md) | Goal, out-of-scope, поля `Loop verifier`/`Exit condition`/`Hard stop trigger`, DoD |
| Stop-controller | [`general/anti-drift`](https://github.com/academici/swissknifeman/blob/main/skills/general/anti-drift/SKILL.md) | Circuit Breaker (мягкий ~10 tool-calls / жёсткий ~20 итераций), сигналы деградации, hard-stop → handoff |
| Between-iterations verifier | [`general/cross-layer-change-checklist`](https://github.com/academici/swissknifeman/blob/main/skills/general/cross-layer-change-checklist/SKILL.md) | проверка затронутых слоёв (Domain/API/Frontend/Data/Docs/Tests) после значимого изменения |
| Simplification gate | [`quality/code-simplifier`](https://github.com/academici/swissknifeman/blob/main/skills/quality/code-simplifier/SKILL.md) | YAGNI-чеклист перед объявлением «готово»: откатить лишние абстракции |
| Independent verifier | [`quality/code-review`](https://github.com/academici/swissknifeman/blob/main/skills/quality/code-review/SKILL.md), [`oss-dev/gh-review`](https://github.com/academici/swissknifeman/blob/main/skills/oss-dev/gh-review/SKILL.md) | независимая проверка diff/tests/docs, а не доверие «уже корректно» |
| Shared-code gate | [`architect/package-contribution-protocol`](https://github.com/academici/swissknifeman/blob/main/skills/architect/package-contribution-protocol/SKILL.md), [`architect/architecture`](https://github.com/academici/swissknifeman/blob/main/skills/architect/architecture/SKILL.md) | стоп перед преждевременным выносом в общий слой (Rule of Three, ADR) |
| Phase orchestration | [`general/complex-task-orchestrator`](https://github.com/academici/swissknifeman/blob/main/skills/general/complex-task-orchestrator/SKILL.md) | декомпозиция на фазы с deliverables и test-gate между ними |
| Long-loop discipline | [`general/context-economy`](https://github.com/academici/swissknifeman/blob/main/skills/general/context-economy/SKILL.md) | Plan→Clear→Execute, `/compact`, раздельные сессии для длинных циклов |
| Выход из круга | [`general/session-handoff`](https://github.com/academici/swissknifeman/blob/main/skills/general/session-handoff/SKILL.md) | сжатый handoff при hard-stop, новая сессия с чистым контекстом |

Loop-aware исполнение — это **связка** этих скиллов, а не новый артефакт.
Стартовый шаблон, который сводит цель/проверку/exit/hard-stop в один kickoff —
сниппет `loop-kickoff.md` скилла `task-brief-template` (копируется в
`.claude/commands/` проекта, как `command-*` сниппеты `context-economy`).

## Почему нет папки `loops/`

Тот же анти-bloat, что и в [методологии против раздувания кода](/guide/methodology):
loop-семантика живёт **внутри canonical-скилла**, а не в параллельном реестре.

- Отдельный `loops/`-реестр = второй индекс рядом со скиллами → дубли одного
  паттерна в двух местах и расхождение SSOT.
- Загонять прозо-цикл в каждый скилл = раздувание; раннер уже встроен.
- Папка `loops/` оправдана только если execution-pattern станет самостоятельным
  reusable-юнитом, которому реально тесно внутри существующих скиллов. На текущем
  этапе такого нет.

Решение фиксируется как инвариант: **сначала усиливаем зрелый скилл, и только при
доказанной необходимости заводим новую сущность.**

## Пример: doc/changelog-sync loop

Конкретный loop из каталога — синхронизация CHANGELOG после изменения — ложится
ровно на release-дисциплину этого репозитория:

```text
Goal:            CHANGELOG.md [Unreleased] точно покрывает все видимые изменения
Run mode:        ручной
Max iterations:  3
Between-check:   git log $(git describe --tags --abbrev=0 2>/dev/null || echo HEAD~20)..HEAD --oneline
Exit condition:  changelog покрывает все user-visible изменения
Step 1:          просмотреть свежие коммиты → дописать Keep-a-Changelog записи → проверить полноту
```

Verifier здесь — слой Docs из `cross-layer-change-checklist`; stop-controller —
`anti-drift`; exit оценивается по честному выводу `git log`, не по утверждению
агента (anti-gaming).

## Когда включать loop-aware режим

1. Сначала ищи подходящий existing skill.
2. Проверь, есть ли у него loop-семантика: критерий выхода, проверка между
   кругами, hard-stop. Если задача требует **более одной осмысленной итерации с
   промежуточной проверкой** — заполни поля loop в `task-brief-template` и
   запускай через `/loop`.
3. Если нужной семантики в canonical-скилле нет — предложи **добавить её в этот
   скилл**, а не заводить новую top-level сущность.

## Источники

- [loops.elorm.xyz/loops](https://loops.elorm.xyz/loops) — каталог переиспользуемых
  loop'ов для AI-агентов (модель Goal/Run mode/Max iterations/Between-check/Exit).
- [loops.elorm.xyz/loops/changelog-sync-after-ship](https://loops.elorm.xyz/loops/changelog-sync-after-ship) — конкретный loop, на котором построен пример выше.
- [Методология: против раздувания кода](/guide/methodology) — общий принцип «спроси перед расширением», на который опирается отказ от `loops/`-реестра.
