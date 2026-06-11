---
name: modular-architecture
bucket: php
version: 0.1.0
description: "Организация Laravel-кода по бизнес-доменам: Модульный Монолит (Modular Monolith) и паттерны DDD"
risk: write
persona: oss-dev
tags: [php, laravel, architecture]
requires: [laravel]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Модульная Архитектура (Laravel)

При росте кодовой базы стандартной структуры Laravel (`app/Http`, `app/Models`) становится недостаточно. Для сложных проектов мы применяем концепцию **Модульного Монолита (Modular Monolith)** или паттерны **Domain-Driven Design (DDD)**.

## Основная Идея

Код должен быть организован не по техническому типу (все контроллеры в одной папке, все модели в другой), а по **Бизнес-Доменам** (например, всё, что связано со Счетами (Invoices), лежит в одном месте).

## Структура Директорий

Обычно мы создаем директорию `app/Modules` (или `src/Modules`).

```text
app/
  Modules/
    Invoices/
      Controllers/    # HTTP слой
      DTOs/           # Data Transfer Objects
      Jobs/           # Фоновые задачи
      Models/         # Eloquent модели домена
      Providers/      # Service Providers модуля
      Repositories/   # Доступ к данным (если используется)
      Services/       # Бизнес-логика
    Users/
      ...
```

## Правила Изоляции Модулей

1.  **Отсутствие перекрестных зависимостей БД:** Модуль `Invoices` не должен напрямую делать SQL Join с таблицами модуля `Users`. Вместо этого модули должны общаться через интерфейсы или публичные Сервисы (Contracts).
2.  **Использование DTO:** При передаче данных между модулями (или от контроллера к сервису) используйте Data Transfer Objects. Никаких сырых массивов.
3.  **Тонкие Контроллеры:** Контроллер должен только:
    - Валидировать Request.
    - Сформировать DTO.
    - Вызвать метод Сервиса или Action-класса.
    - Вернуть Response/Resource.
    Вся бизнес-логика должна жить в слое Services или Actions.

## События (Events)

Для максимальной слабой связности (loose coupling) между модулями используйте Event-Driven подход.
Если при регистрации пользователя нужно отправить письмо и создать кошелек, модуль `Users` просто кидает событие `UserRegistered`.
Модуль `Notifications` и модуль `Wallets` слушают это событие и выполняют свою логику независимо.

## Автозагрузка (Autoloading)

Для регистрации провайдеров, роутов и миграций модулей можно использовать пакеты (например, `nWidart/laravel-modules`) или делать это вручную через кастомный `ModuleServiceProvider`, который сканирует папки модулей.

В `composer.json` может потребоваться настройка PSR-4 (хотя внутри `app/` Laravel по умолчанию резолвит всё под неймспейсом `App\`):
```json
"autoload": {
    "psr-4": {
        "App\\": "app/",
        "Modules\\": "app/Modules/" 
    }
}
```
