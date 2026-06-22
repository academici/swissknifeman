---
name: oss-php
description: PHP-специфика для OSS-проектов: composer.json, PSR-стандарты, PHPStan, PHPUnit, Packagist, CI matrix
type: reference
parent: oss-development
---

# Reference: OSS PHP

Загружается дополнительно к `.ai/skills/oss-dev/oss-development.md` когда язык проекта — PHP (BrainKit, AzGuard и подобные пакеты).

---

### composer.json минимум

```json
{
  "name": "vendor/package-name",
  "description": "Одна строка",
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

### PSR стандарты (обязательно)

| PSR | Что | Инструмент |
|:---|:---|:---|
| PSR-1 | Базовый code style | php-cs-fixer |
| PSR-4 | Autoloading namespace → путь | composer |
| PSR-12 | Extended code style | php-cs-fixer |
| PSR-7 | HTTP interfaces (если HTTP) | nyholm/psr7 |
| PSR-11 | Container interface (если DI) | psr/container |

### Static Analysis

```bash
# PHPStan — минимум level 6, целевой level 8
vendor/bin/phpstan analyse src --level=8

# PHP-CS-Fixer
vendor/bin/php-cs-fixer fix src
```

### PHP Version Support Matrix

```
PHP 8.1 — minimum (enum, fibers, intersection types)
PHP 8.2 — recommended (readonly classes)
PHP 8.3 — latest stable

Правило: поддерживать 2 активные минорные версии PHP
```

### PHPUnit структура

```
tests/
├── Unit/           # Изолированные тесты без IO
├── Integration/    # Тесты с реальными зависимостями
└── Feature/        # Сквозные сценарии
```

```bash
vendor/bin/phpunit --coverage-text
```

### Packagist Publishing

```bash
# 1. Создать тег
git tag v1.0.0
git push origin v1.0.0

# 2. Зарегистрировать на packagist.org (один раз)
# 3. Webhook на GitHub → Packagist (auto-update при тегах)
```

### .github/workflows/ci.yml для PHP

```yaml
- PHP versions: [8.1, 8.2, 8.3]
- composer install --no-interaction
- vendor/bin/phpstan analyse src --level=8
- vendor/bin/php-cs-fixer fix --dry-run --diff
- vendor/bin/phpunit
```

---
