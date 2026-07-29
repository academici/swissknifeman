# HANDOFF — 2026-07-29 — after P0.5

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/high

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P1.1 — матрица «правило → дом»: разобрать семь живых руководств (`CLAUDE.md`, `AGENTS.md`, пять пакетных `CLAUDE.md`) на отдельные правила, связать каждое с одним домом (канон/common-секция/provider-extension/скилл/снятие) и закрыть раздел «Переадресация читателей ТЗ» на девять адресов (D60) |

```
Читай, в этом порядке, НИЧЕГО СВЕРХ:
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — Context, Execution Rules, §3 Routing, Status Board
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P1.md — Phase Context + item P1.1 целиком
4) Required Reads item'а P1.1 в указанном порядке

Исполни item P1.1 СТРОГО по его Scope Included/Excluded, Implementation Rules, Code Guidance —
без импровизации при расхождении с деревом (эскалация вместо самостоятельной правки плана).
Прогони Validation item'а целиком, зафиксируй passed/failed. Закрой item штатной топологией
plan-протокола (item-коммит по Files · bookkeeping-коммит плана · перезапись handoff.md ·
plan-lint --baseline HEAD с атрибуцией K) — модель/effort ЭТОЙ сессии (frontier/high), не пин
`plan-exec` (sonnet/medium): Routing item'а требует `Exec = manual`, поэтому `/task:plan-exec` его
отклонит на гейте — закрывай сам, по протоколу plan-close (Pre-mutation/Pre-final Task Contract,
две ветки закрытия 🟢/🟠, Update Log, launch-block следующего шага).
```

**Штатный носитель исполнения** — `task:plan-run` под сессией **frontier/high** (без ритуала
`/model`+`/effort`, если уже в такой сессии), либо `/model opus` + `/effort high` +
`/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P1.1`. Голая slash-команда `/task:plan-exec` СЮДА НЕ
ПОДХОДИТ: она пинит sonnet/medium, а Routing P1.1 требует frontier/high (`Exec = manual`) — гейт
п. 2 `plan-exec` отклонит запуск (`ROUTING-BLOCKED`).

**Done:** **P0 закрыта целиком (4/5 🟢 + 1/5 🟠, фаза → `🟠 Done with deviations`).** P0.5 закрыт
`plan-exec`/Sonnet 5/medium (Routing `implementation/low`, перебор безвреден — process-отклонение
в Known Deviations item'а):
- Донор `2026.07.18-FOREMAN` архивирован конвейером `plan-close archive` (два коммита:
  `e4a9875d` `git mv` → `plans/archive/2026.07.18-FOREMAN`; `c93b952f` bookkeeping + починка ссылок;
  фикс-коммиты по plan-lint `e047340d`/`fc0e5db0` сверх топологии).
- **Починены потребители пути:** `packages/skiller/tests/test_provider_publication_parity.py:156`
  (хардкод → `core.repo.resolve_plan_dir`), `AGENTS.md:24` (путь/факт архивации),
  `roadmap/codex-subagent-offload.md` (проверен — только bare-ID provenance-цитаты, правки не
  нужны).
- **Регистр `plans/README.md` синхронизирован (D61):** статус донора → «архивирован, поглощён
  `2026.07.29-HARNESS-AGNOSTIC` (его D2)»; новая строка `2026.07.29-HARNESS-AGNOSTIC` (`4/29`,
  снимок 2026-07-29); статус `2026.07.25-ECO-OPT` → «терминален, архивирован 2026-07-29».
- `root/contracts/` донора остаются физически в архиве (прецедент `9b1b5fef`) — живых
  markdown-ссылок вне каталогов планов не найдено, переносить в docs нечего.
- **Known Deviation P0.5:** `bash packages/skiller/scripts/validate.sh` красный
  (`ERROR: реестр устарел относительно источников — прогони: skiller registry`) —
  ПРЕДСУЩЕСТВУЮЩИЙ residual, не от диффа item'а (drift `skills.json`/package-architecture
  SKILL-проекций/`publication-lock.json`/`budget.md`, последний виновный коммит `609ab63b` и
  старше); статус item'а `🟠` вместо `🟢` по status-rule (Validation осталась красной). Фикс —
  `skiller registry` отдельным item'ом/коммитом, вне Scope P0.5.
