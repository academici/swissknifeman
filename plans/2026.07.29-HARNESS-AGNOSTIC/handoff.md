# HANDOFF — 2026-07-29 — after P0.4

**Next:** exec-items: task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P0.5

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | low |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P0.5 — архивировать терминальный `2026.07.18-FOREMAN` конвейером `plan-close archive`, починить ссылки на его путь в живом дереве и привести регистр очереди `plans/README.md` в соответствие (статус донора, новая строка этого плана, статус `2026.07.25-ECO-OPT`) |

```
/task:plan-exec 2026.07.29-HARNESS-AGNOSTIC P0.5
```

§3 Routing P0.5 — `implementation/low`, `Exec = plan-exec`: команда пинит sonnet/medium, это
ПЕРЕБОР над предписанным тиром (безвредно, `plan-exec` §2) — исполнителю записать
process-отклонение в Known Deviations. По `roadmap.md` P0.5 идёт **solo**; предусловие
конвейера (терминальность всех фаз донора) выполнено P0.3. Ключевой риск — R7: путь плана
захардкожен в `packages/skiller/tests/test_provider_publication_parity.py:156` под охраной
`path.exists()`, после переноса тест не падает, а теряет покрытие — чинить через
`core.repo.resolve_plan_dir`, а не хардкодом.

**Done:** **P0.4 закрыт** (`plan-run`, сессия **Claude Opus 5/high** = frontier/high, `Exec =
manual`). Item-коммит `49ffd07e` (1 файл, +216).
- **Запечатан контракт** `root/contracts/provider-parity-definition.md` (216 строк, sealed v1):
  §1 три исхода (`closed-by-adapter` · `claude-only` · `intent-withdrawn`) таблицей «когда
  легален → форма записи в каталоге → чем проверяется» · §2 планка evidence (пять требований
  поверх замороженной формы четырёх ключей) · §3 семь пунктов «что доказательством НЕ является» ·
  §4 fail-closed диагностика · §5 «интенция снята» · §6 машинная проверка C1–C6 · §7 чек-лист
  самопроверки из 15 условий, по которому P2.1 ведёт триаж.
- **R2 снят измерением:** ни одно условие контракта не требует живого прогона Codex; все шесть
  проверок — команды, уже существующие в дереве, каждая прогнана на `99cb35f3`
  (`provider-docs.py --check` exit 0 · аудит `green: true`/`diagnostics: []` · проба
  потребителей · `load_provider_manifest` → `manifest OK`).
- **Новое измерение, вошедшее в контракт (§6.2):** `harness doctor --provider-audit` покрывает
  **23 из 35** capability; вне его — 12, из них одна Codex-`unsupported`
  (`analytics.legacy-migration`). Ссылаться на «зелёный аудит» для capability вне `surface_map`
  запрещено.
- **Правило принуждения исхода (§1):** `claude-only`/`intent-withdrawn` легальны только при нуле
  строгих потребителей по пробе C3 (`skills.repository` — 24 строгих, значит `claude-only`
  структурно невозможен; `lifecycle.daemon-safety` — 0, значит исход §5 доступен).
- **Определение паритета для приёмки P5.3** зафиксировано тремя одновременными условиями; §7
  Exported плана переведён в `sealed (P0.4)`.
