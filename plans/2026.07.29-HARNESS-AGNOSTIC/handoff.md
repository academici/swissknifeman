# HANDOFF — 2026-07-29 — after P1.1

**Next:** ЗАПУСК ВРУЧНУЮ: implementation/high

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P1.2 — переписать 18 фрагментов канона и синхронизировать `catalog.json`/фикстуру совместимости по матрице P1.1, не меняя набор из 67 семантических ID (`catalog_version` → `1.0.1`) |

```
Читай, в этом порядке, НИЧЕГО СВЕРХ:
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — Context, Execution Rules, §3 Routing, Status Board
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P1.md — Phase Context + item P1.2 целиком
4) Required Reads item'а P1.2 в указанном порядке (первый — research/05-instruction-canon-routing.md,
   матрица «правило → дом», закрытая P1.1)

Исполни item P1.2 СТРОГО по его Scope Included/Excluded, Implementation Rules, Code Guidance —
без импровизации при расхождении с деревом (эскалация вместо самостоятельной правки плана).
ВАЖНО, из §7 матрицы (следствия P1.1): (1) обязательство «единый корневой CHANGELOG.md с
[Unreleased]» дописывается в существующую секцию root.development-validation — это добавление
обязательства, а не новый ID (в живом CLAUDE.md правила НЕТ: grep -ci changelog CLAUDE.md = 0);
(2) команду `instructions` в harness.command-surface здесь НЕ вписывать — её добавляет P1.4,
когда команда появится; (3) сужение root.codex.bootstrap и root.codex.launch-and-hook-integrity
(D73) делается ТОЛЬКО после того, как P1.3 завёл принимающие common-ID — иначе дерево несёт
правило дважды и падает INSTRUCTION_EXTENSION_CONFLICT; если P1.3 ещё не закрыт, оставь сужение
в Pending Work и правь остальные фрагменты.
Прогони Validation item'а целиком, зафиксируй passed/failed. Закрой item штатной топологией
plan-протокола (item-коммит по Files · bookkeeping-коммит плана · перезапись handoff.md ·
plan-lint --baseline HEAD с атрибуцией K) — модель/effort ЭТОЙ сессии (implementation/high), не
пин plan-exec (sonnet/medium): Routing item'а требует `Exec = manual`, поэтому /task:plan-exec
его отклонит на гейте — закрывай сам, по протоколу (Pre-mutation/Pre-final Task Contract с
ФАКТИЧЕСКИМ маршрутом сессии, две ветки закрытия 🟢/🟠, Update Log, launch-block следующего шага).
```

**Штатный носитель исполнения** — `task:plan-run` под сессией **implementation/high** (без ритуала
`/model`+`/effort`, если уже в такой сессии), либо `/model sonnet` + `/effort high` +
`/task:plan-run 2026.07.29-HARNESS-AGNOSTIC P1.2`. Голая slash-команда `/task:plan-exec` СЮДА НЕ
ПОДХОДИТ: она пинит sonnet/medium, а Routing P1.2 требует effort `high` (`Exec = manual`, D39/D47) —
гейт п. 2 `plan-exec` отклонит запуск (`ROUTING-BLOCKED`).

**Done:** **P1.1 закрыт `🟢`** (`plan-run`/Claude Opus 5/high — frontier/high, совпадает с §3
Routing; item-коммит `fd5183af`). Произведена матрица «правило → дом»
`research/05-instruction-canon-routing.md` (382 строки):
- Разобраны семь живых руководств по разделам `##`/`###` — **41 заголовок** покрыт (`./CLAUDE.md`
  10 · `./AGENTS.md` 3 · skiller 6 · harness 7 · maind 5 · analyst 6 · task 4, замер на `4bdc4a5e`);
  135 ячеек колонки «Источник».
- **67 существующих ID разнесены поимённо:** 34 обновляются в P1.2, 33 сохраняются без изменений.
- **9 новых ID для P1.3** (D72): common `root.provider-parity`, `root.worktree-safety`,
  `root.untrusted-content`, `root.evidence-integrity`, `root.generated-artifacts`,
  `root.speculative-work`, `root.docs-build`; extension `root.codex.package-scope-routing` (codex)
  и `harness.claude-code.safe-dirs` (claude-code). Инвентарь после P1.3 — **76** (56 + 20).
- **6 выносов в скиллы** (`axioma/ecosystem-map`, `general/plan-protocol`, `general/verify-claims`,
  `ecosystem-mcp`, `skill-authoring`, `release-discipline`) — законность дома подтверждена замером
  паритета: `.agents/skills/` 14 скиллов, `ecosystem-mcp` идентичен Claude-копии,
  `.agents/plugins/marketplace.json` несёт бакеты `general`/`axioma`/`core`.
