# HANDOFF — 2026-07-29 — after P7

**План ТЕРМИНАЛИЗОВАН поглощением** (D60; решение владельца Р1, зафиксированное D2 плана
`2026.07.29-HARNESS-AGNOSTIC`, который несёт `supersedes: 2026.07.18-FOREMAN`). Плановая работа
по этому ID больше не ведётся: `P1.5` и все 23 items фаз P2–P7 переведены в
`⛔ Skipped by decision`, фаза P1 → `🟠 Done with deviations`, фазы P2–P7 → `⛔ Skipped by decision`.
Осталось одно действие вне этого плана — архивация конвейером `plan-close archive`, её носитель
item **P0.5** поглощающего плана.

**Next:** archive: task:plan-close archive 2026.07.18-FOREMAN

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | low |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | Перенести терминальный план в `plans/archive/`, мигрировать ссылки, починить потребителей пути (`resolve_plan_dir`) и регистр очереди `plans/README.md` |

```
/task:plan-close archive 2026.07.18-FOREMAN
```

(Cold-start reads: `plans/2026.07.29-HARNESS-AGNOSTIC/phases/P0.md` item **P0.5** — все 16 полей;
`plans/2026.07.29-HARNESS-AGNOSTIC/research/03-foreman-absorption-inventory.md` — судьба каждого
артефакта; `packages/task/commands/plan-close.md` §«Режим `archive <ID>`» — шесть шагов;
`git show 9b1b5fef` — прецедент миграции `root/` без физического переноса.)

**Штатный носитель исполнения — item `2026.07.29-HARNESS-AGNOSTIC` P0.5**, а не голый запуск
конвейера: его ТЗ добавляет к шести шагам режима `archive` починку четырёх потребителей пути в
живом дереве и правку регистра очереди (D50/D61 того плана). Запускать так:
`/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P0.5`.

**Done:**
- **P0 — 6/6 🟢, терминальна.** Пять sealed-контрактов: parse-контракт драйвер↔plan-protocol
  (`driver-plan-protocol.md`), policy-схема (`artifex-policy-schema.md`), run-folder + мандат
  (`artifex-run-folder.md`) и, из P1, схемы журнала (`plan-journal-schema.md`) и индекса
  (`plan-index-schema.md`).
- **P1 — 🟠.** P1.1/P1.2 🟢 (схемы sealed v1), P1.3 🟢 (`lib/task/journal.py` + запись во всех
  пяти командах `task:plan-*`, коммит `94eada8`), P1.4 🟠 (канон plan-protocol 2.9.0 с
  journal/index + lint + snippets, коммит `c37b3379`, bootstrap-журнал `9844f499`), P1.5 —
  `⛔`: re-пин parse-контракта передан item'у **P4.5** поглощающего плана (его D37).
- **Терминализация 2026-07-29** (`2026.07.29-HARNESS-AGNOSTIC` P0.3): статусы, D60, version bump
  0.22.1 → 0.23.0, строка Update Log, причина в `## Phase Context` каждой `⛔`-фазы.

**Remaining:** по этому плану — ничего. 24 незакрытых items получили адрес в инвентаре
поглощения: 19 → **P4.1** поглощающего плана (вердикт «потребляем · строим · отменяем» + спека
остатка `roadmap/artifex-thin-wrapper.md`, его D38), P1.5 → **P4.5**, четыре items фазы P5
отменены по существу (движок решений потребляется из `2026.07.24-AGENT-RELIABILITY`, D49 выше).

**Sources of truth:**
- **инвентарь поглощения** — `plans/2026.07.29-HARNESS-AGNOSTIC/research/03-foreman-absorption-inventory.md`
  (§2 судьба каждого артефакта и item'а · §3 поимённая сверка пяти якорей parse-контракта ·
  §4 вердикт OQ-2);
- решения этого плана — `plan.md` §5 (D1–D60), контракты — `root/contracts/` (остаются в архиве,
  переносятся только ссылки — прецедент `9b1b5fef`);
- живая реализация журнала — `packages/task/lib/task/journal.py`; канон схемы — `plan-journal-schema.md`;
- поглощающий план — `plans/2026.07.29-HARNESS-AGNOSTIC/` (§5 D2/D9/D10/D37/D38, фаза P4).

**Open risks:**
- **Пин `driver-plan-protocol.md` просрочен и остаётся просроченным**: `plan-protocol`
  **v2.8.0 @ `2cf26e8`** против живого канона **v2.21.0**. Замер P0.3 (§3 инвентаря): из пяти
  якорей §4 сломан один — **форма `Next`** (канон перешёл на провайдер-нейтральные семантические
  формы `exec-items:`/`run-items:`/…), значит по критерию D9 поглощающего плана это **вариант B
  (breaking)**, а по его D37 вариант B эскалируется владельцу, а не исполняется командой. До
  этого момента любой парсер, читающий handoff по запиненной схеме, на новых планах шаг не
  классифицирует.
