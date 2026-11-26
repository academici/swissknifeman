# Client Integrations Operator Guide

SKM's `integrations` module configures local repository checkouts for interactive human work across five coding clients — **Antigravity** (`antigravity`), **Claude Code** (`claude_code`), **Codex** (`codex`), **Cursor** (`cursor`), and **Grok** (`grok`) — while enforcing policy guardrails through `skm-hook` and delivering domain/host hook subscriptions.

For exact per-target capability tables, file ownership boundaries, hook wire formats, and cold-start numbers, see the [Integration Target Capabilities Reference](../reference/integration-capabilities.md), [Configuration reference](../reference/config.md), and [CLI reference](../reference/cli.md).

## Architecture: Control Plane vs Host Operations

Following [ADR 0016](../adr/0016-integrations-vs-runtimes.md) and [ADR 0021](../adr/0021-bus-handlers-and-host-operations.md), `integrations` strictly separates control-plane state from local filesystem access:

- **Control plane (bus & PostgreSQL)**: Computes provider-neutral desired inputs (`integrations.get_desired_projection`) from `extensions`, `settings`, and `policy`. It stores applied file digests and projection state in `skm_integrations`, fans out hookable domain events into `skm_core.outbox` (`hook:<id>`), and delivers signed webhooks outside database transactions. Managed pre-images are private files on the machine that applied the projection.
- **Host operations (`skm integrations ...`, `skm doctor`, `skm budget`, `skm hooks ...`, `skm-hook`)**: Run on the machine holding the bound Git checkout; render target-specific files via `IntegrationTarget`; observe and atomically update files under a per-binding lock and crash-recovery journal (`CheckoutFs`); inspect read-only user layers (`~/.claude/settings.json`, `~/.codex/config.toml`, VS Code settings) during `doctor`/`budget`; and evaluate native client hooks.

## Antigravity

