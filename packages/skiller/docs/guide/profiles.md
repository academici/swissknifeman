# Профили и автодетект

Профиль — это соответствие «тип проекта → набор bucket-ов». Профили лежат в
`profiles/*.json`, по одному файлу на тип проекта.

## Встроенные профили

| Профиль | Автодетект | Bucket-ы (дефолт) |
|---|---|---|
| `obsidian-vault` | `.obsidian/` | system, architect, pm, founder, operator, roles, finance, legal, marketing, sales, research, creative |
| `laravel-project` | `artisan` + `composer.json` | system, architect, **php** (ядро), laravel-testing, laravel-auth, laravel-data-layer, devops, quality, operator |
| `php-package` | `composer.json` без `artisan` | system, oss-dev, php, php-packages, laravel-testing, quality, devops |
| `node-frontend` | `package.json` (Vue/Vite) | system, architect, **frontend** (ядро), frontend-vue, frontend-vite, frontend-linting, frontend-tailwind, quality, devops |
| `standalone` | нет маркеров | все + generate-skill |

> **`php` и `frontend` разбиты на тонкие бакеты** (Filament/Livewire/Nuxt/Naive-UI и пр. — отдельные
> плагины, не тянутся по умолчанию). PHP: ядро `php` + `laravel-{testing,filament,livewire,data-layer,
> auth,architecture,extras}` (+ `php-packages`). Frontend: ядро `frontend` + `frontend-{vue,nuxt,tailwind,
> naive-ui,reka,vite,linting,animations,figma,wayfinder,backend}`. Профиль даёт линяный дефолт; остальное
> подключается точечно — отдельным бакетом или [пресетом](./presets) (`laravel-admin`, `vue-spa`, …).

## Формат профиля

```json
{
  "name": "laravel-project",
  "description": "Large Laravel application development",
  "buckets": ["system", "architect", "php", "laravel-testing", "laravel-auth", "laravel-data-layer", "devops", "quality", "operator"],
  "include_meta": false
}
```

- `buckets` — какие bucket-ы ставить;
- `include_meta` — включать ли мета-скилл `generate-skill` (нужен только там,
  где вы создаёте новые скиллы, обычно `false`).

## Как работает автодетект

`skiller vendor` (как и `connect`) проверяет маркеры в целевом каталоге
в порядке специфичности:

1. `.obsidian/` → `obsidian-vault`
2. `artisan` + `composer.json` → `laravel-project`
3. `composer.json` без `artisan` → `php-package`
4. ничего не найдено → `standalone`

Переопределить можно флагом `--profile`, списком `--buckets` или файлом
[`.swissknife.json`](./installation#фиксация-конфигурации-swissknife-json).

## Свой профиль

Добавьте `profiles/<имя>.json` по формату выше — он сразу станет доступен через
`--profile <имя>`. Валидатор (`./scripts/validate.sh`) проверит, что все
указанные bucket-ы существуют.

::: tip Профили и permissions
Той же логикой автодетекта пользуется
[`apply-permissions.sh`](/harness/configs/claude-permissions#скрипт-apply-permissions-sh) —
он подбирает пресеты разрешений по маркерам стека (`artisan`, `package.json`,
`pyproject.toml`, `Dockerfile`).
:::
