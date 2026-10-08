# Adapter: Grok

Full cycle of integration with Grok Build CLI as the **fourth managed provider**:
skills through `.agents/skills` (same discovery as Cursor), environment via
`.grok/*` (Claude-shaped hooks in `.grok/hooks/*.json`, MCP TOML). No
`.grok/skills` writer and no fourth Task skill tree.

`grok` and PATH `agent` are the **same Grok binary**. Cursor's CLI is
`cursor-agent` (historically also invoked as `agent --workspace`). Session
identity is `GROK_SESSION_ID`. Grok models listed inside Cursor (`grok-4.6` as
a Cursor inventory id) are Cursor models, not this provider.

## Projection and discovery

| Surface | Channel | Note |
|:--|:--|:--|
| Skills | `.agents/skills/` | Grok reads natively; skiller does not write `.grok/skills` |
| Connect/vendor | — | `packages/aicore/configs/provider-distribution.json` discovery only |
| Instructions (extension) | `.grok/rules/*.md` | common contract stays in `AGENTS.md`; `root.grok.*` only |
| MCP | `.grok/config.toml` `[mcp_servers]` | Codex TOML adapter, merge-only |
| Permissions | `.grok/config.toml` `[permission]` | deny floor only; mode is a launch flag |
| Hooks | `.grok/hooks/swissknifeman.json` + `lifecycle.py` | Grok loads `.grok/hooks/*.json` |

## Installation (project)

### 1. Enable provider

```json
{
  "providers": {
    "selection": {
      "grok": { "enabled": true }
    }
  }
}
```

Fleet health still requires only Claude/Codex/Cursor. Grok is optional per project.
Everyday path is `workspace-contained`. `trusted-full-access` only for self-host
under `self-host-apply` / `repo:swissknifeman`.

### 2. Machine plugins (once)

```bash
# from the swissknifeman checkout, when grok is on PATH
./install.sh
```

This installs the Grok marketplace, the host-configured command plugin, and `prefix-hold`
(`--trust`), so a new session lists `/task:*`. Opt out with
`--no-grok-plugins`. The script does not enable Grok on a project.

### 3. Project rollout

The project is already registered (`maind onboard <path|id>`). Skills on the
connect channel refresh through `maind sync` (`skills-catalog` →
`skiller update`) into `.agents/skills`. `skiller sync` is the vendor channel
and needs `.swissknifeman/config.json`.

```bash
maind sync --project my-app
harness hooks --provider grok --observer --safe-dirs --daemon-safety --trusted --target .
maind health --project my-app   # provider:grok trust when enabled
```

The same sync appends `.gitignore` lines for service files that already exist,
including a machine-specific `.grok/config.toml`. Hooks and rules stay
committed. Sync does not run `git rm --cached`.

### 4. Permissions

```bash
harness doctor --settings --provider grok --target .
```

Launch mode, not a project key: `observe` → `--permission-mode default`,
`workspace-contained` → `--permission-mode acceptEdits`,
`trusted-full-access` → `--always-approve`. The shared deny floor survives
`--always-approve`. `[ui] permission_mode` belongs in `~/.grok/config.toml`.

## Launch-block (cold-start)

```bash
grok --cwd <repo-cwd> \
     --model <model-selector> \
     --always-approve \
     '/task:<command> <arguments>'
```

Pins: `grok-4.5` (economy) / `grok-4.6` (implementation) / `grok-4.7` (frontier).
See [Provider model roles](/task/reference/provider-model-roles).

Do not pass Cursor `--workspace` / `--force` flags. Do not follow `root.codex.*`
or `root.cursor.*` launch text from `AGENTS.md` in a Grok session.

## Diagnostics

For the optional Task projection check, set `TASK_ROOT` to the installed Task
package directory and `SWISSKNIFEMAN_ROOT` to its host repository.

```bash
skiller budget --first-turn --provider grok --target .
maind health --cwd
harness doctor --settings --provider grok --target .
python3 "$TASK_ROOT/scripts/render-provider-commands.py" --check --root "$SWISSKNIFEMAN_ROOT"
```

## See also

- [Harness setup: Grok](/harness/setup/grok)
- [Provider model roles](/task/reference/provider-model-roles)
- [Adapter Cursor](/skiller/adapters/cursor) — sibling skill discovery
