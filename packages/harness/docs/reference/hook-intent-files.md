# Hook modes: `[harness.hooks]`, `.swissknifeman/hooks.env` and the legacy `*.env.ini`

## Current model

The modes of the hooks installed in a project are keys of the project configuration,
`.swissknifeman/config.toml`:

```toml
schema_version = 1

[harness.hooks.pack_guard]
mode = "strict"

[harness.hooks.pack_guard.providers.cursor]   # replaces the general key for one provider
mode = "warn"

[harness.hooks.memory]
mode = "maind"
```

`harness hooks sync [--target P]` renders the committed carrier `.swissknifeman/hooks.env` from it
(`harness hooks show [--target P] [--json]` prints the configuration, the carrier, the legacy files
and whether the carrier is stale; contract `hooks-state/v1`). The flags of `harness hooks`
(`--auto-approve`, `--memory`, `--router`, `--run-report`, `--pack-guard`, `--plan-guard`,
`--plan-regen`, `--changelog-gate`, and `--review-gate`, `--git-guardrails` with `--provider`)
set the key and run the sync; they write no `<hook>.env.ini`.

Carrier format: the first line is a "generated, do not edit" comment, then sorted `KEY=value` lines
that the configuration sets: `<HOOK>_<KEY>` (`AUTO_APPROVE_MODE`, `MEMORY_MODE`, `MEMORY_BRAIN`,
`AGENT_ROUTER_POLICY`, `RUN_REPORT_ENABLED`, `RUN_REPORT_RUNS_KEEP`, `PACK_GUARD_MODE`,
`PLAN_GUARD_MODE`, `PLAN_REGEN_MODE`, `CHANGELOG_GATE_MODE`, `REVIEW_GATE_MODE`,
`GIT_GUARDRAILS_MODE`, `OBSERVER_ENABLED`) and `<HOOK>_<KEY>__<PROVIDER>` for a provider
(`MEMORY_MODE__CURSOR`, `PACK_GUARD_MODE__CLAUDE_CODE`). The file is committed (gitignore policy
entry `hook-modes-carrier`), so a fresh clone gets the modes. Hooks parse it as plain lines.

Every reader uses this ladder (a hook installed in `~/.claude/hooks` or in a project has no aicore):

```
<project>/.swissknifeman/hooks.env   (provider key, then the general key)
      ↓ (key not set)
<project>/<provider-dir>/<hook>.env.ini   (legacy, read only)
      ↓ (not found)
<hookdir>/env.ini                          (machine default of the hook, Claude hooks only)
      ↓ (not found)
the default in the code
```

A project with no carrier behaves as before. The legacy files are never written or deleted by new
code; the values move with `swissknifeman upgrade`.

## Legacy `*.env.ini` (read only)

`*.env.ini` — designed media **hook intent per-project** (what mode is included in
THIS tree): not scattered local configs and not a duplicate node config mAInd. File
`~/.swissknifeman/config.json` audit assumption was not confirmed: there is no `config.json`
at all - yes `projects.json`/`topology.json`/`memory/` (fleet register), and node config template
maind — the `[maind]` settings (`config.example.toml` of maind: `node`/`memory`/`graph`/`agents`/`mcp`/`observability`)
and the fleet registry (`configs/registry.example.json`: `namespaces`/`projects`/`mcp.servers`) — another item, merging them would mean breaking the working one
mechanism for the sake of eliminating duplication that does not exist (P5.3, `research/05-p5-hygiene-model.md`,
`findings/P5-hygiene-surfaces-2026-07-31.md` §4).

## Two file classes - and a tracking rule by class

| Class | Path | B git? | Why |
|:--|:--|:--|:--|
| **Per-project intent** (machine specific) | `<project>/.claude/<hook>.env.ini`, `<project>/.codex/memory.env.ini` | **NO** — `.gitignore` | This is the choice of THIS tree (bypass/strict/maind/off), not a common base; the commit would take someone else's choice to someone else's repository |
| **Hook default pattern** | `configs/claude-code/hooks/<hook>/env.ini`, `configs/claude-code/agent-packs/<pack>/hooks/review-gate.env.ini` | **YES** | This is the default being distributed: `harness hooks`/agent-pack copy it to the project as the original stair value |

