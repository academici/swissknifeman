# Профили и автодетект

Профиль — это соответствие «тип проекта → набор bucket-ов». Профили лежат в
`profiles/*.json`, по одному файлу на тип проекта.

## Встроенные профили

| Профиль | Автодетект | Bucket-ы |
|---|---|---|
| `obsidian-vault` | `.obsidian/` | architect, pm, founder, operator, roles, imported |
| `laravel-project` | `artisan` + `composer.json` | architect, php, devops, quality, operator |
| `php-package` | `composer.json` без `artisan` | oss-dev, php, quality, devops |
| `standalone` | нет маркеров | все + generate-skill |

## Формат профиля

```json
{
  "name": "laravel-project",
  "description": "Large Laravel application development",
  "buckets": ["architect", "php", "devops", "quality", "operator"],
  "include_meta": false
}
```

- `buckets` — какие bucket-ы ставить;
- `include_meta` — включать ли мета-скилл `generate-skill` (нужен только там,
  где вы создаёте новые скиллы, обычно `false`).

## Как работает автодетект

`swissknifeman vendor` (как и `connect`) проверяет маркеры в целевом каталоге
в порядке специфичности:

1. `.obsidian/` → `obsidian-vault`
2. `artisan` + `composer.json` → `laravel-project`
3. `composer.json` без `artisan` → `php-package`
4. ничего не найдено → `standalone`

Переопределить можно флагом `--profile`, списком `--buckets` или файлом
[`.swissknife.json`](/guide/installation#фиксация-конфигурации-swissknife-json).

## Свой профиль

Добавьте `profiles/<имя>.json` по формату выше — он сразу станет доступен через
`--profile <имя>`. Валидатор (`./scripts/validate.sh`) проверит, что все
указанные bucket-ы существуют.

::: tip Профили и permissions
Той же логикой автодетекта пользуется
[`apply-permissions.sh`](/configs/claude-permissions#скрипт-apply-permissions-sh) —
он подбирает пресеты разрешений по маркерам стека (`artisan`, `package.json`,
`pyproject.toml`, `Dockerfile`).
:::
