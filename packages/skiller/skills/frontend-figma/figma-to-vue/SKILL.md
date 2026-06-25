---
name: figma-to-vue
bucket: frontend-figma
version: 0.1.0
description: "Маппинг дизайна из Figma Dev Mode MCP в Vue + Tailwind v4: Auto-layout → flexbox/grid, tokens.json → @theme-токены (CSS-first), Variants → class-variance-authority (cva), Variable Modes → тёмная тема (.dark), переиспользование компонентов через Code Connect. Активировать при реализации Vue-экранов/компонентов по Figma; работает поверх figma-mcp-core."
risk: write
persona: oss-dev
tags: [figma, vue, tailwind, tailwindcss-v4, cva, design-tokens, dark-mode, auto-layout]
requires: [figma-mcp-core]
produces_for: [tailwind-conventions, reka-ui-cva, naive-ui-theming, dark-mode]
outputs: ["src/assets/theme.css"]
snippets: [theme.css, variant-component.vue, auto-layout-mapping.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Figma → Vue + Tailwind

## Контекст

Маппинг дизайна, извлечённого через Figma Dev Mode MCP, в код **Vue 3 + Tailwind CSS v4**. Получение
данных из Figma (инструменты, токены, дисциплина no-screenshot) — в `figma-mcp-core`; здесь —
конвертация структуры и токенов в Vue-компоненты и Tailwind-тему.

Активировать, когда:

- реализуешь Vue-экран/компонент по выделению в Figma через подключённый MCP;
- переносишь `tokens.json` (из `figma-mcp-core`) в Tailwind v4 `@theme`;
- маппишь Figma Variants в варианты компонента через `cva`;
- маппишь Variable Modes (light/dark) в тёмную тему `.dark`.

Конвенции Tailwind v4, cva и тёмной темы — в скиллах `tailwind-conventions`, `reka-ui-cva`,
`naive-ui-theming`, `dark-mode`; этот скилл — мост от Figma к ним.

## Алгоритм

1. **Данные из Figma.** Отработать `figma-mcp-core`: `get_metadata` (структура), `get_variable_defs`
   (токены → `tokens.json`), `get_code_connect_map` (готовые компоненты).
2. **Токены → `@theme`.** Перенести `tokens.json` в Tailwind v4 CSS-first `@theme` (см.
   `snippets/theme.css`): имена с префиксами генерируют утилиты (`--color-primary` → `bg-primary`).
   НЕ создавать `tailwind.config.js` — токены живут в CSS (см. `tailwind-conventions`).
3. **Структура → разметка.** Маппить Auto-layout в flexbox/grid по таблице
   `snippets/auto-layout-mapping.md`. Не хардкодить отступы — использовать spacing-утилиты из токенов.
4. **Variants → cva.** Figma Component Set (Default/Hover/Active/Disabled) → варианты `cva`
   (см. `snippets/variant-component.vue`), классы через `cn()`.
5. **Modes → тёмная тема.** Variable Modes light/dark → значения токенов под `.dark` в `@theme`,
   утилиты `dark:*` (см. `dark-mode`).
6. **Сверка.** Один `get_screenshot` — визуально сравнить результат, расхождения чинить через токены.

## Маппинг Auto-layout → Tailwind/flexbox

Полная таблица — `snippets/auto-layout-mapping.md`. Кратко: `layoutMode: HORIZONTAL/VERTICAL` →
`flex flex-row/flex-col`; `itemSpacing` → `gap-*`; `padding*` → `p*`; `primaryAxisSizingMode: FILL` →
`flex-1`; `AUTO` → `w-fit`; выравнивание по осям → `justify-*` / `items-*`.

## Чеклист качества

- [ ] Токены перенесены в `@theme` (CSS-first), без `tailwind.config.js`.
- [ ] Отступы/цвета — через утилиты токенов, без магических чисел.
- [ ] Auto-layout смаппен в flex/grid по таблице, не «на глаз».
- [ ] Variants реализованы через `cva` + `cn()`, не дублированием компонентов.
- [ ] Variable Modes light/dark смаппены в `.dark`/`dark:*`.
- [ ] Существующие компоненты из `get_code_connect_map` переиспользованы.

## Ссылки

- snippets/theme.css — Tailwind v4 `@theme` из tokens.json (+ `.dark` модов).
- snippets/variant-component.vue — компонент с cva-вариантами и cn().
- snippets/auto-layout-mapping.md — таблица Figma Auto-layout → Tailwind.
- Связанные скиллы: `figma-mcp-core`, `tailwind-conventions`, `reka-ui-cva`, `naive-ui-theming`, `dark-mode`.
