# HANDOFF — 2026-07-25 — after P2

Design pass 2/2, шаг 1 из 7: фаза **P2 детализирована до DoR** (скелет-маркер снят,
2→3 items). Исполнение плана НЕ начато. ACTIVE — этот план (D13, этап A программы).

**Next:** design-phase: task:plan-design 2026.07.25-ECO-OPT P3

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | cold-start — plan-step |
| Суть | Детализация скелет-фазы P3 (перенос TOKEN-ECON: замер N + сжатие описаний, maind-тримминг, owner-решения) |

````
/task:plan-design 2026.07.25-ECO-OPT P3

РЕЖИМ: детализация скелет-фазы (P3 несёт скелет-маркер, терминальных items нет — это НЕ реопен)
ВХОД: plans/2026.07.25-ECO-OPT/phases/P3.md (контракт-блок) → plan.md (§3 Routing, D1–D18, Обсуждение 1–9) → plans/archive/2026.07.15-TOKEN-ECON-P6/{plan.md,handoff.md,findings/} (P3 — перенос его P7/P8/P9) → brief/00-brief.md идеи 8–9
СКОУП: 0) ПЕРВЫМ ШАГОМ перечислить внешние факт-классы фазы и только потом искать (D20 — узкий RAG проходит DoR-гейт незамеченным); 1) развернуть 3 items по 16-полевой схеме против контракт-блока; 2) reconcile Потребляет↔Производит (P3.1 ждёт терминальную P1 AGENT-RELIABILITY — D11); 3) снять коллизию «OQ-4/OQ-5» → это открытые вопросы плана 2026.07.15-TELEMETRY-OPT, не этого (D17); 4) учесть D19: пороги budget --first-turn на прежнем токенайзере — перекалибровка кандидат сюда; 5) DoR-чеклист фазы
НЕ ТРОГАТЬ: закрытые D1–D18; brief; findings/research (слои 1–2 не переписываются); фазу P2 (детализирована); канон plan-protocol (cross-plan gate)
````

**Done:** Design pass 1/2 целиком (brief, RAG-финдинги, 7 фаз/17 items, P1
детализирована, D1–D13). Pass 2/2 шаг 1: **P2** — слой 1
`findings/P2-opus5-guide.md` (гайд Opus 5 + док `build-with-claude/effort`) и
`findings/P2-claude5-family-and-migration.md` (гайд Sonnet 5, кросс-модельный
`claude-prompting-best-practices`, перплексити-синтез полевой практики миграции —
с явным статусом каждого утверждения), слой 2 `research/01-P2-opus5-revision-map.md`
(правило A/B/C, инвентарь на якоре `eee7dc6f`, разбиение по гейту; несёт ПОПРАВКУ
второго захода) и `research/02-P2-rag-coverage-postmortem.md` (почему первый заход
сузил рамку). `phases/P2.md` на 3 items, D14–D20, развилки 8–9, Routing построчно,
OQ-4 уточнён, контракт-блок P6 дополнен входом от D20.

**Remaining:** pass 2/2: детализация **P3 → P4 → P5 → P6 → P7** (по фазе на заход,
новая сессия) → `finish` (сквозной reconcile + DoR-свип + `roadmap.md`, k→2/2) →
`/task:plan-audit <ID> design` → exec по очереди D10/D11.
Задачи, сознательно отложенные до `finish` (не дыры фазы, а свип-работа):
(1) решить, нужна ли плану секция `## 7. Contracts` — P2.3 назван зависимым от
контрактов `execution-state-machine-v1`/`risk-review-loop-budget-v1` плана
AGENT-RELIABILITY, но пинить их версию сейчас нельзя (фаза-производитель не начата),
а фальшивый `Pinned` хуже отсутствия строки; (2) `index.md` (WARN `plan-lint`) —
собрать, когда слои 1–2 перестанут расти; (3) числовая неточность в прозе Meta
`Design Passes` («16 items» при фактических 18).

**Sources of truth:** `plan.md` (§2 Execution Rules — cross-plan гейты, §3 Routing,
§5 D1–D20, Обсуждение 1–9) · `phases/P1.md`, `phases/P2.md` (детализированы) ·
`phases/P3–P7.md` (скелеты с контракт-блоками) · `brief/00-brief.md` ·
`findings/{rag-2026-07-25.md,rag-2026-07-25-raytsystem.md,P2-opus5-guide.md,P2-claude5-family-and-migration.md}` ·
`research/{01-P2-opus5-revision-map.md,02-P2-rag-coverage-postmortem.md}` ·
`open-questions.md`.

**Open risks:** cross-plan hotspot остаётся, но сузился — под гейт AGENT-RELIABILITY
P2 попадают P2.3/P7.1 (не P2.2, D14); ревизия под Claude 5 несёт риск ложного класса A
(снос доменного чеклиста или RAG-строки) — контрится правилом D15/D19 и Code Guidance
items; effort-пины не трогаются без замера (D16) — экономия отложена, не потеряна;
пороги `skiller budget --first-turn` откалиброваны по прежнему токенайзеру (D19) —
абсолютные вердикты «в бюджете» до перекалибровки некорректны (кандидат P3.1);
**процессный риск, подтверждённый на этом же заходе (D20): узкий-но-глубокий RAG
проходит DoR-гейт, потому что гейт проверяет форму маркеров, а не полноту множества
внешних фактов фазы** — при детализации P3–P7 сначала перечислять факт-классы фазы,
потом искать; Meta `Design Passes` в прозе всё ещё говорит «16 items» (фактически 18)
— снимается при `finish`.

**Workarounds/Deferred/Open questions:**
- workarounds: —;
- deferred: исполнение всех фаз (design-first, D13); замер effort-sweep для пинов
  (D16 — кандидат в roadmap);
- open_questions: OQ-1 (код-граф), OQ-2 (роль Codex), OQ-3 (дом notify), OQ-4
  (raytsystem — адресат P7.2, P2 его не берёт, D17).
