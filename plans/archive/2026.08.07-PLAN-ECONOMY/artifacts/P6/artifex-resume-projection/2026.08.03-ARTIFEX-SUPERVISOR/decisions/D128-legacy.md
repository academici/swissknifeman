---
id: D128
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

P5.6's escalated question is resolved with a THIRD option: `validate-shadow.py`'s `business carriers exist before exact owner grant` guard is a ONE-TIME HISTORICAL fact, so it MOVES rather than being relaxed or retired — in `validate()` it is asserted at the shadow-freeze commit resolved at run time (all four frozen carriers share exactly one commit, `17cf14cd`), through `git ls-tree`; in `main()` it becomes a refusal raised BEFORE `--write` writes its first byte, where «the freeze may not be re-cut once carriers exist» is true forever. Alternatives rejected: relax-in-place alone leaves `--write` able to overwrite the freeze and keeps the check running AFTER the write it should prevent; retiring the non-`--write` mode would trade four live green invariants (catalog/mapping/shadow/request drift, frozen G2 predecessor pin) for one stale line, and the analogy with the inert read-only `repository-pilot-results-v1.json` does not hold for an active re-derivation. `research/40-p5.6-gate-reconciliation-design.md` §1. RAG:— (repo-grounded: `findings/P5.6-gate-staleness-verification-2026-08-06.md` §1)

## Почему

Правило `findings/P5-retry-carrier-set.md` §3 («расширять item, только когда починка ровно одна») соблюдено, а не обойдено: после первичной проверки фактов остаётся ровно одна связная починка, и это не одна из двух, между которыми эскалация предлагала выбрать. Право принять это конструктивное решение без владельца — `brief/36-p5.6-constructive-authority-owner-direction-2026-08-06.md`
