# P4 readiness preflight

**Date:** 2026-08-15

## Observed evidence

- Route evidence bound this design invocation to `gpt-5.6-sol/high`, repository cwd, approval `never` and `danger-full-access`; the record came from provider thread state.
- The worktree already contained unrelated Task token-estimator and roadmap changes plus P4.1 generated execution evidence. Those bytes are foreign to this design pass and remain preserved.
- `codex doctor --json` returned `overallStatus=ok`; `.codex/hooks.json` parsed, its registered lifecycle handler compiled, and `packages/maind/bin/maind health --cwd --json` returned `connected` with green Claude Code/Codex trust.
- P4.1 journal attempt 1 ended at nonterminal `block-candidate`: Routing requested batch `P4.1–P4.2`, roadmap declared solo/per-cwd launches, and the P4.2 bundle was absent. The P4.1 manifest contains no slice commit and all slices remain pending.
- Pre-design plan lint failed with 15 errors and one warning: P4.1 measured 297,703 estimated tokens and included the 731,605-byte/175,590-token registry as a mandatory model read; P4.2 measured 138,970; P4.3–P4.6 named future P4.1/P4.2 outputs without producer edges; P4 phase prose contained one literal clarification marker.

## Verdict

The failure is a plan-readiness and routing contradiction, not a product or frozen-contract failure. Repair forward in P4 design: isolate six item launches, replace exhaustive model reads with compact repository synthesis plus exact targeted sources, keep the full IANA registry as runtime/checker data rather than model context, and add producer edges for every absent downstream carrier. RAG:— (repo-grounded: `plan.md`, `roadmap.md`, `phases/P4/**`, `bundles/P4.1.json`, `journal.jsonl`, and the commands recorded above).
