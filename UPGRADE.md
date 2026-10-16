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
4. Move `~/.swissknifeman/{projects,topology}.json` (legacy place, skiller warns) to `~/.local/state/swissknifeman/skiller/`. **[todo]**
5. Machine config: write `~/.config/swissknifeman/config.toml` — keep existing sections, point `[aicore.plugins.*].manifest` at the
   main checkout (not `-next`). Move hub settings from the old `config.json` into `[maind]` and the project list into `registry.json`. **[todo]**
6. Claude Code: `/plugin marketplace update swissknifeman`, enable `planner`, `brain`, `skm`; disable `task`. **[todo]**
7. `swissknifeman doctor` → all units green.

## Project steps (each project)

Work on a branch `chore/skm-upgrade`; skip the project if the hub tools are not on PATH. Absolute paths only.
Helper: `scripts/upgrade-project.py PROJECT [--apply]` does steps 4-7 mechanically (dry-run without `--apply`).

1. `git status` — note files already dirty (they are not yours; commit only your own paths).
2. `swissknifeman project init` → `.swissknifeman/launcher.py` + lock. **[verified]**
3. `maind onboard "$PWD" --allow-partial` — registers, wires memory, `skiller integrate`, MCP files, `ecosystem-*` skills, agent-packs,
   creates `.swissknifeman/{config.toml,hooks.env,backups/}`. `✗ instructions only umbrella-monorepo swissknifeman` is expected for
   non-hub projects. **[verified]** on commerz, azguard, corex, vaulter, chatom.
4. `python3 scripts/upgrade-project.py "$PWD" --apply`: moves `.swissknife.json` providers and the `*.env.ini` modes
   (auto-approve, memory, review-gate, agent-router, run-report) into `.swissknifeman/config.toml`; renames `task@swissknifeman` →
   `planner@swissknifeman` in `.claude/settings*.json`; deletes `.swissknife.json`, `*.bak`, the migrated `.env.ini`; lists docs that
   still mention `/task:`. Keeps `.claude/review-gate.env.ini` (the hook still reads `REVIEW_GATE_CMD` from it). **[verified]**
5. `harness hooks sync` → `.swissknifeman/hooks.env`. **[verified]**
6. `skiller connect --file settings.local.json --cleanup-codex-vendored --native-codex` — `system@` is replaced by
   `maind`, `harness`, `analyst`, `brain` (the `system` plugin no longer exists); Codex gets `.codex/config.toml`. **[verified]**
   `task` is kept as a compatibility alias of `planner` (`packages/planner/aliases/task`), so old `/task:*` still resolve; docs
   should move to `/planner:*`.
7. Vendored Codex bundles `.agents/plugins/`:
   - git-ignored → `rm -rf .agents/plugins` (stale `task`/`system` copies). **[verified]** commerz
   - tracked → `skiller connect` regenerates them in place (system → analyst/brain/harness/maind, task → planner); commit the result. **[verified]** corex
   - `SPUB_OWNERSHIP_CONFLICT: ... modified prior artifact` (a vendored file differs from the lock) → `git rm -rf .agents/plugins`,
     re-run step 3 and 6; the project then uses native Codex only. **[verified]** vaulter
8. Verify: `swissknifeman project verify`, `git status`, plans: `plan.py check plans/<plan>` → 0 errors, then commit on the branch.
   `skiller connect` warns `marketplace 'swissknifeman' points to ANOTHER directory` until the machine cutover — do not `--fix-path`.

Do **not** run these steps in a hub clone (`skm-orch-dev`, any checkout that has `packages/*/unit.json`): it rewrites hub files
(`.mcp.json.example`, `packages/harness/CLAUDE.md`) and `skiller integrate` fails on its own marketplace. A hub clone is replaced by the
cutover (or deleted), never upgraded.

## Pilot log

- Rehearsal: `commerz` copy in `scripts/dev-sandbox.sh`, steps 2-6.
- 2026-10-16 real run, hub tools from the `-next` checkout via a PATH prefix and `SKM_DEV_ALLOW_LIVE=1` (machine not cut over yet):
  - `commerz` (commit on `chore/skm-upgrade`): `.swissknife.json` removed, 4 skill files refreshed. 
  - `corex` (commit): codex bundles regenerated (85 files), `.bak` and `.env.ini` removed.
  - `vaulter` (commit, branch based on `improve/test-run-modes`): `SPUB_OWNERSHIP_CONFLICT` fixed by step 7; `.agents/plugins` dropped.
  - `azguard`, `chatom`: only git-ignored files changed — no commit, tracked tree untouched (chatom had 23 unrelated dirty files, left alone).
  - `skm-orch-dev`: hub clone, reverted, not upgraded.

## Known gaps in the tooling (fix or note before the second computer)

- `swissknifeman upgrade` (named by every `*_LEGACY_*` warning and by ADR 0010) does not exist; this document replaces it.
- `maind onboard .` with a relative path raises `ValueError: root must be explicit and absolute`.
- Many `LEGACY_*` read paths remain in modules (`MAIND_LEGACY_CONFIG`, `MAIND_LEGACY_PROVIDERS`, `SKILLER_LEGACY_CONFIG`, ...). Once both
  computers are migrated they are dead code and are removed in a follow-up (grep `LEGACY_`).
