# Read-only review: phase P11 (hub modules maind, analyst, harness; doctor; core and artifex removal)

You are an independent reviewer. The repository is /home/vostrikov/projects/packages/swissknifeman-next (branch
ecosystem-split, clean tracked product tree). Do not edit files; the repository is read-only for you. You may run
tests and commands (write only under a temporary directory). Report findings only; the owners fix them.

## Candidate

- Candidate: `HEAD` (89c858ecd, after the last product commit of the phase).
- Base: a2e89b866 (the commit before the first P11 commit `49b896b13`).
- Change set: `git diff --stat a2e89b866..HEAD -- . ':!plans'` (about 740 files); commits `git log --oneline a2e89b866..HEAD`
  (subjects end with `PLAN3.P11.<n>`; n = 1..14 are the phase items). Work only from product files; plan documents are
  not needed and not part of the scope.

## Scope (new or changed, by area)

- `packages/maind/**` (partner clients, config places, topology/fleet registry, MCP server, doctor/health, harness link)
- `packages/analyst/**` (run analytics moved from the old core, partner access, event subscriber, telemetry, doctor)
- `packages/harness/**` (hooks env, safe-dirs, model catalog use, instructions generator, doctor, standalone layout)
- `packages/aicore/**` (`aicore.util.partners`, `MIN_PYTHON`, state helpers), `packages/skiller/**`, `packages/planner/**`
  (only the P11 touches), `packages/orch/**` and `bridges/**` (only the P11 touches)
- removals: `core/` and `packages/artifex` (must be gone); `configs/ecosystem-units.json`, `configs/ecosystem-baseline.json`,
  `scripts/ecosystem-units.py` (map, baseline, `check --strict`), `.github/workflows`, root `CLAUDE.md`/`AGENTS.md` and
  generated projections, `docs/**` (architecture, ADR 0063–0071), `tests/golden/**`, `scripts/e2e-*.sh`, `scripts/test-integration.sh`

## Contract (what must hold)

1. Modules maind, analyst, harness import only stdlib, themselves and aicore; `python3 scripts/ecosystem-units.py check --strict`
   exits 0; `core/` and `packages/artifex` do not exist; foundation aliases, transitional roots, retired and foundation paths are empty.
2. Partners (analyst, maind, skiller, planner, orch…) are reached only through `aicore.util.partners` and public commands with
   JSON output; an absent partner never breaks a command (a warning such as `PARTNER_UNAVAILABLE`, not a crash).
3. Legacy files are read with a warning; writes go to the active source; there is no silent migration. No writer remains for
   `*.env.ini`, `*.bak`, `~/.maind`, `~/.swissknifeman/*` (state goes through aicore.state, config through the module sections
   `[harness.hooks]`, `[maind]`, `[maind.graph]`, backups through the backup place).
4. Bytes of provider files written by deploy/sync and the lock records did not change (equality tests exist and test something).
5. Hooks read `.swissknifeman/hooks.env`, then the legacy env.ini; safe-dirs is fail-closed (an unreadable or invalid list
   denies, never allows). Registry readers of hooks follow the new state places (topology, projects).
6. Doctor: `bin/<module> doctor --json` of maind, analyst, harness prints a list of `check-result/v1`; text lines are
   `<status> <check_id>: <observed>`; the probe writes nothing (filesystem snapshot before and after); secrets are never
   printed (`AGENTMEMORY_SECRET`, MCP env); the Python threshold comes from `aicore.MIN_PYTHON` (no `(3, 8)` in module libs);
   `maind health --plan-repair` only reads, `--apply-repair` writes, `--fix` is an alias; `unit.json` `provides.doctor`
   has `output: check-result/v1`.
7. maind MCP: protocol version negotiation (an unsupported client version gets the server's version), `tools_digest` is
   printed by `maind mcp tools --json` and by doctor; the `mcp-tools/v1` contract exists in `unit.json`.
8. The analyst event subscriber is idempotent (the same event twice = one effect) and does not copy event `data`;
   its stdout is `{status: ok|skipped, result}`; metric labels pass `metric_label_problems`.
9. harness reads the model catalog from aicore (no `command-routing` in `lib/harness/run`, no planner path in `cursor_render.py`);
   harness works standalone (outside the hub), maind and analyst likewise (`scripts/ecosystem-units.py check` standalone passes).
10. Documentation and ADR 0063–0071 agree with the code: a doc statement that disagrees with the code is a defect; docs
    of removed things (core, artifex) do not remain as live links.
11. Product files are English, contain no plan ids and no home paths (`python3 scripts/public-hygiene.py`).

## E1/E2 cross-check (thesis → expected check)

- E28 doctor probe/repair split → probe writes nothing, output is check-result/v1 (maind, analyst, harness)
- E30 secrets only by reference → SENTINEL test in doctor, health, `analyst events`, MCP output
- E37/R11 telemetry names/cardinality → `analyst/telemetry.py` and its test
- R31 MCP version/digest → see contract 7; R57/R46 stay deferred/rejected
- R15/D35 Python floor → `aicore.MIN_PYTHON` everywhere in doctors
- E13 → `unit.json` of maind, analyst, harness: `output: check-result/v1`
- D2 / §12 → `check --strict` exit 0; `test ! -e core`
- D5 / §5.3 → places of config and state (contract 3)
- D34 → harness reads the aicore model catalog (contract 9)

## How to check

Wide runs of the phase were done already (broad test run, standalone modules, `check --strict`, integration, e2e, golden);
do not repeat the whole suites. Re-run only what you need to confirm or refute a suspicion:

```
export HOME=$(mktemp -d) SKM_HOME=$(mktemp -d) SKM_AICORE_EVENTS__DELIVERY=off
python3 scripts/ecosystem-units.py check --strict
bash packages/<module>/scripts/test.sh          # one module at a time, only when needed
python3 scripts/golden.py check
python3 scripts/public-hygiene.py
```

Never run installers or module CLIs with the real HOME. The repository may carry ignored local tool directories
(for example under `.agents/skills`) that are not part of the candidate; do not report them.

## What to report

Only real defects: wrong behaviour, a violated contract item above, a race or ordering bug, a missed edge case, a test that
passes without testing anything, a doc statement that disagrees with the code, a leftover reference to a removed thing,
a silent legacy migration, a write to a forbidden place. Skip style. For EVERY finding give
`F<n> <severity high|medium|low>, <owner P11.x>, <file:line>`, the fact, a reproduction (failing test or command output,
written outside the repository), and the expected behaviour. Without a reproduction it is at most "plausible".
Also list briefly what you checked and it holds. Finish with `VERDICT: GREEN` or `VERDICT: RED` and, on its own line,
`FINDINGS: N`.
