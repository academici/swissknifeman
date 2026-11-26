# Figma Auto-layout → Tailwind / flexbox

Values are from `get_metadata`/`get_code` (figma-mcp-core), not from the screenshot.

| Figma Auto-layout | Tailwind | Clean CSS |
|:--|:--|:--|
| `layoutMode: HORIZONTAL` | `flex flex-row` | `display:flex; flex-direction:row` |
| `layoutMode: VERTICAL` | `flex flex-col` | `display:flex; flex-direction:column` |
| `layoutMode: NONE` | (fixed dimensions) | absolute-positioning of children |
| `itemSpacing: 16` | `gap-md` | `gap:16px` |
| `paddingLeft/Right/Top/Bottom` | `pl-* pr-* pt-* pb-*` | `padding: …` |
| `primaryAxisAlignItems: CENTER` | `justify-center` | `justify-content:center` |
| `primaryAxisAlignItems: SPACE_BETWEEN` | `justify-between` | `justify-content:space-between` |
| `counterAxisAlignItems: CENTER` | `items-center` | `align-items:center` |
| `primaryAxisSizingMode: FIXED` | `w-[Xpx]` / `h-[Xpx]` | fixed size |
| `primaryAxisSizingMode: AUTO` | `w-fit` / `h-fit` | `width:fit-content` |
| `primaryAxisSizingMode: FILL` | `flex-1` | `flex:1` |
| `layoutWrap: WRAP` | `flex-wrap` | `flex-wrap:wrap` |
| `constraints.horizontal: SCALE` | `w-full` | `width:100%` |

Indents - only spacing-utilities from `@theme` (`gap-md`, `p-lg`), without magic `gap-[16px]`.