- **8 снятий** с поимённой причиной (а) выводимо / (б) дубль / (в) транзиентное-ложное — включая
  строку про `plans/2026.07.18-FOREMAN` в `AGENTS.md` (транзиентная после P0.5).
- **Раздел «Переадресация читателей ТЗ» на девять адресов** (D60/D65/D68) — гейт зелёный:
  `len(rows) == 9`, девять адресных литералов, каждая строка несёт литерал, девять читателей
  (P2.2, P2.3, P3.1, P3.2, P3.3, P3.5, P3.6, P4.3, P5.1) названы.
- Приняты **D72** (перечень новых ID), **D73** (переезд трёх правил из Codex-расширения в common +
  сужение расширений), **D74** (`root.docs-build` в scope `root`, а не тремя пакетными ID).

**Ранее:** P0 закрыта целиком (4/5 🟢 + 1/5 🟠). P0.5 — архивация донора `2026.07.18-FOREMAN`
(`e4a9875d`, `c93b952f`), регистр `plans/README.md` синхронизирован; Known Deviation — красный
`packages/skiller/scripts/validate.sh` (предсуществующий drift реестра). P0.4 — контракт паритета
запечатан. P0.3 — инвентарь поглощения FOREMAN. P0.2 — адъюдикация аудита. P0.1 — изоляция worktree.

**Remaining:** P1.2 → P1.3 → P1.4 → P1.5, затем P2 (5) → P3 (6) → P4 (5) → P5 (3). Итого 23/29
items ещё не исполнено.

**Sources of truth:** `plans/2026.07.29-HARNESS-AGNOSTIC/plan.md` (§3 Routing, §5 D1–D74,
§7 Contracts, § Обсуждение 1–7, три блока `## Audit design`) · `phases/P0.md`–`P5.md` (P0 закрыта,
P1 — 1/5) · **`research/05-instruction-canon-routing.md` (матрица «правило → дом» — вход P1.2, P1.3,
P1.4 и P1.5)** · `research/04-instruction-mechanism-inventory.md` (механизм, G1–G5, ограничения
авторинга) · `findings/02-rag-instruction-loading-2026-07-29.md` Ф7/Ф8 · `roadmap.md` (батч B1
закрыт; дальше всё solo) · `brief/00-brief.md` + `brief/01-refinements.md` · `findings/00`–`06` ·
`research/00`–`04`, `06`–`09` · `open-questions.md` (OQ-3, OQ-5–OQ-9 открыты) · `index.md` ·
`journal.jsonl` · `root/contracts/provider-parity-definition.md` (sealed v1) ·
`plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md`
(frozen v1.0.0 — контракт механизма) · `plans/archive/2026.07.18-FOREMAN/` (архивирован) ·
`docs/reference.md`, `docs/rejected-optimizations.md` · `plans/README.md`.

**Open risks:**
- **Порядковая зависимость P1.3 → P1.2 (новая, D73):** сужение `root.codex.bootstrap` и
  `root.codex.launch-and-hook-integrity` законно только после того, как common-ID заведены. Промежуточное
  состояние «правило и в common, и в extension» отвергается валидатором
  (`INSTRUCTION_EXTENSION_CONFLICT`) — шаги не переставляются, порядок items фазы это допускает
  только если P1.2 оставит сужение в Pending Work до P1.3.
- **Правило `CHANGELOG.md`, которое D55 объявляет «правилом корневого `CLAUDE.md`», в живом файле
  отсутствует** (`grep -ci changelog CLAUDE.md` = 0 на `4bdc4a5e`). Обязательство доезжает в канон
  впервые (P1.2, секция `root.development-validation`), а не переносится.
- **Посторонний дифф в дереве не убран и не тронут** (правило коммит-гигиены): `roadmap/README.md`
  (M) + untracked `roadmap/2026.07.29-launch-block-command-row.md`. Существовал до P0.2, ни в один
  item-коммит P0.1–P1.1 не попал.
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ**: `ERROR: реестр устарел
  относительно источников — прогони: skiller registry`. Предсуществующий, Known Deviation P0.5 —
  красит Validation любого следующего item'а, который прогоняет этот `validate.sh` целиком.
- **`scripts/test-provider-docs.py` на дереве КРАСНЫЙ** (1 fail из 4) — битая ссылка
  `roadmap/self-learning-memory.md` из `README.md:122`. Предсуществующая.
- **`scripts/public-hygiene.py` на дереве красный** (предсуществующая находка) — закрыть или
  объявить исключением до P5.1.
