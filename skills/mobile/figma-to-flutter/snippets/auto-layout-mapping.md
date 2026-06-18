# Figma Auto-layout → Flutter

Значения — из `get_metadata` (figma-mcp-core), не из скриншота.

| Figma Auto-layout | Flutter |
|:--|:--|
| `layoutMode: HORIZONTAL` | `Row(...)` |
| `layoutMode: VERTICAL` | `Column(...)` |
| `layoutMode: NONE` | `Stack` + `Positioned(left/top/width/height)` |
| `itemSpacing: 16` | `spacing: 16` (Flutter 3.27+) или `SizedBox(width/height: 16)` между детьми |
| `paddingLeft/Right/Top/Bottom` | `Padding(padding: EdgeInsets.only(...))` |
| `primaryAxisAlignItems: CENTER` | `mainAxisAlignment: MainAxisAlignment.center` |
| `primaryAxisAlignItems: SPACE_BETWEEN` | `mainAxisAlignment: MainAxisAlignment.spaceBetween` |
| `counterAxisAlignItems: CENTER` | `crossAxisAlignment: CrossAxisAlignment.center` |
| `primaryAxisSizingMode: FIXED` | `SizedBox(width/height: X)` |
| `primaryAxisSizingMode: AUTO` | без ограничений (`mainAxisSize: MainAxisSize.min`) |
| `primaryAxisSizingMode: FILL` | `Expanded(child: ...)` |
| `layoutWrap: WRAP` | `Wrap(spacing/runSpacing: ...)` |
| `constraints.horizontal: SCALE` | `width: double.infinity` |
| `fills: [{ type: IMAGE }]` | `DecorationImage(image: AssetImage(...))` (не скачивать для анализа) |

Отступы/цвета — через токены темы (`context.space.md`, `Theme.of(context).colorScheme`), не литералами.
