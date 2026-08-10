---
id: D105
date: 2026-08-05
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

[OWNER-GRANT:G-OWNER-P5-BUSINESS] branch=`p5-business-trials`; catalog_sha256=`df5d7545b3d87fa3e78c567eb708e8dfb5f3d0983b789d7ebb1838c3daf2745f`; request_sha256=`ec16d0c556abac6f106b285ff6bc84da1afb782f0466b7ed4a60feb70aeef52b`; providers=`claude-code,codex`; controlled_roots=`mktemp:p5-p5-2-p5.2-slice-01-worktree-core · mktemp:p5-p5-2-p5.2-slice-02-worktree-binding · mktemp:p5-p5-2-p5.2-slice-03-worktree-evidence · mktemp:p5-p5-3-p5.3-call-01-crash-after-intent · mktemp:p5-p5-3-p5.3-call-02-crash-after-observation · mktemp:p5-p5-3-p5.3-call-03-duplicate-dispatch · mktemp:p5-p5-3-p5.3-call-04-timeout · mktemp:p5-p5-3-p5.3-call-05-schema-refusal · mktemp:p5-p5-3-p5.3-call-06-third-state · mktemp:p5-p5-4-p5.4-wave-01-recovery-fixture · mktemp:p5-p5-4-p5.4-wave-02-worktree-isolation · mktemp:p5-p5-4-p5.4-wave-03-security-boundary · mktemp:p5-p5-4-p5.4-wave-04-telemetry-assurance · mktemp:p5-p5-4-p5.4-wave-05-committed-gates`; maximum_dispatch_count=`14`; per_trial_caps=`max_slices:1, timeout_ms:180000, max_envelope_bytes:65536, max_event_count:64, max_turns:8, max_output_bytes:16384, token_limit:8000, cost_limit_microunits:5000000`; expiry=`2026-08-12T23:59:59Z`; revoked=`false`; owner-message=`brief/22-p5-last-pass-fast-track.md`. RAG:— (direct repository-owner instruction; exact frozen request `artifacts/P5/business-grant-request-v1.json`).

## Почему

Владелец явно потребовал выполнить все подфазы P5 максимально быстро; carrier разрешает только уже замороженные bounded business trials и не расширяет providers, roots, caps, product/fleet/release scope.
