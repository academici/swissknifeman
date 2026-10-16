# UPGRADE: previous layout → this repository

Audience: an agent on a machine that has the previous `swissknifeman` checkout and projects wired to it.
Semi-automated on purpose: scripts do the mechanical part, the agent checks each step by hand. The previous layout
is not kept anywhere afterwards. Status marks: **[verified]** rehearsed in a sandbox copy (commerz), **[todo]** not yet
rehearsed — check before trusting it.

## End state

- One checkout, `~/projects/packages/swissknifeman` (this repository merged in). No `-next` folder, no second copy.
- `~/.local/bin` holds `swissknifeman skiller maind harness analyst aicore brain` and `plan.py`/`orch.py`, all pointing
  into that one checkout. No `task` CLI.
- Machine config in `~/.config/swissknifeman/config.toml` (+ `overlays/`, `stubs/`), state in `~/.local/state/swissknifeman/`.
- Every project has `.swissknifeman/` (`config.toml`, `launcher.py` + lock, `hooks.env`, `provider-artifacts.lock.json`) and
  no `*.env.ini`, `*.bak`, `.swissknife.json`.
- Plugin names: `task` is replaced by `planner`; new plugins `brain`, `skm`. Marketplace path is unchanged.
- `releases/` is empty and `CHANGELOG.md` has no history; the first release of this line starts from a clean baseline.

## What changed (read once)

| Area | Before | Now |
| --- | --- | --- |
| Plan engine | `packages/task` (`task` plugin, `/task:*`) | `packages/planner` (`planner` plugin, `/planner:*`, `plan.py`) |
| Core library | `core/` | `packages/aicore` |
| Modules | `orch/`, `core/`, `roadmap/` at root, `artifex` | `packages/{aicore,analyst,brain,harness,maind,orch,planner,skiller}` each with `unit.json` |
| Hub config | `config.json`, `safe-dirs.json` in the checkout | `[maind]` + `registry.json` under `~/.config/swissknifeman` **[todo]** |
| Project provider selection | `.swissknife.json` | `[aicore.providers.selection.<id>]` in `.swissknifeman/config.toml` |
| Hook settings | `.claude/*.env.ini` | `[harness.hooks.*]` in `.swissknifeman/config.toml`, generated `.swissknifeman/hooks.env` |
| Project commands | path to `packages/*/scripts` | `python3 -I .swissknifeman/launcher.py <group> ...` |
| Plans (JSON) | schema `plan/v1` | same `plan/v1` — compatible, see "Plans" |

## Plans: nothing to convert, only check

All plans are JSON on schema `plan/v1`; the new planner reads them unchanged. **[verified]** `plan.py check` on every plan of
corex, vaulter, azguard, chatom: 0 errors (warnings only: `context_legacy`, `modify_missing`, `context_unbound` —
pre-existing content issues, not migration blockers).

Added in `plan/v1` (additive; old plans stay valid):
- new schema `read-followups` — follow-ups and owner decisions left in `result.pending` of an item;
- `read-catalog` error codes: `AICORE_REQUIRED`, `CONFIG_INVALID`, `ITEM_OWNED`, `LOG_DATA_INVALID`, `OVERLAY_SLOT_UNKNOWN`,
  `OVERLAY_TOO_LARGE`, `PROJECT_PATH_OVERRIDE_FORBIDDEN`, more (diff `schemas/plan/v1/read-catalog.schema.json`);
- wording only in `check-evidence` and `defs` (Task → planner).
Check per project: `plan.py check plans/<plan>` for each plan folder → `0 error(s)`. Commands `/task:*` become `/planner:*`.

## Machine steps (once per computer)

Needs the owner: they change live machine state (symlinks, `~/.claude`, `~/.config`).

1. Backup: `tar czf ~/skm-backup-$(date +%F).tgz ~/.config/swissknifeman ~/.local/state/swissknifeman ~/.claude/settings.json ~/.claude/plugins/known_marketplaces.json 2>/dev/null` and a copy of the old checkout's `config.json`, `safe-dirs.json`.
2. Replace the checkout: move this repository's content into `~/projects/packages/swissknifeman` (keep `config.json` and
   `safe-dirs.json` aside until step 5), drop `.swissknifeman-dev` and the dev guard (`install.sh` / entry points) — **[todo]**
   the guard is removed in a separate commit at cutover.
