# changelog-gate — commit-gate CHANGELOG-disciplines (optional)

Optional **Python-hook** Claude Code (`PreToolUse`, matcher `Bash`), which catches
`git commit` content type (`feat`/`fix`/`perf`/`refactor`) without editing CHANGELOG among
staged files - enforcement sections «Daily Discipline CHANGELOG» skill
[`oss-dev/release-engineering`](../../../../../skiller/skills/oss-dev/release-engineering/SKILL.ru.md)
(the rule is based on the model's memory - the gate deterministically catches a pass). Default
**NOT installed**: is included explicitly per-project.

## Modes

| Mode | Behavior |
|:--|:--|
| `off` (default) | hook is not registered in the project |
| `warn` (recommended) | warning **into the model context** (`hookSpecificOutput.additionalContext`), **does not block** |
| `strict` | **blocks** `git commit` (exit 2 + reason is stderr) |

## Detection (D33)

- commit type and skip-token is parsed **ONLY** from `-m`-messages from the command itself: message
  via `$EDITOR` (`git commit` without `-m`) is not parsed - no-op, gate does not guess;
- content type - **exactly** `feat`/`fix`/`perf`/`refactor` (at the beginning of the first `-m`);
  `docs`/`chore`/`test`/`style`/`ci`/`build` and any other prefix is auto-skip, without warning;
- marker `[changelog-skip]` in any `-m` — deliberate exception, skip without warning;
- «CHANGELOG affected» = among `git diff --cached --name-only` there is a path matching
  `(?i)changelog` — **any** CHANGELOG (root or per-package) satisfies the condition
  (monorepo-friendly, path not hardcoded);
- repo **without a single** `CHANGELOG*` in the tree (`git ls-files` does not find a match) → exit 0
  (project does not follow this discipline - safe no-op, mirrors pack-guard «no lock'a»).

MAJOR/breaking gate does NOT classify (D32/D33 — this is manually the owner, outside the gate scope).

## Files

| File | Role |
|:--|:--|
| `changelog-gate.py` | PreToolUse-hook: stdin → solution for `-m` + staged-files → exit 0/2 (+ warning) |
| `env.ini` | `MODE` (off/warn/strict). Per-project override: `[harness.hooks.changelog_gate] mode` in `.swissknifeman/config.toml` (carrier `.swissknifeman/hooks.env`; the legacy `.claude/changelog-gate.env.ini` is still read) |

## Installation / enable

```bash
harness hooks --global                                  # copies the hook to ~/.claude/hooks/changelog-gate/
harness hooks --target . --changelog-gate warn           # include in the project (config + hooks.env + registration PreToolUse)
harness hooks --target . --changelog-gate strict         # blocking mode
harness hooks --target . --changelog-gate off             # turn off (kill-switch, hook remains registered but inactive)
```

## I/O-contract (for debugging)

Hook reads JSON payload PreToolUse on stdin (`cwd`/`tool_name`/`tool_input.command`), solution -
by `-m`-command message and `git diff --cached --name-only`/`git ls-files` in `cwd`. Nothing on
the disk does not write.

```bash
echo '{"cwd":"/proj","tool_name":"Bash","tool_input":{"command":"git commit -m \"feat: X\""}}' \
  | python3 changelog-gate.py   # warn + content type without CHANGELOG staged → JSON on stdout, exit 0
echo 'not json{' | python3 changelog-gate.py   # → exit 0 (never drops the session)
```

## Non-blocking warning into the model context

RAG:✅ 2026-07-11 (`code.claude.com/docs/en/hooks.md`, perplexity-web): for `PreToolUse`
non-blocking context is delivered via JSON on stdout with exit 0 —
`hookSpecificOutput.{hookEventName:"PreToolUse", permissionDecision:"allow", additionalContext:<reason>}`
(field `additionalContext` is only ignored when `permissionDecision:"defer"`, therefore warn
always carries an explicit `"allow"`). `strict` does not use JSON-channel - blocks with standard
`exit 2` + reason is stderr (like `pack-guard`/`block-dangerous-git.sh`).

## Fair limits (we will not overpromise)

- Type and skip-marker are visible only if the commit is made via `-m` in the most Bash-command;
  `git commit` without `-m` (opens `$EDITOR`) hook doesn't see - doesn't guess, no-op.
- «Content» — exclusively by conventional-commit prefix (D33): path-heuristic
  on modified files was deliberately rejected as fragile.
- Gate does not classify MAJOR/breaking — this is always a manual decision of the owner (D32).
