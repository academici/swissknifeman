# Composer-specifics of dependency auditing (PHP/Laravel)

Addition to `dependency-audit` for PHP-stack: specific commands and
composer-rake along each of the 5 dimensions.

## Measurement commands

| Measurement | Command | Note |
|:---|:---|:---|
| Vulnerability scan | `composer audit` | in CI: `composer audit --format=json --locked` |
| Outdated (straight) | `composer outdated --direct` | `--major-only` for technical debt assessment |
| Licenses | `composer licenses` | `--format=json` for report |
| Phantom deps | `composer-require-checker check` | imports without dependency in manifest |
| Unused | `composer-unused` | dependencies without use in code |
| Why is the package here | `composer why <pkg>` / `composer why-not <pkg> <ver>` | analysis of conflicts and transitivity |
| Platform | `composer check-platform-reqs` | extensions PHP in prod vs lockfile |

## roave/security-advisories — gate at stage require

```bash
composer require --dev roave/security-advisories:dev-latest
```

Metapackage with `conflict` on all vulnerable versions: installing the vulnerable package
crashes immediately, rather than being caught by an audit after the fact. Complements `composer audit`,
does not replace (does not cover what is already installed before adding it - banish
`composer update --dry-run` after connection).

## Reproducible installs

```bash
# CI/prod: strictly according to lockfile, without resolution
composer install --no-dev --prefer-dist --no-progress --no-interaction
# checking that lockfile is synchronous with composer.json
composer validate --strict
```

- `composer.lock` for applications - always commit; for packages - see
  discussion in the main skill + CI-matrix by versions Laravel/PHP
  (`laravel-package-compatibility`).
- `composer validate --strict` in CI catches out of sync manifest/lock.

## Composer-rake (sharp edges)

- **`minimum-stability: dev`** in the application - addictive dev-versions
  transitive; use `prefer-stable: true` + dot aliases.
- **`repositories` with VCS/path** — code bypassed Packagist: check source
  and commit commit-ref, not a thread.
- **Scripts `post-install-cmd`/`post-update-cmd`** — executable code when
  installation; in CI for untrusted packages: `--no-scripts` + explicit allowlist
  (`allow-plugins` in `config`).
- **`replace`/`provide` in forks** — a package can silently replace another;
  `composer why` will show.
- **Wildcard-constraints (`*`, `>=`)** in require — non-reproducible
  updates; for libraries `^x.y`, for applications lockfile-discipline.

## SBOM for PHP

```bash
composer require --dev cyclonedx/cyclonedx-php-composer
composer make-bom --output-format=JSON --output-file=SBOM.json
```
