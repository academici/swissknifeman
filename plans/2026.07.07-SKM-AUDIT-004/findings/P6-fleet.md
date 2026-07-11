# P6.4 — Fleet-ремонт: Agelto + прочие PHP-проекты

Дата: 2026-07-07.

## Fleet-скан (`maind doctor --audit pao`, 20 проектов)

```
agelto             pao⚠(missing: composer require laravel/pao --dev)
diabox             pao·n-a
flexcrm            pao✓
axiomaerpsdk       pao·n-a
azguard            pao✓
botkit             pao✓
vaulter            pao✓
swissknifeman      pao·n-a
axiomastudio       pao·n-a
corex              pao✓
memster            pao✓
cms                pao✓
edufy              pao✓
vintera            pao·n-a
dterema            pao✓
dterema-app        pao·n-a
sibintek-insiders  pao✓
chatom             pao✓
perplexity-web-mcp pao·n-a
loqum              pao·n-a
```

**Вывод скана:** дыра F-pao-1 (P6.1) была локальной к моменту онбординга Agelto —
все остальные PHP/Laravel-проекты флота (`vaulter`, `azguard`, `corex`, `memster`,
`cms`, `edufy`, `dterema`, `sibintek-insiders`, `chatom`, `botkit`, `flexcrm`)
уже имеют `laravel/pao` установленным (verified: `ls <path>/vendor/laravel/pao`
на `vaulter`/`corex` → `composer.json` внутри пакета, на `memster`/`edufy` →
бинарь `art`). Единственный затронутый проект — **Agelto**.

## Agelto — Boost-гигиена (НЕ про PAO, см. D9)

`.mcp.json` содержал orphaned запись `laravel-boost` (`php artisan boost:mcp`) без
установленного composer-пакета — `vendor/laravel/boost` отсутствовал. По решению
владельца (Approval Owner) — **доустановлен**: `composer require laravel/boost:^2.4
--dev` в `/home/vostrikov/projects/agelto/agelto`. Пакет и зависимости
(`laravel/mcp` v0.8.2, `laravel/roster` v0.5.1, `laravel/boost` v2.4.11) установлены,
`composer.json`/`composer.lock` Agelto обновлены. Post-install хук
`artisan package:discover` вернул код ошибки — **не связано с установкой**: этот шелл
не имеет доступа к БД приложения (`could not find driver (Connection: pgsql, Host:
postgres, …)`, Agelto рассчитан на docker-окружение) — composer тем не менее
подтвердил «3 installs», файлы на месте. MCP-запись `laravel-boost` в `.mcp.json`
теперь не-orphaned.

## Agelto — PAO: заблокирован каскадом зависимостей (эскалация)

`composer require laravel/pao --dev` **упал** — конфликт версий, глубже, чем
диагностика P6.1 могла предвидеть (та проверяла только PHP ≥ 8.3, что выполнено):

1. `laravel/pao` (все версии v0.1.0–v1.1.2) требуют `pestphp/pest` **^4.6.3+ / ^4.4.3+**
   — в Agelto зафиксирован `pestphp/pest: ^3.8` (`v3.8.6`).
2. Апгрейд `pestphp/pest` до `^4.6` тянет `phpunit/phpunit ^12.5.16+` — но в Agelto
   `phpunit/phpunit` зафиксирован отдельно в `require-dev` как `^11.5.50`, и это
   requirement не запрошен на апдейт.

Т.е. `laravel/pao` требует **связной мини-миграции тест-стека Agelto**
(`pest v3→v4` + `phpunit v11→v12`), а не одиночный `composer require`. Это задевает
существующие тесты Agelto (Pest 4 меняет часть API/поведения относительно Pest 3) —
масштаб решения по Agelto-специфике, не по контракту swissknifeman. Обе попытки
(`composer require laravel/pao --dev`, затем с явным `pestphp/pest:^4.6
pestphp/pest-plugin-laravel laravel/pao --with-all-dependencies`) откачены composer'ом
автоматически (`composer.json`/`composer.lock` Agelto не тронуты для PAO — `git diff`
пуст после отката).

**Решение (Approval Owner):** остановиться, эскалировать; апгрейд тест-стека Agelto —
отдельная задача вне этого плана (владелец Agelto решает, когда мигрировать
`pest`/`phpunit`; после миграции — переустановить `laravel/pao`, doctor-гейт P6.3
подтвердит `pao✓`).

## Validation

- `maind doctor --audit pao` прогнан по всем 20 проектам флота (см. таблицу выше).
- Agelto: `laravel/boost` установлен и запушен в `composer.json`/`composer.lock`
  (verified `grep`); `laravel/pao` — **не установлен**, блокер задокументирован выше.
- `git -C agelto status --short composer.json composer.lock` → только Boost-изменения
  (PAO-попытки отменены composer'ом целиком, дифф от них отсутствует).
