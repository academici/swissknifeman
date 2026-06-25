# Vendor-режим: физический перенос скиллов (`sync`)

Два канала доставки скиллов в проект:

| Канал | Команда | Что делает | Гранулярность |
|---|---|---|---|
| **connect** (marketplace) | `skiller connect` | Включает плагины-бакеты Claude Code через `enabledPlugins`. Файлы скиллов **не копируются** в репо. | Бакет целиком |
| **vendor** (физ. перенос) | `skiller sync` | **Копирует** выбранные скиллы в репо, пишет производный `skills-lock.json`. | Отдельные скиллы |

`connect` хорош, когда не нужна фиксация в репозитории и устраивает «весь бакет».
**vendor-режим** — когда нужно: видеть скиллы в репо, выбирать ровно нужные позиции
из разных областей, фиксировать набор и обновлять его из библиотеки по lock-файлу.

::: tip Главный кейс vendor — внешние разработчики
`connect` подключает плагины через `extraKnownMarketplaces`, который указывает на
**локальный путь к реестру swissknifeman**. У разработчика, которому отдали репозиторий
проекта, но **нет** репо swissknifeman, плагины не подключатся — скиллов он не увидит.

`vendor` (`sync`) кладёт **файлы скиллов прямо в репо проекта** (`.claude/skills/`,
git-tracked). Любой, кто клонировал проект, сразу получает скиллы — реестр swissknifeman
ему не нужен. Это канал для проектов с внешней командой.
:::

Выбор канала касается **только скиллов** — у них нет другого функционала, кроме раздачи
файлов. Память, граф и MCP-инструменты хаба mAInd настраиваются независимо от канала.

## Конфиг — единый источник истины

В корне проекта — `.swissknifeman/config.json`. Один настраиваемый конфиг вместо
россыпи: правила разворачиваются в плоский набор скиллов.

```json
{
  "version": 1,
  "mode": "vendor",
  "skills_path": ".claude/skills",
  "presets": ["laravel-admin"],
  "include": ["architect/api-design"],
  "buckets": ["quality"],
  "exclude": ["php/medialibrary"]
}
```

Правила комбинируются: **набор = (presets ∪ buckets ∪ include) − exclude**.

- `presets` — именованные кластеры скиллов (`presets/<name>.json`): раскрываются в
  `buckets`/`include` (с рекурсивным `extends`). Удобные «куски» вместо ручного перечисления —
  напр. `laravel-admin` = ядро Laravel + Filament/права/медиа. См. [Пресеты](./presets).
- `include` — конкретные скиллы из любых областей: `"bucket/rel"` или просто `"name"`.
- `buckets` — бакеты целиком.
- `exclude` — вычитание (имя или `"bucket/rel"`); бьёт и пресеты, и зависимости.
- Можно задать только `presets` или только `include` — переносится ровно нужное.

> Пресеты — концепт **vendor-канала** (раскрываются в per-skill набор). В `connect`
> бакет атомарен, поэтому пресеты там не действуют (как и skill-level `exclude`).

## Поток синхронизации

```
.swissknifeman/config.json   (источник истины — правит человек)
        ↓ resolve            (buckets ∪ include) − exclude → плоский набор
   набор скиллов библиотеки   (резолвится по skills.json реестра)
        ↓ sync               install + update(по sha256) + prune(по managed)
                             + CORE-скиллы по умолчанию (как vendor/connect)
.claude/skills/<name>/        физические копии (видит Claude)
skills-lock.json             производная карта: managed-записи + чужие нетронуты
.swissknifeman-manifest.json  манифест в skills_path (переустановка + индекс хаба)
CLAUDE.md / .ai/guidelines    индекс скиллов (managed-блок), если есть или --hub
```

```bash
skiller sync --dry-run     # показать план: +add ~update -remove =keep
skiller sync               # применить (CORE раздаётся по умолчанию)
skiller sync --force       # перетереть чужой путь версией из библиотеки
skiller sync --hub         # дополнительно сгенерировать индекс скиллов
skiller sync --no-core     # без CORE-скиллов; --no-hub — без индекса
```

`sync` пишет `.swissknifeman-manifest.json` в `skills_path` (контракт чистой
переустановки и источник для `generate-hub.sh`), раздаёт `CORE_SKILLS` по
умолчанию (`--no-core` отключает) и обновляет индекс скиллов в корне проекта
(managed-блок `CLAUDE.md` или `.ai/guidelines/swissknifeman-hub.md` для Boost),
если он уже есть в проекте или передан `--hub`.

## skills-lock.json — производный, не источник