Run `skm integrations plan --target antigravity` and
`skm integrations apply --target antigravity --yes` from a bound checkout.
The projection manages instruction blocks in `.agents/AGENTS.md`, opt-in bundle
rules in `.agents/rules/`, and shared skills in `.agents/skills/`. Antigravity
also loads existing workspace instructions such as `AGENTS.md`. SKM does not
generate Antigravity hooks, agents, permissions, or MCP configuration. Use
`skm integrations remove --target antigravity --yes` to remove its projection.
Skills remain while another target owns the same file.
[Antigravity customization discovery](https://antigravity.google/docs/customization-discovery/)

## Checkout Lifecycle: Plan, Apply, Drift, Adopt, Remove

### 1. Bind a Checkout and Sync Packs

Ensure the instance is initialized, built-in packs (and optional [operator overlays](../extensions/overlays.md) or integration bundles) are synced, and your local repository checkout is bound to the active project and host:

```sh
skm ext sync
skm repo bind --path /path/to/repo --mount main --register --write-marker
```

Select target clients at the instance, workspace, or project scope (`["claude_code"]` by default):

```sh
skm config set integrations.targets '["antigravity","claude_code","codex","cursor","grok"]' --scope project
```

### 2. Preview and Apply Projections

`plan` computes three-way file decisions (`create`, `update`, `noop`, `adopt_clean`, `adopt_required`, `conflict_write_new`, `remove_owned`, `leave_modified`, `boundary_invalid`, `unsafe_target`) without mutating the checkout:

```sh
skm integrations plan --mount main
skm integrations apply --mount main --yes
skm integrations list
```

Key guarantees during `apply`:

- **Idempotency**: Re-running `plan` or `apply` when neither desired inputs nor owned checkout bytes changed produces `noop` for every file (`0` writes, state `in_sync`).
- **Foreign content preservation**: Text outside `<!-- skm:begin ... -->` / `<!-- skm:end ... -->` in `CLAUDE.md` and `AGENTS.md`, unmanaged skills, foreign JSON keys (including explicit `false` flags and team hook commands), and foreign TOML comments/tables in `.codex/config.toml` and `.grok/config.toml` are preserved intact.
- **Secret references stay unresolved**: MCP server `env_refs` (`secret://env/GITHUB_TOKEN`) are written as symbolic references, never resolved secret values.
- **Shared `.agents/skills/`** works across `antigravity`, `codex`, `cursor`, and `grok`. These targets share `.agents/skills/<skill>/SKILL.md` cleanly in a single checkout.
- **Integration bundles**: Enable installed pack bundles via `integrations.bundles` and customize agent role prefixes via `integrations.agents.pack_prefix` (default `"skm"`). Workflow scripts in bundles are projected as inert data files and are never executed by SKM. On `grok`, where `agents` is `unsupported`, SKM projects rules/workflows/skills/hooks/MCP, writes zero agent files, and emits an informational `CAPABILITY_UNAVAILABLE` diagnostic.

### 3. Detect Drift, Resolve `.skm-new` Conflicts, and Adopt Existing Files

Check whether any managed file or owned block/key was edited by hand:

```sh
skm integrations drift --mount main
```

- Clean checkouts exit `0` (`state = "in_sync"`).
- Modified owned content records `ProjectionDriftDetected`, sets projection state to `drifted`, and exits `6` (`PRECONDITION`). Edits outside managed blocks in `CLAUDE.md` or `AGENTS.md` are **not** drift.
- If desired inputs also changed while a managed file/block has local edits, `skm integrations apply --yes` preserves your file untouched, writes the new desired content to `<file>.skm-new` (`conflict_write_new`), and exits `6`. Merge manually or pass `--force-conflicts --yes` to overwrite the current manual edit. SKM retains the original backup from adoption or an earlier capture.
- Pre-existing unmanaged files at a `managed_file` path report `adopt_required` (`INTEGRATION_UNMANAGED_TARGET`). Capture their original bytes as a pre-image before letting SKM manage them:

```sh
skm integrations adopt .claude/rules/common.md --target claude_code --reason "adopt team rule" --yes
skm integrations apply --target claude_code --yes
```

### 4. Remove Projections Safely

Remove SKM-owned files, blocks, and merged JSON/TOML keys for a target:

```sh
skm integrations remove --target claude_code --restore-pre-image --yes
```

- Unmodified `managed_file` entries are deleted (unless still owned by an active sibling projection under `.agents/skills/`).
- Hand-modified `managed_file` entries are kept on disk (`leave_modified`, `INTEGRATION_LEFT_MODIFIED`).
- With `--restore-pre-image`, adopted and merged files whose non-owned content is unchanged since apply are restored byte-for-byte from their local backup. Existing linked project pre-images can still be restored. If a user changed non-owned content after apply, SKM removes only its owned blocks or keys.
- An explicit restore stops before changing files when the current caller's backup is missing. The machine records when a generated file had no original, so restoring that state removes the generated file.

## Read-Only Diagnostics (`doctor`) and Context Budget (`budget`)

### `skm doctor` / `skm integrations doctor`

Inspects client settings layers, permission profile conformance, `skm-hook` PATH resolution, `.claude/settings.local.json` gitignore hygiene, Codex `features.hooks = false` (`codex.hooks_feature_disabled`), projection drift, incomplete host crash journals (`host-journal:...`), and untrusted host subscriptions (`hooks.subscriptions_untrusted`):

```sh
skm doctor --target claude_code --target codex
skm doctor --strict --json
skm integrations doctor --offline
```

Run offline doctor from the bound checkout when the project hub is unavailable. This mode inspects local native layers and marks live project checks as unavailable.

- **Strictly read-only**: `doctor` never modifies checkout or home files, never records drift in PostgreSQL, and never executes configured hook commands (only `which` lookups run).
- **Secret redaction**: Suspicious secret literals in client `env` layers report `claude.secrets_in_env` (`error`, exit `1`) naming only the key and layer path — secret values never appear in human or `--json` output.
- Exit code is `1` when any `error` check fires, or when `--strict` is passed and any `warning` check fires.

### `skm budget` / `skm integrations budget`

Estimates resident first-turn tokens across all five client context sources (`skills`, `agents`, `instructions`, `hooks`, `mcp`) against `integrations.budget.first_turn.target` (`16000`) and `integrations.budget.first_turn.warn` (`23000`):

```sh
skm budget --target claude_code
skm budget --target claude_code --strict --json
```

If a projected file is missing on disk or a custom `SessionStart` command cannot be statically estimated (`run_hooks = false`), SKM reports `tokens: null` (`unknown`) for that source and `verdict: "incomplete"` (`total: null`), exiting `1` under `--strict` rather than executing the hook or reporting `0`.

## Native Client Hooks (`skm-hook`)

Applying a target registers `skm-hook` in the client's native hook configuration (`.claude/settings.json`, `.codex/hooks.json`, `.cursor/hooks.json`, `.grok/hooks/skm.json`). Configure per-surface modes (`strict`, `warn`, `off`) with `integrations.hooks.mode`:

```sh
skm config set integrations.hooks.mode '{"git_guardrails":"strict","changelog_gate":"strict","session_start":"warn"}' --scope project
skm integrations apply --yes
```

Create an expiring personal token as the user who bound the checkout. Use the workspace UUID and save the token under the selected profile's state directory, in `secrets/hook.token`. The `secrets` directory must be owned by the local user with mode `0700`.

```sh
skm token create native-hooks --scope "workspace:${workspace_id}" --expires-in 12h \
  --permission workspace.read --permission project.read \
  --permission checkout.read_locator --permission integration.read \
  --permission policy.read --permission run.read --permission inbox.read \
  --permission lesson.read --save /path/to/profile/state/secrets/hook.token
```

Start `skm-hookd` under the same local user account as the coding client before using enforcement hooks. Run it in the foreground or under a per-user service supervisor with the same `XDG_RUNTIME_DIR` as the client. Set `SKM_INSTANCE` to the verified profile name in both environments when using a named profile. Use `--bootstrap /path/to/bootstrap.toml` for a custom bootstrap location.

- The endpoint is `${XDG_RUNTIME_DIR}/skm/hookd.sock`. When `XDG_RUNTIME_DIR` is unset or empty, the daemon uses `~/.skm-hookd/hookd.sock` under the effective user's account home. The runtime directory and socket must be user-owned with modes `0700` and `0600`. Both endpoints verify the peer UID. Managed shutdown (`SIGINT` or `SIGTERM`) removes the socket. After an abrupt termination, verify that the daemon has stopped before removing a stale socket and restarting.
- Enforcement uses live project policy. An unreachable daemon, invalid payload or reply, backend error, or expired deadline yields a client-native denial. The local request budget defaults to `2000 ms` and can be set with `SKM__INTEGRATIONS__HOOK__TIMEOUT_MS`. Workflow and observation hooks still use the in-process evaluator and its policy cache where applicable.
- For Claude Code, put the executable used to start the session on the hook's trusted `PATH`. The hook probes `claude --version` and refuses enforcement below `2.1.295` or when the version is unavailable. Reapply the projection after upgrading so Claude also blocks hook startup failures and timeouts via `onFailure: "block"`. [Claude Code hooks reference](https://code.claude.com/docs/en/hooks#block-the-action-when-a-hook-fails)
- Bubblewrap, Seatbelt and container launchers refuse filesystem grants overlapping the daemon's runtime directory. Landlock alone confines writes. Child processes that need socket isolation require a filesystem-isolating profile or companion.
- Denials and observations buffer locally beneath `<state_dir>/hook-profiles` with mode `0600` and drain on healthy hook runs.

## Custom Hook Subscriptions and Webhooks (`skm hooks`)

Subscriptions live in configuration key `hooks.subscriptions` (requires `hook.manage` permission) and split cleanly by execution plane:

### Host Command Subscriptions (`execution_location = "host"`)

Host subscriptions run `argv` without a shell on client events (`client:pre_shell`, `client:session_start`, etc.). Because project config may be authored by another team member, **every machine must explicitly trust the exact subscription digest** before SKM executes the command:

```sh
skm hooks list
skm hooks show audit-shell
skm hooks trust audit-shell --yes
skm hooks test audit-shell --event-kind pre_shell --command "git status"
```

- Any change to `argv`, `cwd`, `env_allow`, `env_refs`, `timeout_ms`, `retry`, or `failure_policy` alters the canonical `sha256` digest and invalidates local trust (`skm hooks untrust <id>` revokes manually). If a subscription changes between preview and confirmation, `skm hooks trust` aborts with `VERSION_CONFLICT` (exit `6`).
- Untrusted enforcement commands never run and return `ask` (`HOOK_SUBSCRIPTION_UNTRUSTED`) on Claude/Cursor or fail-closed `deny` on Codex/Grok.
- `SKM_*` credentials/tokens are stripped from child environments. Failed `observation` commands with `failure_policy = "retry"` queue into `<state_dir>/hooks/spool/` and replay via detached `skm hooks drain` (discarding entries whose subscription digest changed).

### Control-Plane Webhooks (`execution_location = "control_plane"`)

Webhook subscriptions deliver hookable domain events (`urn:skm:integrations:webhook-delivery:v1`) via the outbox relay:

- **HMAC-SHA256 verification & key rotation**: Every `POST` carries `SKM-Signature: t=<unix_ts>,v1=<hex>` (plus a second `v1=<hex>` while `previous_secret` is configured) over `<t>.<raw_canonical_json_body>`. Receivers must verify `v1` in constant time, reject `|now - t| > 300 s`, and deduplicate by `SKM-Delivery-Id`.
- **SSRF and transport guards**: Requires `https://` (unless both `hooks.webhook.allow_http_loopback` and `hooks.webhook.allow_private_networks` are enabled for local testing), resolves and pins DNS per attempt, always refuses link-local metadata (`169.254.0.0/16`, `fe80::/10`), multicast, unspecified addresses, and `3xx` redirects (`redirect_refused`), and caps response reads at `hooks.webhook.max_response_bytes`.
- **Dead-letter inspection & retry**: Exhausted retries mark the outbox item `dead` and emit `HookDeliveryFailed` (`blocking = true` only for `workflow` + `failure_policy = "deny"`). Inspect and requeue dead deliveries with:

```sh
skm hooks deliveries --state dead
skm hooks retry <delivery_id>
```

## Scope Boundaries

- **Session telemetry (`P13.03.c` boundary)**: All four `IntegrationTarget.summarize_session` implementations currently return `None`; SKM never emits fabricated empty session summaries, and Claude session transcript parsing / `learning.record_activity` bridging arrives in `P13.03.c`.
- **Planning isolation**: Checkout files (including Markdown plans or legacy workspace files) are never imported into `skm_planning` tables during `integrations` operations; plan authoring and import belong exclusively to `skm plan` commands.
