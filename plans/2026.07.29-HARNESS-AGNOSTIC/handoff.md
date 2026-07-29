# HANDOFF — 2026-07-29 — after P0.1

**Next:** «ЗАПУСК ВРУЧНУЮ: frontier/high»

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P0.2 — перенос посекционных вердиктов входящего аудита в постоянные носители репо (`docs/reference.md`, `docs/rejected-optimizations.md`, `roadmap/codex-publication-consumer-acceptance.md`) + удаление пустого `audits/`. §3 Routing: `frontier/high` + `Exec = manual` (адъюдикация внешнего входа — design-решение, `/task:plan-exec` его отклонит по гейту п.2) |

````
Исполни item P0.2 плана 2026.07.29-HARNESS-AGNOSTIC вручную (Exec=manual, эта сессия
НЕ /task:plan-exec — та пинит sonnet/medium и по Routing-гейту отклонит P0.2).

Порядок чтения (ровно этот, без повторов):
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — §0 Meta, §1 Context, §2 Execution Rules,
   §3 Routing (строка P0.2), §4 Status Board
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P0.md — Phase Context + P0.2 целиком
4) Required Reads item'а P0.2 (в указанном там порядке):
   research/01-audit-adjudication.md · findings/01-rag-cross-harness-2026-07-29.md §Ф3/§Ф4 ·
   docs/reference.md (шапка + сводная таблица + карточка wshobson/agents) ·
   docs/rejected-optimizations.md (шапка «Правило» + формат 4 колонок) ·
   roadmap/README.md + roadmap/codex-publication-consumer-acceptance.md

Дом плана — repo:/home/vostrikov/projects/packages/swissknifeman, но по Execution Rules
(§2) все работы ведутся в worktree swissknifeman-next (ветка next/harness-agnostic) —
запускай эту сессию именно там.

