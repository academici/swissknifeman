# P1 read-budget v1.1.0 measurement

**Дата:** 2026-08-11
**Qualified unit:** `token-estimate-calibration` v2.0.0,
`codex/gpt-5.6-terra`, `codex-exec-jsonl-v1`, `differential-input-total-v2`
**Contract SHA-256:** `3c2f8e6cfe4a41e2a7f0499558880ffe0752d1162769d20029c18a840e43ae22`
**Measured graph SHA-256:** `5c5a4d2f31a4b4010d367552bee63894504951ccf0dd3c3ece79fe167fa7da0f`

## Command and anchor

```bash
python3 packages/task/scripts/plan-weight.py --json plan plans/2026.08.10-TASK-LEAN-AUTONOMY
python3 packages/task/scripts/plan-weight.py --json plan plans/2026.08.10-TASK-LEAN-AUTONOMY \
  | jq -r '.items[].files[].path' | sort -u | xargs sha256sum | sha256sum
```

The graph digest anchors the exact measured carrier/input bytes and deliberately excludes this
report, which is not an executor input and therefore cannot create a self-referential measurement.

## Result

| Item | Admission | D2(a) | D2(b) | Mandatory-read weight |
|:--|:--|:--|:--|--:|
| P0.1 | `ready/pass` | pass | pass | 31,112 |
| P0.2 | `ready/pass` | pass | pass | 34,716 |
| P1.1 | `ready/pass` | pass | pass | 42,202 |
| P1.2 | `ready/pass` | pass | pass | 27,791 |

Maximum item weight is 42,202 versus the frozen 100,000 threshold. Closed-graph aggregate is
135,821 estimated tokens. Unresolved, unreadable, missing and oversized mandatory inputs: zero.

## Before/after and D74 adversarial answer

The committed pre-design snapshot had no contract and three unresolved/stale mandatory inputs.
Its 61,316-token sum was therefore an unqualified lower bound, not a legal baseline pass and not a
valid reduction target. After D15, the graph has the same four items, expands to all current
digest-qualified inputs, closes every gap and measures 135,821 tokens.

**Could this result pass only because work was split, moved, cached, deferred, or excluded?** No.
No item was split or added; no mandatory input moved outside the bundle; bundle selections are
counted; no producer/deferred state exists; the aggregate increased while the gap count fell to
zero. The result is a real closed-graph admission pass, not displacement below the per-item cap.

RAG:— (repo-grounded: command output on the anchored graph, D15,
`packages/task/lib/task/plan_weight.py`, frozen contract v1.1.0).
