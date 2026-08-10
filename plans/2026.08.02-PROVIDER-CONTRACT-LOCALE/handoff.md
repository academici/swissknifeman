# HANDOFF — 2026-08-10 — after P0.8

**Next:** design-item: task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.8

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | Repair the Layout v2/read-budget contract blockers before P0.8 can requalify P0 closure. |
| Команда | `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.8` |

#### Native Codex launch-block

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0.8'
```

**Done:** P0.8 item commit `73dbe192` provides a deterministic four-anchor ledger, re-evaluates historical Task Contract codes as `allow/allow`, appends exactly four correction events, and regenerates P0.1–P0.4 truthful state views. `write-site: pre_mutation: allow · pre_final: allow` is present in every correction note.

**Remaining:** plan-design must resolve the Layout v2 core violation, regenerate dependency-affected bundles through their owners, and redesign/split P0.6's 3,395,793-token read-budget breach; then resume P0.8 fan-in, close P0, and run independent audit pass 2.

**Sources of truth:** `artifacts/P0.8/execution-provenance-v1.json` · `artifacts/p0-execution-provenance.py` · `findings/P0.8-validation-blocker-2026-08-10.md` · `phases/P0/P0.8.state.md`.

**Open risks:** `bash packages/task/scripts/validate.sh` ran 750 tests (1 skip) but fails repository plan-lint on the three recorded active-plan blockers; this is not attested green. Harness doctor also reports missing global hook files and stale run-report hook.

**Workarounds/Deferred/Open questions:**

- workarounds: P0.8 ran at `frontier/high` rather than prescribed `implementation/high`; this is a process deviation.
- deferred: generated P0.1/P0.4 live-evidence rewrites from fan-in producers were restored because they are outside P0.8 Files.
- open_questions: —
