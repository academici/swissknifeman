# PHP Package Gate — release PHP-package to Packagist

Addition to `github-flow` for PHP-stack: what to check in `composer.json`
and in what order to deploy to Packagist. Laravel-release specifics -
`php-packages/laravel-package-release`; audit-commands - `dependency-audit/references/composer.md`.

## composer.json gate

Before the tag, the agent checks the presence and correctness of the fields:

| Field | Requirement |
|:---|:---|
| `name` | `vendor/package-name`, matches the repository on Packagist |
| `description` | one line, 50–100 characters, in English |
| `type` | `library` (or `laravel-package` by tool convention) |
| `keywords` | 5–7 pieces, see below |
| `license` | SPDX-identifier (`MIT`, `Apache-2.0`) — matches LICENSE |
| `authors` | name + email |
| `require.php` | explicit constraint (`^8.2`), not «any version» |
| `autoload.psr-4` | namespace → `src/` |
| `minimum-stability` / `prefer-stable` | `stable` / `true` for public package |

```bash
composer validate --strict   # manifest is valid and in sync with lock
```

**Field `version`** — for Packagist optional (version taken from git-tag).
If the field is present, it MUST match the tag - the agent synchronizes
it in the release commit (`chore(release): ...`). It’s better not to maintain the field at all.

## Keywords

Basic: `php` + ecosystem (`laravel`, `symfony`). By domain - 2–4 clarifying:

| Domain | Keywords |
|:---|:---|
| Permissions / ACL | `permissions`, `authorization`, `acl`, `rbac`, `roles` |
| Security | `security`, `middleware`, `threat-detection` |
| Auth | `authentication`, `auth`, `guards` |
| Bot / Telegram | `telegram`, `bot`, `webhook` |
| Admin panel | `filament`, `admin`, `dashboard` |
| API | `api`, `rest`, `resource` |

More ~10 Packagist does not index effectively - do not bloat.

## Pre-deploy checks (PHP)

- [ ] No `dd()`, `dump()`, `var_dump()`, `ray()` in `src/`:
  `grep -rnE '\b(dd|dump|var_dump|ray)\(' src/`
- [ ] Production-classes are not used dev-packages (`composer-require-checker`,
  see `dependency-audit/references/composer.md`)
- [ ] `.gitignore` contains `vendor/`, `.env`
- [ ] Tests are green: `composer test` / `vendor/bin/phpunit` / `vendor/bin/pest`
- [ ] CI on default-branch green (`gh run list --branch main --limit 1`)

## Sequence Packagist-deployment

```
1. git checkout main && git pull
2. composer validate --strict
3. CHANGELOG.md: [Unreleased] → [X.Y.Z] - YYYY-MM-DD
4. (if field version yes) composer.json → "version": "X.Y.Z"
5. git commit -m "chore(release): ..."
6. git tag vX.Y.Z -m "Release vX.Y.Z" && git push origin main --tags
7. gh release create vX.Y.Z from CHANGELOG-sections
8. Packagist will pick up the tag by webhook
```

Webhook: Packagist → package profile → «GitHub Hook» (is set automatically
when submit via GitHub-account). Check: after push tag new version
appears on the package page in 1–2 minutes; if not - `Settings → Webhooks`
in repo or button «Update» on Packagist manually.
