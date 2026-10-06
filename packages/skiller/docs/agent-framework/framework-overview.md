# Framework Overview — current state

A canonical slice of what is already in the framework. **This is an audit input**
([framework-audit](../workflows/framework-audit)): you submit Perplexity along with
[decisions-ledger](./decisions-ledger), so that the audit looks for deltas and not
re-offered what was ready.

Statuses: ✅ yes · 🔜 in progress (plan phase) · ⏸ deferred.

## Distribution and versioning

- ✅ **Packages:** `harness` (environment Claude Code: hooks/settings/MCP/packs),
  `skiller` (skills + hub), `maind` (memory/graph). Writing to projects - merge-only + `.bak`.
- ✅ **agent-packs** — versioned packs (`harness/configs/claude-code/agent-packs/<pack>/`):
  `pack.json` (semver) + `CHANGELOG.md` + agents/workflows/hooks/settings/docs.
  Per-pack version. Installation/upgrade — agent-driven via skill `system/agent-packs`.
  Ten live packs (`configs/claude-code/agent-packs/backend-laravel/pack.json` 0.12.3,
  `_common/pack.json` 0.5.1, `dart-flutter/pack.json` 0.5.3, `laravel-package/pack.json`
  0.2.3, `node-frontend/pack.json` 0.5.3, `python-backend/pack.json` 0.5.3,
  `role-cto/pack.json` 0.1.3, `role-founder/pack.json` 0.1.3, `role-maintainer/pack.json`
  0.2.3, `role-tech-lead/pack.json` 0.2.3).
- ✅ **lock** — `.claude/agent-pack.lock.json` in project: version + interview answers +
  `sha256` rendered files → upgrade without diff-engine (hash comparison + CHANGELOG).
  Carrier - the Harness agent-packs renderer.
- ⏸ **profiles-inheritance** (`extends`) — as data, not engine (deferred); in
  `profiles/*.json` not used (`grep -l extends profiles/*.json` — empty).

## Skills and their visibility

- ✅ **Registry** `skills.json` (+ `_index.md`, marketplace) — `skiller registry`.
- ✅ **Hub = AI Skills Index**: `scripts/generate-hub.sh`; in Boost-projects is written in
  `.ai/guidelines/swissknifeman-hub.md` (markers `<!-- swissknifeman:hub:start/end -->`),
  not generated CLAUDE.md.
- ✅ **Native field `skills:`** on subagent (preload, Claude Code ≥2.0.43); on
  unknown/disabled name - skip + entry in debug-log, not quiet no-op without a trace
  (first-party `https://code.claude.com/docs/en/sub-agents`, verified 2026-07-29) — from here
  regression «skills are not visible», names are not verified yet.
- ✅ **Fix visibility** (Phase 1, `scripts/generate-hub.sh`): hub gets
  agent-routing slice + name matching `skills:` with `skills.json` (`⚠` on inconsistency) +
  freshness-stamp; `skiller doctor` flagit drift (`generate-hub.sh:194` freshness-hash,
  `:253-255` `⚠` on inconsistency; `lib/skiller/doctor.py:1062-1090` hub drift).

## Roles and orchestration

- ✅ **Plugin agents**: `laravel-reviewer`, `laravel-test-writer` (php), `code-coordinator` (system).
- ✅ **Orchestration Skill** `laravel-architecture/laravel-subagents` (delegation threshold, review/tests, worktree).
- ✅ **Universal roles** (`configs/claude-code/agent-packs/role-bindings.json`):
  reviewer/implementer(slice-builder)/test-writer/explore/plan/spec-writer like seed-agents
  are rendered from packs via linking (`binding_version 1.0.0`, roles `_common` +
  stack packs); general, stack - from profile.
  `skills:` preload + self-load fallback — preload **not applicable**, when role
  started as teammate agent-commands (see [roles](./roles), [agent-teams](./agent-teams)).
- 🔜 **path-scoped rules** (`.claude/rules/`, native) — five have subtle rules on paths
  packs (`agent-packs/{_common,backend-laravel,dart-flutter,laravel-package,node-frontend,
  python-backend}/rules`), **rules index in hub no** (`grep -n rules
  scripts/generate-hub.sh` — empty).

## Hooks and gates

- ✅ **auto-approve** (PreToolUse), **memory**, **notify**, **log** (Harness hooks).
- ✅ **review-gate** (SubagentStop, off|warn|strict, the Harness review-gate hook)
  — full generic-runner, 128 lines, dispatcher `checks/`.
- ✅ **Agent Teams** (opt., experiment, CC ≥2.1.178, default `teammateMode` — `in-process`
  with v2.1.179): preset `harness/configs/claude-code/settings.agent-teams.json` (env-flag +
  `teammateMode`) + doc [agent-teams](./agent-teams) (spawn-templates, module-boundaries,
  quality-gate hooks). Config forward compatible; frame roles are suitable as teammates, **but without
  of his `skills:`-preload** — see [agent-teams](./agent-teams) «Limitations».

## Workflow

- ✅ **Workflow-tool** (native, ~16 competitive / 1000 for run - ceiling workflow-runtime, `findings/04` F17) — Agent-tul carries ITS ceilings, see. «Limits
  subagents» below; agents workflow are not counted in them.
- ✅ **dev-loop** like pack-template (`workflows/dev-loop.js`) for five packs
  (backend-laravel, node-frontend, python-backend, dart-flutter, laravel-package),
  slice→impl→test→review. Defense lessons: one branch per run, hard cap literal
  (is worried resume), circuit-breaker.

## Subagent limits (Agent-tul, first-party `https://code.claude.com/docs/en/sub-agents`,
verified 2026-07-29)

- Total subagents per session: **200** (`CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION`, v2.1.212+).
- Simultaneously: **20** (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, v2.1.217+).
- Nesting depth: **3** (v2.1.219; was 1 in v2.1.217–218, 5 immutable until v2.1.172–216).

## Tasks and memory

- ✅ TodoWrite (session) + `args.slices` (run dev-loop).
- ⏸ Persistent task-graph (next-task between sessions) — on `maind`/agentmemory, deferred.

## Quality

- ✅ `quality/code-simplifier`, `general/anti-drift`.
- ✅ **ponytail-discipline** (YAGNI-ladder + over-engineering-passage, `agent-packs/{backend-laravel,laravel-package}/agents/reviewer.md`)
  absorbed into reviewer-role; optional skill `quality/lean-code` is not started and
  was planned to be mandatory (`skills/quality/` — 11 skills, `lean-code`
  is not among them).

## Tested against tree: 2026-07-30

| Pack | Version |
|:--|:--|
| _common | 0.5.1 |
| backend-laravel | 0.12.3 |
| dart-flutter | 0.5.3 |
| laravel-package | 0.2.3 |
| node-frontend | 0.5.3 |
| python-backend | 0.5.3 |
| role-cto | 0.1.3 |
| role-founder | 0.1.3 |
| role-maintainer | 0.2.3 |
| role-tech-lead | 0.2.3 |

Table - freshness gate machine anchor (P3.3): the host check
`python3 scripts/agent-framework-freshness.py` compares versions with the installed
Harness agent-pack manifests (`pack.json`). Update this file and stamp
at the end of each phase/audit - it is the input of the next audit.
