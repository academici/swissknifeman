---
name: figma-to-flutter
bucket: mobile
version: 0.1.0
description: "Маппинг дизайна из Figma Dev Mode MCP в Flutter: Auto-layout → Row/Column/Expanded/Padding, tokens.json → ThemeData (ColorScheme/TextTheme), Variable Modes light/dark → ThemeData(brightness), абсолютное позиционирование → Stack/Positioned, image fills → DecorationImage. Активировать при реализации Flutter-экранов/виджетов по Figma; работает поверх figma-mcp-core."
risk: write
persona: architect
tags: [figma, flutter, dart, mobile, design-tokens, theming, auto-layout]
requires: [figma-mcp-core]
produces_for: []
outputs: ["lib/theme/app_theme.dart"]
snippets: [app_theme.dart, spacing_extension.dart, auto-layout-mapping.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Figma → Flutter

## Контекст

Маппинг дизайна, извлечённого через Figma Dev Mode MCP, в код **Flutter**. Получение данных из Figma
(инструменты, токены, дисциплина no-screenshot) — в `figma-mcp-core`; здесь — конвертация структуры и
токенов в Flutter-виджеты и `ThemeData`.

Активировать, когда:

- реализуешь Flutter-экран/виджет по выделению в Figma через подключённый MCP;
- переносишь `tokens.json` (из `figma-mcp-core`) в `ThemeData` (`ColorScheme`, `TextTheme`);
- маппишь Variable Modes light/dark в `ThemeData(brightness)`;
- маппишь Figma Auto-layout в `Row`/`Column`/`Expanded`/`Padding`.

`get_code` Dev Mode MCP по умолчанию отдаёт React+Tailwind — для Flutter использовать его лишь как
референс структуры/значений, финальный Dart-код писать по таблицам ниже.

## Алгоритм

1. **Данные из Figma.** Отработать `figma-mcp-core`: `get_metadata` (структура), `get_variable_defs`
   (токены → `tokens.json`), `get_code_connect_map` (существующие виджеты).
2. **Токены → ThemeData.** Перенести `tokens.json` в `ThemeData` (см. `snippets/app_theme.dart`):
   цвета → `ColorScheme`, типографика → `TextTheme`, spacing → extension (`snippets/spacing_extension.dart`).
   НЕ хардкодить цвета/размеры в виджетах — ссылаться на тему.
3. **Структура → дерево виджетов.** Маппить Auto-layout по таблице `snippets/auto-layout-mapping.md`:
   HORIZONTAL→`Row`, VERTICAL→`Column`, FILL→`Expanded`, padding→`Padding`, itemSpacing→`spacing:`/`SizedBox`.
4. **Modes → темы.** Variable Modes light/dark → два `ThemeData` (`brightness: light/dark`),
   переключение через `MaterialApp(theme/darkTheme)`.
5. **Абсолютное позиционирование** (`layoutMode: NONE`): дочерние x/y/w/h → `Stack` + `Positioned`.
6. **Image fills** (`type: IMAGE`): `DecorationImage` с asset-ссылкой; не скачивать для анализа.
7. **Сверка.** Один `get_screenshot` — визуальное сравнение, расхождения чинить через токены.

## Маппинг Auto-layout → Flutter

Полная таблица — `snippets/auto-layout-mapping.md`. Кратко: `HORIZONTAL`→`Row`, `VERTICAL`→`Column`;
`itemSpacing`→`spacing:` (Flutter 3.27+) или `SizedBox`; `padding*`→`Padding(EdgeInsets…)`;
`primaryAxisAlignItems`→`mainAxisAlignment`; `counterAxisAlignItems`→`crossAxisAlignment`;
`FILL`→`Expanded`; `AUTO`→без ограничений; `FIXED`→`SizedBox`.

## Чеклист качества

- [ ] Токены перенесены в `ThemeData` (ColorScheme/TextTheme), без хардкода в виджетах.
- [ ] Spacing — через extension/константы темы, не магические числа.
- [ ] Auto-layout смаппен в Row/Column/Expanded/Padding по таблице.
- [ ] light/dark — два `ThemeData(brightness)`, не дублированные виджеты.
- [ ] Абсолютные узлы → Stack/Positioned; image fills → DecorationImage (без скачивания).
- [ ] Существующие виджеты из `get_code_connect_map` переиспользованы.

## Ссылки

- snippets/app_theme.dart — ThemeData (ColorScheme/TextTheme) из tokens.json + dark.
- snippets/spacing_extension.dart — extension доступа к spacing-токенам.
- snippets/auto-layout-mapping.md — таблица Figma Auto-layout → Flutter.
- Связанные скиллы: `figma-mcp-core`.
- [Flutter ThemeData](https://api.flutter.dev/flutter/material/ThemeData-class.html)
