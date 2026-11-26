# Playwright MCP

## What is this

Playwright MCP from Microsoft gives Claude Code browser control: navigation, clicks, input,
screenshots, expectations. Needed for E2E-tests and web automation.

- Repository: <https://github.com/microsoft/playwright-mcp>
- npm-package: `@playwright/mcp`

## Modes

| Mode | Description | When |
|---|---|---|
| Snapshot (default) | works with accessibility-tree, without GUI | CI, functional tests |
| Vision (`--vision`) | screenshots, agent «sees» page | visual verification, debug |

## Installation

Preset (opt-in):

```bash
skiller integrate --mcp playwright
```

Preset - `configs/claude-code/mcp/playwright.json`:

```json
{
  "command": "npx",
  "args": ["@playwright/mcp@0.0.78", "--headless", "--output-dir", ".playwright-mcp"]
}
```

**Pinned version** (`0.0.78`, verified `npm view @playwright/mcp version` 2026-08-01) — not
`@latest`: unpinned version drifts between sessions and changes server behavior unnoticed
(P5.3/P5.6). **`--output-dir .playwright-mcp`** fixes the reason why screenshots with explicit
(not auto-generated) `filename` resolved from CWD agent and settled at the root of the project in spite of
tool description («Prefer relative file names to stay within the output directory») —
confirmed by fact on `dterema` (27 files in one phase), not according to the documentation. `.playwright-mcp/`
is already in `.gitignore`. Media - three files (provider parity): `configs/claude-code/mcp/
playwright.json`, `configs/claude-code/mcp/bindings.json`, `configs/codex/mcp/bindings.json`.

**`.gitignore`:** harness does not distribute managed `.gitignore`-template - checked
on this repository (`.playwright-mcp/` was never there, added by this item'ohm). Project,
connected preset `playwright`, must add it himself `.playwright-mcp/` to your `.gitignore`.

Browsers are installed separately: `npx playwright install chromium`.

## Tools (part)

`browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`,
`browser_take_screenshot`, `browser_wait_for`, `browser_select_option`, `browser_evaluate`.

## Limitations

::: warning Vision roads by tokens
Each screenshot is worth thousands of tokens. For functional tests use snapshot, vision —
for visual verification only.
:::

- Chromium is stable in headless; Firefox/WebKit headless — experimental.
- On ARM/embedded headless Chromium may not rise - drive it dev/CI, is not on the device.
- For authorized sites, use storageState or `browser_evaluate` for cookies.

Thematically close - skill `quality/playwright-e2e` (config `playwright.config`, storageState,
data isolation, CI): MCP-server gives interactive control of the browser by the agent, skill -
the discipline of setting up the tests themselves.
