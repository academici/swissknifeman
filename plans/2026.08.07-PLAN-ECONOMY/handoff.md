# HANDOFF — 2026-08-08 — after P0.1

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/high

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high — владельческий гейт неизменяемого бюджетного контракта |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | Выпустить `read-budget-v1` на фактической Codex-qualified calibration v2 и закрыть P0.5 по D113–D115 |
| Команда | — |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P0.5'
```

**Done:** `2026.08.07-PLAN-ECONOMY P0.1` закрыт item-коммитом `30460ddf`: provider-neutral
record/core, thin Codex JSONL adapter, dense SSOT, generated v2 artifact и preserved v1 snapshot.
Bounded acceptance: 8 sources, 65 996 bytes, 4 dense samples, 12 calls, no bound violations,
p95 1.371.

**Remaining:** Исполнить P0.5 под `frontier/high`; P0.2–P0.4 уже терминальны. Claude adapter и
его runtime certification deferred до появления Claude Code, shared core не переоткрывать.

**Sources of truth:** `phases/P0.md` P0.1 Completion Notes ·
`packages/task/configs/token-estimate-calibration.json` ·
`artifacts/P0/calibration-probe-log-v2.json` · `research/15-…` · `findings/18-…` · D113–D122.

**Open risks:** Bounded 8-sample pilot не является статистическим доказательством всего флота;
Claude row остаётся `pending-provider`. `bash packages/task/scripts/validate.sh` по-прежнему
красный из внескоупного discovery `plans/.claude`/`plans/__pycache__` (4 ERROR); целевые tests
и точечный plan lint зелёные.

**Workarounds/Deferred/Open questions:**

- Workarounds: —.
- Deferred: Claude token/session adapters и Claude runtime certification.
- Open questions: —.