- **`--check` не зовёт ни один гейт** (D21): до P2.5 конформанс каталога держится ручным прогоном.
- **Ложное срабатывание правила `plan_lint.py:1941-1948` распространилось на живой план:** правило
  считает маркером сам текст строки DoR-чеклиста, поэтому перевод ЛЮБОЙ фазы из `⬜` в `🟡` даёт
  WARN (`phases/P1.md:51` — новый от P1.1, `phases/P0.md:42`, 6 WARN на доноре). ERROR-счёт не
  затронут. Дом починки: правка линтера (чужой предмет) либо переформулировка канонической строки
  DoR во всех фазах — ни то, ни другое не входило в Scope P1.1.
- **`§7 Consumed`, строка AR-контрактов, обещает «пин снимается в P0.3», но Scope P0.3 этого не
  нёс** — фактический адресат P4.1. Правит `plan-design` одной строкой §7.
- **Parse-контракт донора остаётся просроченным и измеренно breaking**: P4.5 по D37 обязан
  эскалировать, а не исполнять.
- **Аудит исчерпан, страховки «ещё один заход» больше нет** — дефект в ТЗ всплывёт на исполнении.
- **Дисциплина «новая Validation обязана быть прогнана»** машинного гейта не имеет
  (PROMOTE-CANDIDATE, дом `roadmap/`). **Правило design-коммита (D69)** — тоже.
- **Маршруты стали мягче:** девять items ушли из гейтованного `plan-exec` в `plan-run` (D47) —
  строка `Session: <model>/<effort>` в отчёте и Update Log каждого такого item'а обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1); **локальный прогон гейтов ≠ CI**
  (R2), CI не зовёт `validate.sh` пакетов `analyst`/`task` (OQ-9).
- **Три items правят один `packages/harness/scripts/validate.sh` со сплошной перенумерацией**
  (P1.5 `[9/9]`, P4.3 `[10/10]`) — знаменатель снимается прогоном, не берётся из ТЗ (D48).
- **Порядок двух коммитов P1.5 — «принятие → гейт» (D66)**; **точка принуждения
  `delegation_contract` живёт в `pending` между P4.3 и P4.4** (D58).
- **P3.5 растит листинг, который меряет P3.4** (D52); **P3.3: гейт, который никогда не краснел, не
  доказан**; **P3.2** не стартует до закрытой P1.5 (D51/D67).
- **P4.4 правит канон ролей, раздаваемый флоту**, и ложится в ДВА носителя без гейта сверки (D35,
  OQ-8); контракты `2026.07.24-AGENT-RELIABILITY` произведены планом, закрытым `🟠` — P4.1 обязана
  метить недоказанное `[UNVERIFIED]`.
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: **правка общего перечня `plans/verify-citations-known-exceptions.json`** (D54) — файл
  вне каталога плана, его дом — design-коммит (D69), не `Files` какого-либо item'а.
- deferred: изоляция общего state (OQ-5) · **вся постройка тонкой обвязки супервизора —
  `roadmap/artifex-thin-wrapper.md`, файл производит P4.1 (D38)** · round-trip гейт живым прогоном
  Codex (Р3, `roadmap/codex-publication-consumer-acceptance.md`) · структурный перебор листинга на
  стороне Codex (OQ-7 → `roadmap/`, D29 в редакции D52) · перекалибровка токенайзера `budget.py`
  (чужой ECO-OPT) · общий differ «канон ↔ инсталляционный шаблон» ролей (OQ-8) · машинный гейт
  «новая Validation прогнана» (PROMOTE-CANDIDATE) · машинный гейт «design-заход оставил состояние
  в истории» (PROMOTE-CANDIDATE D69) · починка ложного срабатывания `[NEEDS CLARIFICATION]` в
  `plan_lint.py` (P0.3) · **`skiller registry` не прогнан — реестр устарел относительно источников
  (P0.5, вне Scope)** · перевод прозы «кап делегирования» в командах `task:*` на ссылку к SSOT ·
  раскатка на потребителей (D45) · push/PR/тег и публикация доков (D41) · расширение CI на
  `analyst`/`task` (OQ-9) · русский канон скиллов в `.gitignore` (Р5) · собственный замер бюджета
  обнаружения на живом Codex CLI (`[UNVERIFIED]`, смежно с P3.4) · **раскатка adoption-режима на 25
  онбордженных проектов** (кандидат `roadmap/`, Scope Excluded фазы P1).
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (замер P3.4) · OQ-8
  дрейф канона ролей и инсталляционного шаблона (Deferred) · OQ-9 CI не покрывает `analyst`/`task`
  (Deferred). OQ-2 закрыта D71 (вариант B), OQ-1 закрыта D31, OQ-4 закрыта D27.