- `plan-lint`: оба плана 0 ERROR (`plans/2026.07.29-HARNESS-AGNOSTIC` — 1 WARN
  предсуществующий/`plans/archive/2026.07.18-FOREMAN` — 41 WARN, предсуществующие).

**Ранее:** P0.4 (`plan-run`/Opus 5/high) — контракт паритета запечатан. P0.3 (`plan-run`/Opus
5/high) — инвентарь поглощения FOREMAN, терминализация донора. P0.2 (`plan-run`/Opus 5/high) —
адъюдикация аудита. P0.1 (`plan-exec`/Sonnet/medium) — изоляция worktree.

**Remaining:** P1 (5) → P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого 24/29 items ещё не исполнено.

**Sources of truth:** `plans/2026.07.29-HARNESS-AGNOSTIC/plan.md` (§3 Routing, §5 D1–D71+,
§7 Contracts, § Обсуждение 1–7, три блока `## Audit design`) · `phases/P0.md`–`P5.md` (P0 закрыта
целиком) · `roadmap.md` (батч B1 закрыт целиком; дальше всё solo до конца P0 — теперь P1) ·
`brief/00-brief.md` + `brief/01-refinements.md` · `findings/00`–`findings/06` · `research/00`, `01`,
`02`, `03`, `04`, `06`, `07`, `08`, `09` · `open-questions.md` (OQ-3, OQ-5–OQ-9 открыты; OQ-2
закрыта D71) · `index.md` · `journal.jsonl` · `root/isolation-procedure.md` ·
`root/contracts/provider-parity-definition.md` (sealed v1 — вход P1/P2/P5.3) ·
`plans/archive/2026.07.18-FOREMAN/` (архивирован, финальный `handoff.md` несёт чек-лист миграции) ·
`docs/reference.md` и `docs/rejected-optimizations.md` · `plans/README.md` (регистр очереди,
синхронизирован P0.5).

**Open risks:**
- **Посторонний дифф в дереве не убран и не тронут** (правило коммит-гигиены): `roadmap/README.md`
  (M) + untracked `roadmap/2026.07.29-launch-block-command-row.md`. Существовал до P0.2, ни в один
  item-коммит P0.1–P0.5 не попал.
- **`scripts/test-provider-docs.py` на дереве КРАСНЫЙ** (1 fail из 4) — битая ссылка
  `roadmap/self-learning-memory.md` из `README.md:122`, файла в `roadmap/` нет. Предсуществующая,
  к каталогу провайдеров отношения не имеет.
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ** (новое, P0.5): `ERROR: реестр устарел
  относительно источников — прогони: skiller registry`. Предсуществующий (drift старше P0.1),
  Known Deviation P0.5 — не блокирует P1, но красит Validation любого следующего item'а,
  прогоняющего `skiller validate.sh` целиком; фикс вне Scope P0.5.
- **`--check` не зовёт ни один гейт** (D21): до P2.5 конформанс каталога держится только ручным
  прогоном исполнителя, меняющего каталог.
- **6 новых WARN `plan-lint` на доноре — ложное срабатывание** правила `plan_lint.py:1941-1948`
  на строке DoR-чеклиста; правка текстов донора запрещена, правка линтера — чужой предмет.
- **`§7 Consumed`, строка AR-контрактов, обещает «пин снимается в P0.3», но Scope P0.3 этого не
  нёс** — фактический адресат P4.1. Правит `plan-design` одной строкой §7.
- **Parse-контракт донора остаётся просроченным и измеренно breaking**: P4.5 по D37 обязан
  эскалировать, а не исполнять.
- **`scripts/public-hygiene.py` на дереве красный** (предсуществующая находка) — закрыть или
  объявить исключением до P5.1.
