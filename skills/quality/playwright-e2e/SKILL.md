---
name: playwright-e2e
bucket: quality
version: 0.1.0
description: "Браузерный E2E на Playwright для веб-приложения (агностично к Vue/Inertia/Livewire): playwright.config с webServer и projects, авторизация одним логином через storageState, конвенция data-testid, изоляция данных/медиа между прогонами, запуск в CI. Активировать когда добавляешь/чинишь end-to-end сценарий через реальный браузер, настраиваешь playwright.config или storageState-логин."
risk: write
persona: oss-dev
tags: [playwright, e2e, browser, testing, storage-state, ci, quality]
requires: []
produces_for: []
outputs: []
snippets: [playwright.config.ts, example.spec.ts, ci-step.yml]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Playwright E2E

## Контекст

Браузерные end-to-end тесты на Playwright: реальный браузер ходит по приложению как пользователь — заполняет формы, кликает, ждёт навигацию, проверяет видимый текст и DOM. Стек фронтенда не важен (Vue/Inertia, Livewire, Blade, любой SPA): Playwright видит итоговый HTML.

**Когда активировать:**
- добавляешь или чинишь end-to-end сценарий, который должен пройти через настоящий браузер (регистрация, оформление заказа, загрузка файла, многошаговая форма);
- настраиваешь `playwright.config.*`: projects/browsers, `baseURL`, `webServer`, авторизацию через `storageState`;
- видишь флейки из-за того, что прогоны делят БД/медиа/загрузки, и нужно изолировать данные между запусками.

**Граница (что НЕ здесь):**
- unit/компонентные тесты фронта (jsdom, монтирование компонента) — скилл `frontend/vitest`;
- выбор уровня тестов, пирамида, coverage-политика, что вообще покрывать E2E — скилл `quality/test-strategy`;
- здесь только то, что бегает в **реальном браузере** через Playwright.

**Laravel Boost**: в Laravel-проектах с установленным Boost браузерные/Livewire-тесты и конвенции тестирования ведёт его встроенный скилл — он версионно-специфичен и обновляется с пакетом; не дублируй и не переопределяй его рекомендации. Этот скилл — про нативный TS-стек `@playwright/test` (для проектов без Boost или там, где E2E вынесены в отдельный JS/TS-слой). Пакет: https://github.com/laravel/boost (скиллы — `vendor/laravel/boost/.ai/`).

## Алгоритм

1. **Найди, как E2E уже устроены в проекте.** Прежде чем создавать конфиг, проверь существующее:
   ```bash
   ls playwright.config.* e2e/ tests/e2e/ tests/Browser/ 2>/dev/null
   grep -RIl --include='*.ts' --include='*.js' -e 'storageState' -e '@playwright/test' -e 'data-testid' .
   grep -E '"(test:e2e|e2e|pw)"' package.json
   ```
   Если конфиг/спеки уже есть — продолжай их конвенцию (расположение спеков, имена projects, селекторы), не вводи параллельную.
   Учти: в Laravel «браузерные» тесты иногда живут как Pest/Dusk-обёртки над Playwright (`tests/Browser/*.php`) — это тот же движок, но через PHP API; данный скилл описывает нативный TS-стек `@playwright/test`.

2. **Установи зависимость и браузеры** (если ещё нет):
   ```bash
   npm i -D @playwright/test
   npx playwright install --with-deps chromium
   ```

3. **Опиши `playwright.config.ts`** (см. `snippets/playwright.config.ts`):
   - `testDir` — каталог спеков (`./e2e` или `./tests/e2e`);
   - `baseURL` — берётся из env (`E2E_BASE_URL`) с дефолтом на локальный адрес; в спеках ходи относительными путями `page.goto('/...')`;
   - `webServer` — команда, которая поднимает приложение перед прогоном (`url`, `reuseExistingServer: !process.env.CI`), чтобы локально не запускать сервер вручную, а в CI он стартовал сам;
   - `projects` — браузеры (минимум `chromium`; добавляй firefox/webkit по необходимости) + **отдельный project `setup`** для одноразового логина (шаг 5);
   - `retries`, `forbidOnly`, `reporter` — зависят от `process.env.CI`: в CI ретраи и `forbidOnly: true`, локально 0.

4. **Организуй спеки по сценариям, а не по страницам.** Один файл = один пользовательский флоу (`order-checkout.spec.ts`, `registration.spec.ts`), а не «все клики страницы». Группируй `test.describe`, общую подготовку — в `beforeEach`. Доменные имена держи нейтральными (`Order`, `Article`, `Document`), без бизнес-терминов конкретного проекта.

5. **Авторизация — один логин на прогон через `storageState`.** Не логинься в каждом тесте формой (медленно и хрупко):
   - заведи `e2e/auth.setup.ts`, помеченный как project `setup`: он один раз проходит форму логина и сохраняет cookies/localStorage в файл `playwright/.auth/user.json` через `page.context().storageState({ path })`;
   - остальные projects объявляют `dependencies: ['setup']` и `use: { storageState: 'playwright/.auth/user.json' }` — каждый тест стартует уже залогиненным;
   - добавь `playwright/.auth/` в `.gitignore` (там реальная сессия);
   - для нескольких ролей — несколько storageState-файлов и несколько projects (admin/user).

6. **Конвенция селекторов — `data-testid`.** Не цепляйся за CSS-классы и видимый текст (ломается при рестайле/переводе). Стабильный контракт «тест ↔ разметка»:
   - в разметке: `data-testid="order-submit"`; в тесте: `page.getByTestId('order-submit')`;
   - задай `testIdAttribute: 'data-testid'` в `use` конфига (можно поменять атрибут проектно);
   - для содержательных проверок допускается `getByRole`/`getByLabel` (доступность), но действия-якоря — через testid;
   - именование testid — `<домен>-<элемент>-<действие?>` в kebab-case, стабильное и осмысленное.

