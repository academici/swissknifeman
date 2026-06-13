# laravel/boost

- **URL:** https://github.com/laravel/boost
- **Packagist:** https://packagist.org/packages/laravel/boost
- **Документация:** https://laravel.com/docs/boost
- **Статус:** trusted (версионное — доверяем на месте; чистый generic — извлекаем точечно)
- **Проверено:** 2026-06-13

**Upstream-отслеживание:**
- `skills/php/laravel-best-practices/upstream.json` (strategy=notify, 21 файл:
  SKILL.md + 20 правил `rules/*.md` ↔ наши `references/*.md`).
- `skills/php/pennant-development/upstream.json` (strategy=notify, SKILL.md) —
  извлечён в реестр (см. «Что извлечено»).

CI/`./scripts/update-upstreams.sh --check` сообщит, когда Boost изменит
отслеживаемые файлы; слияние — вручную.

Официальный пакет Laravel для AI-агентов: поставляет версионно-специфичные
скиллы/гайдлайны, MCP-сервер и генератор корневых CLAUDE.md/AGENTS.md.

## Где физически лежат скиллы Boost

- **В репозитории пакета:** [`/.ai/`](https://github.com/laravel/boost/tree/main/.ai) —
  гайдлайны (`*/core.blade.php` по пакетам и версиям) и скиллы (`*/skill/*/SKILL.blade.php`).
- **В установленном проекте:** `vendor/laravel/boost/.ai/` (обновляются с composer-пакетом);
  выбор — в `boost.json` проекта (массивы `skills`, `packages`); рендер в корневые
  файлы — `php artisan boost:update`.
- **Third-party гайдлайны** приходят из самих пакетов через `boost.json::packages`
  (например `filament/filament`, `spatie/laravel-medialibrary`, `spatie/guidelines-skills`).

## Что извлекаем, а что нет (критерий)

Извлечение скилла Boost в реестр допустимо, только если он одновременно:

1. **Static markdown без Blade** — `SKILL.md`, а не `SKILL.blade.php`; без
   директив `@php`, `@if`, `@foreach`, `@boostsnippet`, `{{ $assist->… }}`.
   Blade-скиллы рендерятся только через `boost:update` в контексте проекта —
   как статику их брать нельзя (импортируешь сломанный шаблон с
   неотрендеренными `{{ … }}`).
2. **Версионно-стабильный** — без version-веток в `.ai/<pkg>/<N>/` (стабильный
   API без развилки по версиям пакета).
3. **Generic и дополняющий** — нет пересечения с существующим скиллом реестра
   (Шаг 0 skill-authoring) и нет конфликта правил.

Если хотя бы один пункт не выполнен — **не извлекаем**, действует политика
доверия (ниже).

### Что извлечено (2026-06-13)

- `pennant-development` → `skills/php/pennant-development/` (static `.md`,
  stable API, аналога в реестре не было). upstream.json strategy=notify.

### Что НЕ извлекаем

- **Версионное** (`laravel/11|12`, `php/8.x`, `pest/3|4`, `inertia-*/1|2`,
  `livewire/2|3|4`, `tailwindcss/3|4`) — рендерится под фактические версии
  пакетов; импорт заморозил бы версию и создал третью копию истины
  (vendor → реестр → проект).
- **Blade-шаблоны** (`folio-routing`, `volt-development`, `mcp-development`,
  гайдлайны `foundation`/`php-core`/`enforce-tests` `*.blade.php`) — требуют
  render-контекста Boost. Ручная de-Blade-переработка возможна, но это уже
  авторинг нового скилла, а не извлечение; делается отдельно по запросу.
- **Вне наших стеков** (`fluxui-*` — платный UI Flux).

## Политика доверия (для невыносимого)

В Boost-проектах версионно-специфичные и Blade-связанные темы отдаём Boost,
наш реестр **дополняет** его архитектурой, структурой и практиками. Конфликт
правил решается приоритетом: проект > Boost > реестр.

## Связи с реестром

- Матрица доверия и вердикты по нашим скиллам — [docs/boost-compatibility.md](../docs/boost-compatibility.md)
- Приоритет источников (проект > Boost > реестр) — [docs/routing.md](../docs/routing.md)
- Интеграция хаба с `boost:update` — `scripts/generate-hub.sh` (режим Boost пишет
  `.ai/guidelines/swissknifeman-hub.md`)
- Устройство SSOT вокруг Boost — скилл `general/skills-ssot`
- Удалённые дубли (2026-06-12): `php/livewire`, `frontend/tailwindcss`,
  `general/mcp-development`; помеченные complementary: `php/laravel-best-practices`,
  `frontend/inertia-vue`, `frontend/wayfinder`, `php/filament`, `php/medialibrary`,
  `php/laravel-testing`
- Извлечено в реестр (2026-06-13): `php/pennant-development` (static `.md`, notify)
