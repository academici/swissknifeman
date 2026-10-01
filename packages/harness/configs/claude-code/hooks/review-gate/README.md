# review-gate — architecture compliance gate (SubagentStop)

Deterministic L5-milestone: after completion, the subagent runs a set of checks and,
if some did not pass, prompts (`warn`) or blocks (`strict`). Complements
`skills:`-preload skiller (L2): preload gives the agent skills, the gate catches what
the agent still scored - a guarantee is where the prose is «follow the skill» does not provide it.

## Modes (`env.ini`, default `warn`)

| MODE | Behavior |
|---|---|
| `off` | gate is completely turned off |
| `warn` | violation → hint for context (`additionalContext`), subagent is NOT blocked; DOWNLOADS any `strict`-check before `warn` (upgrade `warn`→`strict` disabled by global mode) |
| `strict` | strict-checks are blocked (see «Semantics `exit 2`» below); warn-checks, as usual, only suggest |

Per-project override: `.claude/review-gate.env.ini` (`MODE=...`).

## Contents - `checks/`, set and mode - `config.json`

Contents of the test **not** lives in `check_command` — is ONE stable line,
dispatcher call `checks/run-checks.sh`. The checks themselves are scripts that are carried
harness (`checks/<name>.sh`); machine announces ONLY dialing and per-check mode:

```json
{
  "version": 2,
  "check_command": "$REVIEW_GATE_DIR/checks/run-checks.sh",
  "checks": [
    { "name": "generated-assets", "mode": "strict" },
    { "name": "plan-lint", "mode": "strict" },
    { "name": "tests-touched", "mode": "warn" }
  ]
}
```

| Code | Verification | Default mode | What it does |
|:--|:--|:--|:--|
| G1 | `generated-assets` | `strict` | diff touches header file `swissknifeman:generated` → violation (edit belongs to the pack, is being edited override-file) |
| G2 | `plan-lint` | `strict` | diff touched `plans/<ID>/` → run `packages/task/scripts/plan-lint.py`; ERROR → violation |
| W1 | `tests-touched` | `warn` | diff touches `packages/*/lib/**` without `packages/*/tests/**` (heuristics - there are legal exceptions, so there are always `warn`, never `strict`) |

Unknown name in `checks[]` — apparent configuration error (the dispatcher prints it and
considers a violation-warn), and not a silent pass. Empty `check_command` (or
empty `checks[]`) — **fail-open no-op**, as before: quality gate refers to
advisory-class, and practice explicitly allows fail-open for him, but the state
must be VISIBLE (`harness doctor`, below), and not silent.

### Loop protection

`exit 2` on `SubagentStop` **does not interrupt** subagent (first-party: «Prevents the
subagent from stopping») — subagent continues to work with feedback in stderr, then
there is a loop «violation → repairs → check again». `stop_hook_active` is not in the dock
is described, you cannot rely on runtime. Therefore, the dispatcher himself counts in a row
coming strict-failures of the SAME check within a session+agent
(`${XDG_RUNTIME_DIR:-/tmp}/review-gate/<session>.<agent>.<check>`, atomic
entry) and on the third failure in a row lowers EXACTLY this check to `warn` with
`systemMessage` («gate lowered: check X does not work for the 3rd time, I fix it manually»).

### Custom project-local `check_command`

`.claude/review-gate.config.json` of the project is executed ONLY if the owner machine
explicitly allowed this in `$HOOK_DIR/env.ini` (`ALLOW_PROJECT_CONFIG=1`) — otherwise it
arbitrary code execution when opening someone else's repo. For such custom
`check_command` (is not our dispatcher) severity solves only global `MODE`, like
before - three-level strict/warn-per-check protocol applies ONLY to
`checks/run-checks.sh`.

## Three states in `harness doctor`

Instead of quiet no-op (recognized anti-pattern - «appears to be on, but silent
doesn't check anything») `harness doctor` prints EXACTLY one of three:

- `unconfigured (no-op)` — `check_command`/`checks[]` is empty or there is no file;
- `configured: G1, G2 (strict), W1 (warn)` — set and modes in fact `config.json`;
- `disabled (MODE=off)` — is disabled globally.

## Wiring

The hook hangs on the event `SubagentStop` in `settings.global.json`. Installs files
`harness hooks --global` (`apply-permissions.sh`) in `~/.claude/hooks/review-gate/`
(code `review-gate.sh` and `checks/` — are always updated; `env.ini` is not overwritten;
`config.json` is migrated to the new template ONLY if it is byte-for-byte equal to the old one
stub `{"version":1,"check_command":""}` — otherwise local choice is respected,
the file is not touched, the exact manual update command is printed).

## Post-installation check (live)

`exit 2`-block and `additionalContext` are confirmed only by a real run
subagent: set a known failure check and make sure that `warn` comes
hint, and in `strict` subagent receives stderr and continues working (not
is blocked tightly).
