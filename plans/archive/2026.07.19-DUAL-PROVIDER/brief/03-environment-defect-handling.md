# Owner refinement — environment defect handling

**Date:** 2026-07-20

During execution of the remaining dual-provider plan, environment failures must not be hidden
or deferred by default:

1. Immediately notify the owner when a defect can affect model/effort routing, filesystem
   access, MCP/evidence, hooks, sandbox/approval, context budget or validation fidelity, and
   pause work that depends on the failed surface.
2. Repair the defect immediately when the change is safe, local and inside the authorized
   scope; then repeat the affected checks.
3. When the defect demonstrably does not affect current-item quality and should be isolated,
   record evidence in a finding/Pending Work/handoff and provide an exact follow-up launch.
4. A failed, skipped or substituted check must never be reported as green.
5. Item execution remains phase-first: finish P0.3, then P0.4, close and independently audit
   P0, and only then enter P1 and continue through the roadmap owner gates.
