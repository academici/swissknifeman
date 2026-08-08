# Owner directive — P4 audit-1 final remediation

Date: 2026-08-05
Plan: `2026.08.03-ARTIFEX-SUPERVISOR`

The repository owner invoked `$ task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P4` in
reopen mode and required the `## Audit P4 — 2026-08-05` findings F1–F7 to be fixed
forward. This is the last P4 design pass: after it, the plan must execute the bounded
development fixes, close P4, repeat the G2/closure gates, and run the second P4 audit.
No further detailing or audit-of-audit loop is authorized.

The owner requires resolver-valid authority before any new protected mutation, reproducible
Harness validation on the committed item tree, honest historical item statuses, append-forward
commit/journal/handoff provenance, explicit tree anchors for published numbers, and a new G2
successor only after all remediation gates are green.

[REPOSITORY-OWNER-MESSAGE:owner-grant-p4-8-g2-requalification-2026-08-05] [OWNER-GRANT:G-OWNER-P4.8-G2-REQUALIFICATION] branch=`p4.8-g2-authority-requalification`; scope=`plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/authority-policy-v1.md · plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/supervisor-run-v1.md · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/authority-policy-cases-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/supervisor-run-cases-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/contract-manifest-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P1/validate-authority-policy.py · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-hook-integrity.py · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/attention-cases-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/authority-requalification-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/assurance-manifest-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-authority-requalification.py · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-assurance.py · packages/artifex/lib/artifex/authority.py · packages/artifex/lib/artifex/scheduler.py · packages/artifex/lib/artifex/telemetry.py · packages/artifex/lib/artifex/cli.py · packages/artifex/README.md · packages/artifex/tests/test_authority.py · packages/artifex/tests/test_scheduler.py · packages/artifex/tests/test_attention_telemetry.py`; provenance=`repository-owner`

The grant is prospective and finite. It does not retroactively legalize D102 or the historical
P4.5 item commit; P4.8 must create a separately committed, resolver-checked successor. It grants
no P5/P6 execution, G1 rewrite, provider/business activity, unrelated Harness/Task change, tag,
push, publish, or release. Historical commits and existing journal rows remain immutable.

RAG:— (direct repository-owner directive in the active 2026-08-05 conversation).
