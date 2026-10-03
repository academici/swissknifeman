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

## Installation: everyday (fleet)

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

```bash
cd ~/projects/my-app
maind onboard --cwd
maind sync --project <id>
maind health --cwd
skiller sync                         # .agents/skills
harness doctor --settings --provider grok --target .
```

Grok is optional for fleet health. Do not add it to `REQUIRED_PROVIDERS`.
`skiller update` does not auto-enable grok fleet-wide.

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
