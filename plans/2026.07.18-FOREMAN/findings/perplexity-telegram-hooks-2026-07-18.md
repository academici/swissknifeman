---
type: finding
plan: 2026.07.18-FOREMAN
source: perplexity-web search, 2026-07-18
urls:
  - https://medium.com/@dan.avila7/step-by-step-guide-connect-telegram-with-claude-code-hooks-1686fadcee65
  - https://www.youtube.com/watch?v=BqDGc4Z2yXs
verdict: verified (сверено с hooks-докой из headless-факт-листа)
---

# Perplexity: Telegram-интеграция через хуки CC + remote-approve

Запрос: «Claude Code hooks Telegram notification: Notification/Stop hook shell script,
remote approve/interject patterns for unattended runs».

## Событийная схема

- **Stop** → «задача завершена»; **Notification** → «Claude ждёт человека»
  (matchers `permission_prompt|idle_prompt|agent_needs_input|agent_completed`);
  **SessionEnd** → финал обёрточных/CI-прогонов. Трёх событий достаточно.
- Один скрипт на все события, ветвление по `hook_event_name` из stdin-JSON
  (`session_id`, `cwd`, matcher). Токен/чат — в env (`TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID`), НЕ в settings.json. Отправка — curl `sendMessage`.
- `agent_needs_input`/`agent_completed`: CC ≥ v2.1.198; для background-агентов
  фактически работают при открытом agent view — для headless-драйвера опираться
  на Stop/Notification/SessionEnd + собственные сообщения драйвера.

## Remote awareness vs remote control — ключевое разделение

- **Layer 1 (низкий риск, поддержано нативно):** notify-only хуки → TG.
- **Layer 2:** wrapper state machine вокруг `claude -p` — resume, retries,
  human checkpoints. (= драйвер Artifex.)
- **Layer 3 (опциональный, опасный):** TG-бот как command inbox ДЛЯ ОБЁРТКИ
  (`approve <session>` / `deny` / `status` / `note`), не для CC напрямую.
  Механика: PermissionRequest-хук авто-аппрувит узкий скоуп; в `-p` хук возвращает
  `defer` → процесс выходит с сохранённым pending tool call → Agent SDK-обёртка
  собирает решение из TG и резюмит.
- Предупреждение источника: TG-команды, запускающие/управляющие прогонами, =
  remote admin surface → sender allowlist, cooldowns, append-only audit log —
  обязательные требования к P3, если Layer 3 делаем.

## Проекция на Artifex

- P3 MVP = Layer 1 + сообщения самого драйвера (ATTENTION/RED, фаза закрыта, стоимость).
- Layer 3 (TG-approve) — отдельный опциональный item с security-требованиями,
  не смешивать с MVP.
