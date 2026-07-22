# P6 D104 live admission — bounded root-cause replay

**Observed:** 2026-07-22  
**Mode:** read-only planner replay; no `apply`, `repair`, P7 command or live target write  
**Input:** `findings/P6-bootstrap-transfer-live-preflight-2026-07-22.md`, D103/D104

## Replayed state

The live target inventory remains the D104 candidate:

- `.codex/hooks.json` exists at
  `sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`;
- `.codex/hooks/lifecycle.py` is absent;
- `.swissknifeman/provider-artifacts.lock.json` is absent;
- `.mcp.json` already exists without a P2 lock record;
- the effective provider selection read from `config.json` is only `claude-code`.

The worktree-local pure planners were called without `apply_plan`:

| Layer | Result |
|:--|:--|
| P2 D104 transfer | `harness.codex.lifecycle.hooks → update / bootstrap-transfer-admitted`; `harness.codex.lifecycle.handler → create / bootstrap-transfer-admitted` |
| P6 provider projection | one required `claude-code` row targeting `.mcp.json`, status `planned` |
| Ordinary P2 provider check | `maind.provider-deploy.claude-code → refuse / unmanaged-target`; aggregate severity `error` |
| Ordinary check with transfer artifacts added against the unchanged pre-transfer root | hooks still `unmanaged-target`, handler `missing`, `.mcp.json` `unmanaged-target`; aggregate severity `error` |

RAG:— (repo-grounded: `core/provider_lock.py`,
`packages/maind/lib/maind/provider_deploy.py`,
`packages/maind/lib/maind/provision/deploy.py`, `config.json`).

## Root cause

The exact D104 candidate is admissible when its sole P2 planner is called directly. The live
`maind sync --dry-run` operation does not call that planner: effective selection contains only
`claude-code`, so P6's `has_codex` gate correctly leaves the Codex transfer not selected. The
operation then performs the ordinary Claude provider-artifact check against the still-unmanaged
`.mcp.json` and collapses that failure to `MAIND_PROVIDER_DEPLOY_REFUSED`. The dry result carries
no separate bootstrap-transfer selection/projection, so the command-level report cannot
distinguish `not-selected` from an admission refusal.

The direct `harness hooks --dry-run` refusal is a different, expected result: D104 explicitly
keeps P5's ordinary whole-file lifecycle operation fail-closed and makes P6 the sole transfer
selector. Turning that P5 reader green would create a second adoption path and violate D104.

When Codex is selected, the non-dry P6 facade also applies the bootstrap transfer before it
checks the ordinary provider plan. On a live-shaped root where `.mcp.json` is unmanaged, that
ordering can mutate the two D104 targets and only then discover the unrelated provider refusal.
The current live Claude-only operation did not reach this path; it is a source-level
preflight-order defect exposed by the read-only replay.

## Boundary

This evidence does not authorize adopting `.mcp.json`, enabling Codex in project config,
changing P2/P5 contracts, or applying the D104 transfer. It supports only a P6-owned repair that
preserves effective selection, reports `not-selected` versus admitted/refused explicitly, and
plans every selected required subplan before the first write.
