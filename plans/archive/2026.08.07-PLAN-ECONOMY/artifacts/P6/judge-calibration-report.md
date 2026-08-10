ОГРАНИЧЕНИЕ: это калибровка обнаружения рубрики на 30 исторических return events, не production-гейт; она не доказывает переносимость на другие providers/models и не покрывает отсутствующие в корпусе объявленные seams.

# P6.3 — калибровка return-judgement@1.0.0

- Qualified pair: `openai:gpt-5.6-sol` ×
  `63323e5565fa2c321354e36ebe47624f37f86c3c3372ba01efaedcc61b6c2e1e`.
- Corpus: `artifacts/P4/returns-baseline.json`; выборка стратифицирована по provisional
  item-return, phase-level out-of-scope и ungroupable событиям.
- Объём: 30; это нижняя граница режима обнаружения рубрики, а не инженерная эвристика
  production-калибровки 100–300.
- Сырое согласие human ↔ conservative judge: `30/30 = 1.000`.
- κ Коэна: `1.000` (две наблюдавшиеся метки: 22 `INSUFFICIENT_EVIDENCE`, 8 `OUT_OF_SCOPE`).
- Swap-control: 3/3 order-sensitive пар сведены в `INSUFFICIENT_EVIDENCE`; победитель порядка не
  выбирался и не усреднялся.
- Покрытие: исторический корпус не несёт объявленных seams по построению, поэтому он не
  калибрует `JUSTIFIED`/`AVOIDABLE`; schema-valid baseline также не калибрует `MALFORMED`.
  Эти классы остаются задачей следующей перекалибровки до любого production enforcement.
- Claude: `pending-provider`; собственная строка появляется только после provider-owned replay
  того же frozen bank с точным `anthropic:<model>` id.

## Метод

Human labels следуют наблюдаемым carrier-фактам: phase-level subjects не являются item-scoped
capsule и получают `OUT_OF_SCOPE`; item events без объявленного seam или с ungroupable identity
не позволяют доказать содержательный вердикт и получают `INSUFFICIENT_EVIDENCE`. Для трёх
повторных событий доказательство намеренно предъявлялось в прямом и обратном порядке; разные
промежуточные классификации редьюсер заменил воздержанием.

## Правило перекалибровки

Изменение точного model id/provider route, rubric bytes/hash, output schema, parser,
evidence extraction или материальное изменение входного распределения инвалидирует pair. До
нового отчёта редьюсер интерпретирует запись неизвестной пары как `INSUFFICIENT_EVIDENCE`; она не
может дать ужесточающий сигнал.
