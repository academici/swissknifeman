# P08.Z — Runtime and role acceptance evidence

Date: 2026-11-17. Branch: `p08z-impl`. Checked product revision:
`26dbe09b1816ff7a51ef33e25f14560dfb8b5cc6`.
Only this document and the [donor porting map](../porting/runtimes.md) are added
by the acceptance commit; product code, tests, working plan and donor are read-only.
Executor session: `01a1eac4-4b46-7aa0-b43d-8a81cde46026` (runner-provided
`CODEX_THREAD_ID` / `CODEX_SESSION_ID`).

## Execution record

`uv sync --frozen` passed (CPython 3.12.3, frozen lock, 32 packages installed).
Host kernel: Linux `7.0.0-31-generic`. PostgreSQL was required, not optional:
`SKM_REQUIRE_PG=1`, using loopback port 54329. Four xdist workers were requested.
The Docker socket was explicitly set for the sandbox suite. The pytest tool call
passed `yield_time_ms=120000`; the tool's effective wait cap returned a running
session, subsequently polled to completion without background shell commands.

```sh
DOCKER_HOST=unix:///run/user/1000/docker.sock \
SKM_TEST_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_test \
SKM_REQUIRE_PG=1 uv run --frozen pytest -q -n 4 \
  tests/unit/runtimes tests/contracts/runtimes \
  tests/integration/runtimes/test_claude_argv.py \
  tests/integration/runtimes/test_codex_argv.py \
  tests/integration/runtimes/test_grok_argv.py \
  tests/integration/runtimes/test_cursor_argv.py \
  tests/security/test_config_isolation.py tests/security/test_landlock.py \
  tests/security/test_sandbox_profiles.py tests/security/test_process_containment.py \
  tests/security/test_secret_redaction.py tests/security/test_assignment_token.py \
  tests/evals/test_harness.py tests/unit/execution/host/stages \
  tests/unit/execution/application/test_result_retry.py \
  tests/unit/execution/domain/test_triage_reverify.py \
  tests/unit/execution/domain/test_recovery.py \
  tests/unit/execution/domain/test_autonomy_consilium.py \
  tests/unit/execution/domain/test_autopilot.py \
  tests/unit/execution/application/test_recovery_procedure.py \
  tests/unit/execution/application/test_autopilot_commands.py \
  tests/recovery/test_stall_recovery.py \
  tests/integration/execution/test_fix_brief_feedback.py \
  tests/e2e/test_m3_execution.py
```

Executor validation: **passed for the requested P08 scope**.

| Check | Actual result |
|---|---|
| Targeted P08 command above | Exit 0; **1452 passed, 2 skipped in 690.00 s (11:30)**, including M3 and local Landlock/container canaries |
| Skips | Exactly two parameterizations of `test_live_evals_detect_and_verification_context_probe` (Claude/Codex); `tests/conftest.py:107`: `live evals require SKM_EVALS=1`. Neither is counted as a capability pass. |
| `make check-touched` | Exit 0; selected preflight checks passed, including `check_links.py docs README.md AGENTS.md`. It saw the two new documents and the pre-existing untracked session trace; no Python changes were selected. |
| `uv run --frozen python tools/check_links.py docs README.md && git diff --check` | Exit 0 |

Full repository `make check`, `make test-pg` and `make e2e` are not claimed as
new runs: the owner requested the scoped P08 set above plus `make check-touched`
for this gate. All non-live cases in that set passed; there are no unresolved
executor findings within the allowed write set. This is scoped executor
acceptance, independent of the review status recorded below.

## Four-adapter matrix

Versions below are the checked-in `tested_runtime_version` values in adapter
capability records, exercised by fixtures/emulators. They are not installed
provider CLI versions observed by a paid run. All four adapters declare
`adapter_version = 0.1.0`. Their declarations were inspected at the checked
revision; this acceptance does not change their historical verification dates.