7. **Изолируй данные и медиа между прогонами.** E2E пишут в настоящую БД и файловое хранилище — без изоляции прогоны загрязняют друг друга и продакшн-данные:
   - **БД:** отдельная тестовая база (`*_e2e`/`*_testing`), накат миграций перед прогоном; либо транзакция/сидинг с очисткой. Не указывай на боевую БД;
   - **медиа/загрузки:** отдельный диск/каталог для тестов (например `media-test` вместо `media`), который чистится перед/после прогона, чтобы загруженные в тесте файлы не смешивались с боевыми и не копились;
   - оба тестовых каталога — в `.gitignore`;
   - управляй этим через env (`.env.e2e`/`.env.testing`): `webServer.env` в конфиге передаёт серверу нужные `DB_*` и `MEDIA_DISK`/`*_DISK`, чтобы поднятое приложение писало в изолированные ресурсы;
   - уникальные данные в самих тестах — суффикс из `Date.now()`/uuid в email/имени, чтобы повторный прогон не падал на уникальных ключах.

8. **Ожидания — только авто-вэйтинг Playwright, без `sleep`.** Используй `await expect(locator).toBeVisible()`, `toHaveURL()`, `getByText().waitFor()`. Запрети фиксированные `waitForTimeout(ms)` — это источник флейков. Сетевые ожидания — `waitForResponse`/`waitForURL`.

9. **Локальный запуск:**
   ```bash
   npx playwright test                 # все спеки, headless
   npx playwright test --ui            # интерактивный режим отладки
   npx playwright test e2e/order-checkout.spec.ts --headed
   npx playwright show-report          # HTML-отчёт после прогона
   ```
   Добавь скрипты в `package.json` (`"test:e2e": "playwright test"`).

10. **Запуск в CI** (см. `snippets/ci-step.yml`):
    - кэшируй/устанавливай браузеры `npx playwright install --with-deps chromium`;
    - подними зависимые сервисы (БД) как CI-services; прогони миграции на тестовой базе;
    - передай env изоляции (`DB_*`, `MEDIA_DISK`) шагу теста — `webServer` поднимет приложение сам;
    - публикуй артефакты: `playwright-report/`, трейсы/скриншоты/видео при падении (`trace: 'on-first-retry'`, `screenshot: 'only-on-failure'`).

## Структура каталога

```
e2e/                      # testDir
├── auth.setup.ts         # project "setup": один логин → storageState
├── registration.spec.ts  # сценарий: регистрация (без логина — отдельный project)
├── order-checkout.spec.ts# сценарий: оформление заказа (залогинен через storageState)
└── fixtures/             # тестовые файлы для загрузок (картинки, pdf)
playwright/
└── .auth/                # storageState-файлы (в .gitignore)
playwright.config.ts
```

## Антипаттерны

- **Логин формой в каждом тесте** вместо `storageState` — медленно, флейки, дублирование. Один `setup`-project на прогон.
- **Селекторы по CSS-классам и видимому тексту** для действий-якорей — ломаются при рестайле и i18n. Якоря — `data-testid`.
- **`waitForTimeout(3000)`** как «подождать пока прогрузится» — фиксированные паузы. Только авто-вэйтинг `expect(...).toBeVisible()`/`toHaveURL()`.
- **Прогон по боевой БД/диску медиа** — загрязнение и риск удаления продакшн-данных. Отдельная база + отдельный диск, оба чистятся и в `.gitignore`.
- **`baseURL`/`http://localhost:8000` хардкодом в спеках** — относительные пути + `baseURL` из env.
- **Один спек на всё приложение** — дели по пользовательским сценариям.

## Чеклист качества

- [ ] Проверено существующее E2E-устройство проекта; новая конвенция не дублирует имеющуюся
- [ ] `playwright.config.ts` задаёт `baseURL` из env, `webServer` (с `reuseExistingServer: !CI`), projects-браузеры
- [ ] Логин выполняется один раз project'ом `setup` → `storageState`; зависимые projects объявляют `dependencies: ['setup']` и `use.storageState`
- [ ] `playwright/.auth/` и тестовые каталоги данных/медиа добавлены в `.gitignore`
- [ ] Действия-якоря используют `data-testid` (`getByTestId`), `testIdAttribute` настроен в конфиге
- [ ] E2E пишут в изолированную БД и отдельный медиа-диск; изоляция передана серверу через `webServer.env`
- [ ] Уникальные данные в тестах генерируются (Date.now/uuid), повторный прогон не падает на unique-ключах
- [ ] Нет `waitForTimeout`; ожидания через авто-вэйтинг `expect`/`waitForURL`
- [ ] Спеки разбиты по пользовательским сценариям; домены нейтральны
- [ ] CI: установка браузеров, миграции тестовой БД, env изоляции, артефакты отчёта/трейсов при падении

## Ссылки

- https://playwright.dev/docs/test-configuration
- https://playwright.dev/docs/auth — authentication через storageState
- https://playwright.dev/docs/locators — getByTestId / getByRole
- https://playwright.dev/docs/test-webserver
- snippets/playwright.config.ts, snippets/example.spec.ts, snippets/ci-step.yml
- Связанные скиллы: `quality/test-strategy` (что покрывать E2E), `frontend/vitest` (unit/компонентные тесты)
