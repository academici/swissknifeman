# Agent-packs: packs of subagents and rules

Pack (`configs/claude-code/agent-packs/<pack>/`) — versionable artifact bundle
Claude Code (agents/work flow/hooks/fragment settings/rules), which `harness`
deterministically rolls out into a project for a stack or role. Pack catalog, composition
files and complete list CLI-commands - in
[README packages](https://github.com/academici/swissknifeman/tree/main/packages/harness/configs/claude-code/agent-packs);
here is what you need to know when working with an already rolled out pack: how to read
generated file, where to extend the behavior and how to catch the drift.

```bash
harness agent-packs list
harness agent-packs render  --auto --pack <pack> --target .
harness agent-packs upgrade        --pack <pack> --target .
harness agent-packs remove         --pack <pack> --target . [--dry-run]
harness agent-packs doctor  --target . [--pack <pack>]
```

## laravel-package — packs for Laravel-packages

`laravel-package` (`packages/harness/configs/claude-code/agent-packs/laravel-package/`) —
stack pack for those who develop **Laravel-composer-package** (library: `composer.json` without
`artisan`), not an application - including monorepo PHP-packages (`packages/*/src`, like chatom).
Difference from `backend-laravel` (application: `route → controller → Action → DTO → policy`) — slice unit
here «package feature» (contract/interface → implementation → registration in `ServiceProvider` →
publishables), a reviewer is sharpened for **public contract** instead access-layer: Public API/BC
(SemVer-diff, `BC_CHECK_CMD` via `roave/backward-compatibility-check` if there is a binary - otherwise
axis remains prose), `register`-vs-`boot` in `ServiceProvider`, publishables (migrations/config/views)
and tests for Orchestra Testbench instead `php artisan test`.

Take with `backend-laravel` does not spawn: general `review-gate.sh`/`review-gate.env.ini`/
`settings.fragment.json` resolve from `backend-laravel` via `src_pack` (see below) instead of copies, and
general prose (severity-format, «Detect ≠ gating») marked `<!-- shared:name -->` in both packs and
is verified byte-by-byte test (`test_agentpacks_shared.py`) — general text discrepancy is red.
Profile `php-package` (`packages/skiller/profiles/php-package.json`) calls
`agent_pack: ["laravel-package", "_common"]`, so `maind onboard`/`sync` roll out the pack
in the normal way along with skills.

Installation is monitored in `.claude/agent-pack.lock.json` — for each pack file
are there `target`, `base_sha256` rendered content (**including**
provenance-header, see below) and `user_owned`.

## Provenance-header

Each generated pack file (except `kind: merge` — he pours in
fragment into someone else's `settings.json`, your title is inappropriate there) gets
deterministic block passport:

```md
<!-- swissknifeman:generated
Generated-by: harness agent-packs
Pack: backend-laravel@0.11.1
Template: agents/reviewer.md
Edit-policy: generated-core — DO NOT edit; expand through extension-point
Extension-points: .claude/rules/acme-reviewer-overrides.md
Upgrade: harness agent-packs upgrade --pack backend-laravel --target .
-->
```

Fields:

- **Pack@version** — what package and what version generated the file;
- **Template** — source inside the package (`src` from `pack.json`), if you need to find
  original source;
- **Edit-policy** — `generated-core` (file is overwritten by the pack when upgrade,
  editing is pointless) or `user-owned` (the file is given to you forever, pack
  doesn't touch him anymore - see below);
- **Extension-points** — where to write project edits instead of the generated file
  (list `target`-file paths with `role: override` from the pack manifest; usually
  one - `.claude/rules/<prefix>-reviewer-overrides.md`);
- **Upgrade** — ready command for rolling out a new version of the pack.

Header **intentionally without timestamp**: it is included in `base_sha256` along with
the rest of the file contents, and any non-determinism (generation date)
would break idempotent re-render and comparison lock↔disk during drift detection.
The comment syntax is tailored to the target extension - `.md` gets HTML-block
**after** closing `---` YAML-frontmatter (otherwise Claude Code would stop
parse agent metadata), files with shebang - after the first line, `.js`/`.mjs`
get `//`-comment, `.sh`/`.ini` — `#`. Extensions outside this set
the header is not received at all - better without a passport than broken syntax.

## «Generated core not editable»

The rule is rolled out to all common stack packs `_common`-pack in
`.claude/rules/generated-assets.md` (scope - `.claude/agents/**`,
`.claude/workflows/**`, `.claude/hooks/**`): file with block
`swissknifeman:generated` — pack property, agent **doesn't edit it directly
not found in any review**, no matter how reasonable the correction may seem.
Extension - only through a file from `Extension-points` in the header or via
`.claude/rules/*-overrides.md`. If kernel editing is really necessary -
agent stops and reports; himself upgrade pack or editing the template in
`harness` is done by a person, not an agent (see last section).

Where to write design overrides in practice: each stack pack (`backend-laravel`,
`node-frontend`, `python-backend`, `dart-flutter`, `laravel-package`) puts
`.claude/rules/<prefix>-reviewer-overrides.md` (`<prefix>` — interview response
`PACK_PREFIX`, default project directory name) with `user_owned: true` and
`role: override` in the manifest is the only pack file that upgrade
never overwrites and is not considered a conflict. Blank blank
(«Here are the design review axes; pack does not overwrite this file») — is filling
as the project progresses.

## Drift-detect

```bash
harness agent-packs doctor --target . --drift              # informative, rc=0
harness agent-packs doctor --target . --drift --strict      # CI-gate, rc=1 when drifting
```

Compares `base_sha256` from `.claude/agent-pack.lock.json` with real sha256
file on disk - for each installed package and each of its files, except
`kind: merge` (yours sha not tracked) and `user_owned` (we expect drift there and
not a problem - it's an extension). Result - `modified` (someone ruled
generated-file by hand override) or `missing` (file deleted/not readable).
Without `--strict` command only prints findings (is suitable for normal
`doctor`-run); `--strict` turns the found drift into a non-zero code
return - use as CI-gate «no one ruled generated hands by
override».

`doctor --target .` (without `--drift`) additionally warns about **intersection
targets**: two installed packages declared the same file. This is a silent mine -
`remove` of one pack takes away files that the second one also owns; recovery -
`harness agent-packs upgrade --pack <second> --target .` (actual reconciliation will return
missing files). B `--json` the same data comes in the field `shared_targets`.

The same signal comes without an explicit call doctor: `maind analyze`
reads independently `.claude/agent-pack.lock.json` (without importing `harness` —
packages isolated, formula sha256 literally duplicated) and starts
finds drift in `pack_drift`. Drift run verdict - **ATTENTION**
(never RED — this is a hint for a fix, not a run failure), reason is
the report reads like this: «generated-the pack file is edited locally: `<target>` —
move the edit to override and restore (`harness agent-packs render`)».

## pack-guard — preventive layer 2 (optional)

Drift-the detection above catches the edit generated-file **after the fact**, already happened.
`pack-guard` — optional `PreToolUse`-hook (`configs/claude-code/hooks/pack-guard/`),
who catches her **to** how it will happen: intercepts `Edit`/`Write`/
`MultiEdit`/`NotebookEdit` from the file that is in `.claude/agent-pack.lock.json`
like managed (same set `packs[].files[].target`, same as Drift-detection). Files
`user_owned` (overlays - extension point base+overlay) `pack-guard` does not touch: them
can and should be edited. Default **not installing** — is included explicitly
per-project.

| Mode | Behavior |
|---|---|
| `off` (default) | hook is not registered in the project |
| `warn` | stderr-warning when editing generated-file, **does not block** |
| `strict` | **blocks** Edit/Write/MultiEdit/NotebookEdit by generated-file (exit 2) |

Fail-safe semantics: the hook never drops the session. No `.claude/agent-pack.lock.json` /
it is broken or empty / file is not listed as managed (or listed, but
`user_owned`) / `MODE` in `pack-guard.env.ini` missing or unknown / any
internal hook error (broken stdin-JSON etc.) — silent skip in all cases
(`exit 0`, equivalent `off`). Blocking is possible only at the intersection: valid
lock + file is real managed + `MODE=strict`.

```bash
harness hooks --global                        # copies hook files to ~/.claude/hooks/pack-guard/ (once per machine)
harness hooks --target . --pack-guard warn     # include in the project: warn
harness hooks --target . --pack-guard strict   # include in the project: strict
harness hooks --target . --pack-guard off      # turn off (kill-switch)
```

`--pack-guard MODE` writes `<project>/.claude/pack-guard.env.ini` (`MODE=...`) and
registers `PreToolUse`-hook on `Edit`/`Write`/`MultiEdit`/`NotebookEdit` in
`.claude/settings.json` (merge-only, like the rest of the hooks `harness hooks`). `off` —
kill-switch: overwrites `MODE=off`, already registered hook entry in settings
does not remove (merge-only does not delete other people's posts), but the hook reads `MODE=off` for each
call and exits immediately - effectively inactive.

Trigger example (`strict`, file under pack control):

```
$ echo '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/.claude/agents/reviewer.md"}}' \
  | python3 ~/.claude/hooks/pack-guard/pack-guard.py
pack-guard: file generated by the pack 'backend-laravel' (swissknifeman:generated) — not
edit the kernel directly: edit the pack overlay or accept the change via 'harness
agent-packs upgrade': /proj/.claude/agents/reviewer.md
$ echo $?
2
```

In mode `warn` the same message goes to stderr with prefix `[warn]`, but exit-code
remains `0` — editing is in progress.

When to enable: `warn` — run-in default (signal without risk of stopping legitimate
work), `strict` — for overnight/unattended dev-loop, where agent-packs should
remain under strict control, and silent editing generated-file by hand (past
overlay/`upgrade`) without a person in the moment is undesirable.

## How to legally change core

Two ways, both the work of a human, not an agent:

1. **Upgrade pack.** If the project needs an edit right now and is already in
   new version of the pack - `harness agent-packs upgrade --pack <pack> --target .`.
   Files are categorized: `new`/`safe-apply` are installed automatically,
   `user-owned` do not touch, `conflict` (both you and the upstream ruled) is written
   next to it `<target>.pack-new` — squash it with your hands and decide what to keep.
   **The decision is made by the FACT of the files, and not by the version number:** upgrade
   checks source and disk hashes against `base_sha256` from lock, therefore forgotten bump
   `pack.json:version` no longer gives silent «is already relevant» (the change is arriving,
   plus warn to the author of the pack), and the missing one target is restored even if
   versions (case when `remove` of a neighboring pack took away shared files). Matched
   state is honestly printed as «nothing to do». Version bump remains
   is the responsibility of the author of the pack - it simply ceased to be the only protection.
2. **Editing a template in `harness`.** If the desired behavior is not yet available in any
   pack version - the source of the pack changes to
   `packages/harness/configs/claude-code/agent-packs/<pack>/` (template +
   `pack.json` version + `CHANGELOG.md` pack), after which the change reaches
   projects the same `upgrade`. This is an edit to the original package `harness`, and not
   of the rendered file in the target project - normal PR-process,
   `bash packages/harness/scripts/validate.sh` before the commit.

In both cases, the source of truth remains the same - `configs/claude-code/agent-packs/`
in `harness`; the rendered copy in the project is secondary and can be restored by the team from
`Upgrade:` in the file header.

## Removing a pack

```bash
harness agent-packs remove --pack <pack> --target .              # delete
harness agent-packs remove --pack <pack> --target . --dry-run    # plan only
```

`remove` — safe reverse operation to `render`/`upgrade`, for each file
pack from lock:

- **clean file** (sha256 on disk matches `base_sha256` from lock) — is removed;
- **edited locally** (sha256 different) — remains, with a warning;
- **`user_owned`** (extension, given to you forever) — always remains;
- **`kind: merge`** (hooks poured into `.claude/settings.json`) — does not touch
  never (deleting a fragment from someone else's JSON unsafe) — warning with
  list of what to remove manually if desired;
- **is no longer on disk** — is silently skipped.

The pack entry is removed from `.claude/agent-pack.lock.json` anyway (otherwise
repeated `remove`/`render` would see the already deleted pack as installed);
if the pack was the last one in lock — file lock is removed entirely. `--dry-run`
prints the plan (that will be deleted/left) without a single change on disk.

## src_pack — file sharing between packs

`files[]`-entry in `pack.json` may carry an optional field
`src_pack: <other-pack-name>` — then the source (`src`) is read from the directory SPECIFIED
pack, not from your own. File owner (that goes into `Pack:` header,
command `Upgrade:`) while the current pack remains - `src_pack` only affects
for source resolution, delivery/provenance does not change. Suitable when several
packs must distribute the same file (e.g. general rules-fragment) without
physical duplication of content in each package.
