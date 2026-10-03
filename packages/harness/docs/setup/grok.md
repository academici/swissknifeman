# Setting up the environment Grok

How to connect a project to swissknifeman as the **fourth managed provider**:
project `[permission] deny`, MCP TOML in `.grok/config.toml`, Claude-shaped hooks
under `.grok/hooks/*.json`, skills from `.agents/skills`.

## Problem

Grok Build CLI (`grok`, PATH alias `agent`) shares skill discovery with Cursor
and shares hook/MCP TOML shape with Codex. The binaries are not the same:
Cursor is `cursor-agent` with `--workspace`; Grok uses `--cwd` and
`GROK_SESSION_ID`.

Unlike Cursor, Grok accepts a project `[permission] deny` floor. It does
**not** read `[ui] permission_mode` from the project file (that key is
user-level, `~/.grok/config.toml`). Launch mode is `--permission-mode` or
`--always-approve`. The deny floor still applies.

## Profiles (semantic)

Source: `packages/harness/configs/common/profile-catalog.json` +
`packages/harness/configs/grok/config/profile-bindings.json`.

| Profile | Fleet | Launch mode (not a project key) | Deny floor |
|:--|:--|:--|:--|
| `observe` | yes | `--permission-mode default` (`ask`) | secrets blocked |
| `workspace-contained` | **everyday default** | `--permission-mode acceptEdits` | secrets blocked |
| `trusted-full-access` | **only self-host-apply** | `--always-approve` | secrets blocked |

Any non-self-host trusted profile → `HARNESS_GROK_TRUSTED_NON_SELF_HOST_REFUSED`.

## Installation

Two layers. Plugins are once per machine. Each project still opts in on its own.

### Machine (once)

From the swissknifeman checkout, when `grok` is on `PATH`:

```bash
./install.sh
```

The script adds this checkout as a Grok marketplace, then installs
`packages/task` and `packages/task/adapters/grok/prefix-hold` with `--trust`.
Task commands in a new Grok session are `/task:*`. A repeat that prints
`already configured` or `already installed` is success. Opt out with
`--no-grok-plugins`. Marketplace `core` is not installed for Grok: its source
is the repository root.

`./install.sh` does not register a project, does not enable Grok in
`.swissknife.json`, and does not write project files. An already open Grok
session keeps its old command list until a new session starts.

### Project

```json
// .swissknife.json
{
  "providers": {
    "selection": {
      "grok": { "enabled": true }
    }
  }
}
```

The project is already in the hub (`maind onboard <path|id>`). Then:

```bash
maind sync --project <id>
harness hooks --provider grok --observer --safe-dirs --daemon-safety --trusted --target .
maind health --project <id>
harness doctor --settings --provider grok --target .
```

`maind sync` writes MCP into `.grok/config.toml`, refreshes the connect-channel
skill catalog (`skills-catalog` → `skiller update`), and appends `.gitignore`
lines for service files that already exist (`gitignore`). `--trusted` on
`harness hooks` is only the hook-write gate. The everyday launch profile stays
`workspace-contained` (`--permission-mode acceptEdits`).

`skiller sync` is the vendor channel and needs `.swissknifeman/config.json`.
This fleet uses connect, so skills arrive through `maind sync`. Hub defaults
and `REQUIRED_PROVIDERS` stay claude-code, codex, and cursor: a new project
does not get Grok until `providers.selection.grok.enabled` is set.

`.grok/config.toml` from sync contains absolute launcher paths, so the same
sync adds that path to `.gitignore` when the file matches
`configs/gitignore-policy.json`. `.grok/hooks/` and `.grok/rules/` stay
committed. Sync does not run `git rm --cached`. A file that is already tracked
stays tracked until that command is run by hand.

## Trusted self-host (only umbrella)

- `origin=operation`
- `operation_id=self-host-apply`
- `target_identity=repo:swissknifeman`

```bash
cd /path/to/swissknifeman
grok --cwd "$(pwd)" \
     --model grok-4.6 \
     --always-approve \
     '/task:plan-run <PLAN-ID> <Pn.m>'
```

## MCP and hooks

MCP servers render into `.grok/config.toml` `[mcp_servers]` (shared TOML
adapter). Lifecycle hooks render `.grok/hooks/swissknifeman.json` plus
`.grok/hooks/lifecycle.py`. Grok loads every `.grok/hooks/*.json`; a root
`.grok/hooks.json` is not a hook document. Router and observer are hook-native
(Grok also loads every `.grok/rules/*.md`).

## See also

- [Adapter Grok](/skiller/adapters/grok)
- [Provider model roles](/task/reference/provider-model-roles)
- [Harness setup: Cursor](./cursor)