Class rule, not file list: the next hook gets its fate automatically based on
in which of the two directories it lives. `.gitignore` catches the class "per-project intent" patterns
without a leader `/` (`.claude/auto-approve.env.ini`, `.claude/memory.env.ini`,
`.claude/run-report.env.ini`, `.codex/memory.env.ini`) — match at any tree depth.

**Inventory Find (not a hypothesis):** to P5.3 tracking was inconsistent - one
class, three destinies. `.claude/run-report.env.ini` (per-project intent) was committed contrary to
to its class; `packages/skiller/.claude/auto-approve.env.ini` (too per-project intent, inside
monorepo) was committed historically, before the class rule appeared in `.gitignore`.
Both untracked with this item'ohm (`git update-index --force-remove`, without command with substring `rm`);
`.gitignore` added with lines `.claude/run-report.env.ini` and `.codex/memory.env.ini`
(`auto-approve`/`memory` per-project patterns have already covered any depth, including
`packages/skiller/.claude/`).

## Priority ladder of the legacy files

Same for both bash-readers (`auto-approve`, `memory`), after the carrier:

```
$CLAUDE_PROJECT_DIR/.claude/<hook>.env.ini   (per-project override — if the file exists, it is used)
      ↓ (not found)
<hookdir>/env.ini                             (hook default template)
      ↓ (not found)
"off"                                          (hard default in the code)
```

`memory`-hook on Codex-side additionally looks `.codex/memory.env.ini` (the same
per-project class, same format) — `packages/harness/lib/harness/hooks.py:365`.

`run-report.py` and `maind/health.py` **do not carry this ladder**: they read exactly one path
(`<cwd>/.claude/run-report.env.ini`, `<project>/.claude/memory.env.ini`) and its absence
fall on a hard default in the code - the second layer (`<hookdir>/env.ini`) they don't have it. Don't be confused
«one read point + default in code» with a priority ladder are different designs of the same
family.

For new run-report'The output directory is defined separately: `run-report.py` gets
repository root via `git rev-parse --show-toplevel` from actual `cwd` and writes to
`<git-root>/.claude/runs/`; out Git fallback remains `<cwd>/.claude/runs/`. Historical
nested reports are not moved.

## Format scheme (measured, not expected)

`KEY=VALUE`, one key per line, `#`-comments and empty lines are skipped. Format
is parsed manually in four places (`auto-approve/lib/common.sh`, `memory/lib/common.sh`,
`run-report.py`, `maind/health.py`) — the general parser module does not start here (cross-lingual
border bash↔python, P5.3 Scope Excluded).

**Unknown key (measured by run, `packages/harness/tests/test_hooks.py`
`test_read_mode_ignores_unknown_key`):** all four readers silently ignore him - no mistakes,
no warning. `FOO=bar` next to `MODE=permissive` does not change the parsed value `MODE`.
Practical consequence: typo in key name (`MODEE=…`) is not diagnosed by this layer -
the hook will simply roll back to the next rung of the ladder/default.

Known keys by hook:

| Hook | Keys | Valid values |
|:--|:--|:--|
| `auto-approve` | `MODE` | `strict` \| `permissive` \| `bypass` \| `off` |
| `memory` (Claude Code) | `MODE` | `maind` \| `file` \| `federation` \| `agentmemory` \| `off` |
| `memory` (Codex) | `MODE`, `BRAIN` | `MODE` — same set; `BRAIN` — name brain (free line) |
| `run-report` | `ENABLED`, `RUNS_KEEP`, `DIGEST` | `ENABLED`/`DIGEST` — `on`/`off`/`0`/`1`/`true`/`false`/`yes`/`no` (case insensitive); `RUNS_KEEP` — integer ≥ 1 |
| `agent-router` | `POLICY` | modes `agent-router` (see `hooks.py:block_router`) |

## Editing procedure

Edited manually by a person/agent - there is no generator. New hook with own `env.ini`
automatically receives the tracking class and fate according to the rule above - it does not require a separate step.
