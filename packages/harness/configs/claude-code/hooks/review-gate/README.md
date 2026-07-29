# review-gate — гейт соблюдения архитектуры (SubagentStop)

Детерминированный L5-рубеж: после завершения субагента прогоняет набор проверок и,
если какая-то не прошла, подсказывает (`warn`) или блокирует (`strict`). Дополняет
`skills:`-preload skiller (L2): preload даёт агенту скиллы, гейт ловит то, на что
агент всё равно забил — гарантия там, где проза «следуй скиллу» её не даёт.

## Режимы (`env.ini`, дефолт `warn`)

| MODE | Поведение |
|---|---|
| `off` | гейт выключен целиком |
| `warn` | нарушение → подсказка в контекст (`additionalContext`), субагент НЕ блокируется; ПОНИЖАЕТ любую `strict`-проверку до `warn` (апгрейд `warn`→`strict` глобальным режимом запрещён) |
| `strict` | strict-проверки блокируют (см. «Семантика `exit 2`» ниже); warn-проверки как обычно только подсказывают |

Per-project override: `.claude/review-gate.env.ini` (`MODE=...`).

## Содержание — `checks/`, набор и режим — `config.json`

Содержание проверки **не** живёт в `check_command` — это ОДНА стабильная строка,
вызов диспетчера `checks/run-checks.sh`. Сами проверки — скрипты, которые везёт
harness (`checks/<name>.sh`); машина объявляет ТОЛЬКО набор и per-check режим:

```json
{
  "version": 2,
  "check_command": "$REVIEW_GATE_DIR/checks/run-checks.sh",
  "checks": [
    { "name": "generated-assets", "mode": "strict" },
    { "name": "plan-lint", "mode": "strict" },
    { "name": "tests-touched", "mode": "warn" }
  ]
}
```

| Код | Проверка | Дефолт-режим | Что делает |
|:--|:--|:--|:--|
| G1 | `generated-assets` | `strict` | дифф трогает файл с заголовком `swissknifeman:generated` → нарушение (правка принадлежит паку, редактируется override-файл) |
| G2 | `plan-lint` | `strict` | дифф задел `plans/<ID>/` → прогон `packages/task/scripts/plan-lint.py`; ERROR → нарушение |
| W1 | `tests-touched` | `warn` | дифф трогает `packages/*/lib/**` без `packages/*/tests/**` (эвристика — легальные исключения есть, поэтому всегда `warn`, никогда `strict`) |

Неизвестное имя в `checks[]` — явная ошибка конфигурации (диспетчер печатает её и
считает нарушением-warn), а не молчаливый пропуск. Пустой `check_command` (или
пустой `checks[]`) — **fail-open no-op**, как раньше: гейт качества относится к
advisory-классу, и практика прямо разрешает fail-open для него, но состояние
обязано быть ВИДИМЫМ (`harness doctor`, ниже), а не молчаливым.

### Защита от петли

`exit 2` на `SubagentStop` **не прерывает** субагента (first-party: «Prevents the
subagent from stopping») — субагент продолжает работать с фидбеком в stderr, то
есть петля «нарушение → чинит → снова проверка». `stop_hook_active` в доке не
описан, полагаться на рантайм нельзя. Поэтому диспетчер сам считает подряд
идущие strict-отказы ОДНОЙ И ТОЙ ЖЕ проверки в рамках сессии+агента
(`${XDG_RUNTIME_DIR:-/tmp}/review-gate/<session>.<agent>.<check>`, атомарная
запись) и на третьем подряд отказе понижает ИМЕННО эту проверку до `warn` с
`systemMessage` («гейт понижен: проверка X не проходит 3-й раз, чиню вручную»).

### Custom project-local `check_command`

`.claude/review-gate.config.json` проекта исполняется ТОЛЬКО если машина-владелец
явно разрешила это в `$HOOK_DIR/env.ini` (`ALLOW_PROJECT_CONFIG=1`) — иначе это
произвольное исполнение кода при открытии чужого репо. Для такого custom
`check_command` (не наш диспетчер) severity решает только глобальный `MODE`, как
раньше — трёхуровневый strict/warn-per-check протокол относится ТОЛЬКО к
`checks/run-checks.sh`.

## Три состояния в `harness doctor`

Вместо тихого no-op (признанный анти-паттерн — «выглядит включённым, но молча
ничего не проверяет») `harness doctor` печатает РОВНО одно из трёх:

- `unconfigured (no-op)` — `check_command`/`checks[]` пуст или файла нет;
- `configured: G1, G2 (strict), W1 (warn)` — набор и режимы по факту `config.json`;
- `disabled (MODE=off)` — глобально выключено.

## Проводка

Хук висит на событии `SubagentStop` в `settings.global.json`. Файлы ставит
`harness hooks --global` (`apply-permissions.sh`) в `~/.claude/hooks/review-gate/`
(код `review-gate.sh` и `checks/` — обновляются всегда; `env.ini` не перезатирается;
`config.json` мигрируется на новый шаблон ТОЛЬКО если он байт-в-байт равен старой
заглушке `{"version":1,"check_command":""}` — иначе локальный выбор уважается,
файл не трогается, печатается точная команда ручного обновления).

## Проверка после установки (live)

`exit 2`-блок и `additionalContext` подтверждаются только реальным прогоном
субагента: задать заведомо падающую проверку и убедиться, что в `warn` приходит
подсказка, а в `strict` субагент получает stderr и продолжает работу (не
блокируется намертво).
