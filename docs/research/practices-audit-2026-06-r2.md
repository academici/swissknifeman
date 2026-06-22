# Аудит практик из проектов пользователя (2026-06, round 2)

> Продолжение [`practices-audit-2026-06.md`](./practices-audit-2026-06.md) (r1, 2026-06-15).
> r1 за один заход завёл 10 скиллов + реализовал 15-скилловый бэклог (batch-2 того же
> дня). Этот round-2 (2026-06-22) добирает **остаточные** практики из §7 r1 и пары новых
> наблюдений, не воссоздавая уже покрытое. Сверка — с **живым** реестром (`skills/`,
> `skills.json`), а не по памяти. Принцип — анти-bloat (`docs/guide/methodology.md`):
> новый скилл только без пересечений, иначе EXTEND; Rule of Three.

## 1. Метод и связь с r1

Обследованы проекты экосистемы: **azguard, doc-vault, botkit** (PHP-пакеты-монорепо),
**erp-sdk** (Dart/Flutter SDK), **corex**, **sova**, **flexcrm** (Laravel + Inertia/Vue).
После r1 бакеты насыщены: `php` — 42 скилла, `frontend` — 35. Поэтому большинство «сырых»
кандидатов разведки **уже покрыто** зрелыми скиллами — round-2 узкий и адресный.

## 2. Карта покрытия кандидатов

