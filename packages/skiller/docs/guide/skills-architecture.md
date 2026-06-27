# Архитектура скиллов: реальное состояние

> **Читать первым** перед любым предложением «переписать архитектуру скиллов».
> Этот документ фиксирует, как система устроена **на самом деле** — чтобы аудиты и
> агенты не проектировали поверх неверной картины. Числа (счётчики скиллов/бакетов)
> — источник истины `skills.json` и `skills/_index.md`, здесь даны ориентировочно.

## TL;DR

skiller — это **реестр готовых, иерархически организованных, двуязычных скиллов** с
графом зависимостей, который раздаётся в проекты двумя независимыми каналами. Скиллы
**не монолитны**, у них **есть** фронтматтер, зависимости и неявные уровни. Тела
скиллов в рантайме читает **сам агент (Claude Code)**, а не Python-процесс skiller —
поэтому «кэш загрузки скиллов» внутри skiller не имеет вызывающего (см. §7).

## 1. Где живут скиллы и двуязычная модель

- Скилл — это **каталог** с файлом `SKILL.md`: `skills/<bucket>/<name>/SKILL.md`.
- Наши (не-upstream) скиллы **двуязычны**:
  - `SKILL.ru.md` — полный русский **источник** (его правит человек, SSOT).
  - `SKILL.md` — компактный английский **канон**, **генерируется** из RU
    (промт `prompts/generate/claude-canon-from-ru.md`); именно его грузит агент.
  - Свежесть EN метит `<!-- ru-source-sha256: … -->`; когерентность проверяет
    `scripts/check-translations.sh`. `*.ru.md` **не вендорится** в проекты.
- Внешние (upstream) скиллы: канон EN приходит от upstream (см. `upstream-sync`),
  `SKILL.ru.md` для них — лишь справка.
- **Внутренние** скиллы репозитория (`.claude/skills/*`, напр. `package-architecture`)
  — одиночные `SKILL.md`, не двуязычны и не раздаются (мягкий линт в `validate.sh`).

Подробно: [Анатомия скилла](./skill-anatomy.md), [Создание скиллов](./creating-skills.md).

## 2. Фронтматтер и метаданные

Каждый `SKILL.md` несёт фронтматтер (`SKILL_TEMPLATE.md` — каноническая схема):

```yaml
name· bucket· version· description· risk· persona· tags·
requires· produces_for· outputs· snippets· adapters· sha256·
level   # опц.: core|foundation|extension — слой иерархии (см. §4)
```

- **`requires`** — скиллы, которые этот тянет (транзитивно резолвится в vendor).
- **`produces_for`** — скиллы, которым этот полезен (граф/документация).
- **`level`** — *необязательное* само-документирование слоя; пишется в `skills.json`
  при наличии, валидируется enum'ом в `validate.sh`. Opt-in: проставляется по
  желанию авторов, не обязателен. Дополняет `requires`/`produces_for`, **не заменяет**.

Источник истины метаданных — `skills.json` (генерируется `skiller registry`).

## 3. Бакеты и группировка

Скиллы сгруппированы в бакеты по **домену + роли** (а не «один бакет = один язык»):

- по роли: `architect`, `oss-dev`, `pm`, `founder`, `operator`, `quality`, …;
- по технологии: `php` + тонкие `laravel-*` (`laravel-testing/auth/data-layer/…`),
  `frontend` + `frontend-*` (`vue/nuxt/tailwind/…`), `devops`, `python`, …;
- по бизнес-домену: `legal`, `finance`, `marketing`, `security`, …

Метаданные бакета (description/category/tags) обязательны в `buckets.json` (1:1 с
каталогами, проверяет `validate.sh`). См. [Таксономия](./skill-taxonomy.md).

## 4. Неявные уровни (tiering) — уже есть

«Базовый слой, который раздаётся всем» **уже** закодирован, просто не в дереве каталогов:

- `CORE_SKILLS` / `CORE_PLUGIN` (`lib/skiller/config.py`) — токен-экономное **ядро** (7 скиллов),
  раздаётся в КАЖДЫЙ проект по умолчанию (`--no-core` отключает). В **connect** это курируемый
  marketplace-плагин `core` (`source:"./"` + `skills[]` по ссылкам, без копий) — грузит РОВНО эти 7
  вместо целых бакетов `general`+`oss-dev` (резидентный ⊕ tier-0 ~1956 → ~480 ток/проект). В
  **vendor** — те же 7 пофайлово. `CORE_BUCKETS` оставлен для autodetect-фолбэка и миграц.-подсказки.
- `profiles/*.json` — наборы бакетов по типу проекта (autodetect → профиль).
- `presets/*.json` — именованные сквозные кластеры скиллов (vendor).
- опц. поле `level` (§2) даёт это явно во фронтматтере, без переезда файлов.

Поэтому **переразрезание скиллов в дерево `core/foundation/extension` не требуется** —
выгода (само-документирование слоёв) достигается полем `level`; цена переезда (193
двуязычные пары, 49 имён плагинов, локи потребителей) несоразмерна. Полный разбор отклонённых предложений — в разделе 9 ниже.

## 5. Два канала раздачи

| Канал | Что делает | Гранулярность | Конфиг |
|:--|:--|:--|:--|
| **connect** | бакет = плагин Claude Code marketplace; пишет `enabledPlugins` в `.claude/settings.local.json`; скиллы НЕ копируются, автообновляются из реестра | **bucket-granular** (skill-level `exclude` игнорируется) | `.swissknife.json` |
| **vendor (`sync`)** | физически копирует скиллы в `.claude/skills/`; файлы коммитятся в репо проекта; для проектов без доступа к реестру | **skill-granular** (`include`/`exclude` по скиллам) | `.swissknifeman/config.json` |

