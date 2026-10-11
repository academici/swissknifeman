# P10: внешние предпосылки (perplexity-web, 2026-10-10)

Маршрут: perplexity-web-mcp stdio через bash (JSON-RPC, инструменты search и search_deep). Ответы — как вернул сервис; первый ответ search на Q1 был обрезан, повтор — search_deep.

## Q1 — форма операции «следующая работа»: claim с арендой, токен владения, fencing

```text
October 2026. Answer in English, prose plus one compact table, max 700 words, with URLs to primary sources (official docs, GitHub repos, specs).
Context: a local, stdlib-only Python orchestrator of coding-agent CLIs (Claude Code, Codex CLI, Grok CLI) pulls work from a separate planner tool through a "work source" port implemented by an out-of-process bridge (JSON over stdin/stdout, one process per call). The loop is next -> brief -> run -> register. The planner already refuses a second owner of an in-progress item (ITEM_OWNED) and supports --take-over; the orchestrator journal has run-events with seq, owner_epoch (fencing) and effect receipts with idempotency keys.
Questions:
1) In established systems that hand work items to workers (Temporal task queues and activity heartbeats, AWS SQS visibility timeout / Step Functions task tokens, Kubernetes Lease, GitHub Actions runners/jobs, Celery acks_late, Buildkite agents, OpenHands / SWE-agent / AWS cli-agent-orchestrator), what is the recommended shape of the "get next work" operation: peek vs claim-with-lease, lease duration and renewal (heartbeat), what token proves ownership on completion, and how a stale worker's completion is rejected (fencing token)?
2) What is the minimal set of operations and fields for such a port so that completion is idempotent (same attempt id = no-op) and closing an item is decided by recorded evidence (executed check commands and exit codes) rather than by the worker's claim of success?
3) Name pitfalls: double claim races, lost completion after crash (completion applied but response lost), retries that create duplicate side effects, clock skew in lease expiry for local single-machine setups.
```

### Ответ (search, обрезан)

Use an atomic claim with a renewable lease—not a peek—as next. Keep peek optional for inspection. Your existing ITEM_OWNED, owner_epoch, and receipts are useful foundations, but ownership enforcement must live in the planner’s authoritative state, not only the orchestrator journal. The contract below is a design recommendation, not a universal protocol shared by these systems.

## 1. Established patterns