3. `./install.sh` (re-points every symlink; adds `aicore`, `brain`, `plan.py`, `orch.py`; `task` disappears). **[verified]** in a sandbox home.
4. Machine config: write `~/.config/swissknifeman/config.toml` — keep existing sections, point `[aicore.plugins.*].manifest` at the
   main checkout (not `-next`). Move hub settings from the old `config.json` into `[maind]` and the project list into `registry.json`. **[todo]**
5. Claude Code: `/plugin marketplace update swissknifeman`, enable `planner`, `brain`, `skm`; disable `task`. **[todo]**
6. `swissknifeman doctor` → all units green.

## Project steps (each project)

Prefer one project at a time, committed on a branch. All paths absolute (`maind onboard .` crashes — see Known gaps).

1. Clean tree check: `git status` clean (or commit first). Note existing plans: `ls plans`.
2. `swissknifeman project init` → `.swissknifeman/launcher.py` + lock. **[verified]**
3. `maind onboard "$PWD"` — registers the project, wires memory, `skiller integrate`, MCP files (`.codex`, `.cursor`, `.grok`), refreshes
   `ecosystem-*` skills, re-renders agent-packs (generated files such as `.claude/hooks/review-gate.sh` gain the
   `.swissknifeman/hooks.env` carrier), creates `.swissknifeman/{config.toml,hooks.env,backups/}`. **[verified]** Outside a sandbox
   it may print `✗ instructions only umbrella-monorepo swissknifeman` and exit 1 — expected for non-hub projects; rerun with `--allow-partial`.
4. `.swissknife.json` → `.swissknifeman/config.toml`: copy `plugins` into the skiller settings and `providers.selection` into
   `[aicore.providers.selection.<id>]` (`enabled = true`), then delete `.swissknife.json`. The `MAIND_LEGACY_PROVIDERS` /
   `SKILLER_LEGACY_CONFIG` warnings must disappear. Plugin choice lives in `.claude/settings.local.json` (`enabledPlugins`), not in
   `.swissknife.json`. **[verified]** (warnings gone after the move)
5. Plugins: in `.claude/settings.local.json` rename `task@swissknifeman` → `planner@swissknifeman`; add `brain` only if wanted.
   Run `skiller connect --dry-run` first, then without it. **[todo]**
6. Hook settings: for each `.claude/*.env.ini`, put its values under `[harness.hooks.<name>]` in `.swissknifeman/config.toml`, run
   `harness hooks sync` (writes `.swissknifeman/hooks.env`). Keys that exist: `mode` of `auto_approve`, `memory`, `review_gate`.
   **Keep `.claude/review-gate.env.ini`**: the hook still reads `REVIEW_GATE_CMD` from it (no config key yet); delete the other two. **[verified]**
7. Delete leftovers: `*.bak`, `.claude/settings*.json.bak`, `CLAUDE.md.bak`, `.mcp.json.provider-artifact.bak` (git-ignored ones
   are safe to remove; onboard already put copies under `.swissknifeman/backups/`).
8. Plans: for each `plans/<plan>`, `plan.py check` → 0 errors. Replace `/task:` with `/planner:` in project docs and `CLAUDE.md`.
9. Verify: `swissknifeman project verify` and `doctor`, `maind health --cwd`, `git diff --stat` reviewed by hand,
   `grep -rIn "packages/task\|/task:\|swissknife.json\|env.ini" . --exclude-dir={vendor,node_modules,.git}` → nothing.

## Pilot log

- 2026-10-16, `commerz` copy in `scripts/dev-sandbox.sh`: steps 2–3 ran; diff = 7 files (agent-pack regeneration, skill refresh,
  registry sha in `CLAUDE.md`). Steps 4 and 6 applied: `.swissknife.json` removed, providers and three hook modes moved to `config.toml`,
  `harness hooks sync` wrote `hooks.env`, re-onboard printed only `MAIND_LEGACY_CONFIG` (machine-level, step 4 of the machine steps) and the `laravel/pao` hint.
  Steps 5 and 7 not yet applied.

## Known gaps in the tooling (fix or note before the second computer)

- `swissknifeman upgrade` (named by every `*_LEGACY_*` warning and by ADR 0010) does not exist; this document replaces it.
- `maind onboard .` with a relative path raises `ValueError: root must be explicit and absolute`.
- Many `LEGACY_*` read paths remain in modules (`MAIND_LEGACY_CONFIG`, `MAIND_LEGACY_PROVIDERS`, `SKILLER_LEGACY_CONFIG`, ...). Once both
  computers are migrated they are dead code and are removed in a follow-up (grep `LEGACY_`).
