# HANDOFF — 2026-08-08 — after P0.1

**Next:** manual: implementation/high

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | Реализовать shared token-probe contract, thin Codex usage adapter и bounded v2 calibration: 8 real samples, ≤128 KiB payload, ≤12 provider calls |
| Команда | — |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P0.1'
```

**Done:** `2026.08.07-PLAN-ECONOMY P0.1` доведён до DoR под текущий Codex без ожидания
Claude OAuth. D118–D122 закрепили provider-neutral core, минимальные provider edges и независимую
сертификацию: Codex проверяет собственный adapter/projection, Claude позже переводит только свои
строки из `pending-provider` в `verified`. Сквозной пересмотр добавил ранние real-project canary
P2.8/P3.7 и убрал exhaustive cross-provider/full-corpus preflight с critical path.

**Remaining:** Исполнить только `2026.08.07-PLAN-ECONOMY P0.1`: neutral `ProbeRecord`/protocol,
Codex JSONL adapter, dense classifier SSOT, bracket-controls и generated qualified calibration v2.
После зелёного bounded acceptance перейти к P0.2; Claude-specific код сейчас не писать.

**Sources of truth:** `phases/P0.md` P0.1 ·
`research/15-p0.1-provider-neutral-calibration-2026-08-08.md` ·
`research/16-multiprovider-field-loop-2026-08-08.md` ·
`findings/18-codex-token-usage-2026-08-08.md` · D118–D122 · `journal.jsonl`.

**Open risks:** Восемь samples — bounded engineering pilot, не статистическое доказательство всего
флота; расширять его следует по field findings. Claude row честно `pending-provider`, а не green.
Полный `packages/task/scripts/validate.sh` несёт известный внескоупный discovery-дефект
`plans/.claude`/`plans/__pycache__`; пропущенную или упавшую проверку зелёной не считать.

**Workarounds/Deferred/Open questions:**

- Workarounds: —.
- Deferred: Claude token/session adapters и Claude runtime certification — до входа Claude Code.
- Open questions: —.