| Runtime | Declared tested CLI version | Headless / resume / usage (static) | Config isolation (static → without exact host proof) | Evidence and routing limit |
|---|---|---|---|---|
| `claude_code` | `2.1.266` | `native` / `native` / `native` | `adapted` → `unknown` | Replay and argv/session emulation; isolated `HOME`/`CLAUDE_CONFIG_DIR`, generated settings/MCP, safe-mode and user-only setting sources. Missing credentials → `RUNTIME_AUTH_EXPIRED`; no personal HOME fallback. Native subagent usage disclosure remains unverified. |
| `codex` | `0.165.0` | `native` / `native` / `native` | `adapted` → `unknown` | Replay and argv/session emulation; isolated `HOME`/`CODEX_HOME`, generated config, credential-only copy. Unsuppressible project `AGENTS.md` is tracked in self-load accounting rather than duplicated. |
| `grok` | `0.1.0` | `adapted` / `adapted` / `native` | `unsupported` → `unsupported` | Streaming replay/argv paths work under explicit trusted containment. Unattended routing refuses unsuppressible `~/.grok` / project `.grok` settings, including attempts to bypass with degraded allow or `required=false`; explicit trusted-full-access remains the documented exception. |
| `cursor` | unknown (headless records have empty version) | `unknown` / `unknown` / `unknown` | `unknown` → `unknown` | Detection and refusal contract only; routing excludes it and `start` fails closed on headless execution. No successful stream/session or headless support is claimed. |

Sources: adapter declarations under
[claude_code](../../src/skm/adapters/runtimes/claude_code/capabilities.toml),
[codex](../../src/skm/adapters/runtimes/codex/capabilities.toml),
[grok](../../src/skm/adapters/runtimes/grok/capabilities.toml),
[cursor](../../src/skm/adapters/runtimes/cursor/capabilities.toml), and the
[four argv suites](../../tests/integration/runtimes/).
`reliable_cancellation` is statically `adapted` for Claude/Codex/Grok and
`unknown` for Cursor; it remains effectively `unknown` without matching proof.

Enforcing capabilities (`config_isolation`, `sandbox_native`, `permission_flags`,
`workspace_binding`, `reliable_cancellation`) require an exact fresh
`VerificationContext`: host, runtime/version, executable hash, OS/kernel,
adapter version, isolation profile and launch digest. Offline replay and local
security canaries do not create provider verification records. Changed binary
bytes under the same version, wrapper/config/backend changes or a different
host invalidate old evidence. Required immutable executable binding must refuse
before spawn if the launcher cannot supply it. Degraded acceptance is explicit,
never an implicit capability promotion; unsuppressible project settings have
their own refusal regardless of degraded allow.

## Behavioral proof map

