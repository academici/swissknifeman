# Open-source PHP-пакет

Сценарий: разработка пакета для Packagist (в первую очередь — Laravel-пакеты).

## Установка

```bash
cd ~/projects/packages/my-package

# Скиллы: composer.json без artisan → профиль php-package
~/projects/packages/swissknifeman/install.sh --target . --agent claude

# Permissions: base + php-package
~/projects/packages/swissknifeman/scripts/apply-permissions.sh --target .
```

Профиль `php-package` ставит bucket-ы **oss-dev, php, quality, devops**:

- `oss-dev` — README, версионирование, релизы, языковые references;
- `php` — Laravel-пакеты, паттерны, тестирование;
- `quality` — code review, тесты, техдолг;
- `devops` — CI/CD под пакеты.

## Что разрешает пресет php-package

Полный цикл разработки пакета без промптов:

```bash
composer install / update / require / validate
vendor/bin/pest --coverage
vendor/bin/phpstan analyse
vendor/bin/pint
vendor/bin/rector process
vendor/bin/infection
```

Плюс всё из `base`: git (push — с подтверждением), gh для PR и issues,
файловые операции.

## Роль для агента

В bucket-е `roles` есть персона `open-source-maintainer` — если она нужна,
доставьте её явно:

```bash
~/projects/packages/swissknifeman/install.sh --target . --buckets roles --agent claude
```
