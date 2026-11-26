# WendellAdriel/laravel-expressive

- **URL:** https://github.com/WendellAdriel/laravel-expressive/tree/main/.agents/skills
- **Status:** imported
- **Checked:** 2026-06-12

Laravel-package with its own folder `.agents/skills/` — a living example of how
package publishes skills for agents. 8 Package Development Skills (are often needed).

## What's taken

All 8 skills are imported into bucket `php` flat folders with prefix
`laravel-` (attachment SKILL.md inside existing `laravel-packages/SKILL.md`
invisible to plugin discovery — see commit d6bc0f9 about docker):

| upstream `.agents/skills/` | our skill (`skills/php/`) |
|---|---|
| `package-compatibility`    | `laravel-package-compatibility` |
| `package-docs`             | `laravel-package-docs` |
| `package-generate-skill`   | `laravel-package-generate-skill` |
| `package-release`          | `laravel-package-release` |
| `package-scaffold`         | `laravel-package-scaffold` |
| `package-service-provider` | `laravel-package-service-provider` |
| `package-testing`          | `laravel-package-testing` |
| `skeleton-development` (name `expressive-development`) | `laravel-package-expressive` |

The provenance of each is in `upstream.json` next to SKILL.md (`strategy: notify`,
do not auto-replace). Bucket-frontmatter added on top of the original body.

## Connections

- Intersects with `oss-dev/release-engineering` (releases) and our
  `generate-skill/` (pattern package-generate-skill) — left separately as
  package-specific.
