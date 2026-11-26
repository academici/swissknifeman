---
name: oss-php
description: PHP-specifics for OSS-projects: composer.json, PSR-standards, PHPStan, PHPUnit, Packagist, CI matrix
type: reference
parent: oss-development
---

# Reference: OSS PHP

Loaded in addition to `.ai/skills/oss-dev/oss-development.md` when the project language is PHP (BrainKit, AzGuard and similar packages).

---

### composer.json minimum

```json
{
  "name": "vendor/package-name",
  "description": "One line",
  "type": "library",
  "license": "MIT",
  "require": {
    "php": "^8.1"
  },
  "require-dev": {
    "phpunit/phpunit": "^11.0",
    "phpstan/phpstan": "^1.0",
    "friendsofphp/php-cs-fixer": "^3.0"
  },
  "autoload": {
    "psr-4": { "Vendor\\Package\\": "src/" }
  },
  "autoload-dev": {
    "psr-4": { "Vendor\\Package\\Tests\\": "tests/" }
  }
}
```

### PSR standards (required)

| PSR | What | Tool |
|:---|:---|:---|
| PSR-1 | Basic code style | php-cs-fixer |
| PSR-4 | Autoloading namespace → path | composer |
| PSR-12 | Extended code style | php-cs-fixer |
| PSR-7 | HTTP interfaces (if HTTP) | nyholm/psr7 |
| PSR-11 | Container interface (if DI) | psr/container |

### Static Analysis

```bash
# PHPStan — minimum level 6, target level 8
vendor/bin/phpstan analyse src --level=8

# PHP-CS-Fixer
vendor/bin/php-cs-fixer fix src
```

### PHP Version Support Matrix

```
PHP 8.1 — minimum (enum, fibers, intersection types)
PHP 8.2 — recommended (readonly classes)
PHP 8.3 — latest stable

Rule: maintain 2 active minor versions PHP
```

### PHPUnit structure

```
tests/
├── Unit/           # Isolated tests without IO
├── Integration/    # Tests with real dependencies
└── Feature/        # End-to-end scenarios
```

```bash
vendor/bin/phpunit --coverage-text
```

### Packagist Publishing

```bash
# 1. Create tag
git tag v1.0.0
git push origin v1.0.0

# 2. Register on packagist.org (once)
# 3. Webhook on GitHub → Packagist (auto-update with tags)
```

### .github/workflows/ci.yml for PHP

```yaml
- PHP versions: [8.1, 8.2, 8.3]
- composer install --no-interaction
- vendor/bin/phpstan analyse src --level=8
- vendor/bin/php-cs-fixer fix --dry-run --diff
- vendor/bin/phpunit
```

---
