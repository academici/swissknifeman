# P5.5 D108 capability-probe result — 2026-08-05

Exactly two non-business D108 probes were attempted, one per disposable root.
Neither used a D105 admission, started a provider process, created a business
intent, or changed any of the fourteen usage rows.

| Provider | Root | Result | Minimal observation |
|:--|:--|:--|:--|
| Codex `0.146.0` | `mktemp:p5-g2b-codex` | RED, exit 1 | argv referenced the absent P3 output-schema path; CLI refused before execution. |
| Claude Code `2.1.222` | `mktemp:p5-g2b-claude-code` | RED, exit 1 | supplied D108 projection file was not a JSON Schema; CLI refused before execution. |

The probes exhausted D108's exact two-probe allowance. Retrying after adding a
real schema would be a third probe and requires a new owner carrier/additive
item. No raw output, prompts, credentials, environment values, or provider
content are retained.

**Required forward decision:** D108 must explicitly authorize a replacement
bounded probe pair (or a different mechanical schema carrier) before P5.5 can
resume. P5.2–P5.4 remain unrun and blocked/deferred.

## D111/D112 R2 execution — 2026-08-05

The independently authored JSON Schema self-test and both complete fake-binary
argv projections passed with `process_count=0`; Codex strict-config accepted
`rollout_budget.limit_tokens=2000` before launch. Exactly one fresh R2 process
was then started per provider through the Artifex bounded wrapper. Both returned
the closed minimized observation `PROVIDER_NONZERO` with no retained raw output:

| Provider | Root | Process count | Duration | Result |
|:--|:--|--:|--:|:--|
| Codex `0.146.0` | `mktemp:p5-g2b-codex-r2` | 1 | 22 ms | `PROVIDER_NONZERO` |
| Claude Code `2.1.222` | `mktemp:p5-g2b-claude-code-r2` | 1 | 836 ms | `PROVIDER_NONZERO` |

Codex had one fresh `exec` invocation and wrapper limits of 120000 ms, 8192
bytes and 16 events; its argv made no `max_turns` or money-cap claim. Claude
retained the D111 timeout/output/event, `max_turns=2`, cost, `dontAsk` and
strict-empty-MCP controls. There was no retry, fallback, R3, business intent or
D105 usage. The two failed R2 attempts exhaust the owner grant; P5.5 remains
blocked for a new plan-design/owner decision.

## Separate controlled-check record — 2026-08-05

The following completed controlled checks are retained as neutral, minimized
observations. They are a distinct record: they do not replace, retry, or
reinterpret the historical D108 or D111/D112 `PROVIDER_NONZERO` observations,
and they do not consume a D105 admission or authorize a pilot.

| Provider | Process count | Duration | Event count | Result |
|:--|--:|--:|--:|:--|
| Codex | 1 | 13539 ms | 4 | `OK` |
| Claude Code | 1 | 4380 ms | 1 | `OK` |

No raw output, prompt, credentials, or environment values are retained. These
records do not change P5.5's blocked status or the required plan-design/owner
gate.
