# UPGRADE: previous layout → this repository

Audience: an agent on a machine that has the previous `swissknifeman` checkout and projects wired to it.
Semi-automated on purpose: scripts do the mechanical part, the agent checks every step by hand. The previous layout is
not kept anywhere afterwards. Everything below was run on the first computer on 2026-10-16; **[done]** marks a step as
executed there, **[verified]** as checked on real projects. Paths: `HUB=~/projects/packages/swissknifeman`.

## End state

- One checkout, `$HUB`. No second clone, no worktree of it, no `-next` folder.
- `~/.local/bin` holds `swissknifeman skiller maind harness analyst aicore brain` and `plan.py`, `orch.py`, all pointing into `$HUB`.
  No `task` CLI.
- Machine config `~/.config/swissknifeman/config.toml` (+ `overlays/`, `harness/safe-dirs.json`), machine state
  `~/.local/state/swissknifeman/` (`maind/registry.json`, `skiller/projects.json`, ...). No `~/.maind`, no `~/.swissknifeman`.
- Every project has `.swissknifeman/` (`config.toml`, `launcher.py` + lock, `hooks.env`, `provider-artifacts.lock.json`) and no
  `.swissknife.json`, `*.bak`, `*.env.ini` (except `review-gate.env.ini`, see below).
- Plugins per project: `planner` instead of `task` (the `task` alias still resolves), `maind harness analyst brain` instead of `system`.
- Version line: hub `0.30.0` (tag `v0.30.0`, `releases/v0.30.0.json`). `CHANGELOG.md` holds only `[Unreleased]` and `[0.30.0]`; the old
  release snapshots and history are gone (old tags `v0.5`…`v0.28.x` stay in git).
- No stale caches anywhere: Claude/Codex/Grok plugin caches hold only the plugins of this release, no `~/.swissknifeman`, `~/.maind`,
  hub-root `config.json`/`safe-dirs.json`/`*.bak`.

## What changed

| Area | Before | Now |
| --- | --- | --- |
| Plan engine | `packages/task`, `/task:*` | `packages/planner`, `/planner:*`, `plan.py` (`task` kept as alias) |
| Core library | `core/` | `packages/aicore` |
| Layout | `orch/`, `core/`, `roadmap/`, `artifex` at the root | `packages/{aicore,analyst,brain,harness,maind,orch,planner,skiller}`, each with `unit.json` |
| Hub config | `config.json`, `safe-dirs.json` in the checkout | `[maind]` in the machine config + `registry.json`; `harness/safe-dirs.json` |
| Machine places | `~/.swissknifeman`, `~/.maind` | `~/.local/state/swissknifeman/{skiller,maind}` |
| Project providers | `.swissknife.json` | `[aicore.providers.selection.<id>]` in `.swissknifeman/config.toml` |
| Hook settings | `.claude/*.env.ini` | `[harness.hooks.*]` in `.swissknifeman/config.toml`, generated `.swissknifeman/hooks.env` |
| Project commands | paths to `packages/*/scripts` | `python3 -I .swissknifeman/launcher.py <group> ...` |
| Plugin `system` | one plugin | split into `maind`, `harness`, `analyst`, `brain` |
| Codex | vendored `.agents/plugins/` bundles | native selection in `.codex/config.toml` |
| Plans | JSON, schema `plan/v1` | same schema, compatible (below) |

## Plans: nothing to convert, only check

All plans are JSON on `plan/v1`; the new planner reads them unchanged. **[verified]** `plan.py check` on every plan of corex, vaulter,
azguard, chatom: 0 errors (warnings `context_legacy`, `modify_missing`, `context_unbound` are old content issues, not blockers).
Added to `plan/v1` (additive): schema `read-followups` (follow-ups and owner decisions in `result.pending`); error codes in
`read-catalog` (`AICORE_REQUIRED`, `CONFIG_INVALID`, `ITEM_OWNED`, `LOG_DATA_INVALID`, `OVERLAY_SLOT_UNKNOWN`, `OVERLAY_TOO_LARGE`,
`PROJECT_PATH_OVERRIDE_FORBIDDEN`, ...); wording only in `check-evidence` and `defs`. Per project: `plan.py check plans/<plan>` → `0 error(s)`.

## Machine steps (once per computer; the owner runs what changes live state)

