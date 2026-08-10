---
id: D108
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-GRANT:G-OWNER-P5-G2B-SUCCESSOR] branch=`p5-g2b-business-successor`; consumer=`P5.5 only`; exact scope=`plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/business-dispatch-admission-v1.md · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/business-dispatch-successor-cases-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/provider-business-projection-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/provider-business-projection-cases-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/business-successor-generation-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/business-successor-assurance-v1.json · plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/validate-business-successor.py · plans/2026.08.03-ARTIFEX-SUPERVISOR/findings/P5-business-successor.md · packages/artifex/lib/artifex/business_dispatch.py · packages/artifex/lib/artifex/security.py · packages/artifex/lib/artifex/activity.py · packages/artifex/lib/artifex/cli.py · packages/artifex/lib/artifex/providers/codex.py · packages/artifex/lib/artifex/providers/claude_code.py · packages/artifex/README.md · packages/artifex/tests/test_business_dispatch.py · packages/artifex/tests/test_business_provider_projection.py · packages/artifex/tests/test_security_boundaries.py · packages/artifex/tests/test_provider_activity.py · packages/artifex/tests/test_provider_codex.py · packages/artifex/tests/test_provider_claude_code.py · packages/artifex/tests/test_provider_parity.py · packages/artifex/tests/test_cli.py · packages/artifex/tests/test_integration.py · CHANGELOG.md`; predecessor=`G2/P4.8@124df816 immutable`; admission_projection=`each frozen D105 g2_package_digest must equal that G2 predecessor, while current package bytes must equal the sole G2B manifest digest; no admission byte changes`; providers=`codex-cli 0.146.0, Claude Code 2.1.222`; capability_probes=`exactly 2, one per provider`; controlled_roots=`mktemp:p5-g2b-codex · mktemp:p5-g2b-claude-code`; per_probe_caps=`max_slices:1, timeout_ms:120000, max_event_count:16, max_turns:2, max_output_bytes:8192, token_limit:2000, cost_limit_microunits:1000000`; business_usage=`all 14 D105 rows remain 0`; D105_expiry_and_budget=`unchanged; no extension or extra dispatch`; acceptance=`validate-business-successor.py exit 0 + packages/artifex/scripts/validate.sh green + P4 evidence diff empty`; owner-message=`brief/24-p5-phase-successor-authorization.md`; revoked=`false`. RAG:✅ 2026-08-05 current local Codex/Claude version/help plus first-party provider evidence captured in `findings/P5-successor-provider-surface-2026-08-05.md`.

## Почему

The owner explicitly authorized only the finite additive contract/runtime/provider/assurance generation. The carrier separates two capability probes from D105 business pilots and gives the executor a resolver-valid path set, two-link G2→G2B admission projection, versions, caps, predecessor and acceptance predicate.
