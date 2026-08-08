# HANDOFF — 2026-08-08 — after P1.5

**Next:** manual: implementation/high — `2026.08.07-PLAN-ECONOMY P2.1`

**Native Codex launch-block**

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Approval/Sandbox | `-a never -s danger-full-access` |
| Context | continue current root; item-by-item |
| Суть | Построить резолвер раскладки v2 по замороженному reader-contract v1 с legacy parity |
| Команда | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P2.1'` |

**Provider-neutral plan-protocol launch-block**

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | P2.1: резолвер layout v2, дословная legacy-совместимость и замер фактического read path |
| Команда | — |

```text
select session model class implementation
select session effort high
$ task:plan-run 2026.08.07-PLAN-ECONOMY P2.1
```

**Done:** P0 и P1 терминальны. `2026.08.07-PLAN-ECONOMY P1.5` свёл четыре контракта, закрепил
два review-профиля за существующим `auditor`, сохранил `return-to-root` и заморозил reader-contract
v1 решением D127. Воспроизводимая реконструкция покрыла крупный и здоровый реальные планы по трём
items, включая самые тяжёлые Required Reads; превышений порога `100000` нет. Результат остаётся
оценкой раскладки, а не доказательством её реализации.

**Remaining:** P2–P6 по roadmap. Ближайший пункт — `2026.08.07-PLAN-ECONOMY P2.1`; он обязан
повторить измерение уже на фактическом резолвере, не принимать P1-реконструкцию за реализацию.

**Sources of truth:** `plan.md` D127 и `## 7. Contracts` · `phases/P1.md` P1.5 и Phase Handoff ·
`root/contracts/reader-contract-v1.md` · `root/contracts/read-path-v1.md` + `.spec.json` ·
`findings/06-p1-path-feasibility.md` · generated `artifacts/p1-feasibility.json` ·
`phases/P2.md` P2.1.

**Open risks:** P1.4 передал discovery-дефект `plans/.claude`/`plans/__pycache__` в owning item
P3.6. Предыдущий handoff фиксировал lifecycle hook `provenance-invalid`; текущие `codex doctor` и
`maind health --strict` зелёные, но отдельного доказательства ремонта источника регистрации этот
item не создавал. Claude/provider certification остаётся `pending-provider` по D119–D122.

**Workarounds/Deferred/Open questions:**

- Workarounds: —.
- Deferred: реальные layout-v2 носители и резолвер — P2; bundle/freshness gates — P3;
  capsule/verdict review — P4.5/P6.3.
- Open questions: —.