Legacy `skiller vendor --agent cursor|generic` — копии в `.cursor/.ai` (для Claude
deprecated, используй `sync`). См. [Vendor-режим](./vendor-mode.md).

## 6. Два конфига проекта (важно — частый источник путаницы)

В системе **два** конфига проекта с **разными ролями**. Их не нужно сливать:

- **`.swissknife.json`** — лёгкий конфиг для `connect` (+ legacy vendor):
  `project_type/buckets/exclude/presets/agent/skills_path` (+ `memory_brain`,
  `coordinator_ignore` и поля agent-framework `shape/stacks/skills_map`). Полный
  список — `CONFIG_KEYS` (`lib/skiller/common.py`), валидатор `config.validate_config`.
  **bucket-granular.**
- **`.swissknifeman/config.json`** — канонический источник истины **vendor-режима**:
  `version/mode/agent/skills_path/presets/include/buckets/exclude`. Ключи —
  `SKILLSET_KEYS` (`lib/skiller/skillset.py`), валидатор `load_skillset_config`.
  **skill-granular.**

Мост: при первом `sync`/`init` `.swissknifeman/config.json` **лениво материализуется**
из профиля проекта (или из legacy `.swissknife.json`), недеструктивно. Отдельной
команды миграции не нужно.

JSON-схемы обоих конфигов — `schema/*.json` (автодополнение в редакторе через
`$schema`). Рантайм-валидация остаётся ручной и stdlib-only; схемы держатся в синхроне
с кодом гейтом `tests/test_schema.py` и проверкой `skiller doctor`.

Бутстрап: **`skiller init`** создаёт `.swissknifeman/config.json` из автодетекта
(без копирования скиллов — это делает `sync`).

## 7. Как скиллы потребляются в рантайме (и почему «кэша загрузки» нет)

**Тела скиллов читает не skiller, а сам агент (Claude Code):**

- vendor → скиллы физически лежат в `.claude/skills/<name>/SKILL.md`; Claude Code
  грузит их с диска **сам**.
- connect → marketplace указывает на реестр; Claude Code читает `SKILL.md` оттуда.

Python-процесс skiller **никогда не читает тело скилла в рантайме** — нет функции
`load_skill`, нет `loader.py`. skiller только **копирует файлы** (vendor),
**регистрирует плагины** (connect) и **парсит фронтматтер** (registry/budget/vendor —
для метаданных, не для раздачи тела).

Следствие: **подсистема кэширования «загрузки скиллов» внутри skiller не имеет
вызывающего** — кэшировать нечего. Экономию токенов на повторных запросах даёт
**prompt caching** на стороне Anthropic/Claude Code (автоматически, «никакой прокси не
нужна») — для его эффективности важны стабильный порядок и размер скиллов, а не наша
подсистема. Токен-математику считает единый модуль `budget.py` (`skiller budget`).

## 8. Артефакты sync и детект дрейфа

- `skills-lock.json` — карта установленного: `managed:true` + `sha256` (по `SKILL.md`) +
  `content_sha256` (по **всему каталогу** скилла) — отличает наши vendor-копии от
  чужих/ручных; sync трогает только `managed`. **Инкрементальный sync** (`plan_sync`):
  копирует только `add`/`update`, неизменённые `keep` не трогает, выбывшие `managed` прунит.
  Дрейф ловится по `content_sha256`, поэтому правки в `snippets/`/`references/` (при неизменном
  `SKILL.md`) тоже триггерят `update`. Старые локи без `content_sha256` деградируют корректно
  (дрейф по `SKILL.md`), поле доpopulated при следующем sync без перекопирования.
- `.swissknifeman-manifest.json` — манифест переустановки (`installed_at/profile/…`).
- Резолв зависимостей: `vendor.build_requires_index` + `resolve_requires`
  (транзитивный обход `requires`) — на этапе **выборки** (setup-time), не в рантайме.

## 9. Что сюда НЕ входит и почему

Отрецензированный аудит (`research/swissknifeman_skills_architecture.md`,
`research/swissknife_cache_and_config.md`) предлагал несколько вещей, **отклонённых**
после сверки с кодом:

| Предложение аудита | Решение | Причина |
|:--|:--|:--|
| 3-уровневый рефакторинг каталогов | **отклонён** | цель уже решена skill-granular vendor; цена churn несоразмерна; опц. поле `level` даёт само-документирование без переезда |
| Подсистема кэширования (`SkillMemoryCache`/disk) | **отклонён** | нет вызывающего (§7); prompt caching автоматический |
| `core/resolver.py`, `core/project.py` для конфига | **отклонён** | резолв уже в `vendor.py`; `core/project.py` уже есть (детект типа) |
| Единый `swissknife.json` | **не вводится** | два конфига имеют разные роли (§6) |

Принято к реализации: `skiller init`, JSON-схемы + проверки `doctor`, опц. поле
`level`, эта документация. Полная рецензия — в decision-record шапке research-доков.

## Связанные документы

- [Анатомия скилла](./skill-anatomy.md) · [Таксономия](./skill-taxonomy.md)
- [Vendor-режим (sync)](./vendor-mode.md) · [Профили и автодетект](./profiles.md)
- [Реестр skills.json](./registry.md) · [Токеновый бюджет](./budget.md)
- [Методология: против раздувания](./methodology.md)
