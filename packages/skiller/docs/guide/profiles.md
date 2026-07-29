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

## Бюджет листинга (P3.5, D74/D76)

Claude Code роняет описания реже вызываемых скиллов, когда листинг превышает
бюджет — ≈1% контекстного окна в ТОКЕНАХ, переведённых в символы коэффициентом
×3: на 1M-модели это **30 000** символов, на 200K — **6 000** (не 10 000/2 000,
как считал первый заход — репо-факт `claude --debug-file` WARN «47021 chars >
30000 budget», см. `plans/archive/2026.07.25-ECO-OPT/findings/P3.1-listing-diagnosis.md`
§0). Таблица — символы активного набора профиля (бакеты + курируемый `core@`,
дедуп по каталогу), снято 2026-07-28 командой `skiller budget` того же пути,
которым собирается connect-канал:

| Профиль | Скиллов (+`core@`) | Симв | ×бюджет 1M (30 000) | ×бюджет 200K (6 000) |
|:--|--:|--:|--:|--:|
| `blender` | 30 | 6 884 | 0,23 ✅ | 1,15 ❌ |
| `dart-flutter` | 44 | 9 762 | 0,33 ✅ | 1,63 ❌ |
| `node-package` | 46 | 9 519 | 0,32 ✅ | 1,59 ❌ |
| `python-backend` | 62 | 12 175 | 0,41 ✅ | 2,03 ❌ |
| `obsidian-vault` | 66 | 12 177 | 0,41 ✅ | 2,03 ❌ |
| `php-package` | 76 | 15 753 | 0,53 ✅ | 2,63 ❌ |
| `node-frontend` | 79 | 17 021 | 0,57 ✅ | 2,84 ❌ |
| `laravel-project` | 86 | 17 293 | 0,58 ✅ | 2,88 ❌ |
| `platform-service` | 110 | 23 003 | 0,77 ✅ | 3,83 ❌ |
| `standalone` | 227 | 49 458 | **1,65** ❌ | 8,24 ❌ |

**Девять из десяти профилей укладываются в реальный бюджет 1M-модели** (вывод
меняется на противоположный тому, что первым заходом считал `research/20`
§1.1 по неверной единице — там же корень расхождения). **На 200K-модели
переполняют все десять** — это НЕ гейтится тестом (`test_profile_listing_budget.py`
печатает предупреждение по 200K, а не падает: обнулить `blender` до 2 000
симв невозможно без потери смысла профиля).

**`standalone` — именованное исключение, не дефект.** Профиль означает «маркеров
стека нет — поставь весь реестр»; сузить его состав значило бы перестать быть
`standalone`. Он остаётся переполненным СОЗНАТЕЛЬНО (1,65× бюджета 1M) —
названное ограничение (Implementation Rules P3.5), а не то, что тест должен
скрывать. При явном переполнении листинга на `standalone`-проекте — рычаг №2/№3
ниже (снять избыточные бакеты через `--profile`/`--buckets` явно вместо
`standalone`, либо приёмы из карточки рекомендаций).

### Карточка рекомендаций для чужих конфигов

Наш тулинг НЕ пишет `enabledPlugins`/`skillOverrides`/`skillListingBudgetFraction`
чужих проектов (это делает `skiller connect`/`update` по команде владельца, не
автоматика). Если `claude --debug` вашего проекта печатает `Skill listing over
budget`, доступные рычаги — по цене, от дешёвого к дорогому:

1. **Сузить набор** — меньше бакетов/пресетов (`skiller connect --buckets …`),
   отключить неиспользуемые плагины (`skiller status` печатает 0-usage
   кандидатов через `/doctor`).
2. **`skillOverrides: "name-only"`** в `.claude/settings.json` — для длинного
   хвоста редко вызываемых скиллов: листинг несёт имя без описания
   (описание не резидентно, но скилл всё ещё виден по имени):
   ```json
   {
     "skillOverrides": {
       "<bucket-или-скилл>": { "descriptionMode": "name-only" }
     }
   }
   ```
3. **`skillListingBudgetFraction`** — поднять долю контекста под листинг (честно:
   резидентный ⊕ tier-0 растёт вместе с ней):
   ```json
   { "skillListingBudgetFraction": 0.02 }
   ```

Оба ключа пишутся ВАМИ в конфиг проекта — `skiller` их не генерирует и не правит.

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
