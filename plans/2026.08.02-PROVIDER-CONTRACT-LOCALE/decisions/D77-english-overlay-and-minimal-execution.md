---
id: D77
date: 2026-08-14
status: accepted
type: contract_freeze_decision
item: P2.2
items: [P2.2, P2.3]
contract_version: v1.0.0
supersedes: []
superseded_by: null
---
## Решение

The repository owner directed the executor to finish P2.2–P2.3 in the current run with minimum
sufficient acceptance and without additional design, review, synthetic-test, or approval loops.
DecisionRequest `P2.2-validation-carrier-redesign-v1`, action digest
`2d2c8f8c3a66b982cbb9ba7745f83b6a9d4c5f8f08bf213e3e7ec38f3c37fe2a`, was resolved `apply`.

D77 freezes E1–E7 in `root/contracts/english-authoring-overlay-v1.md` v1.0.0, final SHA-256
`8fe3d3eca71e489306e2fd8a021214f8c107e92d93c1cae0c9f985565cfeab4c`; the candidate SHA-256
before approval metadata was `1174bae83c0d3aade165d07ecce8cc033770a7bfa45905c49b727db0fb1198d1`.
The same owner directive freezes C1–C6 in `root/contracts/locale-authoring-review-v1.md` and
S1–S5 in `root/contracts/skill-evidence-v1.md`, both at v1.0.0. Real-project/provider efficacy
evidence remains a P7 acceptance input; P2.3 adds no extra live or synthetic approval loop.
It also accepts the plan-wide minimum-execution rule: a missing Validation command unrelated to
the changed item files is removed locally while the remaining deterministic acceptance stays
mandatory.

## Почему

P2.2 changes only plan-local contract artifacts. The removed translation command referred to an
absent script and could not falsify any changed P2.2 carrier. The overlay checker already owns
source identity, immutable tokens, fallback, provider isolation, matrix parity, and negative
fixtures; plan lint owns plan structure. Adding another script, item, reviewer, or design pass
would add process without new product evidence.

## Consequences

English `SKILL.md` becomes the sole semantic source. Migration removes admitted legacy
`SKILL.ru.md` files after equivalence and rollback evidence; Russian remains only a sparse render
overlay. P2.2–P7 reuse deterministic evidence and add no extra synthetic probes beyond explicit
deliverables or one regression for an observed failure. D77 authorizes no runtime, provider,
project, fleet, credential, or publication write.
