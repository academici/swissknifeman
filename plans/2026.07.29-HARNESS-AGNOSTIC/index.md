# Индекс плана — `plans/2026.07.29-HARNESS-AGNOSTIC/`

**Обновлён:** 2026-07-30 (реопен фазы P1 по вердикту RED аудита ФАЗЫ: items ремедиации P1.6/P1.7,
D75–D79, слой 2 → `research/10`. Ранее: design pass 3/3 завершён — `finish`; затем три захода
`finish` по находкам design-аудита: заход 1 → F1–F9 → D56–D62, заход 2 → A1–A6 → D63–D67,
заход 3 → B1–B5 → D68–D70 + design-коммит истории ветки; четвёртым design-проходом НЕ считаются)

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | мастер-план: Meta, Context, Rules, §3 Routing, Status Board, D-лог (**D1–D79**), §7 Contracts, § Обсуждение, блоки `## Audit design — 2026-07-29`, `## Audit design (заход 2) — 2026-07-29` и `## Audit design (заход 3) — 2026-07-29`; блок аудита ФАЗЫ живёт в `phases/P1.md` — `## Audit P1 — 2026-07-30` |
| `phases/P0.md … P5.md` | по файлу на фазу: Phase Context (контракт-блок) + DoR + items + Phase Handoff |
| `handoff.md` | rolling-указатель «где мы» (перезаписывается) |
| `journal.jsonl` | append-only история запусков `/task:plan-*` |
| `roadmap.md` | исполнительская карта: батчи/solo, гейты владельца, launch-block'и — **пересобрана на `finish`** после правки маршрутов D47 и расформирования батчей D53 |
| `brief/` | слой 0: бриф владельца (М1–М12) + датированные уточнения (Р1–Р8; Р7/Р8 — скоуп и границы реопена P1) |
| `findings/` | слой 1: исходный аудит + верификация внешних фактов (00–06) |
| `research/` | слой 2: авторский синтез (00–10, кроме производимых 03 и 05 — см. строку ниже; 10 — грунт ремедиации P1: прогон покрытия 99/105, форма гейта, проверенные факты бухгалтерии) |
| `open-questions.md` | OQ-1 … OQ-9 — незакрытое (OQ-1 закрыт D31, OQ-4 закрыт D27) |

