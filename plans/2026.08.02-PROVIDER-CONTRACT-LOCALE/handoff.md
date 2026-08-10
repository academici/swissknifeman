# HANDOFF — 2026-08-10 — after P0.6

**Next:** ЗАПУСК ВРУЧНУЮ: task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.7

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | Создать исполняемое privacy-safe security/trust evidence и доказать no-op branch P0.7 |
| Команда | — |

```text
select the session model class: implementation
select the session effort: high
$ task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.7
```

#### Native Codex launch-block

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.7'
```

**Done:** P0.6 closed green on item commits `ffc735d9` and `970ef84e`: D67 freezes the exact v1.0.1 contract bytes; the checker now binds exact G01–G11, R01–R07 and final-audit row semantics, strict decision frontmatter and privacy-safe matrix inputs. The expanded copied-input suite rejects every mapping/recovery-field weakening, verifier spoof, decision spoof and evidence mutation. Downstream gate is green.
**Remaining:** Execute P0.7, then P0.8; close P0 and run the second independent `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P0` before P1.
**Sources of truth:** `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/P0/P0.7.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/P0/P0.6.state.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/root/contracts/provider-recovery-gates-v1.md` · `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/roadmap.md`
**Open risks:** P0.7 must re-observe provider/trust state and may fail closed if a command is unavailable, red or expired. A nonempty action set still requires a separate exact `containment_mutation_decision`; D67 authorizes no mutation.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: Layout v2 phase-level reopen colour remains recorded in `findings/17-layout-v2-phase-reopen-status-gap-2026-08-10.md`; generated views remain generator-owned.
- open_questions: —
