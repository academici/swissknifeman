# laravel/boost

- **URL:** https://github.com/laravel/boost
- **Packagist:** https://packagist.org/packages/laravel/boost
- **Документация:** https://laravel.com/docs/boost
- **Статус:** trusted (не импортируем — доверяем на месте)
- **Проверено:** 2026-06-12

**Upstream-отслеживание:** `skills/php/laravel-best-practices/upstream.json`
(strategy=notify, 21 файл: SKILL.md + 20 правил `rules/*.md` ↔ наши `references/*.md`) —
CI/`./scripts/update-upstreams.sh --check` сообщит, когда Boost изменит правила;
слияние — вручную.

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

## Почему НЕ импортируем

Скиллы Boost — Blade-шаблоны с версионной логикой (Laravel 11/12, Pest 3/4,
Inertia 1/2, Livewire 2/3/4, Tailwind 3/4): они рендерятся под фактические версии
пакетов проекта. Импорт в реестр заморозил бы их и создал третью копию истины
(vendor → реестр → проект). Вместо импорта — **политика доверия**: в Boost-проектах
версионно-специфичные темы отдаём Boost, наш реестр дополняет его архитектурой
и практиками.

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
