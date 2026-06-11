---
name: ci-cd
bucket: devops
version: 0.2.0
description: "GitHub Actions CI/CD pipelines для Laravel проектов"
risk: write
persona: operator
tags: ["ci", "github-actions", "laravel"]
requires: []
produces_for: []
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
