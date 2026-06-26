---
name: figma-mcp-core
bucket: architect
version: 0.1.0
description: "Дисциплина работы с официальным Figma Dev Mode MCP: реальные инструменты (get_metadata, get_variable_defs, get_code, get_code_connect_map, get_screenshot, search_design_system), запрет извлечения значений из скриншотов, selection-driven алгоритм, извлечение design tokens в W3C tokens.json, переиспользование компонентов через Code Connect, аудит design-system, антипаттерны. Активировать при любой задаче по реализации UI из Figma через подключённый MCP-сервер, до маппинга в конкретный фреймворк."
risk: read
persona: architect
tags: [figma, mcp, design-system, design-tokens, dev-mode, code-connect, ui]
requires: []
produces_for: [figma-to-vue, figma-to-flutter]
outputs: ["docs/design/tokens.json", "docs/design/figma-audit.md"]
snippets: [tokens.json, design-system-checklist.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Figma Dev Mode MCP — структурная дисциплина

## Контекст

Базовый, фреймворк-агностичный скилл работы с **официальным Figma Dev Mode MCP-сервером**. Задаёт
агенту дисциплину: читать данные через MCP-инструменты, а не угадывать по картинке. Конкретный
маппинг в код — в производных скиллах `figma-to-vue` (Vue/Tailwind) и `figma-to-flutter` (Flutter).

Активировать, когда:

- в проекте подключён Figma MCP (Dev Mode desktop-сервер или remote) и нужно реализовать экран/компонент;
- нужно извлечь design tokens (цвета, типографику, отступы) из Figma в код;
- нужен аудит design-system Figma-файла перед разработкой;
- агент начал «угадывать» цвета/размеры по скриншоту вместо чтения переменных.

**Ключевой факт об инструменте.** Dev Mode MCP — **selection-driven и code-first**: он отдаёт контекст
по *текущему выделению в Figma desktop* или по node-id из вставленной ссылки, а НЕ обходит дерево
документа по `fileKey` (это модель REST API, не MCP). Алгоритм ниже построен от выделения.

## Реальные инструменты Figma Dev Mode MCP

| Инструмент | Что возвращает | Когда вызывать |
|:--|:--|:--|
| `get_metadata` | разреженное дерево выделения: layer id, name, type, position, size | первый шаг — карта структуры экрана, дешёвый по токенам |
| `get_variable_defs` | переменные и стили (design tokens), использованные в выделении | извлечение токенов; до генерации кода |
| `get_code` (синоним `get_design_context`) | код по выделению; по умолчанию React+Tailwind, подхватывает фреймворк проекта | как **черновик-референс** структуры/значений, не как финальный код |
| `get_code_connect_map` | маппинг Figma node id → компоненты Code Connect в кодовой базе | проверить, есть ли уже готовый компонент под этот узел |
| `get_screenshot` | скриншот выделения | **только** визуальная сверка результата; НЕ источник значений |
| `search_design_system` (remote) | поиск компонентов/переменных в подключённых библиотеках | найти canonical-компонент/токен вместо дублирования |

## Принципиальная позиция: NO SCREENSHOT FOR VALUES

`get_screenshot` допустим **исключительно** для финальной визуальной сверки «похоже/не похоже».
Извлекать из него значения — антипаттерн: скриншот не содержит точных токенов (цвета и размеры
округляются визуально), не передаёт иерархию и override-цепочки, не отдаёт auto-layout-параметры.
Все значения берутся из `get_variable_defs` и `get_metadata`.

## Алгоритм

1. **Получить выделение.** Попросить пользователя выделить нужный фрейм/компонент в Figma desktop
   (или дать ссылку с node-id). Без выделения MCP не имеет контекста.

2. **Карта структуры.** `get_metadata` → дерево узлов (id, name, type, position, size). Определить
   корневой фрейм экрана, дочерние компоненты, текстовые узлы. Узлы с осмысленными именами
   (`card/surface`, а не `Rectangle 42`) — кандидаты в компоненты.

3. **Переиспользование.** `get_code_connect_map` по выделению → если узел уже связан с компонентом
   кодовой базы, **использовать существующий компонент**, не генерировать заново. Для библиотечных
   элементов — `search_design_system`.

4. **Токены.** `get_variable_defs` → все переменные/стили выделения. Структурировать в `tokens.json`
   по W3C Design Token Format (см. `snippets/tokens.json`). Если переменные имеют Modes (light/dark) —
   зафиксировать значение по каждому моду.

5. **Черновик кода.** `get_code` → читать как референс структуры и связей токенов, НЕ копировать
   дословно. Финальный код пишет производный скилл под конвенции проекта (`figma-to-vue`/`figma-to-flutter`).

6. **Сверка.** После генерации — один `get_screenshot` для визуального сравнения. Расхождения чинить
   через данные (шаги 2–4), не подгонкой «на глаз».

## Формат tokens.json

W3C Design Token Format — единый промежуточный артефакт для всех платформ. Полный пример с color/
spacing/typography/border-radius и multi-mode — в `snippets/tokens.json`. Имя токена сохраняет
семантику из Figma (`figma:variable/Primary/Blue-500` в `$description`).

## Аудит design-system

Перед разработкой по незнакомому файлу — пройти чеклист готовности design-system
(`snippets/design-system-checklist.md`): все цвета в Variables, типографика только стилями, spacing
кратен базовой сетке, интерактивные компоненты имеют все Variants, dark mode как Variable Mode и т.д.

## Типичные антипаттерны Figma и действия агента

- **Цвет без переменной** (`fills` с сырым `color`, не привязанным к Variable): создать токен
  `color/unnamed/hex-XXXXXX`, пометить в аудите «требует именования дизайнером».
- **Фиксированные размеры вместо Auto-layout** (`layoutMode: NONE`): зафиксировать как константу,
  пометить «not responsive», НЕ генерировать flex/Expanded.
- **Абсолютное позиционирование детей**: читать x/y/w/h, маппить в Stack/absolute (см. производные скиллы).
- **Image fills** (`type: IMAGE`): НЕ скачивать для анализа; использовать ref как placeholder-asset.

## Выходные данные

- `docs/design/tokens.json` — извлечённые токены (W3C).
- `docs/design/figma-audit.md` — отчёт аудита design-system (при ревизии файла).

## Чеклист качества

- [ ] Структура получена через `get_metadata`, не угадана по картинке.
- [ ] Токены извлечены через `get_variable_defs`, не из `get_screenshot`.
- [ ] Проверён `get_code_connect_map` — существующие компоненты переиспользованы.
- [ ] `get_screenshot` использован только для финальной сверки.
- [ ] `tokens.json` валиден по W3C-формату, имена токенов семантичны.
- [ ] Маппинг в код делегирован `figma-to-vue` / `figma-to-flutter`.

## Ссылки

- snippets/tokens.json — W3C-пример с multi-mode.
- snippets/design-system-checklist.md — чеклист готовности design-system.
- [Figma Dev Mode MCP — Tools and prompts](https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/)
- [Guide to the Figma MCP server](https://help.figma.com/hc/en-us/articles/32132100833559-Guide-to-the-Figma-MCP-server)
- [W3C Design Tokens Format](https://design-tokens.github.io/community-group/format/)
- Связанные скиллы: `figma-to-vue`, `figma-to-flutter`.
