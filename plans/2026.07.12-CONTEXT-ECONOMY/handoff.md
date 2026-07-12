# HANDOFF — 2026-07-12 — after P3.1

**Next:** /task:plan-exec 2026.07.12-CONTEXT-ECONOMY P3.2

| Параметр | Значение |
|:--|:--|
| Model | sonnet/medium (дефолт SSOT — P3 без роутинг-отклонений) |
| Thinking | medium |
| Context | fresh session, корень репо swissknifeman |
| Суть | P3.2 (skiller: гейт error>450/warn>300 + burn-down-рэтчет) — ГЕЙТ: нет (P3.1 закрыт зелёным) |

Основной путь (D14) — общий workflow-исполнитель с per-item роутингом моделей
(автономно P1→P5+P7, стоп перед Owner-гейтами P6/P8; запуск строго scriptPath):

````
Workflow({scriptPath: "plans/2026.07.12-CONTEXT-ECONOMY/workflows/wf-context-economy-exec.js"})
````

Альтернатива — поштучно:

````
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P3.2 — ТЗ: plans/2026.07.12-CONTEXT-ECONOMY/phases/P3.md
````

**Done:** P1 (3/3 🟢) — digest-бюджет (`select_digest_items` project-only shared_max=0, D10),
тихий health-хук, гайдлайн межпроектной памяти в скиллах/доках. P2.1 (фаза P2 1/1 🟢) — policy
config.json agent-router сжат до 1186 симв ≈296 ток. P3.1 (фаза P3 1/2 🟡) — мандаторный минимум
выполнен: **0/8** описаний >450 (было 8: research/security/finance/creative/legal/sales/marketing
super-skills + vue-router-best-practices). Дополнительно укорочены (топ хвоста >300..450) ещё 16
скиллов — итого 24 (SKILL.md + SKILL.ru.md зеркало каждого); 3 из 8 мандаторных доведены до ≤300
(research 297, legal 298, marketing 298), остальные 5 остались в 300–401 (плотность триггеров не
позволила сжать без потерь — легально, см. Code Guidance item'а). Полная таблица было→стало —
Completion Notes P3.md/P3.1. Инструментальный контур: `check-translations.sh --stamp` →
`skiller registry` (идемпотентен) → `validate.sh` (366 тестов, +2 новых) →
`skiller budget --check-core --strict` — все зелёные, CORE не задет. Новый тест
`packages/skiller/tests/test_desc_diet.py` — hard-гейт «0 >450» на РЕАЛЬНОМ реестре (не fixtures)
+ non-regression потолок на 8 мандаторных скиллов.
**Remaining:** P3.2 (гейт error>450/warn>300 + `desc-burndown.txt` bootstrap из 64 оставшихся >300
скиллов) · P4 agent-packs (2) · P5 footprint+телеметрия (4) · P6 rollout+замер (4, baseline ДО
раскатки, Owner-гейты; включает P6.2 resync router-артефакта на машину/флот — D3) · P7 bootstrap
машины (2) · P8 доктрина+скиллы/доки+релиз v0.9.0 (4). Роутинг-отклонения: P6.3 — AskUserQuestion
per-project, P8.4 — approve Owner на тег. Workflow покрывает P1→P5+P7; P6 и P8 — с человеком.
**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D14) · phases/P1.md–P8.md
(P3.1 Completion Notes — полная таблица было→стало + список остатка >300) ·
findings/P0-rag-context-economy.md (нормы бюджетов) · findings/P0-rag-bootstrap-memory-sync.md ·
scratchpad сессии 4af788f3 (analyze_sessions.py — референс, переносится в analyst в P5.3).
**Open risks:** живой прогон SessionStart-хуков в P5.1 исполняет чужие скрипты — обязателен
fail-soft/timeout (в ТЗ); P6 меняет ~17 проектов — сбой волны >3 проектов = стоп+эскалация
(в P6.2); encoded-cwd формат jsonl-каталогов в P5.3 проверить на живых каталогах, не угадывать;
P3.2 Inputs требует P3.1 закрытым зелёным (выполнено) — burn-down bootstrap-список фиксирован
списком остатка >300 из Completion Notes P3.1, брать оттуда, не пересчитывать заново.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: OTEL-пресет P5.4 (D7 — допустим ⛔ Skipped с roadmap-стабом) · межкомпьютерная
  память (D12 — roadmap/cross-machine-memory.md пишется в P7.2) · 64 скилла >300 — вход в
  burn-down P3.2 (не мандаторно для P3.1)
- open_questions: —
