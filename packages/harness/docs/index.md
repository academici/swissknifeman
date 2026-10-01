# CLI harness — agent environment

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
harness hooks --target . --memory core:federation # file|federation|agentmemory|off
```

- `--auto-approve` writes `.claude/auto-approve.env.ini` and registers PreToolUse-hook
  (Bash/ExitPlanMode), merge-only.
- `--memory BRAIN:MODE` attaches the project to the brain: `.swissknife.json:memory_brain`
  + `.claude/memory.env.ini`.
- **review-gate** (`SubagentStop`) — deterministic architecture gate: drives away
  project verification after the subagent, `warn` → hint, `strict` → block. Mode in
  `.claude/review-gate.env.ini` (`off|warn|strict`, default `warn`), check in
  `.claude/review-gate.config.json` (`check_command`; empty → no-op). Details -
  `hooks/review-gate/README.md`.

### `harness safe-dirs`

Machine-owned allowlist trusted directories: inside its roots auto-approve
skips `rm`/`rmdir` past deny_hard (code below git — deletion is reversible), out —
blocks as before. The config lives **at the root of the monorepo swissknifeman** —
`safe-dirs.json` (gitignored, template `safe-dirs.example.json` — same pattern,
what `config.json` node maind); search ladder with hook: `$SKM_SAFE_DIRS_CONFIG`
(exclusive override) → monorepo root (via realpath launcher from PATH) →
legacy `~/.swissknifeman/safe-dirs.json` (`init` migrates it to the repo
automatically). Verdict considers `hooks/auto-approve/lib/safedirs.py` strictly
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
`~/.swissknifeman/projects.json` fall into allowlist automatically.

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

### `harness doctor`

Diagnostics: presence of presets and `apply-permissions.sh`, whether the files are installed
hooks in `~/.claude/hooks/`. Provider audit:

```
harness doctor --settings --provider cursor --target .
harness doctor --provider-audit
```

## Contact skiller and maind

- `skiller connect`/`vendor`/`integrate` name `harness permissions` under the hood
  (`--no-permissions` disables) — does not need to be installed separately.
- Memory shares state with `skiller` (`~/.swissknifeman/`): installed hooks
  `~/.claude/hooks/memory/` read `topology.json`/`projects.json` from there.
- Plugin `harness@swissknifeman` gives slash-commands `/harness:*`.