`sync` пишет на каждый наш скилл запись с пометкой происхождения:

```json
"laravel-best-practices": {
  "source": "swissknifeman",
  "managed": true,
  "bucket": "php",
  "sha256": "…",
  "installed_path": ".claude/skills/laravel-best-practices"
}
```

- **`managed: true`** — скилл под управлением vendor-режима. **Удаление**: при синке
  берётся полная выборка `managed`-записей, сверяется с конфигом; то, чего больше нет
  в конфиге, **удаляется** из lock и из репо.
- **Чужие записи** (`managed` отсутствует/false — ручной вендоринг, скиллы из другого
  хаба, наследие Boost) синк **не трогает**: ни удаляет, ни перетирает. Можно дописывать
  в `skills-lock.json` собственные скиллы вручную — `sync` синхронизирует **только
  `managed: true`** и чужие записи переживают синк (даже при пустом конфиге).
- **Дрейф** — при расхождении `sha256` с библиотекой файл перекопируется (`~update`).
- **Ручная чистка lock.** Если удалить нашу `managed`-запись вручную, а папка скилла
  осталась — `sync` без `--force` сочтёт путь чужим (пропуск с warning), `--force`
  чисто пере-усыновит скилл (одна `managed`-запись, без хвостов).

## Гигиена каналов: не держи бакет в обоих сразу

Один бакет не должен раздаваться **одновременно** плагином (`connect`) и вендором
(`vendor`) — иначе скиллы приедут дважды. `skiller status` это ловит и печатает
`⚠ ДУБЛЬ КАНАЛОВ: …` со списком пересекающихся бакетов. Проверка живёт в skiller
(владелец скиллов) и доступна из зонтика — `swissknifeman skills status`. Лечение:
убрать бакет из `enabledPlugins` (connect) **или** из `.swissknifeman/config.json`
(vendor) + `skiller sync`.

## Конфликты

Если путь нашего скилла уже занят **чужим** (каталог/симлинк/файл, который не наш
`managed`), `sync` без `--force` его **пропускает** с warning, чтобы не затереть
чужое. `--force` заменяет занятый путь версией из библиотеки (симлинк снимается,
цель симлинка остаётся на месте).

## Выбор канала при онбординге (`integrate` / `onboard` / `setup`)

Канал спрашивается заранее — не нужно вручную писать `.swissknifeman/config.json`:

```bash
# визард спросит канал (connect/vendor) интерактивно
skiller integrate
# или без вопроса:
skiller integrate --skills-channel vendor --yes   # vendor → sync в .claude/skills
skiller integrate --skills-channel connect --yes  # плагины marketplace

# на полном онбординге в экосистему (тоже спрашивает; флаг для неинтерактива):
maind onboard <project> --skills-channel vendor
swissknifeman setup <project> --skills-channel vendor
```

При `--skills-channel vendor` для Claude-проекта `integrate` **сам генерит**
`.swissknifeman/config.json` из профиля проекта (`buckets` по типу) и сразу применяет
`sync` — скиллы оказываются в `.claude/skills/`. Дальше уточняй набор правкой
конфига (`include`/`exclude`) и повторным `skiller sync`. Для Cursor/Gemini физический
перенос в `.ai/.cursor` — отдельная legacy-команда `skiller vendor --agent cursor`.

## Философия: Laravel Boost не использовать как канал

Laravel Boost — это **MCP-сервер** (database-query, tinker, logs, docs…) **и** канал
скиллов. Полезен как MCP, но как **источник скиллов** его убираем: все скиллы должны
проходить единую проверку библиотеки swissknifeman, без отдельной совместимости с Boost.

- Boost **остаётся как MCP** (`boost.json: "mcp": true`, сервер `laravel-boost` в
  `.mcp.json`) и может оставлять свои guidelines (`"guidelines": true`).
- Boost **перестаёт быть каналом скиллов**: `boost.json::skills` → `[]`. Его прежние
  скиллы заменяются **прямыми аналогами из библиотеки** (`managed`, через config) —
  напр. `inertia-vue-development`→`frontend/inertia-vue`,
  `tailwindcss-development`→`frontend/tailwind-conventions`.
- нужный, но отсутствующий в библиотеке Boost-скилл **импортируется в неё** как внешний
  (`source: external`), проходит валидацию реестра и дальше живёт как обычный.
- собственные скиллы проекта (git-tracked, напр. в `.ai/skills/`) остаются нетронутыми —
  `sync` их не перетирает (они не `managed`).

См. также [Установка скиллов](./installation) (канал connect) и
[Реестр skills.json](./registry) (источник истины набора).
