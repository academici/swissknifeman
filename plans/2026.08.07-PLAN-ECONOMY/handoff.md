# HANDOFF — 2026-08-09 — after P6.7

**Next:** design-item: task:plan-design 2026.08.07-PLAN-ECONOMY P6.8

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | cold-start — plan-step |
| Суть | Снять разрешённую D150 эскалацию P6.8 и подготовить повторный run по frozen v1.1.0 |
| Команда | `$ task:plan-design 2026.08.07-PLAN-ECONOMY P6.8` |

**Done:** `P6.7` закрыт `🟠 Done with deviations`. `acceptance-protocol` v1.1.0 заморожен
коммитом `edf04aee`; threshold/scope/arms/canary JSON-эквивалентны v1.0.0, прежний RED сохранён
с report+hash provenance. Downstream self-poisoning исправлен коммитами `154cb3ec` и `536a1b3e`;
новые append-only результаты `P6.6 → P6.8` и `P6.7 → P6.8` green на anchor `536a1b3e`.

**Remaining:** `P6.8` остаётся `🔴 Blocked` старым RED v1.0.0. Перед повторным исполнением его
эскалационный блок и state должны быть reconciled с D150/v1.1.0; затем отдельно выполняются arm A,
arm B и exact session canary. `P6.9` и снятие паузы ARTIFEX запрещены до положительного P6.8.

**Sources of truth:** `phases/P6/P6.8.md` ·
`root/contracts/acceptance-protocol-v1.md` ·
`root/contracts/acceptance-protocol-v1.manifest.json` ·
`decisions/D150-stage-aware-acceptance-v1-1.md` ·
`findings/P6.7-downstream-P6.8-05592e969eb1-536a1b3e869f.md`.

**Open risks:** P6.8 — дорогой manual `frontier/high` acceptance item; его прежний RED нельзя
переименовать или пересчитать задним числом. Lifecycle hook provenance по прежнему field evidence
имеет `record-provenance-mismatch`; repair вне P6.8 Files.

**Workarounds/Deferred/Open questions:** workarounds — nested downstream Validation подавляет
только рекурсивный entrypoint `plan-lint.py`, прямой lint остаётся fail-closed · deferred — повтор
P6.8, arm B, session canary, P6.9 · open_questions — none после D150.

## Native Codex launch-block

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.08.07-PLAN-ECONOMY P6.8'
```
