---
type: finding
plan: 2026.07.18-FOREMAN
source: perplexity-web search_deep (быстрый прогон Fable, 2026-07-18) — ПРЕДВАРИТЕЛЬНЫЙ; полный аудит владелец запускает сам отдельным промптом (research/deep-audit-prompt-skills-ecosystem.md)
urls:
  - https://github.com/obra/superpowers
  - https://github.com/eyaltoledano/claude-task-master
  - https://github.com/othmanadi/planning-with-files
  - https://github.com/steveyegge/beads
  - https://github.com/DietrichGebert/ponytail
  - https://github.com/musistudio/claude-code-router
verdict: superseded — полный аудит владельца `owner-deep-audit-skills-2026-07-18.md` (3 стадии) первичен; этот файл — только исторический pre-audit; выводы согласуются (greenfield-зоны совпали)
---

# Pre-audit: готовые OSS-ассеты под компоненты Artifex

Компоненты: C1 supervisor-loop над `claude -p` · C2 прогресс/thrash-детект · C3 policy-движок
permissions · C4 эскалация-боты (TG+MAX, блокирующий Q&A) · C5 пер-плановый журнал/атрибуция
сессий · C6 упаковка/раскатка скиллов.

## Что экосистема ПОКРЫВАЕТ (кандидаты ADOPT/ADAPT)

- **planning-with-files** — конвенции handoff/plan-файлов, plan-identity (SHA-attest),
  stop/complete-хуки → кандидат для сверки с нашим контрактом P0.2/P1.
- **steveyegge/beads** — структурный граф задач + audit-trail журнал → кандидат-референс
  для схемы журнала P1.1.
- **claude-task-master** — task-graph JSON-схема, `next`-выбор задачи → ADAPT-паттерн
  для очереди драйвера P2.2.
- **claude-code-router (CCR)** — Telegram-релей/эскалация → референс P4.1/P4.3.
- **ponytail** — скелет hook-wiring (PreToolUse) → каркас P3.2.
- **superpowers** — формат плагина/marketplace → референс раскатки P6.1 (сверить с нашим
  skiller/agent-packs — у нас своё уже есть).

## Что экосистема НЕ покрывает (build-from-scratch подтверждён, ~1050 LOC суммарно)

1. **C1 supervisor-loop** (spawn/parse/retry state machine) — нет ни у кого → P2 строим сами. ✅ наш план
2. **C2 thrash-детект** (N итераций без дельты → STALL) — нет реализаций → P5 строим сами. ✅
3. **C3 policy-движок** (YAML allowlist → permissionDecision) — как standalone нет → P3.2. ✅
4. **C4 MAX-адаптер** — нулевое покрытие в экосистеме → P4 строим сами. ✅ (RAG-вердикт D12)
5. **C5 парсер session→plan атрибуции** — нет → P1/P2. ✅

Вывод: направление плана подтверждено — конвенционный слой и TG частично переиспользуемы,
процесс-супервизорный слой и MAX — честный greenfield. Финальные ADOPT/ADAPT-вердикты —
после полного аудита владельца.
