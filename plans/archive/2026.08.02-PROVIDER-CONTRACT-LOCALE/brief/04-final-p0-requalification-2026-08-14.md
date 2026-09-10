# Owner refinement — final P0 requalification — 2026-08-14

The owner invokes `task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0` after the
2026-08-13 independent P0 audit and explicitly requires that the next P0 audit be the last
planned audit invocation.

The design must close only the two proven RED boundaries: the stale P0.2 classification evidence
digests propagated through P0.6/P0.8, and P0.7's ten-minute persisted-evidence expiry that cannot
span the independent audit/close boundary. It must preserve the exact artifact set, all 13,421
classification dispositions and policies, P0.1–P0.8 historical commits and journal rows, the
frozen v1.0.1 recovery-contract bytes, P1–P7, and every external fleet/Brain/provider/credential/
trust target.

“Last audit” means one final scheduled `task:plan-audit ... P0` invocation after the bounded
forward repair. That audit must repair reversible in-scope defects within its own audit root and
continue to a GREEN verdict. A new design invocation is not a normal outcome; it is legal only if
the audit reproduces an actual repository-owner or frozen-contract authority boundary that cannot
be repaired without changing the accepted scope.

RAG:— (repo-grounded: owner messages of 2026-08-14 and `phases/P0/P0.md` audit attempt 2)
