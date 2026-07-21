# P3 throughput retrospective and corrective controls

## Observed failure

P3.5's first independent safety probe found a P3.4 ownership defect.  Instead of
first collecting the same-seam fail-closed cases, execution reopened, repaired and
revalidated P3.4 for that one symptom, then restarted P3.5.  The retry exposed
managed-byte drift and corrupt-lock provenance gaps in the same `skillset` planning
seam.  Status reports described P3.5 as "in progress" without foregrounding that
it was blocked behind P3.4 remediation.  This created repeated context/validation
cycles and concealed the schedule/throughput failure until the owner asked.

## Corrective controls (D80/D81)

1. After an item first blocks on an owning-phase defect, stop further item execution
   and perform one bounded root-cause scan of that seam before choosing remediation.
   Bundle all confirmed same-seam, contract-preserving invariants in one repair.
2. An item may be reported as `🟡 In progress` only while it is actually executable.
   If a prerequisite repair is running, the dependent item is `🔴 Blocked` and the
   status/handoff names the owner, defect class and next repair.
3. D80 applies phase-first validation: targeted regression/static checks for each
   bounded item repair; full package validation, release/docs assessment, phase close
   and independent audit exactly once at the terminal phase boundary.
4. On the first repeated re-open of a phase, root proactively reports the schedule
   impact and corrective route.  It does not wait for owner status prompting.

These are process controls only: they preserve frozen contracts, fail-closed
requirements, existing escalation boundaries and the P3+ phase sequence.  The first
concrete application is `research/19-p3-fail-closed-bundle-remediation.md`.

RAG:— (owner-grounded: direct 2026-07-21 feedback; repo-grounded: P3.5 journal
entries 108–113, D78–D80, current P3/handoff).
