---
name: pennant-development
bucket: php
version: 0.1.0
description: "Laravel Pennant — feature-флаги: define/active/for-scope, директива @feature, активация/деактивация, A/B и постепенные раскатки. Адаптировано из laravel/boost (strategy=notify)"
risk: write
persona: oss-dev
tags: ["php", "laravel", "pennant", "feature-flags"]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---
# Pennant Features

> Источник: `laravel/boost` (`.ai/pennant/skill/pennant-development/SKILL.md`),
> адаптировано для реестра swissknifeman (frontmatter бакета; strategy=notify).
> Pennant — стабильный API без версионной развилки, поэтому скилл переносим как
> самодостаточный для проектов без Boost.

## Когда активировать

- Создание, проверка или переключение feature-флагов.
- Управление постепенными раскатками фич (rollouts).
- Реализация A/B-тестирования.
- Работа с директивой `@feature` в Blade.

## Базовое использование

### Определение фич

```php
use Laravel\Pennant\Feature;

Feature::define('new-dashboard', function (User $user) {
    return $user->isAdmin();
});
```

### Проверка фич

```php
if (Feature::active('new-dashboard')) {
    // Фича активна
}

// Со скоупом
if (Feature::for($user)->active('new-dashboard')) {
    // Фича активна для этого пользователя
}
```

### Blade-директива

```blade
@feature('new-dashboard')
    <x-new-dashboard />
@else
    <x-old-dashboard />
@endfeature
```

### Активация / деактивация

```php
Feature::activate('new-dashboard');
Feature::for($user)->activate('new-dashboard');
```

## Проверка

1. Фича определена (`Feature::define`).
2. Поведение протестировано на разных скоупах/пользователях.

## Частые ошибки

- Забыли заскоупить фичу под конкретного пользователя/сущность (`Feature::for(...)`).
- Не следуют существующим конвенциям именования флагов в проекте.

## Ссылки

- Документация: https://laravel.com/docs/pennant
- В проектах с Laravel Boost версионно-специфичные темы отдаём Boost;
  Pennant версионно стабилен — конфликта нет.
