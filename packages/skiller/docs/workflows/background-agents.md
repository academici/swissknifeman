# Background agents

A background agent is an agent in CI, running in parallel with development:
analogue CI/CD, but for code quality, not just tests. He doesn't interrupt
developer - works in an isolated environment and gives the result as
PR-comment or Issue.

**Key limitation:** background agent **suggests** changes, but never
does not apply them without code review. No auto-merges.

The document covers two types of background work: **CI-agents** (GitHub Actions, below) and
**Workflow-orchestration** (`dev-loop` from agent-packs — long offline runs).
Section [«Resilience»](#stability-workflow-orchestration) — about how not to get
«hours of silent grinding» under rate-limit (real incident 2026-07-01).

## Ready-made templates

Templates GitHub Actions are located as snippets of the corresponding skills -
copy the one you need to `.github/workflows/` target project:

| Template | Skill carrier | Trigger | Result |
|---|---|---|---|
| `simplify-on-push.yml` | `quality/code-simplifier` | pull_request (PHP-files) | Suggestions for simplification by commentary on PR |
| `security-audit-scheduled.yml` | `laravel-auth/laravel-security-audit` | cron (weekly) + manual | Issue with findings from severity |

After installing skills via `skiller vendor` snippets are in
`<skills-path>/<skill>/snippets/`; in the registry itself swissknifeman these
workflow are not configurable.

## Requirements

1. **Secret `ANTHROPIC_API_KEY`** in the repository settings - background agents
   are using up paid tokens.
2. **Installed skill** in the target project (`skiller vendor` or
   plugin marketplace via `skiller connect`) — prompt workflow
   refers to the skill protocol.
3. **Permissions** are specified in the templates as the minimum required:
   `contents: read` + `pull-requests: write` or `issues: write`.

## Cost Limit

- `concurrency` with `cancel-in-progress` — do not pay for outdated runs
  with a series of pushes (already in templates).
- `paths`-filters - run only on relevant files.
- Schedule - no more often than the results are actually read: weekly
  an audit that no one looks at is just an expense.
- For one-time checks, prefer to launch the skill locally in the session -
  it is free as part of a subscription.

## Anti-drift rules for background agents

Allowed: simplification suggestions, vulnerability reports, update
PHPDoc/comments in sentences.

Prohibited: changing business logic, adding dependencies, changing the database schema,
merge without review, edit tests. These restrictions are hardwired into prompts
templates - save them when adapting them to your project.

## Resilience Workflow-orchestration

Incident 2026-07-01 (project chatom): `dev-loop`-run under server-side rate-limit
Anthropic auto-retrail `agent()`-calls ~10 hours → 0 commits, without an early signal.
Reason: runtime Workflow itself retracts transient errors (including rate-limit) to
high burl; at a stable throttling this is a watch wall-clock without durable-progress.
Parsing - `docs/audits/2026-07-01-workflow-resilience-ratelimit.md`.

Verified by industry patterns 2025–2026 (RAG): 429 — is a signal
backpressure, is not a single request glitch; unbounded auto-retry = self-DoS; reliable
layer - model **job / worker / supervisor**, where supervisor detects external hangers.

### What a script CAN reliably (in the sandbox)

- **Honest statuses `green | deferred | infra-failed`.** `deferred` — test honestly not
  green (real defect); `infra-failed` — infra failure (rate-limit/timeout/`agent()`
  returned `null`). **Do not disguise infra-failure as `deferred`** — that was a lie
  incident (slices are marked `deferred`, although the reason is throttling).
- **Fail-fast to terminal `agent()===null`.** Runtime has exhausted retries → slice
  `infra-failed`, STOP entire run (not the following slice: throttling won't go away on its own).
- **Smaller batch (default 2, not 3+).** Batch N slices × (impl+test+review) multiplies
  retry-surface under throttling.
- **Heartbeat `log()`** at every step - a signal of liveliness for supervisor and human.
- **Marker text as an alternate return path.** Strict StructuredOutput-diagram at
  long/complex return is fragile (retry-cap runtime = 5 → interrupted the entire run).
  Allow with the last line `===SLICE-RESULT=== status=green|deferred` — is parsed
  regular, the run is not disrupted.

### What the script cannot do - and why it is NOT a crutch, but an escalation

`Date.now()`/`Math.random()`/`setTimeout` in the sandbox Workflow not available/are unreliable, and
`agent()` not cancelable (`AbortController` no). Therefore **lingering hang** (agent retrait
for hours, control did not return to the loop) is not caught in the script. We do not imitate protection -
transfer it to **external supervisor**:

- **Orchestrator report every ~30 min (main layer).** Main session after launch
  background dev-loop puts `Monitor`/`ScheduleWakeup` on `git log <base>..HEAD`; each
  tick - short status report; no commit per tick OR visible `<failures>` →
  `PushNotification` («dev-loop stuck: … slice Y — need intervention») + if necessary
  `TaskStop`. Never wait completion «blindly». Lives outside the sandbox → reliable.
- **Optional - standalone GitHub Actions cron-watchdog** (for runs without live
  orchestrator, e.g. night). Survives session termination:

  ```yaml
  # .github/workflows/dev-loop-watchdog.yml
  on:
    schedule: [{ cron: "*/20 * * * *" }]   # every 20 minutes
    workflow_dispatch:
  jobs:
    liveness:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
          with: { fetch-depth: 50 }
        - id: check
          run: echo "recent=$(git rev-list --count --after='25 minutes ago' HEAD)" >> "$GITHUB_OUTPUT"
        - if: steps.check.outputs.recent == '0'
          env: { GH_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }
          run: gh issue create --title "🔴 dev-loop STALE: no commits 25+ min"
               --body "Watchdog: git log base..HEAD empty - possible in-flight hang. Diagnose/stop." --label infra,watchdog
  ```

  Threshold 25 min ≈ 2× impl-budget (~12 min) + late buffer GHA-cron under load.

### Tool → parallel-safe?

| Tool | Parallel? |
|---|---|
| `agent()` dev-loop | by slices - **sequentially** (canon «parallel-in-layer, sequential-across-layer»); fan-out only on research-phase |
| `perplexity-web` | **bounded concurrency** — ≤ `maxConcurrency` in one pool/daemon (v1.3.0), NEVER 13-way fan-out independent processes (one profile = one process → `SingletonLock`). Details and recovery (`pkill` stale lock) — skill `research/query-craft` |
| `context7`, `WebSearch`/`WebFetch` | yes (stateless) |

### Recovery after stagnation

Owner by signal (push or GHA-issue) requests Claude: reads `<failures>`/`git log`,
`TaskStop`, repairs the root (throttling → wait/solo-fallback; schema-cap → token;
env → preflight), restart with resume. Stopping a run is also important as a break
**orphaned-agent** (frozen `agent()` continues to burn tokens - from the outside this is the only
way to stop it).