Sources:
1. [Temporal](https://docs.temporal.io/activity-execution)

### Ответ (search_deep)

"System / primary source","Acquisition and renewal","Completion authority; fencing limits"
"Temporal","Task delivery creates an execution attempt; heartbeat timeout detects loss; start-to-close bounds execution.","Attempt-specific task token; late completion can return NOT_FOUND. Tokens protect Temporal state, not external effects. temporal+1"
"SQS","Receive hides a message; default visibility 30 seconds; extend with ChangeMessageVisibility.","Latest receipt handle deletes it. An old handle can return success without deletion; visibility is not strict fencing or exclusive execution. aws.amazon+1"
"Step Functions","Assignment/callback task token; configure heartbeat and total timeout separately.","SendTaskSuccess(taskToken) rejects expired/already-closed tasks; retries get new tokens. aws.amazon+2"
"Kubernetes Lease","Holder identity, lease duration, renewal time; used for leadership, not job completion.","client-go explicitly does not guarantee fencing; protected resources need additional enforcement. kubernetes+1"
"GitHub runner, Buildkite","Service-assigned jobs; GitHub runner renews a job lease. Buildkite separates reservation, acquisition credentials, and agent sessions.","Service validates job/session lifecycle. Buildkite’s acquisition-token expiry is not execution-lease duration. Neither cited interface establishes a portable monotonic fence. buildkite+1"
"Celery","acks_late delays acknowledgment; redelivery depends on broker and worker-loss settings.","Acknowledgment is not an application ownership fence. Tasks must tolerate repeated execution. docs.celeryq"
"OpenHands, SWE-agent, AWS CAO","Coding-agent execution, workspaces, delegation/session orchestration.","These are execution-layer references, not evidence of a shared durable claim/lease/fencing protocol. Supply that in your planner port. github+2"

## Q2 — состояние AWS CLI Agent Orchestrator (CAO), октябрь 2026

```text
October 2026. Answer in English, max 500 words, with URLs to primary sources (GitHub awslabs/cli-agent-orchestrator releases, README, docs).
What is the current state of AWS "CLI Agent Orchestrator" (CAO, github.com/awslabs/cli-agent-orchestrator) as of October 2026: latest release version and date; supported provider CLIs (Claude Code, Codex CLI, Q/Kiro, Gemini, Grok?); how an agent profile selects the model and reasoning effort; whether it exposes an API or CLI for launch, status, sending input, shutdown/cancel, flows (scheduled workflows) and resume; how terminal status is detected (tmux, idle/completed/error states); any breaking changes in 2026 releases. Say explicitly what you could not confirm.
```

As of October 10, 2026, the latest release is v2.5.3, released October 8, 2026. It is also the first PyPI release since 2.5.0: GitHub tags 2.5.1 and 2.5.2 were not published to PyPI.

## Supported providers

Yes: Claude Code, Codex CLI, Kiro CLI, and xAI Grok Build CLI. Also supported: Antigravity, Hermes, Kimi, MiniMax Code, GitHub Copilot, OpenCode, Oh My Pi, and Cursor CLI. Amazon Q CLI and Gemini CLI providers were removed in v2.3.0; older documentation mentioning them is historical. The CLI-reference provider table omits Grok/MiniMax, although the README and release notes include them.

## Model and reasoning selection

Profiles are Markdown with YAML frontmatter:
- provider selects the CLI; cao launch --provider overrides it.
- Top-level model selects the provider model, where supported.
- Claude: claudeConfig: {effort: high} becomes --effort high; top-level model becomes --model.
- Codex: codexConfig: {model_reasoning_effort: xhigh} becomes a per-session -c override. These overrides take precedence over matching settings in codexProfile, without modifying global configuration.
I could not confirm a universal reasoning-effort setting or uniform model-selection enforcement across every provider.

## Control surfaces and resume

CAO exposes both a shell CLI and HTTP API, plus orchestration/operations MCP servers.
These operations are documented; workflow cancellation is cooperative, not an instantaneous kill guarantee. Workflow resume uses a durable journal; Python scripts restart from the top and replay completed step results. Claude supervisor conversation resume was added in 2.5.0. I could not confirm equivalent conversation resume for every provider, or a universal agent-turn cancel command.

## Status detection

Agents run as native CLI processes in tmux windows/panes. Detection uses provider-specific terminal-output interpretation, including pyte-rendered screens and bounded pane captures—not merely process existence. States distinguish IDLE, PROCESSING, COMPLETED, ERROR, and WAITING_USER_ANSWER. Spinner, composer, completion-marker, and error-dialog changes require compatibility fixes;

Sources:
1. [github](https://github.com/awslabs/cli-agent-orchestrator/releases)

## Выводы для детализации P10

- Q1: next — атомарный claim, а не peek; завершение принимается только с токеном текущей попытки, опоздавшее завершение отклоняется; токен защищает состояние источника работы, но не внешние эффекты — эффекты защищает свой ключ идемпотентности (effect_key) и повторная проверка предусловия. На одной машине аренда по времени не нужна: владение — ITEM_OWNED planner (D60), передача — явный --take-over; fencing в register — сверка result.executor.session с run_id claim (D63).
- Q2: CAO 2.5.3 (2026-10-08) поддерживает Claude Code, Codex, Kiro, Grok Build и др.; модель и effort — во frontmatter профиля (claudeConfig.effort, codexConfig.model_reasoning_effort); статус — по экрану tmux (IDLE, PROCESSING, COMPLETED, ERROR, WAITING_USER_ANSWER); отмена workflow кооперативная; resume — журнал workflow. Это подтверждает seeds cao (adapted для cancel/resume/watch) и требование свежести capability-record (D64: observed_at, fresh_until, remediation); адаптер CAO по-прежнему вне плана.
