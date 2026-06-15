# Аудит практик из проектов пользователя (2026-06)

> Исчерпывающий разбор наработок в боевых проектах с целью пополнить реестр
> `swissknifeman`. Документ — источник бэклога: всё, что здесь помечено как
> NEW/EXTEND, либо уже заведено в этот заход, либо ждёт своей очереди.
> Сверка проводилась с **живым** реестром (`skills/`, `skills.json`), а не по
> памяти — vendored-копии в проектах за открытия не считаются.

## 1. Резюме и метод

Цель захода — выгрести из локальных проектов те практики, которые ещё не стали
скиллами реестра, отделив их от уже вендоренных копий (которые лишь выглядят как
наработки проекта, а на деле — установленные из реестра скиллы).

**Метод.** Шесть Explore-проходов в два раунда:

- **Раунд 1** — три «близнецовых» Laravel + Inertia/Vue-проекта (Agelto, FlexCRM,
  Sova): стек-фингерпринты (`composer.json`/`package.json`/lock-файлы),
  `.ai/skills` (вендор), `.cursor/rules`, фронтовая структура `resources/js`,
  enum-атрибуты, авторизация, тестовая изоляция, CI.
- **Раунд 2** — иные стеки (unbox/Livewire, art-kombinat/Nuxt, diabox/Blender) и
  PHP-монорепо (azguard, botkit, doc-vault) — на предмет уникальных практик.

**Сверка с реестром.** Каждый кандидат проверялся на присутствие в `skills/` и
`skills.json`. Ключевой результат сверки: ни одного из десяти приоритетных
кандидатов в реестре нет (`tailwind*`, `eslint*`, `*type-sync*`,
`*isolation*`, `attribute-authorization`, `db-test-preflight`, `writing-style`,
`naive-ui`, `reka-ui` — пусто; есть только `enum-attributes` и
`node-pnpm-preflight`, которые относятся к EXTEND/смежным). То есть копии
скиллов в `.ai/skills` проектов — действительно вендор реестра, а не пробелы.

## 2. Стек-фингерпринты проектов

| Проект | Backend | Filament | Фронт | UI-kit | CSS | Менеджер | Тулинг/линт | Realtime | Особое |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| **Agelto** | Laravel 12 (php 8.5) | Filament 5 | Inertia + Vue 3 | reka-ui + CVA + Lucide | Tailwind v4 | **npm** (`yarn.lock` присутствует, но активен npm-стиль) | eslint flat (`@vue/eslint-config-typescript`) + prettier | — | модульный монолит (`nwidart/laravel-modules`), `useAppearance` dark-mode, wayfinder, медиатека Pro |
| **FlexCRM** | Laravel 13 (php 8.5) | Filament 5 (`azguard/filament`) | Inertia 3 + Vue 3 | Naive UI + Tiptap (collab/yjs) | Tailwind v4 | **npm** (`package-lock.json` — см. поправку §2.1) | eslint flat **@stylistic** + prettier (`tailwindcss`+`organize-imports`) + commitlint/husky | Reverb + laravel-echo + pusher-js | `laravel-typescript-transformer` + кастомный `EnumConstWriter`, FilePond, strict TS, `useAppearance` |
| **Sova** | Laravel 13 (php 8.3) | Filament 5 (Shield) | Inertia 3 + Vue 3 | Naive UI | Tailwind v4 (+ admin-конфиг) | **pnpm** | eslint flat (CJS) с границами импортов + commitlint/husky | Reverb + laravel-echo (`useEcho`) | `features/<домен>`, enum `#[Label]/#[Priority]/#[TypeScript]`, `#[CheckPermission]` attribute-auth, test bootstrap isolation guard, Spatie Settings/Health, GitLab CI + coverage-gate |
| **unbox** | Laravel 12 (php 8.4) | Filament 4 | **Livewire** (Flux/Volt) | Flux | Tailwind v4 | npm | — (`.cursor/rules`: livewire-blade, laravel-boost) | Reverb + laravel-echo | модульный монолит (`nwidart` + `laravel-modules-livewire`), Playwright, PowerGrid, wallet, map-picker |
| **art-kombinat/frontend** | (отдельный backend) | — | **Nuxt 4** + Vue 3 | Bootstrap 5 / SCSS | — | **yarn** | — | — | Pinia, vue-i18n, FilePond, GSAP/анимации, sitemap/jsonld SEO |
| **diabox** | — | — | — | — | — | venv (pip) | — | — | **Python + Blender 5** параметрическое 3D (FDM/SLA), `ai/` → `CLAUDE.md` генератор, MCP |
| **erp-sdk** | — | — | — | — | — | melos | — | — | **Dart/Flutter** SDK (drift/riverpod) — вне реестра |
| **azguard / botkit / doc-vault** | PHP-пакеты | — | — | — | — | composer | multi-testsuite (azguard: Arch/Feature/Context/Unit/UnitFilament); botkit: `infection.json5` | — | open-source монорепо |

