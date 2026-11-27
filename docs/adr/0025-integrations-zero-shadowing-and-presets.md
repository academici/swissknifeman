# ADR 0025: Zero-shadowing client projections and presets

Status: proposed
Date: 2026-11-27

## Context

Interactive clients need to share project instructions and skills while preserving local edits.
Project presets supply workspace rules and quality hooks. Package presets also export consumer files
that belong outside the client configuration directories. Client projection follows the ownership
boundary in [ADR 0016](0016-integrations-vs-runtimes.md) and the host operation boundary in
[ADR 0021](0021-bus-handlers-and-host-operations.md).

## Decision

### Instructions and skills

In zero-shadowing mode, the `CLAUDE.md` `MANAGED_BLOCK` contains the single line `@AGENTS.md`.
Preset instructions in `AGENTS.md` also use `MANAGED_BLOCK` and preserve local sections delimited by
`<!-- skm:local:start -->` and `<!-- skm:local:end -->`. Projection preserves user text outside the
managed block. Projected skills in `.agents/skills/` and `.claude/skills/` contain the same canonical
bytes as ordinary `MANAGED_FILE` entries.

The skill manifest accepts an optional `invocation` object. Omitted `user_only` defaults to `false`.
Codex projection emits `agents/openai.yaml` as a `MANAGED_FILE` only for skills with
`invocation.user_only: true`. It sets `policy.allow_implicit_invocation: false`, uses the `SKILL.md`
frontmatter `description` for `short_description`, and uses `invocation.display_name` or a title-cased
skill key for the display name. An unmanaged or edited sidecar follows the normal ownership conflict
and adoption rules. Source skills use the existing pack layout and exclude this projected sidecar.

### Gemini CLI and hook policy

`GeminiCliTarget` uses the existing `Surface.INSTRUCTIONS`, `Surface.SKILLS`, `Surface.PERMISSIONS`
and `Surface.HOOKS`. It configures instruction discovery in `.gemini/settings.json` with
`context.fileName: ["AGENTS.md", "GEMINI.md"]`, sets `advanced.ignoreLocalEnv: true`, and projects
skills to `.agents/skills/`. Settings use `MERGED_JSON` ownership. The adapter supplies
`client_layers(fs, home)` and verifies `BeforeTool` and `AfterTool` payloads against a versioned
client fixture. The Gemini CLI runtime retains responsibility for session execution.

The `.env` guard covers `Edit`, `Write`, `MultiEdit` and `Bash`, with `.env.example` exempt.
The Laravel DB guard covers `artisan migrate:fresh`, `migrate:refresh` and `db:wipe`. Both guards
use `HookSurfaceId.SAFE_DIRS` with `env_guard_enabled` and `db_guard_enabled` in `HookPolicyContext`.

Trusted quality checks run on `HookSurfaceId.SUBSCRIPTIONS`. Read-only `PostToolUse` checks such as
`php -l` and `dart analyze <file>` use advisory `HookClass.WORKFLOW`. Blocking final checks such as
`pint --dirty`, `phpstan`, `dart format` and `skills_lint` use `HookEventKind.STOP` and
`HookClass.ENFORCEMENT` so a failed check can yield `HookVerdict.DENY` and Claude Code's
`{"decision": "block"}`. When `stop_hook_active` is true, `evaluate_hook` returns `HookVerdict.NONE`
before invoking any host subscriptions or causing side effects.

### Preset requests and consumer paths

`skm integrations plan --preset` and `skm integrations apply --preset` accept `php-project`,
`php-package`, `dart-project` and `dart-package`. Both CLI commands send the preset through
`plan_projection` to `get_desired_projection`. Both inputs accept an optional, nullable `preset`
field for which omission or `null` selects the default projection. P04 forwards the selected
preset and includes it in `inputs_digest`. The host apply request consumes prepared `plans` and
verifies `inputs_digest`.

The consumer path allowlist in `bundle.py` admits `resources/boost/**` only for `php-package` and
`skills/<package_name>-*/**` only for `dart-package`. All other paths outside client roots still
raise `INTEGRATION_UNSAFE_TARGET`. Consumer files use `MANAGED_FILE` ownership.

## Alternatives considered

- Full-file ownership for instructions would overwrite user text during projection.
- Managed symlinks for shared skills would add link handling to ownership and drift checks.
- New hook surface IDs would change the closed v1 enum and its settings contract.

## Consequences

Adapters render client-specific artifacts from shared inputs. Preset and consumer-path rules live
in `integrations`. Ownership and digest validation apply to preset output and generated sidecars.

## Compatibility

The v1 skill manifest and host planning request gain optional fields. `HookSurfaceId`, integration
settings and the prepared-plan apply request keep their v1 contracts.

## Verification

P00 verifies schema compatibility and accepted and rejected values. P03 and P04 verify projected
sidecar ownership, preservation of user instructions, Gemini hook fixtures, active Stop short
circuiting, and the plan, apply and remove cycle for all four presets with the consumer path checks.
