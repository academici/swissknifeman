# HANDOFF — 2026-07-12 — after P3.2

**Next:** /task:plan-exec 2026.07.12-CONTEXT-ECONOMY P4.1

| Параметр | Значение |
|:--|:--|
| Model | sonnet/medium (дефолт SSOT — P4 без роутинг-отклонений) |
| Thinking | medium |
| Context | fresh session, корень репо swissknifeman |
| Суть | P4.1 (agent-packs: диета описаний субагентов, все 10 паков + бамп версий) — ГЕЙТ: нет (P3 закрыта зелёным) |

Основной путь (D14) — общий workflow-исполнитель с per-item роутингом моделей
(автономно P1→P5+P7, стоп перед Owner-гейтами P6/P8; запуск строго scriptPath):

````
Workflow({scriptPath: "plans/2026.07.12-CONTEXT-ECONOMY/workflows/wf-context-economy-exec.js"})
````

Альтернатива — поштучно:

````
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P4.1 — ТЗ: plans/2026.07.12-CONTEXT-ECONOMY/phases/P4.md
````

**Done:** P1 (3/3 🟢) — digest-бюджет (`select_digest_items` project-only shared_max=0, D10),
тихий health-хук, гайдлайн межпроектной памяти в скиллах/доках. P2.1 (фаза P2 1/1 🟢) — policy
config.json agent-router сжат до 1186 симв ≈296 ток. **P3 (2/2 🟢)** — рэтчет описаний скиллов
закрыт целиком: P3.1 укоротил худшие 24 описания (мандаторный минимум 0/8 >450 выполнен); P3.2
ужесточил гейт `validate.sh` — `DESC_WARN_MAX` 450→300 (warn), новый `DESC_ERROR_MAX=450` (hard,
без исключений) + burn-down-рэтчет `packages/skiller/scripts/desc-burndown.txt` (bootstrap = 64
скилла, остаток P3.1; ключ `bucket/name` берётся из ПУТИ, не frontmatter — upstream-скиллы часто
без поля `bucket`). Между 300 и 450: скилл в burn-down → warn («унаследованный долг»), вне
burn-down → error («новый долг запрещён» — рэтчет держит новые скиллы <=300). One-way:
протухшая запись burn-down (скилл удалён/переименован или уже ≤300) → warn «убери строку»
(секция 1b validate.sh) — список может только уменьшаться. 4 негативных прогона на HEAD
подтверждены (>450 hard error даже в burn-down; 300–450 вне burn-down → error; 300–450 в
burn-down → warn-only; протухшая запись → warn) + новый `tests/test_desc_burndown_gate.py`
(6 unittest-кейсов, копия validate.sh в tmpdir-реестре, паттерн
`test_validate_upstream_body_path.py`). Итог: `validate.sh` зелёный, exit 0, 372 теста (было 366).
**Remaining:** P4 agent-packs (2, диета описаний субагентов + regression cap-тест) · P5
footprint+телеметрия (4) · P6 rollout+замер (4, baseline ДО раскатки, Owner-гейты; включает
P6.2 resync router-артефакта на машину/флот — D3) · P7 bootstrap машины (2) · P8
доктрина+скиллы/доки+релиз v0.9.0 (4). Роутинг-отклонения: P6.3 — AskUserQuestion per-project,
P8.4 — approve Owner на тег. Workflow покрывает P1→P5+P7; P6 и P8 — с человеком.
**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D14) · phases/P1.md–P8.md
(P3.1/P3.2 Completion Notes — таблицы было→стало + burn-down-механика) ·
findings/P0-rag-context-economy.md (нормы бюджетов) · findings/P0-rag-bootstrap-memory-sync.md ·
scratchpad сессии 4af788f3 (analyze_sessions.py — референс, переносится в analyst в P5.3).
**Open risks:** живой прогон SessionStart-хуков в P5.1 исполняет чужие скрипты — обязателен
fail-soft/timeout (в ТЗ); P6 меняет ~17 проектов — сбой волны >3 проектов = стоп+эскалация
(в P6.2); encoded-cwd формат jsonl-каталогов в P5.3 проверить на живых каталогах, не угадывать;
P4.1 Inputs — замер «до» уже зафиксирован в ТЗ (reviewer 1345B и т.д.), не пересчитывать заново
без причины.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: OTEL-пресет P5.4 (D7 — допустим ⛔ Skipped с roadmap-стабом) · межкомпьютерная
  память (D12 — roadmap/cross-machine-memory.md пишется в P7.2) · burn-down `desc-burndown.txt`
  (64 скилла) — легальный, но неразрешённый долг; сокращать по мере правок конкретных скиллов
  (не отдельный item плана)
- open_questions: —
