---
item: P3.7
date: 2026-08-08
---

# P3 field canary — current v2 + ARTIFEX dry-run

## Current layout-v2 plan

Commands:

```bash
python3 packages/task/scripts/plan-lint.py plans/2026.08.07-PLAN-ECONOMY
PYTHONPATH="packages/task/lib" python3 -c "from task import plan_downstream; print(plan_downstream.discover_consumers('plans/2026.08.07-PLAN-ECONOMY', 'P3.7'))"
cd packages/task && PYTHONPATH="../../:lib" python3 -m unittest tests.test_plan_downstream -v
```

Verdict: shared contract/runtime and default-off lint integration are green. Mechanical discovery
returns later path-linked consumers; it is not empty and no consumer was added manually. The
focused suite reproduces `green`, blocking `red`, non-blocking recorded `unknown`, missing result-key
rejection, default-off lint silence, opt-in refusal, Markdown command extraction, and CLI exit
semantics.

A diagnostic run of P3.7 at item commit `5632a221` discovered seven real future consumers and
returned aggregate `red`, as expected before those items exist. P4.3 and P6.7 already pass their
applicable subset; P4.4, P5.3, P5.4, P6.2, and P6.4 call existing generic scripts with future
subcommands or artifacts and therefore fail. The plan's opt-in is deliberately absent, no result
finding was written, and P6 remains the activation owner. This observation confirms that `red`
cannot be converted into an advisory pass.

## ARTIFEX read-only projection

Command (the literal item recipe was corrected only at the temp-path seam: migrator requires a new,
non-existing output directory):

```bash
canary_root=$(mktemp -d)
canary_dir="$canary_root/2026.08.03-ARTIFEX-SUPERVISOR"
python3 packages/task/scripts/plan-migrate.py plans/2026.08.03-ARTIFEX-SUPERVISOR --dry-run --output "$canary_dir"
python3 packages/task/scripts/plan-lint.py "$canary_dir"
test -z "$(git status --porcelain plans/2026.08.03-ARTIFEX-SUPERVISOR)"
```

Verdict: migration succeeds and the source tree remains unchanged. `plan-lint` is red on one shared
admission precondition: the migrated legacy projection has no plan-owned
`root/contracts/read-budget-v1.md`, while P3.3 correctly refuses to invent a numeric fallback.

Fix-forward ownership:

- P6.6 owns fleet adoption and must materialize the frozen read-budget contract before enabling v2
  gates on a migrated project.
- If migrated legacy plans should instead be outside or pending the D2 admission boundary, that is a
  shared public-contract change and requires `plan-design` to reopen P2.9/P3.3; P3.7 must not add the
  exception locally.

## Verification status

- RAG: official Pact documentation via WebSearch fallback on 2026-08-08; provider verification
  results, pending behavior, `unknown` retry state, content/provider version identity, and
  always-successful dry-run semantics confirmed with medium-to-high confidence.
- Unverified → repeat pass: `context7` and `perplexity-web` were unavailable in this session; the
  fallback used only primary Pact documentation.
- Workarounds/[POSSIBLE-DEFECT]: literal `mktemp -d` output recipe is incompatible with the
  migrator's new-directory precondition; the canary used a new child path. ARTIFEX's missing
  read-budget contract is not worked around and remains assigned to P6.6/design reconciliation.
