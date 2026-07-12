# HANDOFF — 2026-07-12 — after P7.1

**Next:** /task:plan-exec 2026.07.12-CONTEXT-ECONOMY P7.2 (или Workflow — см. ниже)

| Параметр | Значение |
|:--|:--|
| Model | sonnet/medium (дефолт SSOT) |
| Thinking | medium |
| Context | fresh session, корень репо swissknifeman |
| Суть | P7.2 манифест проектов + доки + roadmap-стаб памяти (1 item, blast radius 0 — только этот репо) — гейта нет |

Основной путь (D14) — общий workflow-исполнитель с per-item роутингом моделей
(автономно P7 остаток, стоп перед Owner-гейтами P6/P8; запуск строго scriptPath;
SLICES скрипта уже обрезан до P7.2 — P7.1 закрыт вне очереди):

````
Workflow({scriptPath: "plans/2026.07.12-CONTEXT-ECONOMY/workflows/wf-context-economy-exec.js"})
````

Альтернатива — поштучно:

````
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P7.2 — ТЗ: plans/2026.07.12-CONTEXT-ECONOMY/phases/P7.md
````

**Done:** P1 (3/3 🟢) — digest-бюджет, тихий health-хук, гайдлайн межпроектной памяти.
P2 (1/1 🟢) — policy config.json agent-router сжат до 1186 симв ≈296 ток. P3 (2/2 🟢) — рэтчет
описаний скиллов. P4 (2/2 🟢) — диета `description` 44 агентов + регрессионный cap-тест +
`.bak`-warn в doctor. **P5 закрыта целиком (3/4 🟠 Done with deviations):** P5.1
`skiller budget --first-turn`; P5.2 `maind doctor --context`; P5.3 `analyst sessions` +
run-report usage-блок; P5.4 закрыта ⛔ Skipped by decision (D7) — спека `roadmap/otel-preset.md`.
**P7.1 закрыт (фаза P7 1/2 🟡):** `scripts/bootstrap-machine.sh` — тонкий оркестратор, 6 ступеней
(install.sh пакетов+симлинк → `harness hooks --global` → `harness permissions --global` →
MCP-пресеты (soft-skip — у harness/maind нет `--global`-механизма для MCP, per-project остаётся) →
`maind service install` (мягкая деградация без systemd) → `swissknifeman doctor`); роут
`bin/swissknifeman setup --machine [--dry-run] [--skip-projects] [--bin-dir DIR]` (делегирует
exec в скрипт). `scripts/test-bootstrap-machine.sh` — 8 smoke-проверок (bash -n, --help,
неизвестный флаг, --dry-run не пишет файлов в изолированном HOME, --skip-projects, роут делегирует)
— все зелёные. **Гейт двойного прогона выполнен реально** (не только --dry-run): контейнер
`python:3.12-slim`, repo смонтирован `-v ...:/repo:ro`, `HOME=/root` — RUN1 и RUN2 подряд, оба
rc=0, второй прогон идемпотентен (симлинки идентичны, `.claude/settings.json` мержится с ожидаемым
`.bak`-бэкапом, systemd/Node-степени мягко деградируют одинаково оба раза); лог — Completion Notes
P7.1 (phases/P7.md) + воспроизводящая команда там же. `bash -n` OK; `packages/maind/scripts/
validate.sh` — 415 тестов OK (регрессий нет). Найден (не исправлен, вне scope P7.1 — эскалирован)
дефект `packages/harness/scripts/apply-permissions.sh:57`: `mkdir -p .../auto-approve` выполняется
ДО проверки `$DRY_RUN` — `harness hooks --global --dry-run` создаёт пустой каталог на диске вопреки
контракту dry-run (bootstrap-machine.sh корректно форвардит флаг, сам ничего лишнего не пишет).

**Remaining:** P6 rollout+замер (4 items, ~17 живых проектов флота — Owner ведёт пошагово вместе
с исполнителем, НЕ фоновым workflow: P6.2 явно требует «Brain первым, подтверждение успеха перед
продолжением», P6.3 требует `AskUserQuestion` per-project) · P7.2 манифест проектов + доки +
roadmap-стаб памяти (1, автономно, blast radius 0) · P8 доктрина+скиллы/доки+релиз v0.9.0 (5;
P8.1–P8.3,P8.5 автономно, P8.4 — approve Owner на тег, не автоматизировать). Workflow-скрипт
покрывает P7.2 (P7.1 закрыт вне очереди — при следующем запуске сверить кэш/resumeFromRunId,
возможно потребуется отметить P7.1 done в скрипте); P6 и P8 — с человеком, пошагово, по явному
решению Owner 2026-07-12.

**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D16) · phases/P1.md–P8.md
(P7.1 Completion Notes с логом двойного прогона в phases/P7.md) ·
findings/P0-rag-context-economy.md · findings/P0-rag-bootstrap-memory-sync.md ·
docs/rejected-optimizations.md (сверяться перед повторным изобретением отклонённых идей).

**Open risks:** P6 меняет ~17 проектов — сбой волны >3 проектов = стоп+эскалация (в P6.2);
Owner решил вести P6/P8.4 пошагово вживую, не через фоновый Workflow (2026-07-12); harness
`apply-permissions.sh:57` dry-run mkdir-до-гейта дефект (P7.1 Escalation Needed) не заведён
отдельным item'ом — сделать это при следующем заходе в harness или явным follow-up item.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: OTEL-пресет (D7, закрыт ⛔, roadmap/otel-preset.md) · межкомпьютерная память
  (D12 — roadmap/cross-machine-memory.md пишется в P7.2) · манифест проектов + docs-страница
  развёртывания (P7.2, не реализовано в P7.1 — bootstrap-machine.sh --skip-projects сейчас
  всегда no-op с явной NOTE) · burn-down `desc-burndown.txt` (64 скилла, из P3) — легальный
  неразрешённый долг, сокращать по мере правок конкретных скиллов · KNOWN_MCP_TOOLS в budget.py —
  инженерная прикидка, пересмотреть при живом расхождении · encode_cwd в `analyst/sessions.py` —
  `.`/`_` внутри сегментов пути не перепроверено на живых каталогах, см. Escalation Needed P5.3 ·
  `harness/scripts/apply-permissions.sh:57` dry-run mkdir-до-гейта — найден в P7.1, не исправлен
  (вне Files item'а), нужен follow-up фикс в harness
- open_questions: —
