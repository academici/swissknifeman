# Figma Auto-layout → Tailwind / flexbox

Значения — из `get_metadata`/`get_code` (figma-mcp-core), не из скриншота.

| Figma Auto-layout | Tailwind | Чистый CSS |
|:--|:--|:--|
| `layoutMode: HORIZONTAL` | `flex flex-row` | `display:flex; flex-direction:row` |
| `layoutMode: VERTICAL` | `flex flex-col` | `display:flex; flex-direction:column` |
| `layoutMode: NONE` | (фикс. размеры) | absolute-позиционирование детей |
| `itemSpacing: 16` | `gap-md` | `gap:16px` |
| `paddingLeft/Right/Top/Bottom` | `pl-* pr-* pt-* pb-*` | `padding: …` |
| `primaryAxisAlignItems: CENTER` | `justify-center` | `justify-content:center` |
| `primaryAxisAlignItems: SPACE_BETWEEN` | `justify-between` | `justify-content:space-between` |
| `counterAxisAlignItems: CENTER` | `items-center` | `align-items:center` |
| `primaryAxisSizingMode: FIXED` | `w-[Xpx]` / `h-[Xpx]` | фиксированный размер |
| `primaryAxisSizingMode: AUTO` | `w-fit` / `h-fit` | `width:fit-content` |
| `primaryAxisSizingMode: FILL` | `flex-1` | `flex:1` |
| `layoutWrap: WRAP` | `flex-wrap` | `flex-wrap:wrap` |
| `constraints.horizontal: SCALE` | `w-full` | `width:100%` |

Отступы — только spacing-утилитами из `@theme` (`gap-md`, `p-lg`), без магических `gap-[16px]`.
