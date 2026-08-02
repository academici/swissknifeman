# Бриф владельца — 2026.07.31-SKM-LEAN (слой 0)

**Дата входа:** 2026-07-31 · **Канал:** `/task:plan-design new` · **Слой:** 0 (вход владельца,
переформулировано без потери мыслей; уточнения по ходу — `01-refinements.md`).

## Постановка

Новый мастер-план **SKM-LEAN**, семь фаз. Ниже — мысли владельца, разложенные по фазам,
дословно по смыслу.

### P1 — измеритель first-turn

Нужен **агрегатор** с видимостью marketplace-плагинов: сегодня `skiller budget --first-turn`
и `claude plugin details` — два раздельных инструмента, владелец складывает их вручную.
Далее — **baseline-замер по флоту** и **порог**: без порога, посчитанного от реального
флота, вердикт измерителя бессмыслен.

### P2 — резидент-диета

- `CLAUDE.md` ≤ 200 строк;
- **path-scoped `.claude/rules`** — и на umbrella, и на флоте;
- **MCP-прополка** + **tool search**;
- `.mcp.json.example` перевести в **default-on**.

### P3 — скиллы через нативные поля Claude Code

- **Пилот `paths:`** на одном бакете с замером «до/после» → затем раскатка.
- **`context: fork`** на процедурных скиллах — против «липкости тел» (тело скилла,
  один раз попав в сессию, остаётся в ней до конца).
- **`model:` / `effort:` тиры**.
- **EN-описания + `when_to_use`** — одним проходом закрывают долг 69 описаний и
  Codex listing overflow.

### P4 — exec-драйвер в `packages/harness`

Ядро — **четыре item'а**:

1. **`plan_reader`** — Status Board + `§3 Routing` + `handoff.Next`; парс **переиздать**
   против `plan-protocol` **v2.21.0** (историчный контракт донора не использовать).
2. **`worker`** — `claude -p /task:plan-exec` под таймаутом, захват отчёта и `cost_usd`.
3. **`gate`** — `plan-lint` + git-проверка двух коммитов → `GREEN`/`ATTENTION`/`RED`,
   **три исхода без машины `decide`**.
4. **`journal`** — дозапись в `plans/<ID>/journal.jsonl` + сводка волны.

CLI: `swissknifeman env run <PLAN-ID> Pn`.

**ЯВНО вне скоупа P4:** машина `decide`; run-folder; retry-лестница трёх тиров;
мессенджеры; remote-approve; пакет `packages/artifex`; agent-pack раскатки;
второй водитель `codex exec`.

### P5 — гигиена и безопасность

- supply-chain скан вендоренных скиллов (54 по оценке владельца);
- провенанс `provider-capabilities.json`;
- консолидация `.env.ini`;
- провенанс модели в плане;
- codex publication gate;
- playwright `output-dir`;
- `instruction-authorize-order`;
- формат launch-block;
- `plan-lint --conflicts`.

### P6 — рефактор `core/`

Доменные папки + конфиг-объект, **stdlib-only**.

### P7 — закрытие roadmap в ноль

D-записи по отложенному:

- **`agent-scoped-skill-loading`** — дефолт `connect` **не меняем**; скоуп даёт `paths:`;
- **`skill-rules-sidecar`** — нативный эквивалент уже есть;
- **`project-freshness-agent`** — новых ролей не заводим;
- **`artifex`** — ядро уходит в P4, остаток остаётся с критерием «N волн»;
- **analyst-темы** — переезжают в `packages/analyst/docs/roadmap.md`.

## Источники, названные владельцем

- `audits/skm.md`;
- `roadmap/*`;
- замеры `budget --first-turn`: swissknifeman **10757** · agelto **32611** ·
  flexcrm **29354** · botkit **10843** · diabox **11996**;
- R&D 2026:
  - Opus 5 **AgentTool suppression** в Claude Code 2.1.219+;
  - **CooperBench** (Stanford/SAP) — −25…30 % на общей кодовой базе;
  - нативные поля скиллов `paths` / `context: fork` / `disable-model-invocation` /
    `model` / `effort`;
  - замер использования этих полей в репо: `paths` 1/229, `fork` 0/229.

## Что владелец задал как рамку (не предмет обсуждения)

- Семь фаз именно в этом составе и порядке.
- Список «явно вне скоупа» для P4 — закрытый.
- D-вердикты P7 по четырём отложенным темам — приняты владельцем, план их только оформляет.
