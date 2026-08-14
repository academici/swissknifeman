# HANDOFF — 2026-08-14 — after P0.9

**Next:** run-items: task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.10

| Параметр | Значение |
|:--|:--|
| Batch | p0-final-requalification |
| Model class | implementation |
| Effort | high — live admission and final fan-in |
| Capabilities | — |
| Context | continue-root |
| Суть | Replace persisted freshness authority with live P0 admission and produce the final phase candidate. |

```bash
$ task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.10
```

#### Native Codex launch-block

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.10'
```

**Done:** P0.9 item commit `f3cd5a85` regenerated the P0.2 classification from the P0.5 baseline, proved digest-only semantic equivalence, rebound current P0.6/P0.8 consumers, and closed through the route-bound Task Contract.

**Remaining:** P0.10 live admission and static final fan-in; then phase close and one final independent P0 audit.

**Sources of truth:** `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/P0/P0.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/P0/P0.10.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/artifacts/P0.9/classification-rebind-v1.json`

**Open risks:** P0.10 must preserve D67/frozen recovery-contract bytes and treat only its immediate live `admit` receipt as admission authority.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: —
- open_questions: —
