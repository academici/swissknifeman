---
name: ci-cd
bucket: devops
version: 0.2.0
description: "GitHub Actions CI/CD pipelines для Laravel проектов"
risk: write
persona: operator
tags: ["ci", "github-actions", "laravel", "devops", "release"]
requires: []
produces_for: ["release-engineering"]
outputs: []
snippets: ["github-actions-laravel.yml", "github-actions-release.yml", "github-actions-docker.yml"]
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

## Ссылки

- Смежные скиллы: `oss-dev/github-flow` (Issue→PR→Tag→Release цепочка), `oss-dev/release-engineering` (релизный pipeline, CHANGELOG, SemVer), `devops/gitops` (модель веток, защита), `php/static-analysis` (Pint/PHPStan/Rector в CI), `php/laravel-testing` (тестовый прогон), `quality/mutation-testing` (Infection-гейт в CI), `quality/playwright-e2e` (E2E в CI), `devops/docker-php` (образ для шага build)
