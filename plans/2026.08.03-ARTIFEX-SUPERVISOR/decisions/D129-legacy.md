---
id: D129
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Repair (2)'s frozen anchor is DETERMINED, not chosen: `package-promotion-manifest-v1.json` has exactly one commit in its entire history, `367e477a` (P3.8), and `124df816` is P4.8's item commit which never touched it — so the anchor is resolved at run time (`git log -1 --format=%H -- <manifest>`), with `--historical-commit` kept as an explicit override. Two further defects in the same line are fixed with it: the item's `--prototype` literal was `artifacts/supervisor` while the script requires `artifacts/P3/adapter-manifest-v1.json` (so every run died on an argument check before reaching the gate), and passing `--historical-commit` ALONE would silence F2 rather than repair it — that branch skips the current-tree comparison entirely, so the live half (current package equals the sole G2B digest) must be added. RAG:— (repo-grounded: `findings/P5.6-gate-staleness-verification-2026-08-06.md` §2, `validate-package-promotion.py:79-104`)

## Почему

Литерал в Validation ломал гейт до его сути; «якорь» переставал быть выбором, как только историю манифеста прочитали, а не пересказали
