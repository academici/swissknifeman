# P7.2 self-host E2E — D121 live transaction result

**Observed:** 2026-07-23  
**Runtime:** `gpt-5.6-terra/high`; approval `never`; sandbox `danger-full-access`.  
**Authority:** D121 exact S1+O1 live inventory only.

## Applied inventory

The sealed D108/D110 plan admitted only these changes:

| Path | Result |
|:--|:--|
| `.swissknife.json` | created with only `providers` v1 selection for enabled `claude-code` and `codex` |
| `.codex/hooks.json` | D104 managed observer update |
| `.codex/hooks/lifecycle.py` | D104 managed handler created; `py_compile` and `--surface context.observer` probe passed |
| `.mcp.json` | `NOOP`; SHA-256 remained `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283` |
| `.swissknifeman/provider-artifacts.lock.json` | created with exactly three matching records |

The initial D108 dry preflight returned `bootstrap=admitted`; its exact chain was
`.codex/hooks.json=update`, `.codex/hooks/lifecycle.py=create`, `.mcp.json=noop`.
No `.codex/config.toml` or other provider render path was applied.

## Required idempotence failure and rollback

The immediate second identical D108 operation failed before writing with
`MAIND_PROVIDER_DEPLOY_REFUSED`. `plan_d104_bootstrap_transfer` still parses only the original
single `SessionStart` hook preimage and rejects the managed two-entry post-apply form. This
contradicts the sealed P2.7 second-plan-noop invariant. No second-write delta was produced.

The explicit pre-apply target inventory was restored byte-for-byte: `.swissknife.json`,
`.codex/hooks/lifecycle.py`, and `.swissknifeman/provider-artifacts.lock.json` are absent;
`.codex/hooks.json` recovered SHA-256
`7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`; `.mcp.json` retains
the sealed SHA-256 above. Only pre-existing unrelated `AGENTS.md` and `.serena/project.yml`
remain dirty outside the plan evidence.

**Verdict:** RED — P7.2 cannot satisfy the mandatory live second-apply/noop acceptance. Reopen
the owning P6.11 D108 planner seam; do not retry a live mutation until its post-apply managed
form is accepted as deterministic noop and independently validated.