- **Приёмка `2026.07.24-AGENT-RELIABILITY` формально не выполнена** (его D88/D89), а вся
  «тонкая обвязка» стоит на его контрактах — утверждения «стоим на доказанном контракте» в
  будущей спеке обязаны нести `[UNVERIFIED]` (`research/08` §2 поглощающего плана).
- **`execution-state-machine-v1` живой библиотекой не существует** — машина решений лежит
  ДАННЫМИ в каталоге артефактов архивированного плана (135 ячеек); объём работы «потребить
  `decide`» этим не покрыт.
- **Потребители пути `plans/2026.07.18-FOREMAN` в живом дереве не починены** — это скоуп P0.5:
  `packages/skiller/tests/test_provider_publication_parity.py:156` (хардкод под охраной
  `path.exists()` — после переноса теряет покрытие, не падает), `AGENTS.md:24`,
  `roadmap/codex-subagent-offload.md:81`, регистр `plans/README.md`.
- **Каталог принципов владельца** (`findings/owner-principles-catalog.md`) остаётся со статусом
  «🔒 на утверждение владельцем»: его гейт истёк вместе с носителем (`.artifex/policy.toml`
  отменён), живого потребителя в поглощающем плане нет.

**Workarounds / Deferred / Open questions:**
- workarounds: —
- deferred: постройка тонкой обвязки супервизора целиком — `roadmap/artifex-thin-wrapper.md`
  (производит P4.1 поглощающего плана, D38); каналы эскалации TG/MAX, run-folder и dry-run пилот
  — там же.
- open_questions: OQ-6 (дом rollout-конфигов) и OQ-7 (дом Brain-скилла) закрываются вместе со
  своими фазами (`⛔`) — если тема вернётся, её носитель будет назван спекой остатка, а не этим
  планом. Судьба parse-контракта (OQ-2 поглощающего плана) — измерена, исполнитель P4.5.

## Чек-лист миграции (P0.5, `2026.07.29-HARNESS-AGNOSTIC`)

- **Перенесено:** сам план `plans/2026.07.18-FOREMAN/**` → `plans/archive/2026.07.18-FOREMAN/**`
  (`git mv`, коммит `e4a9875d`), без физического переноса `root/contracts/`.
- **Осталось в архиве:** `root/contracts/` (пять контрактов — `artifex-policy-schema.md`,
  `artifex-run-folder.md`, `driver-plan-protocol.md`, `plan-index-schema.md`,
  `plan-journal-schema.md`) — прецедент `9b1b5fef` (DUAL-PROVIDER/AGENT-RELIABILITY):
  контракты остаются, переносятся только ссылки. Живых markdown-ссылок на
  `plans/2026.07.18-FOREMAN/root/contracts/*` вне каталогов планов не найдено
  (`grep -rln`) — переносить нечего.
- **Починенные потребители пути в живом дереве:**
  - `packages/skiller/tests/test_provider_publication_parity.py:156` — хардкод пути заменён на
    `core.repo.resolve_plan_dir(self.repo_root, "2026.07.18-FOREMAN")` (не хардкод нового пути).
  - `AGENTS.md:24` — путь/факт архивации обновлён («archived, do not execute»); содержательная
    переработка не тронута (P1).
  - `roadmap/codex-subagent-offload.md` — проверен: три упоминания (строки 44/68/81) — bare-ID
    provenance-цитаты (`План \`2026.07.18-FOREMAN\`: D18 …`), НЕ путь; тот же класс, что D3-цитаты
    в коде (Scope Excluded этого item'а) — правки не требуют, остаются как есть.
  - `plans/README.md` — статус донора в регистре очереди переведён в «архивирован, поглощён
    `2026.07.29-HARNESS-AGNOSTIC` (его D2)»; добавлена строка `2026.07.29-HARNESS-AGNOSTIC`;
    починен статус `2026.07.25-ECO-OPT` (терминален, архивирован 2026-07-29) — все три правки D61.
- **Не тронуто** (Scope Excluded item'а): D3-цитаты `2026.07.18-FOREMAN Pn.m` в
  `packages/task/lib/task/journal.py`/`plan_lint.py`; `CHANGELOG.md`; провенансные упоминания
  старого пути внутри плана `2026.07.29-HARNESS-AGNOSTIC` (§5 D-лог, D50); секции `plans/README.md`
  вне трёх названных правок («Почему такой порядок», «Кросс-плановая последовательность»,
  «Принципы кросс-плановой работы», Такт 6, launch-block'ы payload C — bare-ID цитаты, не пути).
