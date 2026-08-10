---
id: D134
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

The P4-evidence anchor stays `3533234c` and is NOT retargeted; D134 supersedes D131 ONLY in the anchor gate's machine form, adding one explicitly authorized exception class. P5.8's repair (2) edits `artifacts/P4/validate-assurance.py`, a P4-evidence path, so the gate becomes TWO commands: `git diff --exit-code 3533234c -- plans/2026.08.03-ARTIFEX-SUPERVISOR/phases/P4.md plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4 ':(exclude)plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-assurance.py'` (every other P4 byte still byte-identical) AND `git log --format=%h 3533234c..HEAD -- plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-assurance.py` returning EXACTLY ONE commit, P5.8's item commit (the excluded path's whole intervening history is the authorized repair and nothing else). Retargeting the literal to P5.8's commit was rejected on a fact, not a preference: `3533234c` is corroborated by a second independent carrier — the `source_tree_ref` of the frozen `trial-catalog-v{1,2,3}` carriers pins that exact tree — and those carriers may never be re-pinned, so a retarget would destroy the anchor's own corroboration and leave a literal resting on itself. Named blind spot: the exclusion is blind to the CONTENT of `validate-assurance.py`, which is why the second command is mandatory — without it the exclusion would be a hole through which any P4-evidence change could pass. RAG:— (repo-grounded: `findings/P5.4-forward-conformance-sweep-2026-08-06.md` §3 with the literal's full consumer sweep, D131, `artifacts/P5/trial-catalog-v1.json` `source_tree_ref`). **Consequences:** the anchor gate stops being a single copy-pasteable command and every consumer of its sentence (P5.4's pre-intent gate, P5.5's and P5.8's Validation) must carry both halves — a gate that is cheaper to run than to read correctly is how the previous form got quoted with the wrong argument list twice.

## Почему

D131 already ruled that the substantive question is whether a P4-evidence change is legitimately owned, not whether some commit touched something else; an authorized forward repair is exactly that case, and expressing it as an exclusion plus a provenance proof keeps the anchor's second corroboration intact.
