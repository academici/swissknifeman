# Playwright MCP

## Что это

Playwright MCP от Microsoft даёт Claude Code управление браузером: навигация, клики, ввод,
скриншоты, ожидания. Нужен для E2E-тестов и веб-автоматизации.

- Репозиторий: <https://github.com/microsoft/playwright-mcp>
- npm-пакет: `@playwright/mcp`

## Режимы

| Режим | Описание | Когда |
|---|---|---|
| Snapshot (по умолчанию) | работает с accessibility-деревом, без GUI | CI, функциональные тесты |
| Vision (`--vision`) | скриншоты, агент «видит» страницу | визуальная верификация, дебаг |

## Установка

Пресетом (opt-in):

```bash
skiller integrate --mcp playwright
```

Пресет — `configs/claude-code/mcp/playwright.json`:

```json
{
  "command": "npx",
  "args": ["@playwright/mcp@0.0.78", "--headless", "--output-dir", ".playwright-mcp"]
}
```

**Версия пинована** (`0.0.78`, проверено `npm view @playwright/mcp version` 2026-08-01) — не
`@latest`: незакреплённая версия дрейфует между сессиями и меняет поведение сервера незаметно
(P5.3/P5.6). **`--output-dir .playwright-mcp`** чинит причину, по которой скриншоты с явным
(не auto-generated) `filename` резолвились от CWD агента и оседали в корне проекта вопреки
описанию инструмента («Prefer relative file names to stay within the output directory») —
подтверждено фактом на `dterema` (27 файлов за одну фазу), не по документации. `.playwright-mcp/`
уже в `.gitignore`. Носитель — три файла (паритет провайдеров): `configs/claude-code/mcp/
playwright.json`, `configs/claude-code/mcp/bindings.json`, `configs/codex/mcp/bindings.json`.

**`.gitignore`:** harness не раздаёт консьюмерам управляемый `.gitignore`-шаблон — проверено
на этом репозитории (`.playwright-mcp/` там не было ни разу, добавлено этим item'ом). Проект,
подключивший пресет `playwright`, обязан сам добавить `.playwright-mcp/` в свой `.gitignore`.

Браузеры ставятся отдельно: `npx playwright install chromium`.

## Инструменты (часть)

`browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`,
`browser_take_screenshot`, `browser_wait_for`, `browser_select_option`, `browser_evaluate`.

## Ограничения

::: warning Vision дорог по токенам
Каждый скриншот — тысячи токенов. Для функциональных тестов используй snapshot, vision —
только для визуальной верификации.
:::

- Chromium стабилен в headless; Firefox/WebKit headless — экспериментально.
- На ARM/embedded headless Chromium может не подняться — гоняй на dev/CI, не на устройстве.
- Для авторизованных сайтов используй storageState или `browser_evaluate` для cookies.

Тематически рядом — скилл `quality/playwright-e2e` (конфиг `playwright.config`, storageState,
изоляция данных, CI): MCP-сервер даёт интерактивный контроль браузера агентом, скилл —
дисциплину настройки самих тестов.
