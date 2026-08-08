## 5. Артефакт и совместимость

Активный `token-estimate-calibration` v2 получает обязательный блок:

```json
{
  "calibration_target": {
    "provider": "codex",
    "adapter": "codex-exec-jsonl-v1",
    "requested_model_id": "gpt-5.6-terra",
    "probe_protocol_version": "differential-input-total-v2",
    "usage_semantics": "provider-reported-input-total-v1"
  }
}
```

Flat-поля v1 `source`/`tokenizer` сохраняются только в историческом snapshot. Новый загрузчик
fail-closed требует `calibration_target`, classifier v2 и полный набор пяти ставок. P0.5 и P3
используют коэффициенты, но при диагностике обязаны показывать qualified target; warning о
несовпадении сравнивает переданный session provider/model с обоими полями, не только model id.

Будущий Claude-артефакт не перезаписывает Codex evidence молча: он либо получает новый qualified
artifact id/version, либо заменяет active artifact отдельным D-решением и повторным прогоном всех
гейтов. Численное равенство между провайдерами не является критерием P0.1.


## 6. Поверхность реализации и доказательства

- Новый `task.token_probe` владеет immutable record validation и adapter protocol; отдельный
  `task.token_probe_codex` владеет `CodexExecProbeAdapter`. Калибратор зависит только от neutral
  interface и не импортирует raw Codex schema.
- `calibrate-token-estimate.py` владеет bounded corpus, bracket-controls, fitter и записью generated artifacts;
  provider выбирается явным CLI-аргументом, default для этого item — `codex`.
- `task.token_estimate` остаётся offline/stdlib-only и знает только qualified provenance артефакта.
- Юнит-тесты парсера: missing/duplicate terminal event, bad exit, missing/negative/non-int total,
  cache не удваивает total, стабильная сборка команды и fake adapter для доказательства
  независимости fitter от Codex.
- Интеграционный smoke-probe запускает один Codex turn в пустом cwd; bounded corpus из восьми
  samples восьми реальных файлов остаётся ручным acceptance шагом item'а, не CI. Log пинует
  source hash/range/sample hash; полный source затем проверяется offline без provider calls.

Сохранность D117 неизменна: v1 snapshot и исходный Claude probe-log не правятся; Codex пишет новый
`calibration-probe-log-v2.json`, где каждый record несёт qualified target и fingerprints.
