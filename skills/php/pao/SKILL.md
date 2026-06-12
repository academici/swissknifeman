---
name: pao
bucket: php
version: 1.0.0
description: "Laravel PAO — агентно-оптимизированный вывод PHP-инструментов: PHPUnit/Pest/Paratest/PHPStan/Rector/Artisan сжимаются в компактный JSON (~20 токенов вместо тысяч) при работе внутри AI-агента. Установка, проверка, ограничения."
risk: write
persona: oss-dev
tags: [php, laravel, testing, tokens, agent-output]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Laravel PAO — Agent-Optimized Output

## Контекст

Полный вывод PHPUnit на большом прогоне — ~10 000 токенов, и он накапливается с каждой итерацией «правка → тест». PAO (https://github.com/nunomaduro/pao) детектирует запуск внутри AI-агента (ENV: `CLAUDE_CODE`, `CURSOR_AGENT` и др.) и заменяет вывод компактным JSON (~20 токенов независимо от размера сьюта). Человек в терминале видит обычный вывод — меняется только агентская среда.

Работает с любым PHP-проектом (Laravel, Symfony, vanilla): PHPUnit, Pest, Paratest, PHPStan, Rector, Laravel Artisan.

## Входные данные

- PHP ≥ 8.3 (жёсткое требование пакета).
- Composer-проект; активация через autoloader — конфиг не нужен.

## Алгоритм

1. Проверь версию PHP: `php -v` (≥ 8.3, иначе PAO не ставить).
2. `composer require laravel/pao --dev`
3. Проверь: запусти тесты из агентской сессии — вывод должен стать JSON:

```json
{"result": "passed", "tests": 1002, "passed": 1002, "failed": 0, "duration_ms": 321}
```

При падении PAO сохраняет всё нужное для исправления — файл, строку, сообщение:

```json
{
  "result": "failed",
  "tests": 1002, "passed": 1001, "failed": 1,
  "failures": [
    {"test": "UserTest::it_validates_email", "file": "tests/Unit/UserTest.php", "line": 45, "message": "Expected true, got false"}
  ]
}
```

4. Если вывод не сжался — проверь, что инструмент запущен через composer/vendor/bin (не через глобальный бинарь) и что ENV агента присутствует (`env | grep CLAUDE`).

## Чеклист качества

- [ ] PHP ≥ 8.3 подтверждён до установки
- [ ] Тестовый прогон из агента возвращает JSON, из терминала — обычный вывод
- [ ] Не установлен параллельно waaseyaa/agent-output (дублирование обёрток вывода)

## Ограничения

- Кастомные `bin/check-*` скрипты PAO не покрывает — для них есть waaseyaa/agent-output (NDJSON, −94.7%): https://jonesrussell.github.io/blog/agent-output-php-ci-tools/. Как стандарт реестра не внедряется — PAO покрывает основной стек.

## Ссылки

- https://github.com/nunomaduro/pao
- https://laravel.com/blog/introducing-laravel-pao-cleaner-output-for-ai-agents
- https://laravel-news.com/pao-agent-optimized-output-for-php-testing-tools
