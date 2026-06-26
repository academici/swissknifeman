---
name: skill-authoring
description: "Правила создания и изменения скиллов реестра в этом репозитории (skills/**, generate-skill/): ДВУЯЗЫЧНАЯ модель SKILL.ru.md (полный русский ИСТОЧНИК, правит человек) → SKILL.md (компактный EN-канон, генерируется из RU, грузит агент), проверка на пересечение, требования полноты, frontmatter, обязательный upstream.json для внешних, requires/produces_for. Активировать при любом добавлении, правке, переносе, удалении скилла И при правке SKILL.ru.md / регенерации SKILL.md."
---

# Авторинг скиллов реестра

Внутренний скилл (не экспортируется). **Процедура** работы со скиллами;
карта пакета — в `package-architecture`, канонический процесс — в
`CONTRIBUTING.md` (здесь только правила, которых там нет).

## Когда активировать

- Создание, правка, перенос или удаление любого `skills/<bucket>/<name>/SKILL.md`,
  его `SKILL.ru.md`, snippets/, references/, adapters/ или upstream.json.
- **Правка `SKILL.ru.md`** (русский источник) — после неё ОБЯЗАТЕЛЬНА регенерация
  `SKILL.md` (см. «Двуязычная модель»).
- Правка внутренних скиллов `.claude/skills/` (правило «без пересечений»
  действует и для них).

## Шаг 0 — проверка пересечений (обязательно ДО создания)

1. Поиск по `skills.json`: name, description, tags по теме нового скилла.
2. `grep -ri` по `skills/` по ключевым словам темы.
3. Проверить `references/` — возможно, импорт уже запланирован.

**Решение:** пересечение по содержимому найдено → расширяй существующий скилл,
не создавай новый. Одинаковое имя в одном бакете — ошибка валидатора; в разных
бакетах — warning (коллизия при вендоринге), допускается только осознанно.

## Двуязычная модель: `SKILL.ru.md` (источник) → `SKILL.md` (EN-канон)

КАЖДЫЙ локальный скилл реестра двуязычен:
- **`SKILL.ru.md`** — полный русский ИСТОЧНИК. Его правит человек, это SSOT: вся
  полнота (контекст, «почему», примеры).
- **`SKILL.md`** — компактный английский КАНОН, **генерируется** из RU. Только его
  грузит агент; русский в контекст не попадает.

**Создание:** сначала пиши `SKILL.ru.md` (полный, по «Требованию полноты» ниже) →
сгенерируй `SKILL.md` промтом `packages/skiller/prompts/generate/claude-canon-from-ru.md`
(компактный EN, сохраняет ВСЕ правила/условия/пороги/код/пути; frontmatter копируется,
переводится только `description`) → `bash packages/skiller/scripts/check-translations.sh --stamp`.

**Изменение:** правь ТОЛЬКО `SKILL.ru.md` → регенерируй `SKILL.md` тем же промтом →
`--stamp`. **НЕ правь `SKILL.md` напрямую** — он перезапишется из RU и правка потеряется.

**Контроль:** `check-translations.sh` (без флагов) → список «EN протух» (RU правлен,
EN не регенерён). Свежесть метит `<!-- ru-source-sha256 -->` в конце `SKILL.md`.
`*.ru.md` коммитятся, но НЕ вендорятся в проекты.

**Внешние (upstream) — исключение:** их `SKILL.md` (EN) приходит от upstream и НЕ
генерируется из RU; `SKILL.ru.md` у них — лишь справка для человека, канон не трогаем.

## Локальный скилл

1. Заполни **полный** frontmatter (в `SKILL.ru.md`; при генерации EN он копируется):
   `name` (kebab-case, == имени каталога), `bucket`, `version`, `description`,
   `risk: read|draft|write|external`, `persona`, `tags`, `requires`,
   `produces_for`, `outputs`, `snippets`, `adapters`, `sha256: ""`.
2. Списки — только inline-синтаксис `[a, b]`: многострочные YAML-списки
   не парсятся ни sync, ни валидатором.
3. Новый бакет → обязательная запись в `buckets.json` (description/category/tags).
4. Вложенный SKILL.md внутри скилла невидим для plugin discovery —
   разворачивать в соседний каталог `<parent>-<child>`.

## Философия гранулярности и размещения (доктрина)

Полная версия — [skill-taxonomy.md](../../../packages/skiller/docs/guide/skill-taxonomy.md). Кратко —
**где** должен жить скилл и **насколько** он дроблён:

1. **Один скилл = одна способность; бакет = крупная область роли.** Не сваливай разнородное в
   один скилл; не плоди бакет-на-каждый-скилл.
2. **`general` — только кросс-стек.** Он входит в **CORE** (раздаётся в КАЖДЫЙ проект, грузится
   всегда) → обязан быть минимальным и универсальным. Стек-специфичное (PHP/Laravel/Node/Vue) в
   `general` — **запрещено**: место в `php`/`devops`/`frontend`.
3. **Project-specific → project-local, НЕ в реестре.** Бизнес-логика конкретного проекта (имена
   доменных классов, enum'ов, `App\…`) живёт в `<project>/.claude/skills/`, а не в общем реестре
   (правило универсальности, см. «Ревью скилла»).
4. **init-only ≠ always-loaded.** Скилл, нужный один раз (выбор стека/пакетов при инициализации),
   не держим в постоянной раздаче — помечай как init-only (frontmatter `lifecycle: init`), не клади
   в CORE/дефолтные профили.
5. **lean SKILL.md.** Тело — точка входа (ориентир ≤150 строк): что это, когда, ключевой алгоритм.
   Детали/длинные примеры/таблицы → `references/`/`snippets/` (progressive disclosure). `validate.sh`
   предупреждает о раздутых телах (мягко). Канал: connect = бакет целиком (грубо), vendor = скилл
   (тонко) — тонкую настройку веди через vendor.

## Требование полноты (скилл «максимально полный»)

Скилл обязан содержать:

1. **Явные критерии активации** — секция «Когда активировать», а description
   во frontmatter работает как роутер (триггеры названы явно).
2. **Полный алгоритм** — без заглушек и «см. в другом месте» для ключевых шагов.
3. **Чеклист качества** — проверяемые булевы пункты.

Сниппеты: анонимизированы (`namespace App\...`,
`// Source: {project}/{file} (anonymized)`), перечислены в `snippets/index.json`.
Адаптерные отличия — только в `adapters/`, никогда дублированным SKILL.md.

## Eval-first: поведенческие тесты скилла (evals/)

Структурная валидация не отвечает на главный вопрос — *скилл работает и срабатывает
к месту?* Поэтому к КАЖДОМУ авторскому (не-upstream) скиллу заводи `evals/` рядом со
SKILL.md (скаффолд: `skiller eval <bucket>/<name> --scaffold`):

- **`evals.json`** — кейсы `{id, prompt, assertions[]}`; ассершены ТОЛЬКО
  детерминированные (`contains`/`not_contains`/`regex`/`not_regex`/`file_exists`/
  `file_absent`/`min_words`) — грейд воспроизводим без LLM-judge. Промпты — на
  реальном языке пользователя, с конкретикой.
- **`pressure.json`** — сценарии-соблазны (из методики «TDD для документации»):
  что подмывает агента сделать, ПРОПУСТИВ скилл, и ассершены на соблюдение/нарушение.
- **`triggers.json`** — `should_trigger` / `should_not` запросы для точности
  срабатывания `description` (ярус-0). Оптимизация: `skiller eval … --triggers`
  предлагает описание ≤150 симв.; правка идёт в `SKILL.ru.md` → регенерация EN.

Прогон `skiller eval <bucket>/<name>` (with-skill vs `--baseline`) пишет
`evals/benchmark.json`. Требует CLI `claude`; без него — офлайн-валидация формата.
`evals/` НЕ вендорится (как `*.ru.md`) и не входит в content-hash. Покрытие видно
строкой `evals coverage:` в `validate.sh`. Канон — `docs/guide/evals.md`.

## Внешний/производный скилл → upstream.json обязателен

Любой скилл, заимствованный или производный от внешнего источника, обязан
иметь `upstream.json` рядом со SKILL.md:

- `schema_version: 1`; `source: github|http|file` (file — только локальные
  фикстуры/тесты); `strategy`:
  - `replace` — зеркало (у апстрима валидный frontmatter, автонакат);
  - `notify` — адаптированная копия (апстрим только репортится);
  - `fork` — форк с нашими правками (pristine-зеркало в `files[].path`; на дрейфе
    `review_pending=true` блокирует распространение — ручной перенос, потом `--resolve`);
  - `merge` — **композит из ≥2 внешних источников**, собранный в единый целиковый скилл.
- `files[]` — каждый с `path`/`url`/`sha256`/`fetched_at` (YYYY-MM-DD); `notes`.

**Composite (`strategy: merge`) — скилл из нескольких источников.** Когда скилл
фактически слеплен из двух+ внешних скиллов, фиксируй провенанс с ролями в `origins[]`:

```json
{
  "schema_version": 1, "source": "github", "strategy": "merge",
  "origins": [
    {"repo": "antfu/skills", "role": "base", "url": "…", "ref": "main",
     "sha256": "…", "fetched_at": "2026-06-26", "note": "взята структура и ядро"},
    {"repo": "onmax/nuxt-skills", "role": "supplement", "url": "…",
     "sha256": "…", "fetched_at": "2026-06-26", "suggest": "добавлены разделы SEO/модули"}
  ],
  "merge": {"review_pending": false, "last_review": "2026-06-26"},
  "files": [ … ]
}
```

- Роли: ровно один `base` (взят за основу) + ≥1 `supplement` (дополняющий
  источник-«suggest»; чем именно дополнил — в `note`/`suggest`).
- **Синк ручной, под управлением агента.** На дрейфе любого `origin` ставь
  `merge.review_pending=true` — это блокирует `validate.sh`/`registry`/релиз, пока
  агент не пере-мерджит источники в SKILL.md вручную и не снимет гейт
  (`scripts/update-upstreams.sh --resolve --skill <id>`). Авто-overwrite для merge запрещён.
- Workflow: каталог → upstream.json с пустыми sha →
  `./scripts/update-upstreams.sh --apply --skill <bucket>/<name>` → статус
  в `references/<source>.md` → imported.
- Эталон: `skills/php/laravel-best-practices/upstream.json` (multi-file, notify).

## requires / produces_for

- Только существующие frontmatter-`name`; без self-reference; без циклов по
  `requires`. Пара `A requires B` + `B produces_for A` — легальна.

## Ревью скилла (стандарт приёмки, для ревьюера и автора)

Скилл реестра обязан быть **универсальным** и не пересекаться с существующими:

1. **Универсальность.** Нет project-specific бизнес-логики и **нет имён
   конкретных проектов/пакетов** в теле/сниппетах (используй обобщённо:
   «проект-потребитель», «зависимый пакет»). Привязка к проекту → место в
   `.ai/skills/` проекта, не в реестре; специфику выноси в `snippets/` с
   параметризацией.
2. **Нет дубля.** Шаг 0 пройден: поиск по `skills.json` (name/description/tags) и
   `grep -ri skills/` по теме чист, либо расширён существующий скилл.
3. **Полнота frontmatter.** Все поля, inline-списки, `name` == каталог,
   `risk`/`persona`/`bucket` валидны, новый бакет — в `buckets.json`.
4. **Триггеры в `description`.** Конкретные сценарии активации (когда включать),
   а не абстрактное описание темы — description работает как роутер.
5. **Сниппеты.** Анонимизированы, перечислены в `snippets/index.json`, несут
   ценность (не пересказ тела).

## Завершение

Правил `SKILL.ru.md` → регенерь `SKILL.md` (промт `claude-canon-from-ru.md`) →
`scripts/check-translations.sh --stamp` → `./scripts/validate.sh` → `skiller registry` →
закоммитить `SKILL.ru.md` + регенерированный `SKILL.md` + `skills.json`,
`.claude-plugin/*`, `docs/guide/graph.md`/`budget.md` вместе с изменением →
далее по `release-discipline`.

## Чеклист качества

- [ ] Шаг 0 выполнен, пересечений нет (или расширен существующий скилл).
- [ ] Двуязычие: `SKILL.ru.md` (источник) обновлён; `SKILL.md` регенерён из него (НЕ правлен напрямую); `check-translations.sh` без stale.
- [ ] Frontmatter полный, name == каталог, inline-списки.
- [ ] Есть «Когда активировать», полный алгоритм, чеклист.
- [ ] Внешний скилл — upstream.json с заполненными sha256/fetched_at.
- [ ] requires/produces_for валидны; новый бакет — в buckets.json.
- [ ] validate зелёный, registry регенерирован и закоммичен.

## Связанные скиллы

`package-architecture` (карта), `release-discipline` (завершение),
`docs-maintenance` (документация).

## Ссылки

`CONTRIBUTING.md`, `SKILL_TEMPLATE.md`, `docs/guide/creating-skills.md`,
`docs/guide/skill-anatomy.md`, `docs/guide/upstream-sync.md`.
