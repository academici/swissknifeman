# CLI harness — agent environment

[Codex request lifecycle](./codex-request-lifecycle) explains native client request capture and
the limits of diagnosing silent intervals from rollout logs.

`harness` — configuration package **environment Claude Code, Codex and Cursor**: presets permissions,
modes auto-approve/bypass, MCP-servers and hooks (memory/notify/log). Previously this
functionality lived inside `skiller`; is placed in a separate package because
it does not apply to skill management. Source of Truth Presets Claude —
`packages/harness/configs/claude-code/`; Cursor shapes —
`packages/harness/configs/cursor/`.

Installed by symlink in `~/.local/bin` (umbrella `./install.sh` puts
`skiller` · `harness` · `maind`). Package stateless — writes in `.claude/` targets
projects and `~/.claude/hooks/`.

## Commands

### `harness permissions`

Infuses presets permissions in `.claude/settings*.json` (merge-only, backup `*.bak`).
Without `--preset` stack is detected automatically (base + laravel/php-package/node/
python/docker). Details and list of presets - [Permissions](./configs/claude-permissions).

```
harness permissions --target .                    # autodetect stack
harness permissions --target . --preset base,laravel,docker
harness permissions --target . --dry-run
harness permissions --list                        # available presets
harness permissions --global                      # baseline + hook files in ~/.claude
```

### `harness mcp`