Не существуют до исполнения и производятся своими items: `research/03` (P0.3), `research/05` (P1.1) · `root/`
(P0.1 · P0.4 · P1.3 · P2.1 · P4.1 · P4.2) · `artifacts/` (P1.5 · **P1.6** · P2.5 · P3.4 · P5.1 · P5.3).
Каталога `workflows/` у плана нет и не будет: ни одна фаза не объявила оркестрацию
(проверка `plan-protocol` §7 записана в Phase Context P4 и P5).

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `brief/00-brief.md` | brief | весь план | двенадцать мыслей владельца (М1–М12) и три явных ограничения |
| `brief/01-refinements.md` | brief | `P0`, `P1`, `P2`, `P4`, `P5` | скоуп харнесов (Claude+Codex) и шесть решений владельца Р1–Р6 |
| `findings/00-owner-audit-perplexity-2026-07-29.md` | findings | `P0.2`, `P3.2`, `P3.3`, `P4.2` | исходный аудит: 14 разделов + референсы; raw-копия переносится в архив каркаса item'ом P3.3 |
| `findings/01-rag-cross-harness-2026-07-29.md` | findings | `P0.2`, `P0.4`, `P1`, `P2` | верификация: GitHub API по `wshobson/agents`, first-party OpenCode/Cursor, бюджет скиллов Codex, шесть repo-замеров |
| `findings/02-rag-instruction-loading-2026-07-29.md` | findings | `P1.1`, `P1.5` | Ф7/Ф8: модель загрузки инструкций обоих провайдеров, first-party доки + исходник `openai/codex@main` (32 KiB, пустой `project_doc_fallback_filenames`) |
| `findings/03-rag-codex-capability-surfaces-2026-07-29.md` | findings | `P2.1`–`P2.5` | Ф9–Ф12: одиннадцать хук-событий Codex и семантика отказа, границы проектного конфига, формат `.codex/agents/*.toml` |
| `findings/04-rag-agent-surface-and-skill-listing-2026-07-29.md` | findings | `P3.1`–`P3.5` | Ф13–Ф18: бюджеты обнаружения обоих провайдеров и режимы деградации, поверхность Agent Teams, лимиты субагентов + §«Замеры реестра» |
| `findings/05-rag-delegation-and-spawn-2026-07-29.md` | findings | `P4.2`, `P4.4` | Ф19–Ф22: пять элементов задания субагенту дословно, компрессия как смысл спавна, шкала спавна (перенос чужого домена, `[UNVERIFIED]`) |
| `findings/06-rag-fleet-propagation-and-merge-2026-07-29.md` | findings | `P5` | Ф23–Ф25: доставка плагинов локального marketplace (first-party), вторичный RAG, замер worktree и версии git |
| `research/00-user-intent.md` | research | `plan-audit design` | трассировка «мысль брифа → адрес в плане»; две мысли сняты с причиной; отдельный раздел — восемь находок сквозного reconcile |
| `research/01-audit-adjudication.md` | research | `P0.2`, `P3.1`, `P3.2`, `P4.2` | посекционные вердикты accept/DONE/reject/REFUTED по всему аудиту |
| `research/02-p0-premortem.md` | research | `P0.1`–`P0.5` | pre-mortem фазы P0 (протокол Klein): R1–R7 «как провалилось» → mitigation с адресом в item'е |
| `research/03-foreman-absorption-inventory.md` | research | `P0.5`, `P4.1`, `P4.5` | **производится item'ом P0.3**: судьба каждого артефакта донора + вердикт сверки якорей parse-контракта (OQ-2) |
| `research/04-instruction-mechanism-inventory.md` | research | `P1.1`–`P1.5` | инвентарь замороженного механизма instruction-projection и пять его разрывов (G1–G5) |
| `research/05-instruction-canon-routing.md` | research | `P1.2`, `P1.3`, `P1.5`, `P3.6`; раздел переадресации — ещё `P2.2`, `P2.3`, `P3.1`, `P3.2`, `P3.3`, `P3.5`, `P4.3`, `P5.1` | **производится item'ом P1.1**: матрица «правило → дом» по семи живым руководствам, перечень новых ID, перечень выносов в скиллы, перечень снятий с причинами, **раздел «Переадресация читателей ТЗ» на девять цитируемых адресов `CLAUDE.md` (D60)**; служит `source-to-semantic mapping` для законного принятия |
| `research/06-codex-parity-triage-groundwork.md` | research | `P2.1`–`P2.4` | пять механических классов записей `unsupported`, кандидатная карта 17 записей, три варианта дома логики обработчиков |
| `research/07-framework-canon-drift-2026-07-29.md` | research | `P3.1`–`P3.5` | постатейная таблица дрейфа канона каркаса, разомкнутые шаги петли аудита, разбор потолков конкурентности |
| `research/08-p4-executor-layer-and-policy.md` | research | `P4.1`–`P4.5` | замер входа исполнительского слоя, разбор пяти кандидатов дома политики, замер грамматики PLAN и двух носителей роли |
| `research/09-p5-return-and-fleet-acceptance.md` | research | `P5.1`–`P5.3` | карта распространения на флот · инвентарь гейтов и локальных эквивалентов · пробел матрицы зрелости · дисциплина дельты · pre-mortem R1–R7 |
| `root/isolation-procedure.md` | root | `P0.1`, `P5.1`–`P5.3` | **производится item'ом P0.1**: создание/активация/снятие изолированного контура + общие поверхности; единственный носитель host-специфичных путей плана |
| `root/contracts/provider-parity-definition.md` | root | `P1`, `P2`, `P5.3` | **производится item'ом P0.4**: три исхода триажа, планка evidence, машинная проверка вердикта |
| `root/contracts/instruction-canon-addendum-v1.md` | root | `P1.5`, будущие планы | **производится item'ом P1.3**: аддитивная дельта семантических ID поверх замороженного контракта донора |
| `root/contracts/codex-parity-verdicts-v1.md` | root | `P2.2`–`P2.5`, evidence манифеста | **производится item'ом P2.1**: вердикт по каждой из 17 записей `unsupported` + носитель, evidence и черновик `limitations` |
| `root/executor-layer-rescope-v1.md` | root | `P4.2`, `P4.5` | **производится item'ом P4.1**: замер входа, судьба 24 незакрытых items донора, поимённые `[UNVERIFIED]`, граница плана |
| `root/contracts/execution-policy-v1.md` | root | `P4.3`, `P4.4` | **производится item'ом P4.2**: четыре раздела схемы, потолки таблицей по субъектам, пять полей задания, трассировка «поле → потребитель» |
| `artifacts/P2-codex-parity-conformance.md` | artifacts | приёмка паритета, `P5.1` | **производится item'ом P2.5**: состояние 35 capability до/после фазы с вклеенными выводами команд |
| `artifacts/P3-skill-listing-budget.md` | artifacts | OQ-7, `roadmap/`, `P3.5` | **производится item'ом P3.4**: замер листинга по профилям и обоим провайдерам; раздел дельты дописывает P3.5 |
| `artifacts/P5.1-fleet-baseline/` | artifacts | `P5.3` | **производится item'ом P5.1**: снимок флота «ДО» тремя диагностиками, база парного прогона |
| `artifacts/P5.3-fleet-delta.md` | artifacts | приёмка М10 | **производится item'ом P5.3**: дельта «ДО→ПОСЛЕ», волатильный набор, перечень «НЕ раскатано на потребителей» |

## Внешние входы за пределами каталога плана

| Источник | Роль | Кто читает |
|:--|:--|:--|
| `plans/archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md` | замороженный контракт канона инструкций (не правится) | `P1.1`–`P1.5` |
| `plans/2026.07.18-FOREMAN/root/contracts/*` — **ЖИВОЙ путь, до архивации** | те же пять sealed-контрактов донора глазами читателя, который идёт ДО P0.5 | `P0.3` (архивацию делает P0.5, то есть на момент чтения плана донора в `plans/archive/` ещё нет) |
| `plans/archive/2026.07.18-FOREMAN/root/contracts/*` — **архивный путь, после P0.5** | пять sealed-контрактов донора (переиспользуются как есть) | `P1.3`, `P4.1`, `P4.2`, `P4.5` |
| `plans/archive/2026.07.24-AGENT-RELIABILITY/root/contracts/*` | контракты исполнительского слоя, приёмка формально не выполнена | `P4.1` |
| `plans/archive/2026.07.25-ECO-OPT/` (его P3.4/P3.5, D74/D75) | модель бюджета листинга, исполненный рычаг №1, порядок четырёх рычагов владельца | `P3.4`, `P3.5` (сверка — D52) |
| `roadmap/skill-description-quality.md`, `roadmap/codex-publication-consumer-acceptance.md`, `roadmap/codex-subagent-offload.md` | существующие спеки каталога — обновляются, а не дублируются | `P0.2`, `P0.5`, `P3.5` |
