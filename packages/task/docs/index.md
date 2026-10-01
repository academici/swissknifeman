# task - commands for setting and completing tasks

**What is it.** Optional helpers Claude Code (`/task:*`), Codex (`$ task:*`) and Cursor (`task:*`)
for explicit job selection.
From version Task **0.21.0** workflows are enabled only by explicitly calling the command/skill. Codex
gets `allow_implicit_invocation: false`, Claude - `disable-model-invocation: true`;
harness does not implement Task policy in SessionStart and does not select commands by keywords.
Each command **pins the model + reasoning effort + workflow profile**, interrupting the session settings,
to avoid switching them manually. Default-on in each onboarded project (connect channel);
no resident tax - command descriptions are not injected into every request.

**When to take.** When an explicit route is useful for development, research, design or review.
The normal task can be executed directly; teams do not require the creation of a plan.

Native installation of Task includes commands, configuration and Python runtime, not only
skill projections. Since v0.16.1 release attestation checks this full native cache
separate from the compact project bundle. Local ignored telemetry is not included in the release.
After the update, open a new Codex/Claude session: receipt confirms the files on disk,
but not reinitializing an already running agent.

**When NOT to touch.** This is not an engine - it only routes to the model/effort/profile. The workflow itself and
subagents live in `harness` (agent-packs); master plan protocol - in skill
`general/plan-protocol`.

## Commands

| Team | Pinit | For what |
|:--|:--|:--|
| `/task:fix` | Sonnet/medium | minor edits (narrow single-agent, no fan-out) |
| `/task:design` | Opus/high | design (artifacts, not code) |
| `/task:dev` | Sonnet/high | development by vertical slices with risk-adaptive review-gate |
| `/task:research` | Opus/high | multi-source research with RAG verification |
| `/task:review` | Sonnet/high | risk-scaled read-only review |
| `/task:plan-design` | Opus/high | create/detail a master plan `plans/<ID>/` |
| `/task:plan-run` | session route | execute plan items under the current session route; the minimum comes from the plan's Routing row |
| `/task:plan-close` | Sonnet/low | recovery-reconciliation of item or closing the phase after a fresh GREEN |
| `/task:plan-audit` | Opus/xhigh | one pre-exec or pre-close audit by material trigger |

## How to use it

For an existing plan `scripts/plan-work.py` inside the installed Task combines
service operations: `design-context` gives compact context, `finalize-design` checks
design and updates derived files, `prepare` performs admission/start and returns
execution capsule, `finalize` matches the already recorded terminal evidence. Run the script
via `python3` with `--help` for parameters. Semantic handoff and factual evidence
remain an input; the operation does not invent successful checks.

Design respects the owner's budget, reuses known findings and does not require a census
all callers/tests. Completing design does not require a new process. For limited local
work available explicit boundary `owner-session`; externalities preserve `provider-proof` —
see [authority](./reference/plan-authority.md).

The specific command selection is described in the table above; master plans (plan-protocol) - skill
`general/plan-protocol`. Process day by day - [Methodology](./methodology.md).

Plan validator: `python3 packages/task/scripts/plan-lint.py plans/<PLAN-ID>`.

A tool failure or bookkeeping defect does not open a new design cycle. Performer first
reproduces the influence, repairs the reversible local cause in the same attempt and continues. Stop
is needed only for confirmed acceptance/safety/authority border; re-audit without
material scope/SHA/risk change does not run.

`continue-root` continues a compatible ready item of the same Routing batch in the current root session;
new launch-block is printed only on the real cold-start/wait boundary. Before `plan-design`
for an existing Task phase checks item carriers: the detailed unfinished phase goes to
`plan-run` rather than re-design.

## Return fingerprints

To diagnose repeated returns between execution and design, use
deterministic view `returns`. It stores the canonical tuple being checked next to the digest.
rather than inferring the reason from the text of the notes:

```bash
python3 packages/task/scripts/plan-views.py returns --plan-dir plans/<ID> --json
```

## History of item layout v2

History is not a file that is maintained manually, but an on-demand view for the auditor over three
sources: log, immutable solutions and item-scoped findings. Default command
prints it to stdout; Only the explicit `--output` creates a permanent copy and is ignored by Git:

```bash
python3 packages/task/scripts/plan-views.py history --plan-dir plans/<ID> --item Pn.m
python3 packages/task/scripts/plan-views.py history --plan-dir plans/<ID> --item Pn.m \
  --output .plan-cache/history/Pn.m.md --check
```

## Digest of the closed phase layout v2

The closed phase retains the original address `phases/Pn/Pn.md`, but receives a deterministic
digest `phases/Pn/Pn.closed.md` for the designer. The generator only works for the terminal
phase and fails for live; `--check` checks byte freshness:

```bash
python3 packages/task/scripts/plan-views.py closure --plan-dir plans/<ID> --phase Pn
python3 packages/task/scripts/plan-views.py closure --plan-dir plans/<ID> --phase Pn --check
```

## Methodology plan-protocol 2.0

| Page | What's there |
|:--|:--|
| [Methodology - full cycle](./methodology) | Mermaid map research → design → refine (DoR, pre-mortem) → approve → exec (commit gate, two houses) → review (taxonomy) → archive → docs |
| [Continue-first, block confirmation and delivery receipt](./continue-first) | Autofix of small deviations, isolated confirmation of real Blocked, 100% RAG for external candidates and protection from early final |
| [Plan structure](./plan-structure) | folder canon `plans/<ID>/` 2.0, diff `root/`/`artifacts/`, migration table root/ → docs |
| [Templates](./templates) | reference snippets: plan/phase/handoff/launch-block/code-guidance - what is where |
| [Provider model roles](./reference/provider-model-roles) | pins economy/implementation/frontier + inventory and Auto policy for three providers |
| [Plan tooling](./reference/plan-tooling) | launch-block: Codex/Cursor native-forms, route evidence |
| [Control plane map](./reference/control-plane-map) | sources of truth, design gate, types and diagnostics of failures |
| [Workflow Designer](./workflows) | 4 canonical orchestration script templates: when which one, slot rules |

Normal cross-module development accepts a message or task file without `plans/` and phases.
Executable plan is created only upon explicit request; size, risk and carryover
do not change the route on their own. General contract - `references/intent-routing.md` of the Task package;
The owner's current request is older than the instructions within the old audit or handoff. Separate order
design/review retains the border. Next recommends continuation within Scope and Acceptance.
