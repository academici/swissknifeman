---
type: finding
plan: 2026.07.18-FOREMAN
source: perplexity-web search_advanced (web+social), 2026-07-18
urls:
  - https://code.claude.com/docs/it/headless
  - https://code.claude.com/docs/en/cli-reference
verdict: verified (совпадает с first-party докой)
---

# Perplexity: паттерны супервизора над `claude -p` (2025–2026)

Запрос: «Claude Code headless orchestration supervisor script patterns: multi-phase
plans via sequential fresh sessions, parsing --output-format json, retry/escalation».

## Консенсус-паттерн

- **Fresh session per phase — дефолт**; resume (`session_id` + `--resume`) только когда
  реально нужна разговорная память предыдущего шага. «Externalize state, minimize
  session reuse» — состояние держит супервизор в артефактах (у нас это handoff.md
  план-протокола — совпадение 1:1 с нашей архитектурой).
- JSON-контракт: валидировать `type=="result"`, смотреть `is_error` + exit code +
  наличие `result`, НЕ судить об успехе по stdout. stream-json — только если нужна
  прогрессивная наблюдаемость (NDJSON, парсер сложнее).

## Двухуровневый retry

- Tier 1 — transport-ошибки (timeout, auth, rate-limit, битый JSON): retry с backoff.
- Tier 2 — semantic-ошибки: менять промпт/права/скоуп, дробить фазу на подфазы,
  НЕ повторять то же самое.
- Лестница эскалации прав: read-only анализ → уже́ный промпт → edit-права только на
  exec-шаге → сплит фазы. Пофазовые allowlist'ы, не глобальные.

## Pitfalls (в Implementation Rules драйвера)

1. `-p` — не стабильный RPC: дефенсивный JSON-парсинг, лог `claude --version`,
   пин бинаря, отказ от неизвестных/старых версий перед длинным прогоном.
2. `--bare` ускоряет/детерминирует, но отключает хуки/скиллы/CLAUDE.md — для Artifex
   НЕ подходит (весь смысл — тулинг владельца); использовать только для служебных
   вызовов самого драйвера, если будут.
3. Overbroad `Bash` в `--allowedTools` превращает ревью-скрипт в неконтролируемый
   исполнитель — паттерн-скоупить (`Bash(git diff *)`).
4. Каждый вызов — под `timeout` (сурогат отсутствующего `--max-turns`).
