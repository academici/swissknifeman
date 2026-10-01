# Permissions for Claude Code

Ready-made permission presets (package `harness`, `packages/harness/configs/claude-code/`)
solve the main pain of the new project: dozens permission-prompts in the first half hour
work. One run `harness permissions` — and the agent can perform all typical
stack instrumentation, and dangerous operations remain under control.

> Complete machine setup (global baseline + log of all agent commands) —
> in the guide [Setting up the environment Claude Code](../setup/claude).

## Presets

| Preset | File | What it allows |
|---|---|---|
| `base` | `settings.base.json` | git (push — with confirmation), gh, file operations, curl/wget, jq/rg/sed/awk, make, orchestration (`Workflow`/`Agent`/`TodoWrite`); deny for secrets and `sudo` |
| `laravel` | `settings.laravel.json` | `php artisan`, composer, pest/phpunit/pint/phpstan/rector, sail, npm/vite |
| `php-package` | `settings.php-package.json` | composer, tests and linters - without artisan |
| `node` | `settings.node.json` | node/npm/npx/pnpm/yarn, tsc, vitest, eslint, prettier |
| `python` | `settings.python.json` | python/pip/pytest, uv, poetry, ruff/black/mypy |
| `docker` | `settings.docker.json` | docker + docker compose; deletion and prune — with confirmation |
| `product-boundary` | `settings.product-boundary.json` | deny to write to the dependent package (`Write/Edit(vendor/**)`) — border «project ↔ package» |
| `yolo` | `settings.yolo.json` | `bypassPermissions` — only for isolated environments |

