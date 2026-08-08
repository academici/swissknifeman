---
id: D118
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Активная калибровка P0.1 становится Codex-first, но её архитектурный контракт — provider-neutral.** Общий слой принимает нормализованный `token-probe-record-v1` с qualified target (`provider`, adapter version, requested/effective model, protocol), единственным `input_tokens_total`, diagnostic breakdown и wrapper/environment fingerprints; A/B/A′, fitter и consumers читают только этот слой. Первый adapter — `codex-exec-jsonl-v1`: из ровно одного `turn.completed` поле `usage.input_tokens` становится canonical total, а cache fields сохраняются, но не суммируются. Claude adapter отложен и позже добавляется аддитивно над тем же contract; его отсутствие не блокирует P0/P3, cross-provider numeric equality не требуется. **Consequences:** `supersedes D92` только в части АКТИВНОГО provider/channel и Claude-specific `sum3`; исторические v1 Claude artifact/probe-log/Completion Notes остаются неизменными по D117. Артефакт v2 и P0.5 qualified по `provider + model + protocol`; калибровки разных targets нельзя смешивать или молча перезаписывать, смена active target требует нового generated evidence и повторного прохождения bound/tightness. Отвергнуты ожидание Claude OAuth (ненужный owner-gate) и Codex JSONL внутри fitter (закрепляет временного провайдера в core).

## Почему

Прямое уточнение владельца 2026-08-08: сейчас писать под Codex, Claude доработает позже, мультипровайдерность обязательна. Codex JSONL/flags подтверждены официальной документацией OpenAI и локальным read-only probe `codex-cli 0.147.0`; terminal event дал отдельные `input_tokens`/`cached_input_tokens`, effective model id не сообщил. RAG:✅ 2026-08-08 (`findings/18-codex-token-usage-2026-08-08.md`; синтез `research/15-p0.1-provider-neutral-calibration-2026-08-08.md`).
