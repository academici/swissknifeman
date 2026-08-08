# P1.5 — Оценка выполнимости reader-contract v1

Этот документ фиксирует **оценку реконструкции, а не доказательство реализованной раскладки**.
Носители layout v2 ещё не построены: P2 реализует их и обязан повторить измерение на фактическом
пути. Машинный источник чисел — `artifacts/p1-feasibility.json`; он полностью пересобирается:

```bash
PYTHONPATH=packages/task/lib python3 plans/2026.08.07-PLAN-ECONOMY/artifacts/p1-path-reconstruction/generate.py
```

## 1. Что реконструировано

Для каждого пункта материализованы пять слотов `read-path` v1: стабильное ядро плана, Phase
Context, стабильное ТЗ пункта, digest-qualified bundle и синтетический item-state по схеме P1.2.
Bundle хранит SHA-256 исходного файла и выбранных байтов. Section/symbol slice применяется только
когда он явно объявлен в `Required Reads`; неявное сужение запрещено контрактом и генератором.

Выборка покрывает два реальных плана разного веса и по три пункта в каждом. Для каждого плана
включён пункт с самым тяжёлым `Required Reads`: `P2.1` у крупного и `P6.1` у здорового.

## 2. Сквозная сверка четырёх контрактов

Сверка обнаружила и до freeze закрыла три расхождения:

- `scoped-review` и `full-audit` добавлены как профили существующего `auditor`; reader set остался
  `designer/executor/auditor/owner`, а `scoped-review.control = return-to-root`;
- носители `index` и `artifacts`, ранее осиротевшие между registry и path spec, добавлены как
  optional slow slots designer/auditor/owner; executor получает artifact только через свой bundle;
- вход bundle уточнён до digest-qualified whole-file или явно объявленного section/symbol slice.
  Это закрывает тяжёлый `P2.1`, не поднимая порог и не определяя преждевременно схему bundle P3.

Машинная проверка также подтвердила: все `carrier_id` существуют; не осталось carrier без пути или
`superseded_by`; volatility монотонна на четырёх путях; executor не видит `history` и `handoff`;
текущие поля item-state не пересекаются с полями событий history; history требует ровно поля
запечатанной схемы `2026.07.18-FOREMAN` и не добавляет нового поля журнала.

## 3. Результаты против read-budget v1

Единица: `token-estimate-calibration@2.0.0`, target `codex/gpt-5.6-terra`, adapter
`codex-exec-jsonl-v1`, protocol `differential-input-total-v2`; порог — `100000`. Каждый файл
дополнительно проверен против обоих single-read limits (`262144` bytes и `25000` estimated tokens).

| План / класс | Пункт | legacy v1 lower bound | reconstruction v2 | Максимальный файл | Вердикт |
|:--|:--|--:|--:|--:|:--|
| `2026.08.07-PLAN-ECONOMY` / large, legacy floor `510633` bytes | P2.1 | 384081 | 59840 | 10978 | pass |
| тот же | P0.4 | 188136 | 22333 | 5212 | pass |
| тот же | P0.5 | 154992 | 25641 | 5399 | pass |
| `2026.07.15-TOKEN-ECON-P6` / healthy, legacy floor `33310` bytes | P6.1 | 23215 | 21995 | 5217 | pass |
| тот же | P7.1 | 6419 | 3781 | 1849 | pass |
| тот же | P7.2 | 6419 | 3759 | 1849 | pass |

Все числа в таблице воспроизводятся из `p1-feasibility.json` одной командой:

```bash
python3 -c "import json; d=json.load(open('plans/2026.08.07-PLAN-ECONOMY/artifacts/p1-feasibility.json')); [print(p['plan_id'], i['item'], i['legacy_v1_tokens_lower_bound'], i['total'], max(f['tokens'] for f in i['files']), i['passes']) for p in d['plans'] for i in p['items']]"
```

## 4. Per-file overhead и воспроизводимость

Сумма каждого пункта включает отдельный overhead `318.793666412498` для каждого
материализованного файла: core, phase context, item spec, bundle manifest, каждого input unit и
item-state. Двойной прогон дал один byte digest набора реконструкции:
`8adaa14a7d09e2be1b673cc50bbb2f361df16a16a947bf560004e27128029255`.

Legacy-v1 значения и floor берутся из замороженного generated baseline
`artifacts/fleet-weight.json`, а исходные байты v2 — из дерева item-коммита `b82aa8ee`, не из
mutable plan bookkeeping или рабочего дерева. Sample aggregate: legacy-v1 lower bound `763262`,
reconstructed-v2 `137349`. Это не выдаётся за
whole-plan closed-graph aggregate: выборка проверяет выполнимость пути и тяжёлые Required Reads,
но не заменяет двурукую приёмку P6.8. Обязательные входы не исключены: явно объявленные slices
остаются внутри измеряемого bundle и привязаны к source/selected SHA-256.

## 5. Что этот замер НЕ доказывает

- Он не доказывает, что генераторы P2 строят те же байты или что freshness gate P3 fail-closed.
- Он не доказывает whole-plan aggregate и не разрешает пройти D74 только дроблением, кэшем,
  переносом, отложением или исключением работы.
- Он не сертифицирует Claude/provider adapters: текущая единица квалифицирована только для
  `codex/gpt-5.6-terra`; другие provider rows остаются `pending-provider` до своей проверки.
- Он не задаёт capsule/verdict schema scoped reviewer: это остаётся P4.5/P6.3.
- Он не разрешает менять порог `100000`; изменение требует новой владельческой D-записи.

## 6. Владельческий freeze-гейт

Владелец 2026-08-08 явно поручил: «Исполнить P1.5 и заморозить reader-contract v1», затем запустил
`task:plan-run 2026.08.07-PLAN-ECONOMY P1.5` под `gpt-5.6-sol/high`. После предъявленной выше
сверки и проходящей оценки это решение записывается D127 и переводит четыре контракта P1 в frozen.