0. `scripts/check-env.sh` (read-only): every required item must be `ok`; fix the recommended gaps it names (`jq`, `node`, `uvx`,
   `bubblewrap` + `socat` and, on Ubuntu 24.04+, the AppArmor profile for `bwrap`: [requirements](docs/getting-started.md#requirements)).

1. **Backup** **[done]**: `mkdir ~/skm-backup-$(date +%F)`; `tar czf` of `~/.config/swissknifeman ~/.local/state/swissknifeman ~/.swissknifeman
   ~/.claude/settings.json ~/.claude/plugins/known_marketplaces.json`; copy `$HUB/config.json` and `safe-dirs.json`;
   `git bundle create <dir>/base-main.bundle main` in `$HUB`.
2. **Replace the checkout** **[done]**. The new line comes as a git ref (a clone, a remote branch or a bundle). In `$HUB`:
   `git fetch <source> main && git merge -s ours --no-commit --no-ff FETCH_HEAD && git read-tree -u --reset FETCH_HEAD && git commit`.
   The tree becomes the new layout, the old history stays as the first parent; ignored machine files (`config.json`, `safe-dirs.json`,
   `.claude/*`) stay. Then delete what the old layout left untracked: `core/`, `orch/` (only `__pycache__`), `packages/artifex/`
   (one `.lock`); look at `roadmap/` first (personal notes, git-ignored — keep).
3. `./install.sh --force` in `$HUB` **[done]** — re-points every symlink, adds `aicore brain plan.py orch.py`, installs Codex/Grok plugins.
4. `python3 scripts/migrate-machine.py` (dry-run), then `--apply` **[done]**: `config.json` → `[maind]` + `registry.json`,
   `safe-dirs.json` → `~/.config/swissknifeman/harness/`. Before applying, make sure `config.json` lists every project (azguard was
   added by hand) and holds no duplicates.
5. Legacy machine places **[done]**: `mv ~/.maind ~/.local/state/swissknifeman/maind` (the registry lands in `~/.maind` while it
   exists — move it); `~/.swissknifeman/projects.json` → `~/.local/state/swissknifeman/skiller/projects.json` (copied; delete
   `~/.swissknifeman` after checking `topology.json` is not needed).
6. `~/.config/swissknifeman/config.toml` **[done]**: `[aicore.plugins.*].manifest` points to `$HUB/bridges/...`, not to any clone.
7. `harness hooks --global` **[done]** (refreshes stale hook copies in `~/.claude`).
8. Claude Code: `/plugin marketplace update swissknifeman`; enable `planner`, `brain`, `skm`; `task` may stay as an alias.
   `~/.claude/settings.json` has a trust sentence naming the old clone path (`.../swissknifeman-next`): change it to `$HUB`.
   The hub project itself (`$HUB/.claude/settings.local.json`) is not a consumer project, so project steps skip it: run
   `skiller connect --file settings.local.json`, then replace `system@swissknifeman` by `maind`, `harness`, `analyst`, `brain` and
   `task@` by `planner@` in `enabledPlugins` by hand (connect adds `planner` but keeps `system`; check there is no duplicate). **[done]**
   `/plugin marketplace update swissknifeman` is global (one `known_marketplaces.json` entry): run it once, in any project, then
   restart the Claude Code session in every project to load the new plugin set. **[done]**
9. `swissknifeman doctor`: from v0.31.0 expected `0 fail` and `0 warn` on a machine that passes `scripts/check-env.sh --strict`
   (the `aicore.doctor`/`skiller.doctor` "probe output is not JSON" failures were a defect of the doctor aggregator, which ignored
   `output: text`). Warns that remain are the owner's: memory daemon (`maind start --only memory`), `orch.sandbox` (see
   [requirements](docs/getting-started.md#requirements)).
10. **Caches — delete every old one, nothing of the previous version may take part** **[done]**:
    - Claude Code: back up `~/.claude/plugins/installed_plugins.json`, drop every `*@swissknifeman` entry from it, then
      `rm -rf ~/.claude/plugins/cache/swissknifeman ~/.claude/plugins/data/core-swissknifeman` (it was 1.9 GB of sha- and version-keyed copies,
      among them `task/0.28.3` and `system`). They are re-created at the next session start / `/plugin marketplace update swissknifeman`
      from the enabled plugins of each project; restart the session in every project.
    - Codex and Grok: `rm -rf ~/.codex/plugins/cache/swissknifeman ~/.grok/installed-plugins/*`, then `./install.sh --force` in `$HUB`
      reinstalls `core` and `planner` at the current version (Grok `registry.json` is recreated).
    - Project side: `.agents/plugins/` vendored bundles are removed or regenerated (project step 7); `.swissknifeman/backups/` of a project
      is only the safety copy of the upgrade — delete it once the project is committed and verified.
    - Hub root: after step 4 delete `config.json`, `safe-dirs.json`, `safe-dirs.json.bak`, `CLAUDE.md.bak` (their content lives in
      `[maind]`/`registry.json`/`harness/safe-dirs.json`; the originals are in the backup folder). Move `~/.swissknifeman/topology.json` to
      `~/.local/state/swissknifeman/maind/topology.json` and delete `~/.swissknifeman`.
    - `swissknifeman doctor` must print no `legacy` warning (see 9).
11. Clean-up of clones **[done on computer 1]**: delete the old clone folder(s), every `git worktree` of it (`git worktree list`, then
    `git worktree prune`), temp sandboxes `/tmp/skm-sandbox-*`. Before deleting a clone, bring its branches in:
    `git fetch <clone> 'refs/heads/*:refs/heads/next/*'` and compare tags (`git tag | wc -l` equal) so nothing is lost.

## Project steps (each project)

Work on a branch `chore/skm-upgrade`. Absolute paths only (`maind onboard .` fails on a relative path). Helper:
`python3 $HUB/scripts/upgrade-project.py PROJECT [--apply]` does step 4 (dry-run without `--apply`).

1. `git status` — files already dirty are not yours; commit only your own paths.
2. `swissknifeman project init` → `.swissknifeman/launcher.py` + lock. **[verified]**
3. `maind onboard "$PWD" --allow-partial` — registers, wires memory, `skiller integrate`, MCP files, `ecosystem-*` skills,
   agent-packs, `.swissknifeman/{config.toml,hooks.env,backups/}`. `✗ instructions only umbrella-monorepo swissknifeman` is
   expected for non-hub projects. **[verified]**
4. `upgrade-project.py "$PWD" --apply`: `.swissknife.json` providers and the `*.env.ini` modes (auto-approve, memory, review-gate,
   agent-router, run-report) → `.swissknifeman/config.toml`; `task@` → `planner@` in `.claude/settings*.json`; deletes
   `.swissknife.json`, `*.bak`, migrated `.env.ini`; lists docs still mentioning `/task:`. Keeps `.claude/review-gate.env.ini`
   (the hook reads `REVIEW_GATE_CMD` from it; no config key yet). **[verified]**
5. `harness hooks sync` → `.swissknifeman/hooks.env`. **[verified]**
6. `skiller connect --file settings.local.json --cleanup-codex-vendored --native-codex` — replaces `system@` by `maind harness
   analyst brain`, writes `.codex/config.toml`. **[verified]** Do not use `--fix-path` (the marketplace path is `$HUB` already).
7. Vendored Codex bundles `.agents/plugins/` are replaced by the native selection in `.codex/config.toml` (step 6). Retire them with
   `skiller connect --file settings.local.json --native-codex-only --cleanup-codex-bundles` (moves the tree and its lock records to
   `.swissknifeman/backups/legacy-codex-bundles-*`, refuses when a file under `.agents/plugins` is not lock-owned), then commit the
   deletion. A bundle left in place is stale after every patch release and no longer blocks `release-fleet` (v0.30.2+).
8. Verify: `swissknifeman project verify`, `maind health --cwd` (memory daemon warning aside), `plan.py check plans/<plan>`,
   `git diff --stat` read by hand, `grep -rIn "packages/task\|/task:\|swissknife.json" . --exclude-dir={vendor,node_modules,.git,plans}`
   → only prose in docs you chose to keep. Commit on the branch; do not push without the owner.

Never run the project steps in a hub clone (a checkout with `packages/*/unit.json`): it rewrites hub files and `skiller integrate`
fails on its own marketplace. A hub clone is replaced by step 2 of the machine steps or deleted.

## Result on computer 1

| Project | Outcome |
| --- | --- |
| commerz | commit on `chore/skm-upgrade`: `.swissknife.json` removed, skill files refreshed |
| corex | commit: Codex bundles regenerated, `.bak`/`.env.ini` removed |
| vaulter | commit (branch off `improve/test-run-modes`): `SPUB_OWNERSHIP_CONFLICT` fixed by step 7, `.agents/plugins` dropped |
| azguard, chatom | only git-ignored files changed — no commit (chatom's unrelated dirty files untouched) |
| skm-orch-dev | hub clone — not upgraded, deleted with the other clones |

## Release 0.30.0 (what was done for the version line)

`CHANGELOG.md` heading `[0.30.0]`; `planner` follows it (`packages/planner/configs/command-routing.json` `plugin_version`, three
`plugin.json`, `unit.json`, `ownership.md`), bridge range `^0.30`; package-owned plugins were aligned with their `package.json`
(analyst 0.4.0, harness 0.7.2, maind 0.6.1, skiller 0.19.3) and the skill units that changed bytes since `v0.28.3` were bumped
(`core`, `devops`, `general`, `laravel-testing`, `quality`, `axioma`) — otherwise `RELEASE_IMMUTABLE_TUPLE`. Then `skiller registry`,
`render-provider-commands.py --write --repair-owned`, `golden.py capture` (planner-provider-commands, skiller-registry),
`skiller attest --release v0.30.0 --previous v0.28.3`, `verify-tag.py v0.30.0`, tag, push. Each later release is the usual flow
(`skiller release`, `version-guard`). The `task` alias is to be removed in the next minor.

## Tooling facts met on the way

- Fixed in the main line (`360384f8d`): after step 4 `maind health/onboard` failed with `PCFG_SCHEMA_INVALID` (the project provider layer
  from `config.toml` carried an empty `available`). A second computer needs that commit before step 4.
- `swissknifeman upgrade` (named by `*_LEGACY_*` warnings and ADR 0010) does not exist; this document and the two scripts replace it.
- `version-guard` had no path for a line without release snapshots; fixed in the same cleanup that emptied `releases/`.
- Many `LEGACY_*` read paths remain in the modules (`MAIND_LEGACY_CONFIG`, `MAIND_LEGACY_PROVIDERS`, `SKILLER_LEGACY_CONFIG`, ...) and the
  dev guard (`.swissknifeman-dev` marker). With both computers migrated they are dead code: remove them in a follow-up (grep `LEGACY_`).

## Notes from computer 2 (2026-10-16, no `-next` clone used: `git merge -s ours` straight from `origin/main`)

- Dirty hub checkout: `git stash` it first (`read-tree -u --reset` overwrites tracked edits); untracked files survive.
- `skiller connect` did **not** replace `system@swissknifeman` in project `.claude/settings.local.json` when the profile pins explicit plugin
  lists (it printed "included in addition ... system@swissknifeman"). Replace by hand: `system` → `maind harness analyst brain`.
- A project may carry a stale `extraKnownMarketplaces.swissknifeman.path` (e.g. `/tmp/skm-grok-delivery`): `skiller connect` warns and
  needs `--fix-path` there. "Do not use `--fix-path`" holds only when the path is already `$HUB`.
- `plan.py check` fails with `PLAN_NOT_FOUND` on a trailing slash (`plans/<plan>/`); pass `plans/<plan>` without it.
- `install.sh` prints `plan.py (wrapper: target is not executable)`: `packages/planner/scripts/plan.py` lacks the executable bit
  (the wrapper still works).
- Projects with a husky pre-commit hook may fail the migration commit on unrelated lint; fix there, never `--no-verify`.
- Hub-owned `rm` in `$HUB` is blocked by the harness `deny_hard` hook; the owner runs the clean-up of step 10 via `!`.
- In projects that were already dirty, files touched both by the owner and by the upgrade (`CLAUDE.md`, `.claude/settings*.json`,
  regenerated `.agents/plugins`) cannot be committed separately: leave them on `chore/skm-upgrade` for the owner.
- Do the project steps **on the project's current branch**, not on a side branch. `maind onboard` resets the memory mode to `maind`:
  read the old `MODE` from `.claude/memory.env.ini` first and pass `--memory <mode>` (or restore `[harness.hooks.memory] mode` in
  `.swissknifeman/config.toml` and run `harness hooks sync`). Seen on edufy and Brain (both were `manual`).
- Run `maind onboard` and `upgrade-project.py` before deleting anything from `.claude/*.env.ini`: those files are the only record of the old
  hook modes when they are git-ignored.
- `skiller release` proposes `0.31.0` when a `feat:` commit is in range; for a patch release set the `CHANGELOG.md` heading by hand, bump the
  `planner` files (`command-routing.json`, `unit.json`, three `plugin.json`, `ownership.md`), then `skiller registry`,
  `render-provider-commands.py --root . --write --repair-owned`, `golden.py capture` and `skiller attest`.
- `release-fleet` re-creates `~/.swissknifeman/receipts/` (legacy place). Up to v0.30.1 it ended `PARTIAL` (`DELIVERY_READBACK_FAILED` on stale
  vendored `.agents/plugins`, `DELIVERY_PROVIDER_UNCONFIRMED` for a directory marketplace); from v0.30.2 it ends `GREEN` on a migrated machine.
  The tag must point at `HEAD` (`RELEASE_FLEET_HEAD_MISMATCH` otherwise): commit docs before tagging.
- Registries: after `skiller list --prune` and dropping a deleted clone from `maind` `registry.json` the fleet run has no `TARGET_MISSING`
  rows. Never run package tests against the real state directory: `maind` onboard tests registered 15 `/tmp/tmp*` projects in
  `skiller/projects.json`.
- Claude Code plugin manifests must list agent files (`./agents/<name>.md`), not the directory, otherwise the plugin fails to load.
