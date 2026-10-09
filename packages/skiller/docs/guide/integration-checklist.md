# Project integration checklist

During integration swissknifeman you choose for the project, **whatever you want from the maximum
functionality**. There are two ways: interactive **wizard** (`skiller integrate`),
which goes through the checklist and applies the selection, and **manual** — same actions
with separate commands.

```bash
cd ~/projects/my-app
skiller integrate            # interactive (menu for each block)
skiller integrate --dry-run  # show the plan without writing anything down
skiller integrate --yes --bundle recommended   # no questions asked, ready set
```

## Levels (bundles)

Quick start without going through each item - `--bundle`:

| Bundle | Skills | Permissions | MCP | auto-approve | Memory | output-style | Hub |
|---|---|---|---|---|---|---|---|
| `minimal` | connect | — | — | — | — | lean | — |
| `recommended` (default for `--yes`) | connect | autodetect | context7¹ | strict | — | lean | yes |
| `full` | connect | autodetect | context7¹ | strict | brain `core`, federation | lean | yes |
| `custom` (default interactive) | asks each block | | | | | | |

`output-style` — the only item included **in all** bundles (even `minimal`):
token-saving terse-output is needed by the project regardless of the amount of other automation.

¹ In development environments (everything except obsidian-vault).

## Checklist (what can be included)

Each item gives, as the wizard turns on, a manual equivalent.

### 1. Skills (mandatory minimum)
Distributing registry skills to the project.
- **connect** — Claude Code via plugin marketplace (rules `.claude/settings.local.json`:
  `extraKnownMarketplaces` + `enabledPlugins`). Version = git SHA registry.
- **vendor** — Cursor and other agents (copies skills to `.cursor/skills` / `.ai/skills`).
- Profile/buckets - autodetect (`.obsidian/` → vault, `artisan`+`composer.json` → laravel,
  `composer.json` → php-package, otherwise standalone), is overridden by flags.
- **By default in EVERY project** (connect) are added, in addition to the profile:
  - curated plugin `core` (lightweight token-saving core CORE-skills; `--no-core` disables);
  - command plugin **`planner`** — intent commands `/planner:design|dev|review|research|fix` (kick
    model/effort for the task; offers them intent-router). Disable point by point -
    `enabledPlugins["planner@swissknifeman"]=false`. Availability checks `maind audit` (dimension `core`).
- Handles: `skiller connect` / `skiller vendor --agent cursor`.

### 2. Permissions-presets
Ready `allow/ask/deny` under the stack - less permission-prompts.
- Autodetect by markers (base + laravel/php-package/node/python/docker).
- Handles: `./scripts/apply-permissions.sh --target <project>`.
- More details: [Permissions](/harness/configs/claude-permissions).

### 3. MCP-servers (development environment)
Presets `.mcp.json` for working scenarios - poured in merge-only in
`<project>/.mcp.json` (`mcpServers`, other people's servers are intact, backup `*.bak`).
- Now there is one: **context7** (remote HTTP `mcp.context7.com/mcp`) — up-to-date
  documentation of libraries directly in the agent context.
- Gate «development environment»: is placed in everything **except** obsidian-vault. `recommended`/
  `full` are enabled by default, `minimal` — no, `custom` — asks.
- Server presets - `configs/claude-code/mcp/<name>.json`.

### 4. auto-approve (per-project)
PreToolUse-hook that parses **all** command line (compound commands), modes
`strict|permissive|bypass|off`.
- Wizard writes `.claude/auto-approve.env.ini` (MODE) + registers a hook on
  `PreToolUse` (Bash + ExitPlanMode) in `.claude/settings.json`.
- Hook files are installed once per machine: `apply-permissions.sh --global`.
- More details: [configs Claude Code](https://github.com/academici/swissknifeman/tree/main/configs/claude-code#auto-approve-command-hooks).

### 5. Memory (general membership «brain»)
The project shares facts with other members of its group (brain); modes
`file|federation|agentmemory|off`.
- Wizard writes `.swissknife.json:memory_brain` + `.claude/memory.env.ini` (MODE).
- Group members - `~/.claude/hooks/memory/config.json` (`brains.<name>.members`).
- Hook files - `apply-permissions.sh --global`. Skill harness: `system/shared-memory`.

### 6. output-style (agent's terse voice)
Token saving: compresses agent output to a squeeze+code (`lean`), engineering rules do not cut it.
- The Wizard is calling `harness hooks --output-style lean` — copies the preset to
  `.claude/output-styles/lean.md` + puts `outputStyle` in `.claude/settings.local.json`.
- Enabled by default **in all** bundles (incl. `minimal`); `custom` — asks.
- Already connected projects (created before this point) rolls in `maind sync --all --only
  output-style`; opt-out — `project.output_style: "off"` in `config.json` (maind).
- Activates after `/clear` or new session Claude Code.

### 7. Hub (skill index)
Managed-block in `CLAUDE.md` (or `.ai/guidelines/swissknifeman-hub.md` when Boost) —
agent sees which skills are connected.
- Wizard includes `--hub` y connect/vendor.
- Handles: `./scripts/generate-hub.sh --target <project>`.

### 8. Brain docs-sync (from the volt side)
Two-way sync `docs/`/`docs-public` between the project and Obsidian-volt Brain.
- **Not automated from the project** — is configured in Volt: in frontmatter
  project notes add `repo: <project path>`, then `brain status/sync`.
- The wizard prints the required snippet.

## Prerequisites (once per machine)

The wizard checks them and suggests executing:
- **Topology** — `skiller topology init` (`~/.swissknifeman/topology.json`);
  memory and coordinator depend on it (resolve nodes/members).
- **Hook files** — `./scripts/apply-permissions.sh --global` puts
  `~/.claude/hooks/{notify,auto-approve,memory}` (notify/logs are active immediately,
  auto-approve/memory are included by design).

## Wizard Security

- `--dry-run` — shows the entire plan, **does not write anything**.
- All edits **merge-only**: foreign keys in `.claude/settings*.json` and `.swissknife.json`
  are not overwritten, backup before recording `*.bak`.
- Machine prerequisites (`--global`, `topology init`) — with confirmation only.
- Idempotent: repeated execution does not produce duplicate hooks/rules.

## See also
- [Installing skills](./installation) — details connect/vendor.
- [CLI swissknifeman](./cli) — all commands.
- [Profiles and auto-detection](./profiles).
