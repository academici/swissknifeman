---
name: cross-layer-change-checklist
bucket: general
version: 0.1.0
description: "Универсальный checklist для изменений, затрагивающих несколько слоев: код, доступы, UI, документацию и тесты."
risk: read
persona: oss-dev
tags: [checklist, workflow]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Cross-layer Change Checklist

## Когда активировать

Используйте этот skill при изменениях, которые проходят через несколько слоев системы.

## Обязательная цепочка проверки

1. **Домен и контракты**
   - Enum/DTO/сигнатуры синхронизированы.
   - Нет скрытого изменения смыслов в названиях.

2. **Авторизация**
   - Permission enum ↔ policy method ↔ gate definition согласованы.
   - Негативные кейсы доступа покрыты.

3. **HTTP/API**
   - Route → Controller → Action/Service цепочка целостна.
   - Контроллер остался тонким.

4. **Frontend**
   - UI-триггеры обновлены.
   - Нет хардкода URL при наличии route/action helpers.
   - Обработаны состояния ошибок и запрета доступа.

5. **Данные/миграции**
   - Схема и модельные контракты согласованы.
   - Переименования/переносы не ломают существующие связи.

6. **Документация и контекст агентов**
   - Обновлены релевантные docs (`docs/workflow/*`, `docs/dev/*`, глоссарий и т.д.), если меняется поведение или термины.
   - Если меняются архитектурные договорённости или правила для ИИ: правки в `.ai/guidelines/` и при узком контексте в `.ai/skills/*` (в т.ч. триггеры в `description`), затем `php artisan boost:update`.

7. **Тесты**
   - Happy path.
   - Forbidden/validation path.
   - Контрактные тесты на измененные переходы/правила.

## Формат финальной самопроверки

```text
[x] Domain
[x] Authorization
[x] HTTP/API
[x] Frontend
[x] Data/Migrations
[x] Docs
[x] Tests
Остаточные риски:
```