### 2.1. Поправки к исходным фингерпринтам

Две детали по факту разошлись с входными данными — фиксирую, чтобы будущие скиллы
не унаследовали ошибку:

- **FlexCRM использует npm, а не pnpm.** В корне лежит `package-lock.json`
  (`/home/vostrikov/projects/flexcrm/package-lock.json`), pnpm-lock отсутствует.
  Это влияет на выбор preflight-скилла (`node-npm-preflight` вендорен в проекте,
  не `node-pnpm-preflight`).
- **Agelto — npm-стиль**, хотя в репозитории присутствует `yarn.lock`; вендорен
  `node-yarn-preflight`. Уверенность ниже, чем по FlexCRM; для скилла это не
  критично (Tailwind/ESLint от менеджера пакетов не зависят).

## 3. Поправка vendored-vs-local: что отбросили и почему

Проекты Agelto/FlexCRM/Sova **вендорят** скиллы реестра в `.ai/skills` (и часть в
`.claude/skills`). Эти копии — установленный реестр, а не наработки проекта,
поэтому за открытия они не считаются. Отброшено как «уже в реестре»:

| Категория | Что в `.ai/skills` проектов | Соответствие в реестре |
|:---|:---|:---|
| PHP-ядро | `laravel`, `laravel-structure`, `laravel-testing`, `laravel-permissions`, `laravel-broadcasting`, `php-patterns`, `repositories`, `named-arguments`, `static-analysis`, `dependency-injection`, `database` | `php/*` (одноимённые) |
| Авторские ранее | `pao`, `pennant-development` | `php/pao`, `php/pennant-development` |
| Filament/Inertia | `filament(-development)`, `inertia-vue(-development)`, `medialibrary` | `php/filament`, `frontend/inertia-vue`, `php/medialibrary` |
| Docker/CI | `docker(-dev-prod/php/postgres/services/vite)`, `gitops`, `ci-cd`, `makefile` | `devops/*` |
| System/общее | `shared-memory`, `cross-project-coordinator`, `local-topology`, `project-map`, `session-handoff`, `skills-ssot`, `context-economy`, `git-commit-rules` | `system/*`, `general/*` |

**Важный нюанс по `writing-style`.** Скилл `writing-style` вендорен в FlexCRM и
Sova (`/home/vostrikov/projects/flexcrm/.ai/skills/writing-style/SKILL.md`), но в
реестре его **нет** (`skills/general/` им не содержит). То есть это вендор-копия
из ещё-не-закоммиченного скилла либо из внешнего источника — реальный пробел, а
не отброс. Включён в §4 как NEW.

**Настоящие пробелы** (есть в проектах, нет в реестре): отдельный Tailwind,
Livewire, Pest, dark-mode, Naive UI, reka-ui, backend→TS type-sync, enum
`#[TypeScript]`, attribute-authorization, ESLint-flat-config-тулинг,
test-isolation, db-test-preflight, writing-style.

## 4. Авторено в этот заход (10)

Десять скиллов, добытых и закоммиченных в реестр в текущем заходе. Для каждого —
суть, эвиденс (пути) и тип (NEW — нового бакета/скилла; EXTEND — дополнение
существующего).

### Frontend

**1. `frontend/tailwind-conventions` — NEW.**
Конвенции Tailwind **v4**: `@import 'tailwindcss'` вместо конфигов JS,
`@theme inline { --color-* }` для дизайн-токенов, `@custom-variant dark`,
`@source` для путей вне дерева, `tailwind-merge`/`clsx` для слияния классов,
порядок классов через `prettier-plugin-tailwindcss`.
Эвиденс: `/home/vostrikov/projects/agelto/agelto/resources/css/app.css`
(`@custom-variant dark (&:is(.dark *))`, `@theme inline`, `@source`),
зависимости `tailwindcss ^4`, `tw-animate-css`, `tailwind-merge` во всех трёх
Inertia-проектах; Sova ведёт два конфига (`tailwind.config.js` +
`tailwind-admin.config.js`).

