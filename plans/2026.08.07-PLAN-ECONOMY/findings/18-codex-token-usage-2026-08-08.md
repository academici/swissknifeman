# P0.1 — наблюдаемая форма token usage Codex exec

**Дата проверки:** 2026-08-08  
**Класс:** внешний current API/CLI contract + локальная проверка среды  
**Потребитель:** `2026.08.07-PLAN-ECONOMY P0.1`

## Внешний контракт

Официальная документация OpenAI для non-interactive Codex фиксирует:

- `codex exec --json` пишет поток JSONL-событий;
- terminal-событие имеет тип `turn.completed` и блок `usage`;
- в документированном примере `usage` отдельно содержит `input_tokens`,
  `cached_input_tokens`, `output_tokens` и `reasoning_output_tokens`;
- `--ephemeral` не сохраняет rollout, `--ignore-user-config` и `--ignore-rules` исключают
  пользовательскую конфигурацию и execpolicy, `--skip-git-repo-check` разрешает изолированный
  временный cwd.

Источник: OpenAI, «Codex non-interactive mode», проверено 2026-08-08:
https://learn.chatgpt.com/docs/non-interactive-mode. Confidence: **high** (официальная документация).

## Локальная проверка

В пустом каталоге выполнен read-only probe локальным `codex-cli 0.147.0`:

```text
printf '%s\n' 'Return exactly OK. Do not use tools.' |
codex -C <empty-tmp-dir> -m gpt-5.6-terra -c 'model_reasoning_effort="low"' \
  -a never -s read-only exec --ephemeral --ignore-user-config --ignore-rules \
  --skip-git-repo-check --json -
```

Команда завершилась exit 0 и выдала ровно одно terminal-событие:

```json
{"type":"turn.completed","usage":{"input_tokens":13388,"cached_input_tokens":9984,"cache_write_input_tokens":0,"output_tokens":5,"reasoning_output_tokens":0}}
```

Наблюдение подтверждает форму события и наличие cache breakdown. Оно не доказывает стабильность
числа между прогонами и не раскрывает effective model id в событии: адаптер обязан пиновать
requested model в команде и сохранять CLI/version/fingerprint как провенанс.

## Вердикт для архитектуры

Общий fitter не должен читать JSONL Codex или знать имена его usage-полей. Провайдерский адаптер
возвращает нормализованную запись с `input_tokens_total`; Codex-адаптер маппит это поле только из
`turn.completed.usage.input_tokens`. `cached_input_tokens` и `cache_write_input_tokens` сохраняются
как диагностические breakdown-поля и **никогда не прибавляются** к `input_tokens_total`: канонический
total выбирает адаптер провайдера, а ядро не реконструирует его из частей. Парсер принимает ровно
одно terminal-событие и падает на пропуске, дубликате, отрицательном/нецелом usage или ненулевом
exit.

Claude Code в этом решении не объявляется несовместимым и не удаляется: его будущий адаптер должен
маппить собственную семантику usage в ту же нормализованную запись. Числа разных
`provider + model + protocol` не смешиваются в одном артефакте и не считаются взаимозаменяемыми.

## Проверка (verification status)

- RAG: официальная документация OpenAI ×1 + локальные `codex exec --help`, `codex --version` и
  read-only probe ×1 — OK; confidence high.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: форма terminal usage будущего Claude-адаптера — отложена и не
  является load-bearing фактом для Codex-first `2026.08.07-PLAN-ECONOMY P0.1`.
- Обходки/[POSSIBLE-DEFECT]: —.
