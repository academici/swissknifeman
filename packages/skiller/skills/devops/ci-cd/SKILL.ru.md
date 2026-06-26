---
name: ci-cd
bucket: devops
version: 0.4.0
description: "GitHub Actions / GitLab CI пайплайны для Laravel: lint, тесты, build, release + security-гейты (SAST, аудит зависимостей, скан образа) + coverage-gate в CI (Clover-порог, jobs)"
risk: write
persona: operator
tags: ["ci", "github-actions", "gitlab-ci", "laravel", "devops", "release", "security", "coverage"]
requires: []
produces_for: ["release-engineering"]
outputs: []
snippets: ["github-actions-laravel.yml", "github-actions-release.yml", "github-actions-docker.yml", "github-actions-security.yml", "github-actions-coverage-gate.yml", "gitlab-ci-practices.md"]
adapters: [claude, cursor, fable]
sha256: ""
---

## Контекст

Настройка CI/CD через GitHub Actions.

## Алгоритм

1. Lint + static analysis
2. Unit/feature tests
3. Build Docker image on main
4. Release workflow on tag
5. Security gates (см. ниже) — отдельным job, не блокируют merge на warning, блокируют на high/critical

## Security gates

Три независимых среза, каждый — отдельный шаг/job (сниппет `github-actions-security.yml`):

- **SAST (код).** Статический анализ уже в шаге 1 — добавить taint-режим: PHPStan на максимуме
  правил, по возможности `psalm --taint-analysis` (поток непроверенного ввода в SQL/вывод).
  Алгоритм и конфиг — скилл `php/static-analysis`.
- **Зависимости.** `composer audit` (PHP) и `npm audit --audit-level=high` (JS) в CI;
  Dependabot/Renovate для авто-PR на уязвимые версии. Глубже (SBOM, политика обновления) —
  скилл `oss-dev/dependency-audit`.
- **Образ.** `trivy image` (или `aquasecurity/trivy-action`) на собранном образе из шага 3:
  CVE в base-слоях и пакетах ОС. Образ собирается по скиллу `devops/docker-php`.

Принцип гейта: `exit-code: 1` только на HIGH/CRITICAL; LOW/MEDIUM — в отчёт, не в блок
(иначе CI «шумит» и его глушат — анти-паттерн).

## Coverage-gate в CI

Порог покрытия проверяется **отдельным job**, не блокирует быстрый прогон тестов:
сперва `lint`+`tests` (быстрый fail), затем coverage-job собирает Clover и прогоняет
гейт. Два независимых порога — глобальный (`COVERAGE_GLOBAL_MIN`, типично 70%) и
ужесточённый для критичных директорий (`COVERAGE_CRITICAL_MIN`, типично 55%; покрывает
`Actions/Policies/Services/Middleware` — места, где баги дороже всего).

**Не переписывать парсер.** Конфиг (`coverage.php`), скрипт-гейт
(`check-coverage-gate.php`, режимы `report|soft|hard`, пофайловая проверка критичных
зон) и composer-скрипты (`test:coverage`, `test:coverage:gate`, `test:critical`) — в
скилле `laravel-testing/laravel-testing` (его сниппеты `coverage-gate-config.php`,
`check-coverage-gate.php`, `composer-test-scripts.json`). CI лишь **вызывает** их.

Алгоритм CI-job:

1. Поднять PHP с драйвером покрытия (**pcov** быстрее xdebug; `pcov.directory=app`).
2. На Postgres-проектах — дождаться БД (`until pg_isready ...; do sleep 1; done`) и
   прогнать миграции до тестов (`php artisan migrate --force`).
3. `php artisan test --coverage --coverage-clover=coverage/clover.xml`.
4. `php scripts/check-php-coverage-gate.php` (или `composer test:coverage:gate`) с env
   `COVERAGE_GATE_MODE=hard`, `COVERAGE_GLOBAL_MIN`, `COVERAGE_CRITICAL_MIN`.
5. Сложить `coverage/clover.xml` в артефакты (отчёт/тренд).

- **GitHub Actions** — сниппет `github-actions-coverage-gate.yml`.
- **GitLab CI** — паттерн `.php-base` (сборка PHP-расширений, `pg_isready`-ожидание,
  миграции) + job `php-coverage` в сниппете `gitlab-ci-practices.md` (раздел
  «Coverage-gate job»).

Режим гейта: `hard` (блокирует merge) на дефолтной ветке и MR; `report`/`soft` —
для ознакомительных прогонов. Порог — нижняя граница риска, не цель: качество тестов
меряется мутационным тестированием (`quality/mutation-testing`), не процентом строк.

## Ссылки

- Смежные скиллы: `oss-dev/github-flow` (Issue→PR→Tag→Release цепочка), `oss-dev/release-engineering` (релизный pipeline, CHANGELOG, SemVer), `devops/gitops` (модель веток, защита), `php/static-analysis` (Pint/PHPStan/Rector + taint в CI), `oss-dev/dependency-audit` (аудит зависимостей, SBOM, политика обновлений), `laravel-testing/laravel-testing` (тестовый прогон **+ конфиг/скрипт coverage-gate**, переиспользуется этим job), `quality/test-strategy` (coverage policy и пирамида, на которую опирается порог), `quality/mutation-testing` (Infection-гейт в CI), `quality/playwright-e2e` (E2E в CI), `devops/docker-php` (образ для шага build и скана)
- snippets/github-actions-security.yml — security-job: composer/npm audit + Trivy скан образа
- snippets/github-actions-coverage-gate.yml — coverage-job: pcov + `test --coverage` + gate-скрипт с глобальным и critical-dir порогами
- snippets/gitlab-ci-practices.md — практики `.gitlab-ci.yml` + `.php-base`/`php-coverage` job для coverage-gate