**2. `frontend/inertia-vue` — EXTEND (per-feature `features/`).**
Базовый скилл уже описывает слой `features/` и доменные подпапки. Расширение —
паттерн Sova: внутри `features/<домен>/` своя структура
`{actions, composables, model}` (вертикальный срез фичи) + **ESLint-границы
импортов**, запрещающие доменным Vue-компонентам тянуть wayfinder напрямую в
обход actions/composables-слоя.
Эвиденс:
`/home/vostrikov/sibintek/projects/sova/resources/js/features/ticket/{actions,composables,model}`
(18 composables: `useTicketRealtime`, `useTicketForm`, `useTicketPrecognition`…),
правила `no-restricted-imports`/`no-restricted-syntax` в
`/home/vostrikov/sibintek/projects/sova/eslint.config.cjs`.

**3. `frontend/backend-type-sync` — NEW.**
Генерация TS-типов из PHP через `spatie/laravel-typescript-transformer`: DTO и
enum с `#[TypeScript]`, `default_type_replacements` (Carbon → `string`), и —
ключевое — **кастомный writer**, который пишет и `.d.ts` (через
`GlobalNamespaceWriter`), и runtime-enum в `enums.ts`, плюс шапку-предупреждение
«сгенерировано».
Эвиденс: `/home/vostrikov/projects/flexcrm/config/typescript-transformer.php`,
`/home/vostrikov/projects/flexcrm/app/TypeScript/EnumConstWriter.php`,
`/home/vostrikov/projects/flexcrm/app/Providers/TypeScriptTransformerServiceProvider.php`;
в Sova — `spatie/laravel-typescript-transformer ^3` + `#[TypeScript]`-enum'ы.

**4. `frontend/eslint-flat-config` — NEW.**
Тулинг ESLint flat-config для Vue+TS: `defineConfigWithVueTs`,
`@stylistic/eslint-plugin` (`brace-style 1tbs`, `padding-line-between-statements`
вокруг управляющих конструкций), `import/order` с алфавитной сортировкой и
группами, `consistent-type-imports` (`prefer: type-imports`), интеграция с
prettier через `eslint-config-prettier/flat`, игнор генерируемых каталогов
(`actions/`, `routes/`, `wayfinder/`, `components/ui/`).
Эвиденс: `/home/vostrikov/projects/flexcrm/eslint.config.js` (полная flat-цепочка
с @stylistic), `/home/vostrikov/sibintek/projects/sova/eslint.config.cjs`
(CJS-вариант с границами импортов).

### PHP

**5. `php/test-isolation-guard` — NEW.**
Защита тестовой БД от боевой на уровне bootstrap: `tests/bootstrap.php`
дублирует изоляцию (`DB_DATABASE=*_test`, `CACHE_STORE=array`,
`SESSION_DRIVER=array`, `QUEUE_CONNECTION=sync`, `MEDIA_DISK=media-test`) в
`$_SERVER`/`$_ENV`/`putenv` **до** автозагрузчика, потому что Laravel/Dotenv
читает `$_SERVER` первым (`ServerConstAdapter`) и Docker впрыскивает туда `DB_*`.
В `phpunit.xml` — `force="true"` на тех же ключах + комментарии о порядке чтения.
Эвиденс: `/home/vostrikov/sibintek/projects/sova/tests/bootstrap.php`,
`/home/vostrikov/sibintek/projects/sova/phpunit.xml` (строки 21–43, `<server>` +
`<env force>`).

**6. `php/attribute-authorization` — NEW.**
Декларативная авторизация контроллеров через PHP-атрибут + middleware:
`#[CheckPermission(permission: Enum, arguments: ['ticket'])]` (`IS_REPEATABLE`,
`final readonly`), middleware `CheckAccess` через `ReflectionMethod` достаёт
атрибуты метода роута, резолвит route-параметры в аргументы и зовёт
`Gate::allows(ability, arguments)` с `abort_if`. Permission — UnitEnum, не
строка.
Эвиденс: `/home/vostrikov/sibintek/projects/sova/app/Attributes/CheckPermission.php`,
`/home/vostrikov/sibintek/projects/sova/app/Http/Middleware/CheckAccess.php`,
применение — `app/Http/Controllers/Ticket/TicketsController.php` (6+ методов).

