# Provider migration gates

**Version:** v0.1.0-draft  
**Status:** draft; sealing owner-gated in P0.4

Контракт должен определить точные entry/release gates, producer item, evidence path,
owner, pass/fail rule и failure action для P1–P7, Claude compatibility, Codex security,
self-hosting, bootstrap cleanup, P7.4→FOREMAN handoff и fleet no-write boundary.

До P0.4 этот файл фиксирует только назначение. Он не снимает паузу FOREMAN, не разрешает
fleet rollout и не заменяет owner approval или adversarial release verdict.
