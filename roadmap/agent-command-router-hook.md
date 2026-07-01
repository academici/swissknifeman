# Roadmap: router-hook для агентов и slash-команд

**Статус:** ✅ **активирован** (v1) — реализация в
`packages/harness/configs/claude-code/hooks/agent-router/` (пара хуков) + `harness router` +
провиженер `router-config` в `maind sync`. Триггер внедрения сработал: владелец забывает ставить
задачи через `/task:*` (замеренный мисроут на реальном потоке).

## Проблема

Claude Code **автоматически** маршрутизирует **скиллы** (по `description`, прогрессивное раскрытие)
и субагентов (по `description` + `<example>`-блокам). Субагенты иногда не выбираются, если
формулировка задачи далека от примеров. Роутить скиллы не нужно (дубль нативного поведения) —
ценность для **агентов и команд**.

> **Коррекция (verified perplexity-web 2026-07-01, офиц. доки):** прежний тезис «slash-команды НЕ
> автоактивируются вовсе» **устарел**. Плагинные слэш-команды (в т.ч. `/task:*`) **МОГУТ**
> авто-инвокаться моделью через инструмент **`SlashCommand`** (описание в frontmatter → команда в
> tool-листе); pin модели/effort применяется и при авто-вызове; `disable-model-invocation: true`
> делает команду user-only. Хук её всё равно не запускает (`hooks cannot trigger / commands`) —
> инициирует модель. Поэтому режим `propose` (предложить строку) — дефолт по политике, а
> `auto_dispatch` (модель сама вызывает через SlashCommand) — поддерживаемая опция.

## Дизайн (когда дойдём)

- **Хук `UserPromptSubmit`** (stdlib-Python, НЕ JS — конвенция репо), живёт в
  `packages/harness/configs/claude-code/hooks/agent-router/`. Раздаётся как остальные хуки
  (`harness hooks --global` + per-project enable).
- **Контракт** (как у Rio, проверен): на stdin — JSON payload промпта; на stdout —
  `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "<подсказка>"}}`.
  **Ненавязчиво**: только подсказка «рассмотри @prefix-reviewer / `/foo`», решение за моделью.
- **Матчеры** — данные, не код: `agent-router.config.json` в проекте
  `{ "agents": [{"name": "...", "keywords": [...], "weight": N}], "commands": [...] }`.
  Источник можно **сгенерировать** при `maind onboard`/`sync` из доставленных
  `.claude/agents/*.md` (имена) + `description`-ключевых слов.
- **Порог + дедуп**: суммируем веса по вхождению ключевых слов (lowercase substring как дефолт,
  опц. regex), подсказываем top-1, если score ≥ порога. Никогда не форсируем.

## Реализовано (v1) — дельты от исходного дизайна

- **Dual-hook** (не один UPS): `session-policy.py` (SessionStart) несёт СТАТИЧЕСКУЮ политику
  через `additionalContext` раз за сессию; `router.py` (UserPromptSubmit) per-turn эмитит лишь
  крошечную idempotent-подсказку `[intent-router] bias …` при score ≥ THRESHOLD. Дешевле и без
  stale-replay большого текста (офиц. доки рекомендуют именно так).
- **Гибридный классификатор:** keyword-прескор (`_lib.score_entries`) — только bias; финальную
  классификацию «вопрос vs задача / какая команда» делает МОДЕЛЬ по политике.
- **Каталог из всех источников:** `harness router --generate` → `.claude/agent-router.config.json`
  из `/task:*` (курируемые) + `.claude/agents/*.md` + **локальных `.claude/skills/*/SKILL.md`**
  (низкий вес — бэкстоп нативного авторутинга скиллов).
- **Режимы (env.ini `POLICY`):** `propose` (дефолт, human-in-loop) · `auto_dispatch` (модель сама
  вызывает через SlashCommand) · `off`. Escape-hatch: префикс `~` глушит подсказку на один промпт.
- **Раздача:** `harness hooks --global` ставит хуки; `harness hooks --target . --router propose`
  включает per-project (пишет env.ini + регистрирует пару в settings.json); провиженер
  `router-config` в `maind sync` регенерит каталог для проектов, где хук включён (opt-in).
- **Follow-up:** слэш-команды соседних пакетов (skiller/harness/maind) из зонтичного marketplace в
  каталог v1 НЕ включены (per-project резолв ненадёжен) — `/task:*` уже дают кросс-пакетный интерфейс.

## Риски (почему осторожно)

- **Латентность на каждый промпт** — хук в горячем пути; держать матчинг дешёвым (чистый
  Python, без подпроцессов).
- **Stale-replay на `--continue/--resume`**: `UserPromptSubmit.additionalContext` повторяется
  — подсказка должна быть **статичной/обобщённой**, без динамических данных (иначе протухает).
- **Keyword-brittleness**: подстрочный матч даёт ложные срабатывания; начинать с узких
  ключевых слов, расширять по факту.
- **Зрелость прототипов низкая** (Rio ~20★, ранний) — берём только контракт I/O, реализуем сами.

## Зависимости

- Доставка субагентов уже работает (Phase 1–4): профиль → пак → `.claude/agents/*.md`. Роутер
  лишь повышает их **активацию**, не доставку.
- Реестр ключевых слов лучше генерировать из уже доставленных агентов (см. `maind sync`).
