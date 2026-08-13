# HANDOFF — 2026-08-13 — after P0

**Next:** design-phase: task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0

| Параметр | Значение |
|:--|:--|
| Batch | n/a |
| Model | frontier |
| Thinking | high |
| Capabilities | plan design · decision contract |
| Context | cold-start-root: audit-root-terminal |
| Суть | Reopen only the proven P0 classification/freshness acceptance boundary. |
| Команда | `$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0` |

```
$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0

РЕЖИМ: доказанная граница audit-fixer; НЕ ordinary repair-run и НЕ второй audit
ВХОД: plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/P0/P0.md → блок `## Audit P0 — 2026-08-13`; прочитать ПЕРВЫМ
СКОУП: 1) forward-repair P0.2 evidence digests без смены exact set/classes 2) через новый D# согласовать P0.6/P0.8 SHA и compact-projection acceptance 3) определить исполнимую freshness/refresh границу P0.7→audit→close, затем перепроизвести evidence 4) сохранить c5467e55 и append-only correction history
НЕ ТРОГАТЬ: P0.1–P0.8 historical commits/journal rows; P1–P7; classification dispositions; внешние fleet/Brain/provider/credential/trust targets; frozen recovery semantics без нового exact owner decision
```

#### Native Codex launch-block

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.08.02-PROVIDER-CONTRACT-LOCALE P0'
```

**Done:** Audit attempt 2 repaired P0.7 false-green capture/timeout in `c5467e55`, restored
P0.5/P0.7 write-site state evidence, and rebound candidate `dba2debb…`; verdict remains RED.

**Remaining:** forward-repair the stale P0.2→P0.8 digest chain and define an executable P0.7
freshness/refresh boundary before another phase-close candidate. P1 remains closed.

**Sources of truth:** `phases/P0/P0.md` → `## Audit P0 — 2026-08-13` ·
`artifacts/P0.8/execution-provenance-v1.json` · D69 · `phases/P0/P0.7.state.md`.

**Open risks:** P0.2 production check rejects the committed classification as stale; P0.7 evidence
expires after ten minutes and no persisted refresh action bridges audit-root-terminal to close.

**Workarounds/Deferred/Open questions:**

- workarounds: none; audit-fixer changes are committed and journaled.
- deferred: P1 remains closed pending P0 redesign and requalification.
- open_questions: —
