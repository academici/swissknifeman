# WendellAdriel/laravel-expressive

- **URL:** https://github.com/WendellAdriel/laravel-expressive/tree/main/.agents/skills
- **Статус:** imported
- **Проверено:** 2026-06-12

Laravel-пакет с собственной папкой `.agents/skills/` — живой пример того, как
пакет публикует скиллы для агентов. 8 скиллов по разработке пакетов (часто нужны).

## Что взято

Все 8 скиллов импортированы в bucket `php` плоскими папками с префиксом
`laravel-` (вложение SKILL.md внутрь существующего `laravel-packages/SKILL.md`
невидимо для plugin discovery — см. коммит d6bc0f9 про docker):

| upstream `.agents/skills/` | наш скилл (`skills/php/`) |
|---|---|
| `package-compatibility`    | `laravel-package-compatibility` |
| `package-docs`             | `laravel-package-docs` |
| `package-generate-skill`   | `laravel-package-generate-skill` |
| `package-release`          | `laravel-package-release` |
| `package-scaffold`         | `laravel-package-scaffold` |
| `package-service-provider` | `laravel-package-service-provider` |
| `package-testing`          | `laravel-package-testing` |
| `skeleton-development` (name `expressive-development`) | `laravel-package-expressive` |

Провенанс каждого — в `upstream.json` рядом со SKILL.md (`strategy: notify`,
не авто-заменять). Bucket-frontmatter добавлен поверх оригинального тела.

## Связи

- Пересекается с `oss-dev/release-engineering` (релизы) и нашим
  `generate-skill/` (паттерн package-generate-skill) — оставлено отдельно как
  package-specific.