| Boundary | Executed suite / assertions and scope |
|---|---|
| Final `AgentRuntime` | [runtime contracts/replay](../../tests/contracts/runtimes/), the four argv suites and [M3](../../tests/e2e/test_m3_execution.py): shared start/events/cancel/result port; fake subprocess and real local execution/control-plane path. Cursor contributes honest refusal, not fabricated replay success. |
| Draft → final → start/result | M3 requires final manifests for actual steps with prompt digest/file version and model binding, same-role retry/rework, check failure repair, review feedback and accepted local integrations. This proves the fake-runtime path, not paid providers. |
| Unsupported / degraded / auth / admission | [routing](../../tests/unit/runtimes/domain/test_routing.py), [admission](../../tests/unit/runtimes/domain/test_admission.py), [capability](../../tests/unit/runtimes/domain/test_capability.py), argv and config-isolation suites: missing/expired auth, unsupported/unknown distinctions, `ADMISSION_REFUSED`, `ROUTE_UNDERSHOOT`, strict minimums and exact-context invalidation. |
| Resume / cancel / terminal | Contract/replay, argv and [result retry](../../tests/unit/execution/host/stages/test_result_retry.py): resume only with live reference and admission/authority match; otherwise Fresh with schema errors. Exit 0 without native terminal → `RUNTIME_STREAM_INCOMPLETE`; ignored cancellation emits `cancel_ignored`; requested stop is not confirmed empty containment. |
| Usage / observation | [usage](../../tests/unit/runtimes/domain/test_usage.py), [observation](../../tests/unit/runtimes/domain/test_observation.py), replay and argv suites: `UsageStatus.UNKNOWN` is not measured zero; fresh tokens exclude cache read; partial crash usage survives. Observation canonical UTF-8 JSON ≤16 KiB, StepId/model match, nullable unavailable counters, monotonic epoch boundaries and distinct capture/tool coverage. Provider-reported model is a nullable claim, not a resolved-model fallback or authority. |
| S7 isolation / lifecycle | [Landlock](../../tests/security/test_landlock.py), [sandbox profiles](../../tests/security/test_sandbox_profiles.py), [containment](../../tests/security/test_process_containment.py): actual inherited write fence plus refusal tests, container read/write/network canaries and cleanup identity checks. Landlock alone is not read/network isolation; worktree alone is not enforcement. |
| S12 secrets | [secret redaction](../../tests/security/test_secret_redaction.py), argv and transcript paths: stdin prompts, redacted artifacts/previews, no assignment secret in argv/config/log output. |
| S22 / S22a config | [client-home contracts](../../tests/contracts/runtimes/test_client_home.py), [config isolation](../../tests/security/test_config_isolation.py): poisoned HOME/worktree canaries, credential-only copy, private modes, symlink/escape rejection, self-load accounting and fail-closed routing. Provider live probes are skipped without opt-in. |
| S23 assignment token | [assignment token](../../tests/security/test_assignment_token.py): stage/assignment binding, revocation/expiry, fence and scope checks; a prior step's token cannot acquire a later step's authority. |
| Seven roles / triage / fix brief | [role stages](../../tests/unit/execution/host/stages/), [application result retry](../../tests/unit/execution/application/test_result_retry.py), [triage reverify](../../tests/unit/execution/domain/test_triage_reverify.py), [fix feedback](../../tests/integration/execution/test_fix_brief_feedback.py): real handler/protocol paths, conservative form repair, read-only independent reproduction and stable finding feedback. Registrar defaults to deterministic output. |
| Supervisor / recovery / consilium | Domain recovery/autonomy-consilium, application recovery procedure and [stall recovery](../../tests/recovery/test_stall_recovery.py): suspicion is not kill authority, unknown identity cannot be signalled, bounded recovery and safe resume retain authority guards. |
| Autopilot | [domain](../../tests/unit/execution/domain/test_autopilot.py) and [commands](../../tests/unit/execution/application/test_autopilot_commands.py): approved queue, ordered stop reasons, owner/emergency guards, monotone limits; continuation preserves spent counters and session start. |
| Eval harness | [offline harness](../../tests/evals/test_harness.py): opt-in separation, bounded task/budget, unknown usage stop, sanitized evidence and disposable environment cleanup. No paid request is needed for these tests. |

## Paid live evaluation and review

| Runtime | Paid small-task eval | Provider live capability probe | Actual live CLI version / cost |
|---|---|---|---|
| `claude_code` | `not_run` | `not_run` | unknown / null |
| `codex` | `not_run` | `not_run` | unknown / null |
| `grok` | `not_run` | `not_run` | unknown / null |
| `cursor` | `not_run` | `not_run` | unknown / null |

No `SKM_EVALS=1` opt-in or paid provider invocation was performed. The
[existing eval report](../../tests/evals/REPORT.md) and
[config-isolation evidence](runtime-config-isolation.md) retain their own
provenance. A passed local Docker canary is distinct from a paid provider eval.
Missing live evidence does not block the implemented offline harness/P08.Z per
the leaf, and does not certify production provider capabilities.

Executor adversarial self-check: **completed, no findings**. It covers the diff's scope, revision provenance,
unsupported/degraded distinctions, nullable telemetry, resume/fencing guards,
cleanup versus requested cancellation, and live-eval honesty. Independent manual
review status: `not_requested`; no independent acceptance is asserted.
