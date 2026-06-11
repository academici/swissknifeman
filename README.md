# academici/swissknifeman

> Skills & Snippets registry for the [academici](https://github.com/academici) ecosystem.

Единый реестр скиллов — provider-neutral `SKILL.md` + `snippets/` + опциональные `adapters/`. Совместим с `skills-lock.json` schema v3 из `academici/brain`.

## Structure

```
skills/
├── founder/          # 5 skills
├── pm/               # 8 skills
├── architect/        # 9 skills
├── oss-dev/          # 5 skills + references/
├── quality/          # 4 skills
├── operator/         # 5 skills
├── devops/           # 6 skills — Docker, CI/CD, GitOps
├── php/              # 7 skills — Laravel, AzGuard, Botkit, Filament
├── roles/            # 4 personas
└── imported/         # 12 super-skills

adapters/             # cursor, claude-code, perplexity
generate-skill/       # Meta-skill for creating new skills
skills.json           # Registry (source of truth)
```

## Quick Start

```bash
# Install all skills
./install.sh

# Install specific bucket
./install.sh ~/.cursor/skills php

# Update registry hashes
./sync.sh --update-registry

# Sync to academici/brain (not Obsidian — отдельного sync-скрипта для vault нет)
BRAIN_PATH=~/path/to/brain ./sync.sh --update-registry
```

## Creating a Skill

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Scanner

```bash
./scripts/scan-skills.sh              # find candidates
./scripts/scan-skills.sh --extract    # anonymize to .scanner-output/
./scripts/scan-and-pr.sh              # commit + PR
```

Configure paths in `.skills-scanner.json`.

## CI/CD

| Workflow | Purpose |
|----------|---------|
| `validate.yml` | Frontmatter + snippet manifest validation |
| `sha256-update.yml` | Recalculate registry hashes |
| `sync-to-brain.yml` | Daily sync to academici/brain |
| `scanner-pr.yml` | Weekly scanner PR |
