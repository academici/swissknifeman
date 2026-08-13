# P6 v0.13.1 exact-validation audit — 2026-08-13

## Reproduction

The phase candidate before repair was
`de59b8d450c8ba27478037fcaac8f9791d4665a5789a3bee20dc85d6801bbce8`.
In a clean detached worktree at tagged commit
`3e24951ec643ad8826cba3018883fc93acaba51f`, the required command
`bash packages/task/scripts/validate.sh` exited `1` after 882 passing tests and one skip.
The terminal diagnostics name three forms of the same defect:

1. mandatory `bundles/P6.2.json` is stale;
2. D2(b) generated-bundle byte freshness is broken;
3. the `bundle-v1` carrier hash does not match current item carriers.

The release capsule and finding had recorded this exact gate as exit `0`. The byte-fresh
P6.2 plan carriers occur only in later bookkeeping commit
`bfaa2ee84315f3f2f2f1a2676ab225fa2b83b5b5`, so they cannot be overlaid while preserving
the exact-candidate invariant. Focused `test_plan_gates.py`, all other package validators,
registry, provider rendering, docs sync, diff, annotated-tag binding and fsck remain green
at the tagged commit.

## Verdict and recovery boundary

This is a release-blocking false Validation claim. The safe audit-fixer correction changes
the machine-readable Task exit to `1` and returns P6.2 to non-green. Repairing the already
tagged release requires an owner-authorized forward candidate and a new patch version;
`v0.13.0` and `v0.13.1` remain immutable, and push/GitHub release/registered rollout remain
out of scope. Because the exact-anchor validation anti-pattern recurs after the P6.1 audit,
the audit classifies it as `PROMOTE-CANDIDATE`.

## Independent risk judgement

One fresh isolated reviewer received the compact evidence capsule and returned a
schema-valid `JUSTIFIED` judgement. Local `return-judgement.v1` parsing retained it.

```json
{"schema_version":"return-judgement.v1","judgement_id":"RJ-P6.2-v0131-validation-001","return_event_id":"transient:P6-audit-v0.13.1-validation","ts":"2026-08-13T15:35:56Z","subject_id":"P6.2","fingerprint_digest":"de59b8d450c8ba27478037fcaac8f9791d4665a5789a3bee20dc85d6801bbce8","model_id":"openai:gpt-5.6-sol","model_version":"2026-08-13","model_effort":"high","rubric_sha256":"63323e5565fa2c321354e36ebe47624f37f86c3c3372ba01efaedcc61b6c2e1e","input_digest":"8d5b9f028b9c7c96723aa789c93bce78d2e8450c034c942c67aaaaff69815f3f","capsule_digest":"13a65b045f2b234a7b0cc834199ff67d4046cff4ebf6db2c9450f1425f0f488b","evidence_ids":["validation:3e24951e:task-validate:exit-1","spec:P6.2:fee4ddfe52c511d65c980e9e63a090cb9763bb09409d21741f134f86d8809bce","artifact:patch-release-v1:43b6e8153b3a9208f379de5bd75cc22ab6657a3df53ada79c5af139618d4c53e","commit:3e24951ec643ad8826cba3018883fc93acaba51f","commit:bfaa2ee84315f3f2f2f1a2676ab225fa2b83b5b5","tag:e5492ebcae1d36de735042a08f27a0c4f6a2fd6f","validation:3e24951e:other-gates-green"],"verdict":"JUSTIFIED","parser_version":"return-judgement-parser.v1","policy_version":"return-loop.v1","root_session_id":"019ffbb4-cacf-7f40-a90c-7e9d9a3c944e","root_run_id":"audit-P6-de59b8d4","executor_actor":"frontier/xhigh","reviewer_actor":"reviewer:openai:gpt-5.6-sol/high","review_route":{"model_class":"frontier","effort":"high","model":"gpt-5.6-sol"},"return_control_to":"root"}
```
