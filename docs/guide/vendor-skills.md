# Скиллы из пакетов (vendor-skills)

Скиллы попадают в проект двумя путями, и они дополняют друг друга:

| Направление | Механизм | Кто источник |
|---|---|---|
| **Реестр → проект** | `swissknifeman vendor` | SwissKnifeMan: универсальные скиллы под тип проекта |
| **Пакет → приложение** | `vendor:publish` | Composer-пакет: доменные скиллы о самом пакете |

Первое направление описано в [Установке](/guide/installation). Эта страница —
про второе: как пакет возит свои скиллы с собой.

## Идея

Пакет, решающий доменную задачу (безопасность, биллинг, интеграции), знает
о своей предметной области больше, чем любой универсальный реестр: паттерны
использования, миграционные сценарии, типовые ошибки. Логично, чтобы такой
пакет **сам поставлял скиллы** для AI-агента потребителя:

```
composer require acme/my-package
php artisan vendor:publish --tag=my-package-skills
# → агент приложения умеет работать с пакетом
```

Так скиллы остаются рядом с кодом, который они описывают, версионируются
вместе с пакетом и обновляются при его апгрейде.

## Структура внутри пакета

```
vendor/acme/my-package/
└── resources/
    └── skills/
        └── my-package-security/      ← имя папки с префиксом пакета!
            ├── SKILL.md
            └── snippets/
                ├── threat-detection.php
                └── rbac-policy.php
```

::: warning Префикс пакета обязателен
Имя папки скилла — `<package>-<skill>`, не просто `<skill>`. У потребителя
скиллы из разных источников лежат в одном каталоге; префикс исключает коллизии.
:::

## Публикация в ServiceProvider

```php
// В PackageServiceProvider::boot()
if ($this->app->runningInConsole()) {
    // Вариант A: агент-нейтральная раскладка
    $this->publishes([
        __DIR__.'/../resources/skills' => base_path('.ai/skills/vendor/my-package'),
    ], 'my-package-skills');

    // Вариант B: плоская раскладка для Claude Code
    $this->publishes([
        __DIR__.'/../resources/skills' => base_path('.claude/skills'),
    ], 'my-package-skills-claude');
}
```

У потребителя:

```bash
php artisan vendor:publish --tag=my-package-skills-claude

# после апгрейда пакета — обновить скиллы:
php artisan vendor:publish --tag=my-package-skills-claude --force
```

## Сосуществование с swissknifeman vendor

Оба механизма работают в одном проекте и не мешают друг другу:

- `swissknifeman vendor` ведёт манифест `.swissknifeman-manifest.json` и при
  переустановке чистит **только свои** скиллы — опубликованные пакетами
  не трогаются;
- префикс пакета в имени папки гарантирует отсутствие коллизий имён;
- в реестре проекта vendor-скилл можно пометить provenance-полями:

```json
{
  "name": "my-package-security",
  "path": ".claude/skills/my-package-security/SKILL.md",
  "source": "vendor",
  "package": "acme/my-package",
  "version": "1.2.0"
}
```

## Как добавить публикацию скиллов в свой пакет

Готовый рецепт — скилл `php/laravel-packages` (ставится с профилями
`php-package` и `laravel-project`): scaffold пакета, сниппет
`boost-skill-publisher.php` и чеклист с проверкой полного цикла
`composer install → vendor:publish → агент видит SKILL.md`.

## Круговорот скиллов

Полный цикл экосистемы выглядит так:

```
SwissKnifeMan ──swissknifeman vendor──→ проект пакета (скиллы для разработки пакета)
проект пакета ──разработка──→ доменные скиллы   (resources/skills/)
пакет ──vendor:publish──→ приложения-потребители (скиллы для использования пакета)
приложения ──сканер──→ SwissKnifeMan             (новые сниппеты из практики)
```

Сканер ([scanner](/guide/scanner)) замыкает цикл: удачные паттерны из боевых
проектов возвращаются в реестр.
