---
id: D130
date: 2026-08-06
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

`validate-repository-pilot.py` answers two different questions with one exit code, and P5.2's `0/3 accepted` is immutable recorded evidence (its three D122 admissions are one-shot and spent) — so the script can NEVER exit 0, and both P5.6's own «exits 0» and P5.4's pre-intent gate «`validate-repository-pilot.py` green» were unreachable as authored. The verdicts are split by exit code: `0` = evidence intact AND every slice accepted; `2` = evidence intact with the honest partial/zero-acceptance report; `1` = structural failure, staleness or mutated bytes. Consumers gate on «not `1`». P5.4's pre-intent gate sentence is re-worded accordingly in this design pass (P5.6 must not edit another item's acceptance). Alternatives rejected: grepping the output text makes a gate depend on a prose string (the class that greens on a blank); an owner exemption would place «expected red» inside the last gate before release — exactly the state P5.6 exists to end. `research/40-p5.6-gate-reconciliation-design.md` §3. RAG:— (repo-grounded: `findings/P5.6-gate-staleness-verification-2026-08-06.md` §3)

## Почему

Это не «мягкий пункт Validation»: порог не снижен и ничего не стало опциональным — второй, ранее невыразимый вердикт получил своё машинное значение, а все прежние классы отказа по-прежнему возвращают `1`
