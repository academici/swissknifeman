---
name: oss-development
bucket: oss-dev
version: 0.1.1
description: "Use for OSS repository structure, package docs, architecture decisions, versioning, and CI."
risk: write
persona: oss-dev
tags: [oss, architecture, documentation, ci]
requires: []
produces_for: [release-engineering, dx-design, oss-governance, dependency-audit]
outputs: ["ProjectName/ProjectName.md", "ProjectName/Architecture.md", "ProjectName/Roadmap.md", "ProjectName/ADR/"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: OSS Development

Apply when: task on an OpenSource project (BrainKit, AzGuard, ThemeOn, other OSS). Engineering track — architecture, code, developer docs.

## Startup track vs OSS track

| | Startup | OSS |
|:---|:---|:---|
| Audience | Investors, users, team | Developers, contributors |
| Docs | BRD, GTM, Unit Economics | README, API docs, Contributing guide |
| Focus | Business value | Technical correctness |
| Metrics | MAU, Revenue, Churn | GitHub stars, forks, npm downloads, contributors |

## Step 1. Repo Structure

Detailed OSS repo structure (dirs, required files) → [references/repo-structure.md](references/repo-structure.md).

## Step 2. README structure

```markdown
# ProjectName

[One line: what it does + for whom]

[![npm version](badge)] [![license](badge)] [![CI](badge)]

## Why [ProjectName]?
[3-5 specific advantages over alternatives]

## Quick start
[Minimum 3 lines of code to get the result]

## Installation
[Installation command]

## Usage
[Basic examples]

## API / Documentation
[Link to full documentation or inline]

## Requirements
[Dependency versions]

## Contribution
[Link to CONTRIBUTING.md]

## License
[License type]
```

## Step 3. Architecture

Use C4 model (text variant):
- **Level 1 — Context:** who uses it, what external systems.
- **Level 2 — Container:** main components and their interaction.
- **Level 3 — Component:** details of key components.
- **ADR:** each non-trivial decision → separate ADR file.

Mermaid diagrams mandatory in Architecture.md.

## Step 4. Versioning Strategy

**SemVer:** `MAJOR.MINOR.PATCH`
- MAJOR: breaking changes
- MINOR: new features, backward compatible
- PATCH: bug fixes

Rules:
- `0.x.x` — experimental, any breaking changes allowed.
- `1.0.0` — stable public API, breaking changes only in MAJOR.
- Always update CHANGELOG.md before release.

## Step 5. Contributing Guide

CONTRIBUTING.md must contain:

```markdown
## How to run locally
[Commands for setup]

## Project structure
[Briefly what is where]

## How to run tests
[Command]

## How to create PR
1. Fork repository
2. Create branch: `git checkout -b feature/name`
3. Commits: [conventional commits format]
4. Tests: everyone must pass
5. PR: fill out the template

## Code style
[Linter, formatter, pre-commit hooks]
```

## Step 6. CI/CD minimum

```yaml
# .github/workflows/ci.yml
- Lint
- Type check (if TypeScript/Go/Rust)
- Tests
- Build
- (optional) Publish on npm/crates.io with tag
```

## Vault file formats (OSS project)

```
05 - Projects/03 - OpenSource/ProjectName/
├── ProjectName.md          # Index: status, link to GitHub, key solutions
├── Architecture.md         # C4 + Mermaid
├── ADR/
│   └── ADR-001_*.md
├── Roadmap.md              # Phases, planned features
└── _index.md
```

## OSS health metrics

| Metric | Target |
|:---|:---|
| Test coverage | ≥ 80% |
| CI pass rate | ≥ 95% |
| Issue response time | < 48 hours |
| PR review time | < 1 week |
| Docs current | Updated with every MINOR |

## Agent adds on its own

- License rec (MIT for max adoption, Apache 2.0 if patent protection needed).
- Security policy (`SECURITY.md`) if project relates to security.
- README badges (npm version, CI status, coverage, license).
- Semver warning if API changes without versioning.

## PHP specifics

See [[../references/oss-php]] (file `../references/oss-php.md` relative to this skill) — composer.json, PSR standards, PHPStan, PHPUnit, Packagist, CI matrix.

## Links

Root of OSS track; branches off:
- `oss-dev/release-engineering` — SemVer contract, CHANGELOG, release pipeline.
- `oss-dev/dx-design` — README/quick-start, API ergonomics, error messages.
- `oss-dev/oss-governance` — LICENSE, CoC, CONTRIBUTING, SECURITY, RFC.
- `oss-dev/dependency-audit` — vuln/license/supply-chain dependency audit.
- `oss-dev/github-flow` — Issue→PR→Tag→Release process chain on GitHub.

Adjacent (entry/detail):
- `architect/tech-stack-selection` — stack choice BEFORE repo structure (ADR-first step).
- `architect/architecture` — C4/ADR detail (here — base level only).
- `devops/ci-cd` — GitHub Actions pipelines (here — CI minimum only).
- `php-packages/laravel-packages` — scaffold/publish Laravel packages (language specifics).

## Hard forbidden

NEVER:
- Business docs (BRD, GTM, Unit Economics) in OSS track.
- Commits directly to main (PR only).
- Merge without green CI.
- Breaking changes without MAJOR version (if ≥ 1.0.0).
- PHP package without PSR-4 autoloading.
- Publish to Packagist without tests (coverage < 80%).
