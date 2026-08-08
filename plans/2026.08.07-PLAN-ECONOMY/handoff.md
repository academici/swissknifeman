# HANDOFF — 2026-08-08 — after P2.8

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/high

## Native Codex launch-block

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | high |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Approval/Sandbox | `-a never -s danger-full-access` |
| Context | continue (/clear) — ручной item |
| Суть | Реализовать stage-aware admission и bounded split carriers P2.9. |
| Команда | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P2.9'` |

## Provider-neutral plan-protocol launch-block

| Параметр | Значение |
|:--|:--|
| Model | frontier |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | Заморозить stage-aware admission без ослабления D2/D74 и разрезать oversized task carriers. |
| Команда | — |

```text
$ task:plan-run 2026.08.07-PLAN-ECONOMY P2.9
```

**Done:** P2.8 losslessly migrated the self-host plan to Layout v2; the inventory covers 1,053
elements and 45 items, views and structural lint are fresh, and the honest baseline preserves all
D2(a), D2(b), missing and unresolved facts. The phase-status reducer was repaired so terminal
deviations no longer falsely block phase-first execution. Item commit: `b3c6435a`.

**Remaining:** P2.9 defines/enforces stage-aware admission and bounds shared task carriers; P2.10
rebuilds the full read graph and makes the final D74 self-host verdict. P3 remains gated on P2.

**Sources of truth:** `decisions/D131-stage-aware-read-admission.md` ·
`phases/P2/P2.9.md` · `research/20-p2.8-stage-aware-admission-redesign.md` ·
`findings/21-p2.8-read-admission-diagnosis-2026-08-08.md`.

**Open risks:** P2.9 is a public admission-contract change and is routed `frontier/high`; the
current `implementation/high` session must not execute it. The final self-host claim belongs only
to P2.10.

**Workarounds/Deferred/Open questions:**

- Workarounds: —.
- Deferred: P2.9/P2.10 are explicit remaining items.
- Open questions: —.
