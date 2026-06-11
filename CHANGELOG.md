# Changelog

## [0.2.0] - 2026-06-11

### Added

- **Upstream-sync система**: per-skill `upstream.json` (source, strategy replace/notify,
  sha256, fetched_at), `scripts/update-upstreams.sh` (--check/--apply/--force, exit-коды
  для CI), еженедельный workflow `upstream-sync.yml` с PR-ревью
- `upstream.json` + baseline для всех 12 `skills/imported/*` (get-zeked super-skills)
- **Контекстная установка**: `install.sh` v2 — автодетект типа проекта, `profiles/*.json`
  (obsidian-vault, laravel-project, php-package, standalone), `.swissknife.json` override,
  `--agent claude` с плоской раскладкой под `.claude/skills/` и manifest-cleanup
- **`references/`** — каталог 15 внешних источников с принципом выборочного отбора
- `scripts/validate.sh` — единая валидация (frontmatter, upstream.json, profiles,
  реестр, snippet-манифесты) локально и в CI
- Provenance в `skills.json`: `source: local|github|http`, `upstream`, `fetched_at`
- `.swissknife.example.json`

### Fixed

- `validate.yml`: glob `skills/**` не работал в bash без globstar — CI фактически
  не валидировал скиллы
- `sync.sh`: name/description парсились по всему файлу, а не только из frontmatter
- `skills/pm/prd-from-brd`: отсутствовало поле `version` во frontmatter

## [0.1.0] - 2026-06-11

### Added

- Skills registry v3 with 65 skills across 10 buckets
- Migration of 36 skills from `academici/brain`
- New buckets: devops, php, roles, imported
- 12 perplexity super-skills in `skills/imported/`
- PHP skills: laravel, laravel-permissions (with AzGuard patterns), laravel-testing, laravel-packages, php-patterns, botkit, filament
- DevOps skills: docker (php, vite, postgres, dev-prod), ci-cd, gitops
- Roles: startup-cto, tech-lead, open-source-maintainer, solo-founder
- `install.sh`, `sync.sh`, scanner pipeline
- CI: validate, sha256-update, sync-to-brain, scanner-pr
- Adapters: cursor, claude-code, perplexity
- `generate-skill/` meta-skill