- `plan-lint`: 0 ERROR / 1 WARN (новых от диффа item'а: 0).

**Ранее:** P0.3 (`plan-run`/Opus 5/high) — инвентарь поглощения FOREMAN, терминализация донора,
OQ-2 закрыта D71 (`2dbef470`). P0.2 (`plan-run`/Opus 5/high) — адъюдикация аудита в
`docs/reference.md`, `docs/rejected-optimizations.md`, `roadmap/` (`8aebf200`). P0.1
(`plan-exec`/Sonnet/medium) — процедура изоляции worktree (`1dcdd8e2`). Design-фаза: три прогона
+ три `finish`, `AUDIT-CAP` исчерпан.

**Remaining:** P0.5 (фаза P0, 4/5 закрыто) → P1 (5) → P2 (5) → P3 (6) → P4 (5) → P5 (3).
Итого 25/29 items ещё не исполнено.

**Sources of truth:** `plans/2026.07.29-HARNESS-AGNOSTIC/plan.md` (§3 Routing, §5 D1–D71,
§7 Contracts — одна строка Exported уже `sealed`, § Обсуждение 1–7, три блока `## Audit design`) ·
`phases/P0.md`–`P5.md` (P0.1–P0.4 закрыты) · `roadmap.md` (батч B1 закрыт целиком; дальше всё
solo до конца P0) · `brief/00-brief.md` + `brief/01-refinements.md` · `findings/00`–`findings/06` ·
`research/00`, `01`, `02`, `03`, `04`, `06`, `07`, `08`, `09` · `open-questions.md` (OQ-3, OQ-5–OQ-9
открыты; OQ-2 закрыта D71) · `index.md` · `journal.jsonl` · `root/isolation-procedure.md` ·
**`root/contracts/provider-parity-definition.md` (sealed v1 — вход P1/P2/P5.3)** ·
`plans/2026.07.18-FOREMAN/` (донор терминален, ждёт архивации item'ом P0.5) · `docs/reference.md`
и `docs/rejected-optimizations.md` (каталоги провенанса, пополнены P0.2)

**Open risks:**
- **Посторонний дифф в дереве не убран и не тронут** (правило коммит-гигиены): `roadmap/README.md`
  (M) + untracked `roadmap/2026.07.29-launch-block-command-row.md`. Существовал до P0.2, в
  item-коммиты `8aebf200`/`2dbef470`/`49ffd07e` не попал; исполнителю P0.5 достаётся в том же виде.
- **`scripts/test-provider-docs.py` на дереве КРАСНЫЙ** (1 fail из 4) — битая ссылка
  `roadmap/self-learning-memory.md` из `README.md:122`, файла в `roadmap/` нет. Предсуществующая,
  к каталогу провайдеров отношения не имеет; названа в §6.3 контракта, чтобы P2.x не принял её за
  свою регрессию. Чинится одной строкой `README.md` (или заведением файла) — вне Scope P0.4.
- **`--check` не зовёт ни один гейт** (D21): до P2.5 конформанс каталога держится только ручным
  прогоном исполнителя, меняющего каталог.
- **6 новых WARN `plan-lint` на доноре — ложное срабатывание** правила
  `plan_lint.py:1941-1948` на строке DoR-чеклиста; правка текстов донора запрещена, правка
  линтера — чужой предмет.
- **`§7 Consumed`, строка AR-контрактов, обещает «пин снимается в P0.3», но Scope P0.3 этого не
  нёс** — фактический адресат P4.1. Правит `plan-design` одной строкой §7.
- **Parse-контракт донора остаётся просроченным и измеренно breaking**: P4.5 по D37 обязан
  эскалировать, а не исполнять.
- **`scripts/public-hygiene.py` на дереве красный** (предсуществующая находка:
  `plans/archive/2026.07.25-ECO-OPT/artifacts/p5-pilot/stage0/install.log`) — закрыть или объявить
  исключением до P5.1.
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
- **Переадресация читателей `CLAUDE.md` — единственный мост между P1 и ТЗ фаз P2–P5** (D60/D65/D68).
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
  `[NEEDS CLARIFICATION]` в `plan_lint.py` (P0.3) · **починка битой ссылки `README.md:122` →
  `roadmap/self-learning-memory.md`, красящей `scripts/test-provider-docs.py` (новое, P0.4)** ·
  перевод прозы «кап делегирования» в командах `task:*` на ссылку к SSOT · раскатка на
  потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на `analyst`/`task`
  (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · собственный замер бюджета обнаружения на
  живом Codex CLI (`[UNVERIFIED]`, смежно с P3.4).
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1 — исход §5
  запечатанного контракта и проба C3 дают ему машинный критерий) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (замер P3.4) · OQ-8
  дрейф канона ролей и инсталляционного шаблона (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). **OQ-2 закрыта D71** (вариант B), OQ-1 закрыта D31, OQ-4 закрыта D27.
