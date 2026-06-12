---
name: skill-authoring
description: "Правила создания и изменения скиллов реестра в этом репозитории (skills/**, generate-skill/): проверка на пересечение, требования полноты, frontmatter, обязательный upstream.json для внешних, requires/produces_for. Активировать при любом добавлении, правке, переносе или удалении скилла."
---

# Авторинг скиллов реестра

Внутренний скилл (не экспортируется). **Процедура** работы со скиллами;
карта пакета — в `package-architecture`, канонический процесс — в
`CONTRIBUTING.md` (здесь только правила, которых там нет).

## Когда активировать

- Создание, правка, перенос или удаление любого `skills/<bucket>/<name>/SKILL.md`,
  его snippets/, references/, adapters/ или upstream.json.
- Правка внутренних скиллов `.claude/skills/` (правило «без пересечений»
  действует и для них).

## Шаг 0 — проверка пересечений (обязательно ДО создания)

1. Поиск по `skills.json`: name, description, tags по теме нового скилла.
2. `grep -ri` по `skills/` по ключевым словам темы.
3. Проверить `references/` — возможно, импорт уже запланирован.

**Решение:** пересечение по содержимому найдено → расширяй существующий скилл,
не создавай новый. Одинаковое имя в одном бакете — ошибка валидатора; в разных
бакетах — warning (коллизия при вендоринге), допускается только осознанно.

## Локальный скилл

1. Скопировать `SKILL_TEMPLATE.md`, заполнить **полный** frontmatter:
   `name` (kebab-case, == имени каталога), `bucket`, `version`, `description`,
   `risk: read|draft|write|external`, `persona`, `tags`, `requires`,
   `produces_for`, `outputs`, `snippets`, `adapters`, `sha256: ""`.
2. Списки — только inline-синтаксис `[a, b]`: многострочные YAML-списки
   не парсятся ни sync, ни валидатором.
3. Новый бакет → обязательная запись в `buckets.json` (description/category/tags).
4. Вложенный SKILL.md внутри скилла невидим для plugin discovery —
   разворачивать в соседний каталог `<parent>-<child>`.

## Требование полноты (скилл «максимально полный»)

Скилл обязан содержать:

1. **Явные критерии активации** — секция «Когда активировать», а description
   во frontmatter работает как роутер (триггеры названы явно).
2. **Полный алгоритм** — без заглушек и «см. в другом месте» для ключевых шагов.
3. **Чеклист качества** — проверяемые булевы пункты.

Сниппеты: анонимизированы (`namespace App\...`,
`// Source: {project}/{file} (anonymized)`), перечислены в `snippets/index.json`.
Адаптерные отличия — только в `adapters/`, никогда дублированным SKILL.md.

## Внешний/производный скилл → upstream.json обязателен

Любой скилл, заимствованный или производный от внешнего источника, обязан
иметь `upstream.json` рядом со SKILL.md:

- `schema_version: 1`; `source: github|http|file` (file — только локальные
  фикстуры/тесты); `strategy: replace` (зеркало, у апстрима валидный
  frontmatter) или `notify` (адаптированная копия, апстрим только репортится);
  `files[]` — каждый с `path`/`url`/`sha256`/`fetched_at` (YYYY-MM-DD); `notes`.
- Workflow: каталог → upstream.json с пустыми sha →
  `./scripts/update-upstreams.sh --apply --skill <bucket>/<name>` → статус
  в `references/<source>.md` → imported.
- Эталон: `skills/php/laravel-best-practices/upstream.json` (multi-file, notify).

## requires / produces_for

- Только существующие frontmatter-`name`; без self-reference; без циклов по
  `requires`. Пара `A requires B` + `B produces_for A` — легальна.

## Завершение

`./scripts/validate.sh` → `swissknifeman registry` → закоммитить
регенерированные `skills.json`, `.claude-plugin/*`, `docs/guide/graph.md`
вместе с изменением → далее по `release-discipline`.

## Чеклист качества

- [ ] Шаг 0 выполнен, пересечений нет (или расширен существующий скилл).
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
