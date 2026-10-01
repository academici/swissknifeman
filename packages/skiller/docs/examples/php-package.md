# Open-source PHP-package

Scenario: developing a package for Packagist (first of all - Laravel-packages).

## Installation

```bash
cd ~/projects/packages/my-package

# Skills: composer.json without artisan → profile php-package
skiller vendor --agent claude

# Permissions: base + php-package
~/projects/packages/swissknifeman/packages/skiller/scripts/apply-permissions.sh --target .
```

Profile `php-package` puts bucket-s **oss-dev, php, quality, devops**:

- `oss-dev` — README, versioning, releases, languages references;
- `php` — Laravel-packages, patterns, testing;
- `quality` — code review, tests, technical debt;
- `devops` — CI/CD for packages.

## What the preset allows php-package

Full package development cycle without prompts:

```bash
composer install / update / require / validate
vendor/bin/pest --coverage
vendor/bin/phpstan analyse
vendor/bin/pint
vendor/bin/rector process
vendor/bin/infection
```

Plus everything from `base`: git (push — with confirmation), gh for PR and issues,
file operations.

## Role for agent

B bucket-e `roles` has a person `open-source-maintainer` — if needed,
deliver it explicitly:

```bash
skiller vendor --buckets roles --agent claude
```
