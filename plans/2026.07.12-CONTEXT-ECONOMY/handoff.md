# HANDOFF — 2026-07-12 — after P1.2

**Next:** /task:plan-exec 2026.07.12-CONTEXT-ECONOMY P1.3

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | fresh session, корень репо swissknifeman |
| Суть | P1.3 (гайдлайн межпроектной памяти: скиллы + доки) — ГЕЙТ: P1.1 закрыт (выполнено) |

Основной путь (D14) — общий workflow-исполнитель с per-item роутингом моделей
(автономно P1→P5+P7, стоп перед Owner-гейтами P6/P8; запуск строго scriptPath):

````
Workflow({scriptPath: "plans/2026.07.12-CONTEXT-ECONOMY/workflows/wf-context-economy-exec.js"})
````

Альтернатива — поштучно:

````
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P1.3 — ТЗ: plans/2026.07.12-CONTEXT-ECONOMY/phases/P1.md; нормы: findings/P0-rag-context-economy.md
````

**Done:** P1.1 (digest-бюджет) — `select_digest_items` в packages/maind/lib/maind/memory.py
(чистая функция, байт-бюджет 4000/item_max 500/shared_max=0 project-only, D10) + 4 константы
в constants.py + config-дефолты `memory.digest` в config.py + 3 CLI-флага
(`--budget-chars --item-max --shared-max`) + 9 новых тестов (7 TestDigestSelection +
2 config-дефолтов/override); `bash packages/maind/scripts/validate.sh` → 397 тестов OK.
P1.2 (шаблоны хуков) — session-start-hook.sh переведён на `health --cwd --strict`: rc=0 →
тихий `exit 0` (ничего в additionalContext), rc≠0 → печать stdout, затем `exit 0`
(хук-безопасность сохранена); memory-digest-hook.sh — бамп-комментарий шапки (v2/P1.2,
byte-change → stale для `maind sync`), вызов остался argless. 5 новых тестов в
packages/maind/tests/test_health.py (`TestSessionStartHookTemplate`: статика --strict+rc-гейт,
тихий stdout при fake-maind rc=0, печать статуса при rc=1, тихий no-op без maind в PATH;
`TestMemoryDigestHookTemplate`: маркер бампа шапки + argless-вызов); `validate.sh` → 402 тестов OK.
**Remaining:** 7 фаз / 20 items ⬜, P1 — 2/3 🟡 (P1.3 гайдлайн памяти) · P2 router v2 (1) ·
P3 описания скиллов (2, порядок P3.1→P3.2) · P4 agent-packs (2) · P5 footprint+телеметрия (4) ·
P6 rollout+замер (4, baseline ДО раскатки, Owner-гейты) · P7 bootstrap машины (2) ·
P8 доктрина+скиллы/доки+релиз v0.9.0 (4). Роутинг-отклонения: P2.1 — fable/opus (семантика
policy), P6.3 — AskUserQuestion per-project, P8.4 — approve Owner на тег. Workflow покрывает
P1→P5+P7; P6 и P8 — с человеком.
**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D14: D4 router сжать ·
D6 описания+бакеты · D9 версии/тег · D10 digest project-only, supersede D5 · D12 память между
машинами → roadmap) · phases/P1.md–P8.md · findings/P0-rag-context-economy.md (нормы бюджетов,
OTEL, декомпозиция инцидента) · findings/P0-rag-bootstrap-memory-sync.md (bootstrap-паттерн,
запрет shared-папки для стора) · scratchpad сессии 4af788f3 (analyze_sessions.py — референс,
переносится в analyst в P5.3).
**Open risks:** живой прогон SessionStart-хуков в P5.1 исполняет чужие скрипты — обязателен
fail-soft/timeout (в ТЗ); P6 меняет ~17 проектов — сбой волны >3 проектов = стоп+эскалация
(в P6.2); encoded-cwd формат jsonl-каталогов в P5.3 проверить на живых каталогах, не угадывать.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: OTEL-пресет P5.4 (D7 — допустим ⛔ Skipped с roadmap-стабом) · межкомпьютерная
  память (D12 — roadmap/cross-machine-memory.md пишется в P7.2)
- open_questions: —