**7. `php/enum-attributes` — EXTEND (`#[TypeScript]` + Filament + per-domain оси).**
Базовый скилл покрывает `#[Label]/#[Color]/#[Description]` + Concern-трейты +
reflection-резолвер + `emreyarligan/enum-concern`. Расширение из Sova: совмещение
с `Spatie\...\Attributes\TypeScript` (`#[TypeScript]` над enum → выгрузка во
фронт), `implements HasLabel` для Filament, доменные оси `#[Priority(forTicket: N)]`
с числовым приоритетом ролей.
Эвиденс: `/home/vostrikov/sibintek/projects/sova/app/Enums/User/UserRole.php`
(`#[TypeScript]` + `#[Label]` + `#[Priority(forTicket:…)]` + `HasLabel`),
`app/Attributes/Common/Label.php`, `app/Attributes/Ticket/Priority.php`,
`app/Enums/Meeting/MeetingAgendaForm.php`.

**8. `php/modular-architecture` — EXTEND (`nwidart/laravel-modules`).**
Базовый скилл описывает Modular Monolith на `app/Modules`. Расширение — реальный
пакет `nwidart/laravel-modules`: каталог `Modules/`, `modules_statuses.json`,
интеграция с Livewire-модулями (`mhmiton/laravel-modules-livewire`),
правило `.cursor/rules/module-development.mdc`.
Эвиденс: Agelto — `Modules/`, `modules_statuses.json`, `nwidart/laravel-modules`
в composer, `/home/vostrikov/projects/agelto/agelto/.cursor/rules/module-development.mdc`;
unbox — `nwidart/laravel-modules ^12` + `mhmiton/laravel-modules-livewire ^5.2`.

### General

**9. `general/writing-style` — NEW.**
Живой язык комментариев и коммитов: писать о причине, а не пересказывать код;
настоящее/прошедшее время вместо канцелярита; заголовок коммита — завершённое
действие, в body причина и эффект. Формат Conventional Commits — в
`git-commit-rules`, здесь — тон и язык. Связан с проектным правилом «русский по
умолчанию».
Эвиденс (вендор-копия, но не в реестре):
`/home/vostrikov/projects/flexcrm/.ai/skills/writing-style/SKILL.md`,
`/home/vostrikov/sibintek/projects/sova/.ai/skills/writing-style/`;
проектное правило `/home/vostrikov/projects/flexcrm/.cursor/rules/russian-language-priority.mdc`.

### DevOps

**10. `devops/db-test-preflight` — NEW.**
Pre-flight перед прогоном тестов: проверить доступность среды
(`docker compose ps`), запускать тесты тем же способом, что и приложение
(хост/контейнер), убедиться что тестовая БД создана
(`make db-create-test` / init-скрипты `docker/postgres/init/`), дождаться
готовности Postgres (`pg_isready`), и **не путать** тестовую БД (`*_test`) с
рабочей — мутации вне `--env=testing` пишут в dev-базу.
Эвиденс: `/home/vostrikov/projects/flexcrm/.cursor/rules/test-preflight-docker-db.mdc`
(один-в-один воспроизводится в Sova), `docker/postgres/` init-скрипты,
`make db-create-test`. Дополняет devops-связку с CI coverage-gate (см. §7).

## 5. Отложенный бэклог (verified, ниже уверенность / 1 проект)

Практики подтверждены эвиденсом, но встречаются в одном проекте или требуют
больше обобщения, прежде чем стать скиллом реестра. По одной строке с источником:

> **Граница с Laravel Boost.** `livewire-blade-attributes` и любые будущие
> Tailwind/Livewire/MCP-кандидаты создавать ТОЛЬКО как complementary-дельту с
> строкой-границей «Laravel Boost: …» в `## Контекст` — версионные основы остаются
> за Boost. Удалённые дубли (`php/livewire`, `frontend/tailwindcss`,
> `general/mcp-development`) не воссоздавать. См. `docs/boost-compatibility.md`.

