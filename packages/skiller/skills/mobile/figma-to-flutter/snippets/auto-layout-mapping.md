# Figma Auto-layout → Flutter

Values are from `get_metadata` (figma-mcp-core), not from the screenshot.

| Figma Auto-layout | Flutter |
|:--|:--|
| `layoutMode: HORIZONTAL` | `Row(...)` |
| `layoutMode: VERTICAL` | `Column(...)` |
| `layoutMode: NONE` | `Stack` + `Positioned(left/top/width/height)` |
| `itemSpacing: 16` | `spacing: 16` (Flutter 3.27+) or `SizedBox(width/height: 16)` between children |
| `paddingLeft/Right/Top/Bottom` | `Padding(padding: EdgeInsets.only(...))` |
| `primaryAxisAlignItems: CENTER` | `mainAxisAlignment: MainAxisAlignment.center` |
| `primaryAxisAlignItems: SPACE_BETWEEN` | `mainAxisAlignment: MainAxisAlignment.spaceBetween` |
| `counterAxisAlignItems: CENTER` | `crossAxisAlignment: CrossAxisAlignment.center` |
| `primaryAxisSizingMode: FIXED` | `SizedBox(width/height: X)` |
| `primaryAxisSizingMode: AUTO` | without restrictions (`mainAxisSize: MainAxisSize.min`) |
| `primaryAxisSizingMode: FILL` | `Expanded(child: ...)` |
| `layoutWrap: WRAP` | `Wrap(spacing/runSpacing: ...)` |
| `constraints.horizontal: SCALE` | `width: double.infinity` |
| `fills: [{ type: IMAGE }]` | `DecorationImage(image: AssetImage(...))` (do not download for analysis) |

Padding/colors - via theme tokens (`context.space.md`, `Theme.of(context).colorScheme`), are not literals.