Перед мутацией и перед закрытием собери Task Contract (task.task_contract.build +
route_evidence.capture_actual("design", "high", source="self-attested", model="opus")
— actual_route ЭТОЙ сессии) и убедись, что pre_mutation/pre_final = "allow"; красный код —
см. таблицу в packages/task/commands/plan-exec.md п.2/п.7 (эскалация или D#-запись по классу).

Исполняй СТРОГО Scope Included P0.2 (см. phases/P0.md), не трогай Scope Excluded.
Пометь Status: 🟡 In progress (item + Phase Status) до работы, journal.append --result
in-progress перед началом.

По завершении: прогони ВСЮ Validation P0.2 построчно, закрой item по топологии
plan-protocol §7 (item-коммит по Files P0.2 → bookkeeping плана → перезапись handoff.md →
plan-lint --baseline HEAD → bookkeeping-коммит), обнови Status Board/Update Log/Last
Updated, append журнал финал-записи (--result closed-green|closed-deviations).
Статус 🟢 при чистом закрытии, 🟠 Done with deviations — если Validation осталась
красной вне скоупа или Scope выполнен не полностью (запись в Known Deviations
обязательна). Заметил конфликт правил / неясный acceptance / чужой замороженный
контракт под вопросом — эскалируй (plan-protocol §8), не импровизируй.

Дай отчёт в формате Expected Output plan-exec (Status/Completed/Pending Work/Files
Changed/Commits/Validation/Lint/Известные отклонения/Escalation Needed/Launch-block
следующего шага — P0.3).
````

**Done:** **P0.1 закрыт** (`plan-exec`/Sonnet/medium) — процедура изоляции worktree.
Написан `root/isolation-procedure.md` (187 строк, коммит `1dcdd8e2`): создание второго
git-дерева (уже существовало фактически) · установка CLI-контура `./install.sh --bin-dir
~/.local/bin-skm-next` из `swissknifeman-next` · активация только префиксом PATH (без
записи в rc-файлы) · снятие/откат (справочно, не выполнялось) · раздел «Общие
поверхности» (`~/.swissknifeman/{topology,projects}.json`, `~/.maind/**`, `.mcp.json`
онбордженных). Чек «старый контур цел» — четыре проверки, все зелёные, ДО/ПОСЛЕ
одинаково: резолв 5 симлинков `~/.local/bin` не сдвинулся (основное дерево
`swissknifeman`); резолв `~/.local/bin-skm-next` — внутрь worktree; `which swissknifeman`
без префикса PATH — старый контур; `swissknifeman doctor` через старый контур —
идентичный вердикт (`harness: OK`, 2 warn maind 18/5, «Все проверки пройдены»,
«Окружение готово»); mtime общих поверхностей не сдвинулись (до сегодняшней даты).
`plan-lint` — 0 ERROR / 0 WARN на закоммиченном дереве.

**Ранее (design, три прогона + три `finish` по аудиту):** см. предыдущую запись этого
файла в истории коммитов (`git log -p -- plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md`)
и `plan.md` §6 Update Log строки design pass 1–3 + три блока `## Audit design`.
`AUDIT-CAP` исчерпан заходом 3 (вердикт ATTENTION, все находки закрыты D68–D70) —
повторный design-аудит не назначается.

**Remaining:** P0.2–P0.5 (фаза P0, 1/5 закрыто) → P1 (5) → P2 (5) → P3 (6) → P4 (5) →
P5 (3). Итого 28/29 items ещё не исполнено.

**Sources of truth:** `plans/2026.07.29-HARNESS-AGNOSTIC/plan.md` (§3 Routing после D47,
§5 D1–D70, §7 Contracts, § Обсуждение 1–7, три блока `## Audit design`) ·
`phases/P0.md`–`P5.md` (все шесть детализированы, DoR-свип пройден; P0.1 закрыт) ·
`roadmap.md` · `brief/00-brief.md` + `brief/01-refinements.md` (М1–М12, Р1–Р6) ·
`findings/01`–`findings/06` · `research/00`, `01`, `02`, `04`, `06`, `07`, `08`, `09` ·
`open-questions.md` (OQ-2, OQ-3, OQ-5–OQ-9) · `index.md` (карта слоёв и внешних входов) ·
`journal.jsonl` (история запусков) · `plans/archive/2026.07.25-ECO-OPT/` (вход по D52) ·
`root/isolation-procedure.md` (новый, P0.1) · `plans/2026.07.18-FOREMAN/` (донор,
поглощается P0.3/P0.5)

**Open risks:**
- **Аудит исчерпан, страховки «ещё один заход» больше нет.** Дефект, не найденный тремя
  design-заходами, всплывёт уже на исполнении — цена ошибки в ТЗ перекладывается на
  exec-сессии.
- **Дисциплина «новая Validation обязана быть прогнана».** Машинного гейта нет —
  PROMOTE-CANDIDATE аудита (дом кандидата `roadmap/`, не этот план).
- **Правило design-коммита (D69) машинного гейта не имеет** — следующий design-заход
  (если понадобится) обязан соблюсти его сам.
- **`plans/2026.07.18-FOREMAN/plan.md` тронут дважды** — design-коммитом (`Paused By`) и
  предстоящим item'ом P0.3; исполнитель P0.3 читает файл в закоммиченном виде, «чистого»
  донора не ждёт.
- **Маршруты стали мягче.** Девять items ушли из жёстко-гейтованного `plan-exec` в
  `plan-run` (D47) — строка `Session: <model>/<effort>` в отчёте и Update Log каждого
  такого item'а обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем
  (D4); **P0.1 подтвердил гейт «старый контур цел» (R3) зелёным** — проверка «пережил
  волну» остаётся за P5.3.
- **P5.2 — единственная необратимая внутрь граница плана**: merge меняет живой инструмент
  25 онбордженных проектов в момент коммита; якорь отката фиксируется ДО, смоук — сразу
  после, грязное дерево или конфликт = СТОП+эскалация (R1).
- **Локальный прогон гейтов ≠ CI**: матрица python 3.9–3.13 и ruff-пин runner'а локально
  не воспроизводятся; формулировка «CI зелёный» в отчёте P5.1 запрещена (R2).
- **CI не зовёт `validate.sh` пакетов `analyst` и `task`** (OQ-9) — плановая дисциплина не
  проверяется на PR; компенсация только локальная.
- **Три items правят один файл `packages/harness/scripts/validate.sh` со сплошной
  перенумерацией** (P1.5 `[9/9]`, P4.3 `[10/10]`) — порядок фаз обязателен, фактический
  знаменатель снимается прогоном перед правкой, а не берётся из ТЗ (D48).
- **Порядок двух коммитов P1.5 — «принятие → гейт» (D66)**: обратный порядок оставляет в
  ветке промежуточный коммит с заведомо красным `validate.sh` и ломает бисект.
- **Точка принуждения `delegation_contract` живёт в состоянии `pending` между P4.3 и P4.4**
  (D58): зелёный `--check` на этом отрезке НЕ является доказательством приземления
  контракта.
- **Переадресация читателей `CLAUDE.md` — единственный мост между P1 и ТЗ фаз P2–P5**
  (D60, гейт полноты D65/D68): если раздел P1.1 выйдет неполным, исполнители
  P2.2/P2.3/P3.1/P3.2/P3.3/P3.5/P3.6/P4.3/P5.1 получат мёртвые адреса.
- **Релизная запись появляется только на P5.1** (D55): пакетных `CHANGELOG.md` у
  `harness`/`skiller` в дереве нет и план их не заводит.
- P1.5 — единственная живая транзакция фазы P1 (always-on контекст всего репо); откат
  опирается на pre-image, записанный ДО мутации.
- **P2.3 — единственный item, чей дефект блокирует оператора ложным отказом**
  (инвертированная семантика `block` у `Stop`/`SubagentStop` в Codex).
- Уровень манифеста и реализация неразделимы (`HARNESS_CAPABILITY_MANIFEST_INVALID`):
  P2.2–P2.4 правят каталог синхронно со своим кодом.
- **P3.5 растит листинг, который меряет P3.4** (39 коротких описаний удлиняются): дельта
  обязана быть измерена обоими провайдерами и записана (D52).
- **P3.3: гейт, который никогда не краснел, не доказан** — негативный прогон обязателен;
  **P3.6** зависит от перечня P1.1; **P3.2** не стартует до закрытой P1.5 (D51/D67).
- **P4.4 правит канон ролей, раздаваемый флоту**, и ложится в ДВА носителя без гейта
  сверки (D35, OQ-8); **P4.5 зависит от чужого замера** P0.3, вариант B эскалируется (D37).
- Контракты `2026.07.24-AGENT-RELIABILITY`, на которых стоит P4, произведены планом,
  закрытым `🟠` с формально невыполненной приёмкой — P4.1 обязана пометить недоказанное
  `[UNVERIFIED]`.
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — правило действует на P5.1–P5.3, носитель таких
  путей у P0.1 — уже произведённый `root/isolation-procedure.md`.

**Workarounds/Deferred/Open questions:**
- workarounds: **правка общего перечня `plans/verify-citations-known-exceptions.json`**
  (D54) — файл вне каталога плана, тронутый дизайном; его дом — design-коммит (D69), не
  `Files` какого-либо item'а.
- deferred: изоляция общего state (OQ-5) · round-trip гейт с живым прогоном Codex (Р3) ·
  структурный перебор листинга на стороне Codex (OQ-7 → `roadmap/`, D29 в редакции D52) ·
  перекалибровка токенайзера `budget.py` (чужой ECO-OPT P3.4, в наш скоуп не втягивается) ·
  постройка тонкой обвязки супервизора (D38 → `roadmap/artifex-thin-wrapper.md`) · общий
  differ «канон ↔ инсталляционный шаблон» ролей (OQ-8 → `roadmap/`, D35) · машинный гейт
  «новая Validation прогнана» (PROMOTE-CANDIDATE, дом `roadmap/`) · машинный гейт
  «design-заход оставил состояние в истории» (PROMOTE-CANDIDATE D69, дом `plan-protocol`) ·
  перевод прозы «кап делегирования» в командах `task:*` на ссылку к SSOT политики ·
  раскатка на потребителей: скиллы connect-канала, vendor-копии, agent-packs, `harness
  instructions` на чужих целях (D45) · push/PR/тег и публикация доков (D41) · расширение CI
  на `analyst`/`task` (OQ-9) · отдельный русский канон скиллов в `.gitignore` (Р5, вне
  плана).
- open_questions: OQ-2 судьба parse-контракта (замер в P0.3, исполнитель P4.5) · OQ-3 две
  capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики Codex-обработчиков
  (P2.1) · OQ-7 структурный перебор бюджета обнаружения на стороне Codex (замер P3.4 →
  `roadmap/`, D52) · OQ-8 дрейф канона ролей и инсталляционного шаблона (Deferred) ·
  OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-1 закрыта D31, OQ-4 закрыта D27.
