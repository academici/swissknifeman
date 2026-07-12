# HANDOFF — 2026-07-12 — after P7.2 (P7 закрыта целиком)

**Next:** P6 (rollout+замер, с человеком пошагово) или P8 (доктрина+релиз v0.9.0) — оба требуют
Owner в цикле (см. Remaining); автономных items в плане не осталось.

| Параметр | Значение |
|:--|:--|
| Model | sonnet/medium (дефолт SSOT) для P6/P8 автономных items; P8.4 — approve Owner, не автоматизировать |
| Thinking | medium |
| Context | fresh session, корень репо swissknifeman |
| Суть | P7 закрыт полностью (2/2 🟢); дальше только P6 (флот, живые сессии, AskUserQuestion per-project) и P8 (5 items, P8.4 — тег релиза approve Owner) |

Workflow-скрипт `wf-context-economy-exec.js` покрывал P1→P5+P7 автономно и останавливался перед
Owner-гейтами P6/P8 (D14) — этот контракт исчерпан, дальше по плану строго с Owner в цикле;
не запускать Workflow на P6/P8 без явного нового решения Owner.

Поштучно (когда Owner даст добро на конкретный item P6/P8):

````
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P6.1 — ТЗ: plans/2026.07.12-CONTEXT-ECONOMY/phases/P6.md
````

**Done:** P1 (3/3 🟢) — digest-бюджет, тихий health-хук, гайдлайн межпроектной памяти.
P2 (1/1 🟢) — policy config.json agent-router сжат до 1186 симв ≈296 ток. P3 (2/2 🟢) — рэтчет
описаний скиллов. P4 (2/2 🟢) — диета `description` 44 агентов + регрессионный cap-тест +
`.bak`-warn в doctor. **P5 закрыта целиком (3/4 🟠 Done with deviations):** P5.1
`skiller budget --first-turn`; P5.2 `maind doctor --context`; P5.3 `analyst sessions` +
run-report usage-блок; P5.4 закрыта ⛔ Skipped by decision (D7) — спека `roadmap/otel-preset.md`.
**P7 закрыта целиком (2/2 🟢):** `scripts/bootstrap-machine.sh` — тонкий оркестратор, 7 ступеней
(install.sh пакетов+симлинк → `harness hooks --global` → `harness permissions --global` →
MCP-пресеты (soft-skip — у harness/maind нет `--global`-механизма для MCP, per-project остаётся) →
`maind service install` (мягкая деградация без systemd) → `swissknifeman doctor` → **манифест
проектов** `--projects FILE`: clone отсутствующих + `swissknifeman setup <path>`, уже клонированные
НЕ pull'ятся, только повторный onboard, идемпотентно); роут `bin/swissknifeman setup --machine
[--dry-run] [--skip-projects] [--projects FILE] [--bin-dir DIR]`. Доки:
`docs/deploy.md` (сценарии «новая машина»/«команда», в sidebar), `docs/machine-manifest.example.json`
(схема с плейсхолдерами). `roadmap/cross-machine-memory.md` — D12 закрыт: явный запрет
shared-папки для `state_store.db` + 2 безопасных варианта (демон-хост через Tailscale/LAN;
export/import событий) + критерий активации. `scripts/test-bootstrap-machine.sh` — 16
smoke-проверок (было 8 после P7.1, +6 манифест-проверок P7.2 + невалидный-манифест кейс), все
зелёные; **гейт двойного прогона выполнен реально** дважды: P7.1 — контейнер `python:3.12-slim`
(install.sh/hooks/permissions/doctor, лог в Completion Notes P7.1); P7.2 — реальный `git clone`
+ полный `swissknifeman setup` на локальном git-фикстуре (без сети), RUN2 подтверждённо не
клонирует повторно и не делает pull (git-история клона не изменилась), только повторный
идемпотентный onboard. `bash -n` OK; `npx vitepress build docs` зелёный (страница `/deploy`
собралась, dead-links нет). Найден в P7.1 (не исправлен там, исправлен post-review фиксом того
же item'а — см. Update Log plan.md) дефект `apply-permissions.sh:57` — уже пофикшен, закрыт.

**Remaining:** P6 rollout+замер (4 items, ~17 живых проектов флота — Owner ведёт пошагово вместе
с исполнителем, НЕ фоновым workflow: P6.2 явно требует «Brain первым, подтверждение успеха перед
продолжением», P6.3 требует `AskUserQuestion` per-project) · P8 доктрина+скиллы/доки+релиз v0.9.0
(5 items; P8.1–P8.3,P8.5 автономно, P8.4 — approve Owner на тег, не автоматизировать). P7 закрыт
полностью — Workflow-скрипт `wf-context-economy-exec.js` исчерпал свой автономный контракт (D14),
дальше в плане нет items без Owner в цикле.

**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D16) · phases/P1.md–P8.md
(P7 Completion Notes с логами двойного прогона P7.1+P7.2 в phases/P7.md) ·
findings/P0-rag-context-economy.md · findings/P0-rag-bootstrap-memory-sync.md ·
docs/rejected-optimizations.md (сверяться перед повторным изобретением отклонённых идей) ·
roadmap/cross-machine-memory.md (D12, новый — межкомпьютерная память).

**Open risks:** P6 меняет ~17 проектов — сбой волны >3 проектов = стоп+эскалация (в P6.2);
Owner решил вести P6/P8.4 пошагово вживую, не через фоновый Workflow (2026-07-12).

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: OTEL-пресет (D7, закрыт ⛔, roadmap/otel-preset.md) · межкомпьютерная память
  (D12, закрыт — roadmap/cross-machine-memory.md написан в P7.2, реализация НЕ входит в релиз,
  критерий активации — появление второй постоянной машины/команды) · манифест `profile`-поле —
  принимается схемой, но не форвардится в `maind onboard` CLI (нет такого флага; см. Known
  Deviations P7.2 phases/P7.md) · burn-down `desc-burndown.txt` (64 скилла, из P3) — легальный
  неразрешённый долг, сокращать по мере правок конкретных скиллов · KNOWN_MCP_TOOLS в budget.py —
  инженерная прикидка, пересмотреть при живом расхождении · encode_cwd в `analyst/sessions.py` —
  `.`/`_` внутри сегментов пути не перепроверено на живых каталогах, см. Escalation Needed P5.3
- open_questions: —
