---
id: D111
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-GRANT:G-OWNER-P5-G2B-PROBE-R2] branch=`p5-g2b-business-successor`; consumer=`P5.5 only`; preserves=`all D108 package/test/assurance paths and immutable G2→G2B/D105 predicates`; additive_scope=`plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/business-worker-output-schema-v1.json` only; replacement_attempts=`exactly 2, one Codex and one Claude Code, after JSON-Schema self-test + fake-binary complete-argv validation + process_count:0`; controlled_roots=`mktemp:p5-g2b-codex-r2 · mktemp:p5-g2b-claude-code-r2`; providers=`codex-cli 0.146.0, Claude Code 2.1.222`; per_probe_caps=`max_slices:1, timeout_ms:120000, max_event_count:16, max_turns:2, max_output_bytes:8192, token_limit:2000, cost_limit_microunits:1000000`; business_usage=`all 14 D105 rows remain 0`; retry_fallback_pilot=`none`; D105_expiry_and_budget=`unchanged`; acceptance=`both R2 canaries + validate-business-successor.py exit 0 + packages/artifex/scripts/validate.sh green + P4 evidence diff empty`; failure=`P5.5 stays blocked; no automatic R3`; owner-message=`brief/26-p5.5-probe-r2-owner-grant.md`; revoked=`false`. This exact finite carrier activates the proposal in `research/36-p5.5-probe-recovery-design.md` and supersedes D110 only where it keeps P5.5 blocked awaiting owner choice; the exhausted D108 observations remain immutable. **Consequences:** P5.5 may add one schema artifact and spend one final replacement attempt per provider, but any local/pre-provider/provider refusal exhausts that path without retry and keeps P5.2–P6 blocked. RAG:— (direct repository-owner decision; repo-grounded exact proposal in `research/36-p5.5-probe-recovery-design.md`).

## Почему

The owner explicitly selected the smallest forward recovery: one independently testable schema carrier and two R2 roots under unchanged caps, with no D105 or pilot authority.