Сырые кандидаты разведки (codegen-scaffold'ы и т.п.) и их статус против живого реестра:

| Кандидат | Статус | Где покрыто / куда уходит |
|:---|:---|:---|
| `laravel-action-scaffold` | покрыто | `php/dependency-injection` (`action-di.php`, `composite-action.php`) + `php/laravel` (`action-class.php`, `actions.md`) + `php/laravel-structure` |
| `laravel-command-scaffold` | покрыто | `php/laravel-package-scaffold` (commands), `php/laravel-structure` (`Console/Commands/`) |
| `laravel-config-template` | покрыто | `php/spatie-settings` (рантайм-конфиг), `php/pennant-development` (флаги), `config/` в `php/laravel-structure` |
| `laravel-dto-generator` | покрыто | `php/laravel-data`, `php/php-patterns` (VO/DTO) |
| `orchestra-testbench-setup` | покрыто | `php/laravel-package-testing` (Testbench, TestCase, фикстуры) |
| `laravel-migration-generator` | покрыто | `php/database`, `php/laravel` (`db-conventions.md`) |
| `filament-package-scaffold` | частично | `php/filament` + `php/laravel-package-scaffold`; отдельный скилл не заводим (нет 2-го независимого потребителя сверх покрытого) |
| **CI coverage-gate** | **EXTEND** | → `devops/ci-cd` (CI-job; парсер переиспользован из `php/laravel-testing`) |
| **Pest multi-testsuite + Arch** | **EXTEND** | → `quality/test-strategy` (разделы + 2 сниппета) |
| **enum-state-machine** | **NEW** | → `php/enum-state-machine` |
| **spatie-settings ↔ инфра-конфиг во фронт** | **EXTEND** | → `php/spatie-settings` (§7a) |

«Покрыто» означает: дублей не заводим (Шаг 0 skill-authoring), evidence-проекты лишь
подтверждают, что паттерн уже обобщён в реестре.

## 3. Заавторено в этот заход (4)

### DevOps / Quality

**1. `devops/ci-cd` — EXTEND (coverage-gate в CI), v0.3.0 → 0.4.0.**
Порог покрытия отдельным CI-job: тесты с Clover (`--coverage-clover`), затем gate-скрипт с
двумя порогами — глобальный (`COVERAGE_GLOBAL_MIN`) и ужесточённый для критичных директорий
(`COVERAGE_CRITICAL_MIN`). **Парсер не дублируется** — конфиг/скрипт/composer-скрипты уже в
`php/laravel-testing` (`coverage-gate-config.php`, `check-coverage-gate.php`,
`composer-test-scripts.json`); EXTEND даёт только обвязку job'а: GitHub Actions-сниппет
`github-actions-coverage-gate.yml` (pcov, Postgres-service) и GitLab `.php-base`/`php-coverage`
job в `gitlab-ci-practices.md`.
Эвиденс: `sova/.gitlab-ci.yml` (`.php-base`, `php-coverage`, `COVERAGE_GATE_MODE=hard`,
`GLOBAL_MIN=70`, `CRITICAL_MIN=55`, `pcov`, `pg_isready`-ожидание),
`sova/scripts/check-php-coverage-gate.php`.

**2. `quality/test-strategy` — EXTEND (композиция сюитов + Pest Arch), v0.1.0 → 0.2.0.**
Два новых раздела: (а) **композиция именованных `<testsuite>`** — `Arch/Unit/UnitFilament/Feature/Context`,
Arch гоняется первым/отдельно без БД, `<exclude>` убирает пересечения, строгие флаги
прогона (`failOnWarning/Risky/EmptyTestSuite`, `executionOrder=random`); (б) **архитектурные
тесты Pest Arch** — инварианты strict_types, запрет debug-хелперов, final actions, readonly
DTO/VO/Events, contracts=interfaces, Actions/Repositories без `Request`. Сниппеты
`pest-arch-test.php`, `phpunit-testsuites.xml`.
Эвиденс (**2 проекта** → Rule of Three OK): `azguard/phpunit.xml` (5 сюитов
Arch/Feature/Context/Unit/UnitFilament), `doc-vault/packages/core/tests/Arch/ArchTest.php`
(полный набор arch-правил).

### PHP

**3. `php/enum-state-machine` — NEW, v0.1.0.**
Граф переходов доменного статуса как **единый источник** — статический метод enum
`transitionDefinitions()` (рёбра `from→to` + `guard`/`action`/`label`), поверх — тонкий
рантайм-реестр `*StatusTransitions` (ленивый кэш adjacency, `allowedFrom`/`canTransition`).
Переход исполняется в `final readonly` Action под `DB::transaction()`, доменное событие
реализует `ShouldDispatchAfterCommit`. UI строит действия из `allowedFrom($current)`.
**Гэп, не дубль:** `php/enum-attributes` явно исключает state-machine; `general/ticket-workflow`
— проектно-специфичная инстанциация (`{{project_name}}`, `App\Enums\Ticket\TicketStatus`).
Универсальный паттерн в реестре отсутствовал. Тело анонимизировано (`OrderStatus`), без
имён конкретных проектов; evidence — только здесь.
Эвиденс: `sova/app/Enums/Ticket/TicketStatus.php::transitionDefinitions()` (граф рёбер с
`policy`/`action`/`label`/`condition`), `sova/app/Services/Ticket/TicketStatusTransitions.php`
(рантайм-реестр `allowedFrom`/`canTransition`).

**4. `php/spatie-settings` — EXTEND (рантайм-инфраконфиг → фронт), v0.1.0 → 0.2.0.**
Узкий EXTEND поверх уже существующего шага 7 (Filament-биндинг). Новое — **архитектурный
паттерн §7a**: инфраструктурный параметр (websocket-клиент Reverb/Pusher: host/port/scheme/
app_key) редактируется админом в рантайме через типизированный Settings-класс и **отдаётся во
фронт публичным DTO**, не сырыми настройками; флаг `enabled` переключает «настройка vs env/Vite»;
секреты остаются в env/`addEncrypted` и во фронт не уходят. Связь с `frontend/laravel-echo-client`
(клиент) и `frontend/backend-type-sync` (DTO→TS).
Эвиденс: `sova/app/Settings/Broadcast/WebsocketClientSettings.php`,
`sova/app/Filament/Pages/Settings/ManageWebsocketClientSettings.php`.

## 4. Остаточный бэклог (отложено с явной причиной)

- **Dart/Flutter (erp-sdk).** 1 проект (melos/drift/riverpod), Dart-бакета в реестре нет,
  практики не переносимы в PHP/JS/Python-каркас. **Rule of Three не выполнен** — ждёт второго
  Dart-проекта; тогда — отдельный профиль/бакет. (Подтверждает решение §6 r1.)
- **Уже покрытое из §7 r1** (фиксируем, чтобы не открывать повторно):
  - `ShouldDispatchAfterCommit` на доменных событиях → `php/laravel-broadcasting` (покрыто;
    теперь также упоминается в `php/enum-state-machine` как часть перехода).
  - Makefile dev/prod как точка входа → `devops/makefile` + `devops/docker-dev-prod`.
  - Conventional Commits + commitlint/husky → `general/git-commit-rules` + `general/writing-style`.
  - Spatie Settings ↔ Filament UI-binding → было частично в `php/spatie-settings` шаг 7;
    round-2 добавил архитектурный слой «инфраконфиг → фронт» (§3.4).
- **filament-package-scaffold.** Покрыто комбинацией `php/filament` + `php/laravel-package-scaffold`;
  отдельный скилл не оправдан без независимого 2-го потребителя сверх уже покрытого.

## 5. Вне охвата

- **erp-sdk** — см. §4 (Dart, 1 проект).
- Раздувание реестра scaffold-генераторами под уже покрытые паттерны (action/command/config/
  dto/migration) — сознательно отклонено: каждый закрыт существующими php-скиллами (см. §2).

---

> Источник истины по составу реестра — `skills.json` и каталог `skills/`. Пути-эвиденс
> абсолютны и проверены на момент аудита (2026-06-22).