| Кандидат | Бакет | Источник-эвиденс |
|:---|:---|:---|
| `reka-ui-cva-primitives` | frontend | Agelto `resources/js/components/ui/*` (20 примитивов: button/dialog/sidebar…) + CVA в `*/index.ts` |
| `naive-ui-theming` | frontend | FlexCRM `resources/js/config/naive-ui.ts` (`GlobalThemeOverrides`), подключение в `app.ts`; Naive UI в FlexCRM/Sova |
| `dark-mode-appearance` (composable `useAppearance`) | frontend | Agelto/FlexCRM `resources/js/composables/useAppearance.ts` + `components/AppearanceTabs.vue` + `pages/settings/Appearance.vue` |
| `echo-reverb-client` (composable) | frontend | Sova `resources/js/composables/useEcho.ts` (runtime-конфиг Reverb), `events/adapters/echo-*.ts`, тесты `tests/composables/useEcho.test.ts` |
| `lucide-dynamic-icon` | frontend | Agelto `resources/js/components/Icon.vue` (динамический выбор `lucide-vue-next`) |
| `filepond-upload` | frontend | FlexCRM (`vue-filepond`, `filepond-plugin-*`), Sova `components/forms/VueFilePond.ts` + `composables/shared/useFileUpload.ts`, art-kombinat |
| `livewire-blade-attributes` | php/frontend | unbox `.cursor/rules/livewire-blade.mdc` (запрет `@if`/`@js()` в атрибутах, `ComponentAttributeBag`) |
| `playwright-e2e` | quality/devops | unbox `package.json` (`playwright ^1.57`), `tests/Browser`, `MEDIA_ISOLATION.md` |
| `health-check-suite` | php/operator | Sova `app/Health/Checks/*` (Reverb TCP/client, Queue, Scheduler heartbeat, Disk/Storage write, Cache, DB), `config/health.php`, `tests/Feature/Health/` |
| `spatie-laravel-settings` (+ Filament UI-binding) | php | Sova `app/Settings/**` (`WebsocketClientSettings`, `Ticket/Deadlines`) + `app/Filament/Pages/Settings/Manage*` |
| `monorepo-mutation-testing` | quality/php | botkit `infection.json5`; azguard multi-testsuite (`Arch/Feature/Context/Unit/UnitFilament`) |
| `blender-parametric-config` | **blender** (новый профиль/расширение) | diabox `config/`, `lib/{spline,geometry}.py`, `ai/`→`CLAUDE.md` генератор (`scripts/ai_generate_rules.py`), `CURRENT_MODEL`/`revolve_profile`/`apply_bool` |

## 6. Вне охвата

- **erp-sdk** (`/home/vostrikov/projects/packages/erp-sdk`) — Dart/Flutter SDK
  (melos/drift/riverpod). В реестре нет Dart-бакета; практики не переносимы в
  PHP/JS/Python-каркас. Кандидат на отдельный профиль, если Dart-проектов станет
  больше одного.
- **axioma-studio** — скелет проекта, содержательного кода для извлечения практик
  пока нет.

## 7. Лучшие практики, замеченные, но не ставшие скиллом

Наблюдения, которые ценны как ориентир, но либо слишком проектно-специфичны, либо
уже частично покрыты смежными скиллами (`ci-cd`, `makefile`, `laravel-testing`):

- **CI coverage-gate.** Sova `.gitlab-ci.yml` + `scripts/check-php-coverage-gate.php`:
  жёсткий порог покрытия (`COVERAGE_GATE_MODE=hard`, `COVERAGE_GLOBAL_MIN=70`,
  `COVERAGE_CRITICAL_MIN=55`) по Clover после `php artisan test --coverage`, с
  отдельным минимумом для критичных директорий. Шаблон полного `.php-base`
  (сборка PHP-расширений, `pg_isready`-ожидание, миграции) — готовый референс для
  EXTEND `devops/ci-cd`.
- **Pest-композиция и multi-testsuite.** azguard разбивает на
  `Arch/Feature/Context/Unit/UnitFilament` — арх-тесты как отдельный suite; это
  усиление `quality/test-strategy`.
- **`ShouldDispatchAfterCommit` на доменных событиях.** Sova `app/Events/Ticket/*`
  (`Created`, `StatusChanged`, `Published`, `ParticipantsChanged`) —
  broadcast/листенеры срабатывают только после коммита транзакции, иначе слушатель
  увидит несохранённое состояние. Кандидат в `php/laravel-broadcasting` (EXTEND).
- **Spatie Settings ↔ Filament UI-binding.** Sova связывает
  `app/Settings/**` (typed settings-классы) с Filament-страницами
  `Manage*Settings` — рантайм-конфиг (например, Reverb) редактируется из админки и
  отдаётся во фронт через DTO. См. §5 `spatie-laravel-settings`.
- **Makefile dev/prod как единая точка входа.** Все Inertia-проекты несут
  `Makefile` + `docker-compose.{yml,prod.yml,override.example.yml}`; команды
  `make db-create-test` и пр. — основа для проектного onboarding. Частично
  покрыто `devops/makefile` и `devops/docker-dev-prod`.
- **Conventional Commits + commitlint/husky.** FlexCRM/Sova несут
  `commitlint.config.mjs` + husky-хуки + русскоязычные коммиты — связка
  `git-commit-rules` × `writing-style` × `russian-language-priority`.

---

> Источник истины по составу реестра — `skills.json` и каталог `skills/`.
> Все пути-эвиденс в документе абсолютные и проверены на момент аудита (2026-06).