- **Аудит исчерпан, страховки «ещё один заход» больше нет** — дефект в ТЗ всплывёт на исполнении.
- **Дисциплина «новая Validation обязана быть прогнана»** машинного гейта не имеет
  (PROMOTE-CANDIDATE, дом `roadmap/`). **Правило design-коммита (D69)** — тоже.
- **Маршруты стали мягче:** девять items ушли из гейтованного `plan-exec` в `plan-run` (D47) —
  строка `Session: <model>/<effort>` в отчёте и Update Log каждого такого item'а обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4);
  проверка «пережил волну» — за P5.3.
- **P5.2 — единственная необратимая внутрь граница плана**: merge меняет живой инструмент 25
  онбордженных проектов в момент коммита (R1).
- **Локальный прогон гейтов ≠ CI**: матрица python 3.9–3.13 и ruff-пин локально не воспроизводятся;
  «CI зелёный» в отчёте P5.1 запрещено (R2). **CI не зовёт `validate.sh` пакетов `analyst`/`task`**
  (OQ-9).
- **Три items правят один `packages/harness/scripts/validate.sh` со сплошной перенумерацией**
  (P1.5 `[9/9]`, P4.3 `[10/10]`) — знаменатель снимается прогоном, не берётся из ТЗ (D48).
- **Порядок двух коммитов P1.5 — «принятие → гейт» (D66)**; **точка принуждения
  `delegation_contract` живёт в `pending` между P4.3 и P4.4** (D58).
- **Переадресация читателей `CLAUDE.md` — единственный мост между P1 и ТЗ фаз P2–P5** (D60/D65/D68) —
  **это и есть P1.1**, следующий item.
- **P3.5 растит листинг, который меряет P3.4** (D52); **P3.3: гейт, который никогда не краснел, не
  доказан**; **P3.2** не стартует до закрытой P1.5 (D51/D67).
- **P4.4 правит канон ролей, раздаваемый флоту**, и ложится в ДВА носителя без гейта сверки (D35,
  OQ-8). Контракты `2026.07.24-AGENT-RELIABILITY`, на которых стоит P4, произведены планом,
  закрытым `🟠` с формально невыполненной приёмкой — P4.1 обязана метить недоказанное
  `[UNVERIFIED]`, а `decide` из `execution-state-machine-v1` живой библиотекой не существует.
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: **правка общего перечня `plans/verify-citations-known-exceptions.json`** (D54) — файл
  вне каталога плана, его дом — design-коммит (D69), не `Files` какого-либо item'а.
- deferred: изоляция общего state (OQ-5) · **вся постройка тонкой обвязки супервизора —
  `roadmap/artifex-thin-wrapper.md`, файл производит P4.1 (D38); туда же ушли каналы эскалации
  TG/MAX, run-folder, dry-run пилот и раскатка донора** · round-trip гейт живым прогоном Codex (Р3,
  приземлён P0.2 в `roadmap/codex-publication-consumer-acceptance.md`) · структурный перебор
  листинга на стороне Codex (OQ-7 → `roadmap/`, D29 в редакции D52) · перекалибровка токенайзера
  `budget.py` (чужой ECO-OPT) · общий differ «канон ↔ инсталляционный шаблон» ролей (OQ-8) ·
  машинный гейт «новая Validation прогнана» (PROMOTE-CANDIDATE) · машинный гейт «design-заход
  оставил состояние в истории» (PROMOTE-CANDIDATE D69) · починка ложного срабатывания
  `[NEEDS CLARIFICATION]` в `plan_lint.py` (P0.3) · **`skiller registry` не прогнан — реестр
  устарел относительно источников (P0.5, вне Scope)** · перевод прозы «кап делегирования» в
  командах `task:*` на ссылку к SSOT · раскатка на потребителей (D45) · push/PR/тег и публикация
  доков (D41) · расширение CI на `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore`
  (Р5) · собственный замер бюджета обнаружения на живом Codex CLI (`[UNVERIFIED]`, смежно с P3.4).
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (замер P3.4) · OQ-8
  дрейф канона ролей и инсталляционного шаблона (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). OQ-2 закрыта D71 (вариант B), OQ-1 закрыта D31, OQ-4 закрыта D27.