Adds MCP-servers in `.mcp.json` (Claude Code) from presets (merge-only, other people's servers are intact).
For **Cursor** MCP in `.cursor/mcp.json` writes `maind sync` when the provider is enabled.
Catalog of presets and descriptions - [Integrations](./integrations/).

```
harness mcp --list
harness mcp --target . --mcp context7,playwright
harness mcp --target . --mcp context7 --dry-run
```

Cursor MCP and permissions — [Settings Cursor](./setup/cursor).

### `harness hooks`

Global installation of hook files (times per car) and enabling project modes.

```
harness hooks --global                            # auto-approve/memory/notify/log/review-gate → ~/.claude/hooks
harness hooks --target . --auto-approve strict    # strict|permissive|bypass|off
harness hooks --target . --memory core:federation # file|federation|agentmemory|maind|manual|off
harness hooks sync|show [--target P] [--json]     # render / inspect .swissknifeman/hooks.env
```

- The mode flags (`--auto-approve`, `--memory`, `--router`, `--run-report`, `--pack-guard`, `--plan-guard`, ...) set a key of
  `[harness.hooks.<hook>]` in the project configuration and regenerate the committed `.swissknifeman/hooks.env`; no
  `*.env.ini` is written any more ([hook modes](./reference/hook-intent-files)). `harness hooks sync` regenerates the carrier
  from the configuration, `harness hooks show` prints configuration, carrier and legacy files (`hooks-state/v1`).
  For a project bound to a workspace, the configuration is `projects/<code>/local/config.toml` inside that workspace.
  Carrier generation reads that project layer and excludes machine defaults.
- `--auto-approve` also registers the PreToolUse-hook (Bash/ExitPlanMode), merge-only.
- `--memory BRAIN:MODE` attaches the project to the brain: `.swissknife.json:memory_brain`
  + `[harness.hooks.memory]` (`MEMORY_MODE` in `.swissknifeman/hooks.env`).
- **review-gate** (`SubagentStop`) — deterministic architecture gate: drives away
  project verification after the subagent, `warn` → hint, `strict` → block. Mode in
  `[harness.hooks.review_gate]` (`off|warn|strict`, default `warn`), check in
  `.claude/review-gate.config.json` (`check_command`; empty → no-op). Details -
  `hooks/review-gate/README.md`.

### `harness safe-dirs`

Machine-owned allowlist trusted directories: inside its roots auto-approve
skips `rm`/`rmdir` past deny_hard (code below git — deletion is reversible), out —
blocks as before. The config is `safe-dirs.json` in `<config>/harness/` (`~/.local/share/swissknifeman/config/harness/safe-dirs.json`; the old `~/.config/swissknifeman/...` is read while the new `config/` folder does not exist,
`$SKM_HOME/config/harness/safe-dirs.json` when `SKM_HOME` is set; template
`configs/safe-dirs.example.json`). One search ladder for the command and the hook:
`$SKM_SAFE_DIRS_CONFIG` (exclusive override) → the file above → legacy `<hub root>/safe-dirs.json`
→ legacy `~/.swissknifeman/safe-dirs.json`; the first existing file is the active one, `init` creates
the new file only when none exists and does not move the legacy ones. Verdict considers `hooks/auto-approve/lib/safedirs.py` strictly
fail-closed: argv via shlex, realpath vs symlink-escape/`..`, containment
by component, protection `.git` and the root itself, globs by static prefix;
any shell-magic (`$VAR`, `$( )`, backticks, `xargs rm`) → deny.
Project-override hook config on allowlist **has no effect** (security).

```
harness safe-dirs init                                  # config with defaults
harness safe-dirs list                                  # effective allowlist through the eyes of a hook
harness safe-dirs add ~/projects                        # add root (--exclude — withdrawal)
harness safe-dirs prune-ask --global --all-projects     # remove old ones ask-rules rm
```

Default `include_registered_projects=true` — onboarded projects from
`<state>/skiller/projects.json` (legacy `~/.swissknifeman/projects.json` while it is the only one) fall into allowlist automatically.

::: warning bypass clears confirmations
Mode `bypass` auto-approves everything except hard denylist — only for
containers/VM, is not on the production machine.
:::

### `harness agent-packs`

Rolls out versioned subagent packs/rules under the stack (`backend-laravel`,
`node-frontend`, `python-backend`, `dart-flutter`) or role (`role-cto` etc.)
on top of skills. Details - [Agent-packs](./configs/agent-packs).

```
harness agent-packs list
harness agent-packs render  --auto --pack <pack> --target .
harness agent-packs upgrade        --pack <pack> --target .
harness agent-packs doctor  --target . [--drift [--strict]]
```

- Each generated file receives **provenance-header**
  (`swissknifeman:generated`) — pack/version/edit-policy/extension points;
  cannot be corrected generated-core, a override-file (`.claude/rules/<prefix>-reviewer-overrides.md`).
- `doctor --drift` (and `--strict` for CI) catches generated-files, edited
  locally by override; the same signal hits `pack_drift` verdict
  `maind analyze` (ATTENTION, not RED).

### `harness instructions`

Controls twelve root projections/batch instructions (`CLAUDE.md`/`AGENTS.md`
in the root and one per package) from general canon `configs/common/instructions/**` —
mechanism, three observations (`stale-source`/`managed-drift`/`ownership-conflict`) and
two machine gates are discussed in detail in [canon of root instructions](./reference/instruction-canon).

```
harness instructions plan                         # no-write snapshot
harness instructions check                        # + literal coverage gate
python3 -m harness.instructions --check            # modular point (same verdict)
harness instructions apply --authorize CLAUDE.md,packages/harness/AGENTS.md
harness instructions repair --authorize <targets> --observed-hash <target=hash,...> \
  --preimage-dir adjacent-backup
harness instructions adopt --authorize <target> --owner-decision D# \
  --mapping mapping.json --preimage-dir preimages/
```

- `plan`/`check` — no-write; `apply`/`repair`/`adopt` are written only after an explicit
  operator authorization (`--authorize`), list of targets - ALPHABETIC by path.
- `apply`/`repair` create/repair targets already under control;
  `--preimage-dir` y `repair` — fixed string `adjacent-backup`.
- `adopt` takes control of an EXISTING unmanaged file: requires
  `--owner-decision`, `--mapping` and `--preimage-dir` (directory pre-image'ov) all three.
- Manual editing of managed blocks (between HTML-markers) banned forever -
  next `check`/`repair` will see this as `managed-drift`.

### JSON commands for other modules

`maind` (and any other module) reaches harness only through these commands, found by `aicore.util.partners`; each prints a
closed contract with `--json`:

| Command | Contract |
|:--|:--|
| `harness mcp catalog [--provider ID]` | `mcp-catalog/v1`: the catalog, the bindings and the sources for the artifact lock |
| `harness profiles resolve --provider ID --profile ID --target-scope S ...` | `profile-resolution/v1` |
| `harness hooks codex-lifecycle fragment` / `validate --document FILE --memory-command CMD` | `codex-lifecycle/v1` |
| `harness instructions scopes` | `instruction-scopes/v1` (scope ids and target files from the catalog) |
| `harness hooks show` / `sync` | `hooks-state/v1` |

The pure MCP projection these commands feed is `aicore.provider.mcp`; the profile renderers stay in harness.

### Settings: `policy_profile`

The project's expected policy is `policy_profile` under `[harness]` in `.swissknifeman/config.toml`; the legacy
`.swissknife.json` key is still read with one `HARNESS_LEGACY_POLICY_PROFILE` warning until `swissknifeman upgrade`.
The provider selection of a project is `[aicore.providers.selection.<id>]`. Settings writers keep the replaced file through
`aicore.state.backup`; the locks `.swissknifeman/provider-artifacts.lock.json` and `.claude/agent-pack.lock.json` stay where
they are.

### `harness doctor`

`harness doctor --json` prints a list of `check-result/v1` documents: `harness.environment` (Python floor
`aicore.MIN_PYTHON`, presets and launcher), `harness.hooks` (hook files in `~/.claude/hooks/`), `harness.hooks-env` (the
carrier is current) and `harness.safe-dirs`; the text form prints `<status> <check_id>: <observed>`. The probe writes nothing and
prints no secret. Provider audit:

```
harness doctor --settings --provider cursor --target .
harness doctor --provider-audit
```

## Contact skiller and maind

- `skiller connect`/`vendor`/`integrate` name `harness permissions` under the hood
  (`--no-permissions` disables) — does not need to be installed separately.
- Memory shares state with the other modules: installed hooks `~/.claude/hooks/memory/` read the machine
  `topology.json`/`projects.json` registries (legacy place `~/.swissknifeman/`).
- Plugin `harness@swissknifeman` gives slash-commands `/harness:*`.


## Skills

The module plugin ships `agent-packs`. The sources live in `packages/harness/skills/` and are released with the module.
A project receives them through the host-provided `system` bucket of `skiller`: `skiller connect` enables the plugin
`harness`, and `skiller sync` copies the skills into the project. The `skiller` guide
"Configuration, host buckets and metadata" describes the bucket.
