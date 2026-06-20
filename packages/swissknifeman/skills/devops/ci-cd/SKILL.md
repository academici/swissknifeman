---
name: ci-cd
bucket: devops
version: 0.3.0
description: "GitHub Actions CI/CD pipelines для Laravel проектов: lint, тесты, build, release + security-гейты (SAST, аудит зависимостей, скан образа)"
risk: write
persona: operator
tags: ["ci", "github-actions", "laravel", "devops", "release", "security"]
requires: []
produces_for: ["release-engineering"]
outputs: []
snippets: ["github-actions-laravel.yml", "github-actions-release.yml", "github-actions-docker.yml", "github-actions-security.yml"]
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

## Ссылки

- Смежные скиллы: `oss-dev/github-flow` (Issue→PR→Tag→Release цепочка), `oss-dev/release-engineering` (релизный pipeline, CHANGELOG, SemVer), `devops/gitops` (модель веток, защита), `php/static-analysis` (Pint/PHPStan/Rector + taint в CI), `oss-dev/dependency-audit` (аудит зависимостей, SBOM, политика обновлений), `php/laravel-testing` (тестовый прогон), `quality/mutation-testing` (Infection-гейт в CI), `quality/playwright-e2e` (E2E в CI), `devops/docker-php` (образ для шага build и скана)
- snippets/github-actions-security.yml — security-job: composer/npm audit + Trivy скан образа
