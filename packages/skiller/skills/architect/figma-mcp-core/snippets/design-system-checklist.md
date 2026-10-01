# Readiness checklist Figma design-system

Walk through an unfamiliar file before starting development. Take data via `get_metadata` /
`get_variable_defs`, not from the screenshot.

- [ ] All colors are displayed in Variables/Styles (no raw `fills.color` without binding).
- [ ] Typography is set to text styles only (no inline-fonts without style).
- [ ] Spacing is a multiple of the base unit (4px or 8px grid).
- [ ] All interactive components have Variants: Default, Hover, Active, Disabled, Focus.
- [ ] Components with text have a long text option (overflow-test).
- [ ] Icons - separate Component Set, are not bitmaps.
- [ ] Dark mode — separate Variable Mode, rather than duplicate components.
- [ ] Responsive — Auto-layout + Min/Max width instead of fixed frames.
- [ ] Layer names are semantic (`card/surface`, and not `Rectangle 42`).
- [ ] Components published in Team Library (are not duplicated across pages) — check `search_design_system`.
- [ ] Nodes with ready-made codebase components are visible in `get_code_connect_map` (reuse).
