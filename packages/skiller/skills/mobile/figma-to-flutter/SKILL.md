---
name: figma-to-flutter
bucket: mobile
version: 0.1.0
description: "Map Figma Dev Mode MCP design to Flutter: Auto-layout → Row/Column/Expanded/Padding, tokens.json → ThemeData (ColorScheme/TextTheme), Variable Modes light/dark → ThemeData(brightness), absolute positioning → Stack/Positioned, image fills → DecorationImage. Activate when building Flutter screens/widgets from Figma; runs on top of figma-mcp-core."
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

Convert Figma Dev Mode MCP output into Flutter widgets + `ThemeData`. Figma data extraction (tools, tokens, no-screenshot discipline) lives in `figma-mcp-core`.

Activate when:
- building a Flutter screen/widget from a Figma selection via connected MCP;
- porting `tokens.json` (from `figma-mcp-core`) into `ThemeData` (`ColorScheme`, `TextTheme`);
- mapping Variable Modes light/dark to `ThemeData(brightness)`;
- mapping Figma Auto-layout to `Row`/`Column`/`Expanded`/`Padding`.

`get_code` (Dev Mode MCP) returns React+Tailwind by default — for Flutter use it only as structure/value reference; write final Dart from the tables below.

## Algorithm

1. **Figma data.** Run `figma-mcp-core`: `get_metadata` (structure), `get_variable_defs` (tokens → `tokens.json`), `get_code_connect_map` (existing widgets).
2. **Tokens → ThemeData** (see `snippets/app_theme.dart`): colors → `ColorScheme`, typography → `TextTheme`, spacing → extension (`snippets/spacing_extension.dart`). Do NOT hardcode colors/sizes in widgets — reference the theme.
3. **Structure → widget tree.** Map Auto-layout per `snippets/auto-layout-mapping.md`: HORIZONTAL→`Row`, VERTICAL→`Column`, FILL→`Expanded`, padding→`Padding`, itemSpacing→`spacing:`/`SizedBox`.
4. **Modes → themes.** Variable Modes light/dark → two `ThemeData` (`brightness: light/dark`); switch via `MaterialApp(theme/darkTheme)`.
5. **Absolute positioning** (`layoutMode: NONE`): child x/y/w/h → `Stack` + `Positioned`.
6. **Image fills** (`type: IMAGE`): `DecorationImage` with asset ref; do not download for analysis.
7. **Verify.** One `get_screenshot` for visual diff; fix discrepancies via tokens.

## Auto-layout → Flutter

Full table: `snippets/auto-layout-mapping.md`. Short: `HORIZONTAL`→`Row`, `VERTICAL`→`Column`; `itemSpacing`→`spacing:` (Flutter 3.27+) or `SizedBox`; `padding*`→`Padding(EdgeInsets…)`; `primaryAxisAlignItems`→`mainAxisAlignment`; `counterAxisAlignItems`→`crossAxisAlignment`; `FILL`→`Expanded`; `AUTO`→no constraints; `FIXED`→`SizedBox`.

## Quality checklist

- [ ] Tokens moved to `ThemeData` (ColorScheme/TextTheme), no hardcode in widgets.
- [ ] Spacing via extension/theme constants, no magic numbers.
- [ ] Auto-layout mapped to Row/Column/Expanded/Padding per table.
- [ ] light/dark → two `ThemeData(brightness)`, not duplicated widgets.
- [ ] Absolute nodes → Stack/Positioned; image fills → DecorationImage (no download).
- [ ] Existing widgets from `get_code_connect_map` reused.

## Links

- snippets/app_theme.dart — ThemeData (ColorScheme/TextTheme) from tokens.json + dark.
- snippets/spacing_extension.dart — extension for spacing-token access.
- snippets/auto-layout-mapping.md — Figma Auto-layout → Flutter table.
- Related skills: `figma-mcp-core`.
- [Flutter ThemeData](https://api.flutter.dev/flutter/material/ThemeData-class.html)

<!-- ru-source-sha256: e08ed4aa4086898fd7117ff76e601a0eac4b697c5757cf195fab250744d6ad9a -->
