# HANDOFF — 2026.08.02-PROVIDER-CONTRACT-LOCALE — after P7.7

**Done:** P7.7 completed the sole D90 bounded F2–F6 successor audit. The terminal result is RED;
the independent calibrated reviewer returned `JUSTIFIED`. Audit evidence is committed at
`49e57f97197325fbca9afea2128199086d531603`. D89 and the external blocker payload are unchanged,
and no release operation was authorized.

**Remaining:** Apply recommendations 1–4 from `artifacts/P7-final-release-audit.md`: bind the
release-tree gate to its JSON manifest, make runtime carriers and current foreign-byte verification
explicit, repair P7.5/P7.6 write-site/downstream bookkeeping, and add qualifiable command input
hashes. Rerun only the targeted P7.7 gates, recover-close P7.7, then close phase P7. D89 external
rollout/live-efficacy work remains outside the phase and release stays forbidden.

**Sources of truth:** `artifacts/P7-final-release-audit.md` · `findings/P7-release-verdict.md` ·
`findings/P7.7-return-judgement-5108cc842329.md` · `phases/P7/P7.7.state.md` · D89 · D90 ·
scope commit `072f806507c0b2672fb393c6fb15812bbb3cddd6` · audit commit
`49e57f97197325fbca9afea2128199086d531603`.

**Next:** close: task:plan-close 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.7

| Поле | Значение |
|:--|:--|
| Batch | solo |
| Model | implementation (`gpt-5.6-terra`) |
| Thinking | low |
| Context | `cold-start-root` |
| Суть | Recovery-сверка RED P7.7 по уже записанным fixes; без нового design-loop |

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="low"' -a never -s danger-full-access '$ task:plan-close 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.7'
```