Preset `product-boundary` **opt-in** (is not included in autodetect): use it in
consumer projects that modify their packages so that the agent does not rule
package code «along the way» product task. More details - skill
[`package-contribution-protocol`](https://github.com/academici/swissknifeman/blob/main/skills/architect/package-contribution-protocol/SKILL.md);
option for path-repo (`packages/**`) — in his snippet `permissions-deny.md`.

The logic of each preset is three-level:

- **allow** — everyday stack instrumentation works without prompts;
- **ask** — irreversible or external (git push, `migrate:fresh`,
  `docker system prune`, `npm publish`) requires confirmation;
- **deny** — secrets (`.env`, `*.pem`, `*.key`, `~/.ssh`, `~/.aws`) and `sudo`
  are always blocked.

::: tip rm is controlled by a hook, not ask-rules
`rm`/`rmdir` in presets **are not in ask**: hard blocks them deny_hard
auto-approve-hook, and inside the trusted directories (machine-owned allowlist
`safe-dirs.json` at the root of the monorepo swissknifeman, command `harness safe-dirs`) —
skips.
Static The ask-rule would only get in the way here: hook-`allow` does not penetrate ask
from settings (official semantics permissions), and rm in safe-dirs would prompt
always. If ask-rules rm are left in the project from old presets - remove them:
`harness safe-dirs prune-ask --global --all-projects`.
:::

## Orchestration: `Workflow` / `Agent` / `TodoWrite`

B `allow` presets `base` **and** `global` added three orchestration tools -
`Workflow`, `Agent`, `TodoWrite`. They are not stack bound: they are available in any
project, so they live in the universal layer (and not in `laravel`/`node`/`python`).

Why: at startup `Workflow` each run will spawn subagents (`Agent`),
leads the plan (`TodoWrite`) and itself is a tool call `Workflow`. Without these
rules Claude Code asked for confirmation **after each phase/stage**, and long
multiphase work flow turned into a series of prompts. Auto-allow relieves this pain.

Security is not affected: only the fact of calling the tool is allowed. Subagent,
generated `Agent`/`Workflow`, performs his Bash/Read/Edit-calls **via that
same permission-layer** — wide allow doesn't open anything here, but `TodoWrite`
edits only the local task list. Point rule for a specific subagent
(`Agent(Explore)`) still works on top (see section «Rules syntax»).

The source of truth is presets; so that the rule reaches the already onboarded project,
roll it over (`harness permissions --target .` or `--global`).

## CLI `harness permissions`

```bash
# base + stack auto-detect based on project markers
harness permissions --target ~/projects/my-laravel-app

# Explicit set of presets
harness permissions --target . --preset base,laravel,docker

# Preview without recording
harness permissions --target . --dry-run

# List of available presets
harness permissions --list

# Shared settings.json instead of local
harness permissions --target . --file settings.json
```

Autodetect uses the same markers as `skiller vendor`:

| Marker | Preset |
|---|---|
| `artisan` + `composer.json` | `laravel` |
| `composer.json` without `artisan` | `php-package` |
| `package.json` | `node` |
| `pyproject.toml` / `requirements.txt` | `python` |
| `Dockerfile` / `compose.yaml` | `docker` |

Merge-semantics are safe: `allow`/`ask`/`deny` are merged with existing
goal rules without duplicates, nothing is overwritten, `defaultMode` is taken from
preset only if it is not specified in the target. A backup is created before recording
`settings.local.json.bak`.

## Where to use: settings.json vs settings.local.json

| File | Who can see it | When to use |
|---|---|---|
| `.claude/settings.local.json` | just for you (does not commit) | **default** — personal permissions |
| `.claude/settings.json` | to the whole team (in git) | consistent command rules |
| `~/.claude/settings.json` | all your projects | global preferences |

Priority (from higher): managed-settings → CLI-arguments →
`settings.local.json` → `settings.json` → `~/.claude/settings.json`.
**Deny cannot be interrupted at any level allow-ohm on the other.**

## Rules syntax - cheat sheet

Rules are evaluated in order **deny → ask → allow**, wins first
match. Therefore, the combination works in presets «wide allow + spot ask»:
`Bash(git *)` in allow and `Bash(git push *)` in ask — push will ask the rest
git no.

### Bash

```json
"Bash(npm run build)"   // exact match
"Bash(npm run *)"       // prefix: npm run lint, npm run test:unit, ...
"Bash(git * main)"      // wildcard in any position
"Bash(* --version)"     // and at the beginning too
```

Nuances verified according to official documentation:

- space before `*` is important: `Bash(ls *)` matchit `ls -la`, but not `lsof`;
  `Bash(ls*)` matches both. Suffix `:*` is equivalent ` *`;
- one `*` covers any sequence of characters, including spaces:
  `Bash(git *)` matchit `git log --oneline --all`;
- **compound commands** are sorted by operator `&&`, `||`, `;`, `|` —
  the rule must match each subcommand separately. `Bash(safe-cmd *)`
  will not allow `safe-cmd && rm -rf .`;
- wrappers `timeout`, `time`, `nice`, `nohup`, `stdbuf` and naked `xargs`
  are cut off before matching; and here `npx`, `docker exec`, `devbox run` — no:
  `Bash(devbox run *)` will allow everything that comes after `run`;
- read-only commands (`ls`, `cat`, `grep`, `pwd`, reading forms `git` etc.)
  are natively enabled in all modes and allow are not needed.

### Read / Edit

Paths - in gitignore-semantics, **four anchors**:

```json
"Read(//etc/hosts)"      // absolute path (double slash!)
"Read(~/.zshrc)"         // from home
"Edit(/src/**/*.ts)"     // from project root (single slash)
"Read(*.env)"            // from current directory
```

::: warning Common error
`/Users/alice/file` — this **not** is an absolute path, and the path is from the project root.
For absolute paths, you need a double slash: `//Users/alice/file`.
:::

The bare file name matches at any depth: `Read(.env)` ≡ `Read(**/.env)`.

### Other tools

```json
"WebFetch(domain:github.com)"        // fetch only for domain
"mcp__github"                        // all tools MCP-server github
"mcp__github__get_*"                 // him get-tools
"Agent(Explore)"                     // rule for subagent
```

## Modes: defaultMode

| Mode | Behavior |
|---|---|
| `default` | prompt on first use of each tool |
| `acceptEdits` | auto-accept file edits and fs-commands in the working directory - **is used in the preset base** |
| `plan` | read and parse only |
| `dontAsk` | auto-deny everything that is not explicitly allowed |
| `bypassPermissions` | without prompts at all - **preset only yolo** |

::: danger Preset yolo
`settings.yolo.json` includes `bypassPermissions`: Claude Code doesn't ask
nothing but explicit ask-rules and built-in fuse on `rm -rf /` and
`rm -rf ~`. Use **only in isolated environments** — containers,
VM, devcontainer-ah, where the agent cannot harm the main system. Preset
saves deny on `~/.ssh`, `~/.aws`, `*.pem` and `sudo` and ask on `git push --force`.
:::

## Example: content base

::: details settings.base.json in full
```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": [
      "Bash(git *)",
      "Bash(gh pr *)", "Bash(gh issue *)", "Bash(gh run *)",
      "Bash(gh api *)", "Bash(gh repo view *)",
      "Bash(mkdir *)", "Bash(touch *)", "Bash(cp *)", "Bash(mv *)",
      "Bash(ln -s *)", "Bash(chmod +x *)",
      "Bash(tar *)", "Bash(zip *)", "Bash(unzip *)",
      "Bash(rg *)", "Bash(jq *)", "Bash(sed *)", "Bash(awk *)",
      "Bash(sort *)", "Bash(uniq *)", "Bash(xargs rg *)", "Bash(make *)",
      "Bash(curl *)", "Bash(wget *)",
      "Bash(* --version)", "Bash(* --help)",
      "WebFetch(domain:github.com)",
      "WebFetch(domain:raw.githubusercontent.com)",
      "WebFetch(domain:api.github.com)",
      "Workflow", "Agent", "TodoWrite"
    ],
    "ask": [
      "Bash(git push *)", "Bash(git reset --hard *)", "Bash(git clean *)",
      "Bash(chmod -R *)", "Bash(chown *)"
    ],
    "deny": [
      "Read(.env)", "Read(.env.local)", "Read(.env.production)",
      "Read(**/*.pem)", "Read(**/*.key)",
      "Read(~/.ssh/**)", "Read(~/.aws/**)", "Bash(sudo *)"
    ]
  }
}
```
:::

> Preset source - `packages/harness/configs/claude-code/settings.base.json`
> (fragment above - copy for convenience). Other presets -
> [packages/harness/configs/claude-code/](https://github.com/academici/swissknifeman/tree/main/packages/harness/configs/claude-code).

## Settings audit: `harness doctor --settings`

Presets are applied by the writer (`harness permissions`); checks the resulting
configuration - paired **read-only** audit `harness doctor --settings`
(settings-doctor). It reads all layers (`user → project → local → managed`),
builds an effective configuration with provenance and reports conflicts: broken JSON
layer, non-canonical keys (e.g. `permissions.autoApprove` — Claude Code silently
ignores), conflict `defaultMode` between layers, inaccessible/unexecutable
hook commands, plaintext secrets in `env`, discrepancy with expectation
policy-profile.

```bash
# report on the current project
harness doctor --settings --target .

# machine output (CI/fleet): single JSON, exit-code 0 clean / 1 warn / 2 error
harness doctor --settings --target . --json

# check with explicit policy-profile (overlaps .swissknife.json:policy_profile)
harness doctor --settings --profile max-permissive
```

Project declares expected policy as key `policy_profile` in `.swissknife.json`
(profiles - `configs/claude-code/policy/<name>.json`: `base`, `max-permissive`);
doctor checks the fact against the declaration. Audit **doesn't fix anything** — writer remains
`harness permissions`. The same audit is available from the skill registry by facade
`skiller doctor --settings`.

## Fine-tuning for the project

The preset is the starting point. Edit after use
`.claude/settings.local.json` for the project or use `/permissions` straight
in Claude Code — interface shows all rules and source files.

Typical modifications:

```json
{
  "permissions": {
    "allow": [
      "Bash(./bin/console *)",
      "WebFetch(domain:laravel.com)"
    ],
    "deny": [
      "Read(storage/oauth-*.key)"
    ],
    "additionalDirectories": ["../shared-lib"]
  }
}
```
