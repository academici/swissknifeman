---
item: P6
date: 2026-08-16
gate: plan-delivery-v1
qualification: recovered-tooling-defect
---

# P6 plan-delivery locator compatibility — 2026-08-16

The installed plan-design delivery recipe expected `codex plugin marketplace list --json` to
return a top-level list with an `install_path` field. The observed Codex response instead used a
top-level `marketplaces` object whose local entry exposed `root`, so the recipe resolved an empty
plugin path and did not invoke delivery. This is a launcher/adapter discovery incompatibility, not
a plan or product failure.

Recovery stayed worktree-local as required by repository policy: the owning
`packages/task/scripts/plan-delivery.py` was invoked directly. It returned exit 0 with
`status=handoff-persisted` and `next_exact=run-items: task:plan-run
2026.08.02-PROVIDER-CONTRACT-LOCALE P6.3`. No skipped or failed delivery check is treated as
green.

RAG:— (repo-grounded: observed Codex marketplace JSON, worktree-local Task delivery script and
the resulting `handoff-recommendation-receipt/v1`).
