# HANDOFF — 2026-09-20 — after P1.1

**Next:** run-items: task:plan-run 2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION P2.1

| Параметр | Значение |
|:--|:--|
| Batch | solo |
| Model class | frontier |
| Effort | high |
| Capabilities | filesystem/git read · managed read-only run-report stores · plan-owned writes · no consumer writes |
| Context | continue-root |
| Суть | Провести три изолированных read-only field audit corex, agentools и edufy, затем cross-project synthesis по запечатанной rubric. |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION P2.1'
```

**Done:** Global design audit GREEN. P1.1 и фаза P1 закрыты GREEN: claim ledger отделяет verified facts от hypotheses и coverage gaps; measurement contract заморозил шесть task classes, A/B controls, practical thresholds, invalidity, budgets, stop rules и reducer `go|keep|defer|reject`. Product/runtime/docs/consumer files не менялись.
**Remaining:** P2.1 — три read-only consumer case и synthesis; затем P3.1, P4.1 и только admitted P5.1. Exact P5 route/review остаются post-P4 admission по D8.
**Sources of truth:** `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/findings/01-p1-verified-baseline.md` · `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/research/02-p1-measurement-contract.md` · `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/phases/P2/P2.1.md` · `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/decisions/D8-p1-p4-audit-and-p5-post-manifest-routing.md`.
**Open risks:** Perplexity был configured, но не exposed как callable tool в P1.1 и записан `n/a`; Codex run-report coverage отсутствует; нули memory/codegraph остаются coverage gaps. Task provider-model-roles projection drift предшествует P1 и остаётся вне item.
**Workarounds/Deferred/Open questions:**
- workarounds: ordinary primary-source retrieval использован после intermittent failures web adapter; config не менялся.
- deferred: product simplification, provider mapping changes, telemetry enablement, consumer writes, release, push и rollout.
- open_questions: —
