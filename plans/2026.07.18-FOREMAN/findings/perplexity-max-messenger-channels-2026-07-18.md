---
type: finding
plan: 2026.07.18-FOREMAN
source: perplexity-web search, 2026-07-18
urls:
  - https://7days.ru/promokodi/blog/poleznye-sovety/kak-sozdat-bota-dlya-messendzhera-max
  - https://ict-online.ru/news/Krizis-Maksa-na-iOS-prilozheniye-ischezlo-iz-App-Store-a-push-uvedomleniya-perestali-dokhodit-do-iPhone-327659
  - https://www.ixbt.com/news/2026/06/04/max-iphone-app-stoe.html
  - https://www.rbc.ru/technology_and_media/10/02/2026/698afe729a79470c08a17b91
verdict: verified (медиа-источники консистентны; API-детали при имплементации перепроверить по dev-доке MAX)
---

# Perplexity: мессенджер-каналы для эскалации Artifex (MAX / Telegram)

Запрос: «MAX Bot API возможности/ограничения; push MAX на iOS; статус Telegram в РФ 2026».

## MAX (VK)

- **Официальный Bot API существует**: HTTP API, токены, webhook + long polling
  (getUpdates-подход), отправка текста/медиа, inline-клавиатуры, мини-приложения,
  SDK (Python/Node/PHP). По духу близок к Telegram Bot API → адаптер дешёвый.
- Ограничения: rate limits, антиспам (риск блокировки бота при рассылках без opt-in),
  webhook требует публичный HTTPS-endpoint, платформа ограничивает работу при VPN.
- **iOS-пуши сломаны системно**: июнь 2026 — приложение делистнуто из российского
  App Store (VK подтвердил); массовый останов доставки APNs-пушей; источники допускают,
  что без изменения позиции Apple пуши «могут не вернуться никогда». Костыль:
  PWA/веб-версия + web-push (iOS 16.4+). Bot API как HTTP-слой работает — проблема
  только в доставке уведомлений человеку на iPhone.

## Telegram в РФ (июль 2026)

- Формальной тотальной блокировки нет, но: с февраля 2026 — официальное замедление
  и частичные ограничения (звонки); источники называли ~апрель 2026 рубежом фактической
  блокировки по сценарию Instagram/Facebook; РКН заявляет продолжение ограничений.
- Технически доступен большинству со стандартными обходами; юридический фон ухудшается.

## Проекция на Artifex (P4)

1. **Канал-агностик слой обязателен** — оба кандидата ненадёжны каждый по-своему:
   TG (доступность в РФ) vs MAX (доставка на iOS). Интерфейс: `notify(digest)` +
   `inbox(reply)`; адаптеры TG / MAX / (web-push, email — резерв).
2. Несколько активных каналов параллельно → единый inbox: дедупликация ответов по
   session/вопросу, первый полный ответ выигрывает, остальным каналам — «resolved».
3. Блокирующий Q&A (100% понимание) ложится на механику PermissionRequest `defer` +
   Agent SDK resume (см. `perplexity-telegram-hooks-2026-07-18.md`); ответ владельца
   обязан фиксироваться в артефактах плана (слои знаний), не оставаться в чате бота.
4. Security-требования Layer 3 (sender allowlist, cooldowns, audit log) — на КАЖДЫЙ
   канал-адаптер, не только TG.
