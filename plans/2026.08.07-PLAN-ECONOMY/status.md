<!-- plan-projection
projection: status-view
projection_version: v1
source_scope: plan core + phases + journal
through: 2026-08-08
inputs_sha256: 0267f7a5361d1f114a1c16b01b84345d39b2b25b2e595b10e112bd74aaf52311
generated_by: task plan-views status
-->

# Статус плана

> Не править руками: это генерируемый вид.

## 0. Meta

| Поле | Значение |
|:--|:--|
| Version | 0.27.0 |
| Status | 🔴 Blocked |
| Last Updated | 2026-08-08 |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Измерить вес чтения и заморозить метрику | 2/5 | 🟠 Done with deviations |
| P1 | Заморозить контракт читателей плана | 4/5 | 🟠 Done with deviations |
| P2 | Перестроить носители плана | 5/10 | 🟠 Done with deviations |
| P3 | Собирать bundle и включить машинный гейт | 5/7 | 🟠 Done with deviations |
| P4 | Ограничитель кружения design↔exec | 0/6 | 🔴 Blocked |
| P5 | Безлюдный протокол решений и рамка полномочий | 0/5 | ⬜ Not started |
| P6 | Раскатать протокол и проверить критерий | 0/9 | ⬜ Not started |

## Phase P0

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P0.1 | Откалибровать оценку токенов сверху и заморозить артефакт | 🟠 Done with deviations | 2026-08-08 |
| P0.2 | Измерить лимит одного чтения как параметр среды, а не литерал | 🟠 Done with deviations | 2026-08-08 |
| P0.3 | Построить инструмент замера веса обязательного чтения | 🟠 Done with deviations | 2026-08-08 |
| P0.4 | Закрыть учёт корней в `sweep` и снять машинный замер по всему живому флоту планов | 🟢 Done | 2026-08-08 |
| P0.5 | Заморозить порог приёмки и единицу измерения | 🟢 Done | 2026-08-08 |

## Phase P1

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P1.1 | Заморозить роли читателей и реестр носителей | 🟢 Done | 2026-08-08 |
| P1.2 | Заморозить форму слепка состояния как проекции с метаданными | 🟢 Done | 2026-08-08 |
| P1.3 | Заморозить генерируемый исторический вид и границу «исполнителю не видно» | 🟢 Done | 2026-08-08 |
| P1.4 | Заморозить обязательный путь чтения и правило порядка секций | 🟠 Done with deviations | 2026-08-08 |
| P1.5 | Свести контракт, оценить выполнимость и заморозить владельческим гейтом | 🟢 Done | 2026-08-08 |

## Phase P2

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P2.1 | Ввести версионированную раскладку и адресацию носителей | 🟢 Done | 2026-08-08 |
| P2.2 | Вынести журнал решений в decisions/ с генерируемыми видами | 🟠 Done with deviations | 2026-08-08 |
| P2.3 | Разбить фазу на тонкий индекс и файлы пунктов | 🟠 Done with deviations | 2026-08-08 |
| P2.4 | Перестроить ядро plan.md и собрать владельческий вид status.md | 🟢 Done | 2026-08-08 |
| P2.5 | Реализовать генератор слепка состояния пункта | 🟠 Done with deviations | 2026-08-08 |
| P2.6 | Реализовать генератор исторического вида пункта | 🟠 Done with deviations | 2026-08-08 |
| P2.7 | Убрать терминальные фазы с живого пути и собрать дайджест закрытия | 🟠 Done with deviations | 2026-08-08 |
| P2.8 | Перевести этот план на раскладку v2 конвертером и подтвердить замером | 🟢 Done | 2026-08-08 |
| P2.9 | Заморозить stage-aware admission и разрезать oversized task carriers | 🟢 Done | 2026-08-08 |
| P2.10 | Пересобрать read graph и доказать self-host admission | 🟢 Done | 2026-08-08 |

## Phase P3

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P3.1 | Заморозить форму манифеста входов пункта | 🟢 Done | 2026-08-08 |
| P3.2 | Построить детерминированный сборщик bundle | 🟢 Done | 2026-08-08 |
| P3.3 | Включить гейт бюджета чтения и читаемости файлов | 🟢 Done | 2026-08-08 |
| P3.4 | Включить гейт разрешимости bundle и свежести производных | 🟢 Done | 2026-08-08 |
| P3.5 | Включить гейт предиката порядка и границ обязательного чтения | 🟢 Done | 2026-08-08 |
| P3.6 | Перевести осиротевшие проверки линтера на носители v2 | 🟠 Done with deviations | 2026-08-08 |
| P3.7 | Заморозить и построить гейт потребителя (D13-б1) | 🟠 Done with deviations | 2026-08-08 |

## Phase P4

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P4.1 | Заморозить форму отпечатка причины возврата | 🔴 Blocked | 2026-08-08 |
| P4.2 | Построить вычислитель отпечатка и durable-счётчик | ⬜ Not started | 2026-08-08 |
| P4.3 | Заморозить потолок, блокирующую силу и пакет владельческого гейта | ⬜ Not started | 2026-08-08 |
| P4.4 | Включить ограничитель и квалификацию эскалации выключенными проверками | ⬜ Not started | 2026-08-08 |
| P4.5 | Заморозить контракт среза-суждения и монотонность его влияния | ⬜ Not started | 2026-08-08 |
| P4.6 | Исполнить вердикт детерминированно и воспроизвести детект на историческом корпусе | ⬜ Not started | 2026-08-08 |

## Phase P5

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P5.1 | Заморозить контракт запроса и ответа решения | ⬜ Not started | 2026-08-08 |
| P5.2 | Заморозить владельческую рамку полномочий поверх классов AUTO/AUTO-FIX/OWNER | ⬜ Not started | 2026-08-08 |
| P5.3 | Построить детерминированный резолвер политики и автоответ уточнений | ⬜ Not started | 2026-08-08 |
| P5.4 | Носители очереди, адресная пауза субъекта и батчинг владельческих гейтов | ⬜ Not started | 2026-08-08 |
| P5.5 | Надеть форму запроса на пакет гейта кружения и доказать приёмку фазы | ⬜ Not started | 2026-08-08 |

## Phase P6

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P6.1 | Перевести пять команд на путь чтения v2 при сохранённом v1 | ⬜ Not started | 2026-08-08 |
| P6.2 | Научить закрывающие команды производить записи и снять переходное правило | ⬜ Not started | 2026-08-08 |
| P6.3 | Ввести интерфейсы модельного суждения: запрос решения и ассет рубрики среза | ⬜ Not started | 2026-08-08 |
| P6.4 | Включить четыре проверки по одной за коммит и ретайрить поле активации | ⬜ Not started | 2026-08-08 |
| P6.5 | Перевести авторинг в EN-only и привести канон plan-protocol к v2 | ⬜ Not started | 2026-08-08 |
| P6.6 | Раскатать канон и рамку по флоту с инвентарём адопции | ⬜ Not started | 2026-08-08 |
| P6.7 | Предобъявить протокол приёмки | ⬜ Not started | 2026-08-08 |
| P6.8 | Исполнить приёмку двумя руками и вынести вердикт | ⬜ Not started | 2026-08-08 |
| P6.9 | Снять паузу ARTIFEX и вернуть мандат замера | ⬜ Not started | 2026-08-08 |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-08-07 | claude-opus-5[1m]/high | plan-design · in-progress · план создан режимом new: слои 0-2 записаны, семь фаз запечатаны contract-first, D1-D10 |
| 2026-08-07 | opus/high | plan-design · in-progress · фаза детализирована до DoR |
| 2026-08-07 | opus/high | plan-design · in-progress · фаза детализирована до DoR |
| 2026-08-07 | opus/high | plan-design · in-progress · фаза детализирована до DoR |
| 2026-08-07 | opus/high | plan-design · in-progress · фаза детализирована до DoR |
| 2026-08-07 | opus/high | plan-design · in-progress · фаза детализирована до DoR |
| 2026-08-07 | opus/high | plan-design · in-progress · фаза детализирована до DoR |
| 2026-08-07 | opus/high | plan-design · in-progress · фаза детализирована до DoR |
| 2026-08-07 | opus/high | plan-design · in-progress · прогон дизайна 2/2 finish: сквозной реконсиль, D81-D83, roadmap пересобран |
| 2026-08-07 | opus/xhigh | plan-audit · audit-red · заход 1, вердикт RED |
| 2026-08-07 | opus/high | plan-design · in-progress · прогон 3/3 finish: находки аудита F1-F12 закрыты D84-D95 |
| 2026-08-07 | opus/xhigh | plan-audit · audit-red · заход 2, вердикт RED |
| 2026-08-07 | opus/high | plan-design · in-progress · прогон 4/4 finish: находки аудита захода 2 N1-N11 закрыты D96-D104 |
| 2026-08-07 | opus/xhigh | plan-audit · audit-red · заход 3, вердикт ATTENTION (AUDIT-CAP исчерпан) |
| 2026-08-07 | opus/high | plan-design · in-progress · узкий finish по находкам аудита захода 3: A1/A2 закрыты D105-D106 |
| 2026-08-07 | sonnet/medium | plan-run · blocked · предписано implementation/high, сессия sonnet(implementation)/medium — недобор effort |
| 2026-08-07 | sonnet/high | plan-run · in-progress · — |
| 2026-08-07 | sonnet/high | plan-run · closed-deviations · калибровка закрыта (14/14, violations=0, p95=1.17); CHANGELOG.md вне Files item'а |
| 2026-08-07 | sonnet/medium | plan-exec · in-progress · — |
| 2026-08-07 | sonnet/medium | plan-exec · escalated · зонд даёт байтовый отказ Read, Inputs специфицируют токенный — конфликт правил, D2(б) |
| 2026-08-07 | opus/high | plan-design · in-progress · ТЗ item'а доведено до DoR |
| 2026-08-07 | sonnet/medium | plan-exec · in-progress · — |
| 2026-08-07 | sonnet/medium | plan-exec · closed-deviations · read-limit.json+справка записаны зондом; CHANGELOG.md заблокирован permission-deny среды |
| 2026-08-07 | opus/high | plan-run · in-progress · — |
| 2026-08-07 | opus/high | plan-run · closed-deviations · plan_weight + лаунчер + 45 тестов; замер по 19 планам флота снят |
| 2026-08-07 | sonnet/medium | plan-exec · in-progress · — |
| 2026-08-07 | sonnet/medium | plan-exec · escalated · Validation-команда P0.4 не совпадает с реальным CLI sweep (nargs=+ каталоги, нет unreadable_roots) |
| 2026-08-07 | opus/high | plan-design · in-progress · ТЗ item'а доведено до DoR |
| 2026-08-07 | sonnet/high | plan-run · in-progress · — |
| 2026-08-07 | sonnet/high | plan-run · closed-green · sweep root accounting + fleet sweep (19 roots, 61 plans, 2248 items) |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · escalated · ожидаются решения владельца по порогу D2(a), D109 и сроку legacy opt-in |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · владелец утвердил D113-D115; проверяется зависимость реопена P0.1 |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · escalated · P0.5 ждёт plan-design и исполнение реоткрытого P0.1 без плейсхолдера калибровки |
| 2026-08-08 | frontier/high | plan-design · in-progress · ТЗ item'а доведено до DoR |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · реопен D114/D116/D117: dense_ascii, калибровка v2 |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · escalated · Claude Code OAuth expired; A/B/A′ calibration has zero accepted probes |
| 2026-08-08 | frontier/high | plan-design · in-progress · ТЗ item'а доведено до DoR после auth-остановки |
| 2026-08-08 | frontier/high | plan-design · in-progress · ТЗ item'а доведено до DoR |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-deviations · Codex v2 calibration: 8 samples, 12 calls; docs path outside Files and known validate discovery defect |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-green · read-budget v1 заморожен на qualified Codex calibration v2; P0.5 закрыт |
| 2026-08-08 | implementation/low | plan-close · closed-deviations · фаза P0 закрыта: сверены 5 терминальных items и known deviations |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-green · записаны роли читателей и реестр носителей |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-green · записана форма проекции состояния пункта |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-green · записан исторический вид и граница executor path |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-green · записан обязательный путь чтения и предикат порядка |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-deviations · package validation выявил ложный plan discovery support-каталогов |
| 2026-08-08 | gpt-5.6-sol/high | plan-design · in-progress · прогон 5/5 finish: session continuity и adaptive review зафиксированы D123-D125 |
| 2026-08-08 | frontier/xhigh | plan-audit · audit-red · заход 4, вердикт RED |
| 2026-08-08 | frontier/high | plan-design · in-progress · owning-root remediation: F4.1-F4.4 закрыты D126 без пятого аудита |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-green · reader-contract v1 заморожен D127; реконструкция воспроизводима; item validation 0/0 |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-green · scoped-review нашёл незакреплённый runtime; fix-forward 5633a75a и clean-worktree regeneration без diff |
| 2026-08-08 | gpt-5.6/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6/high | plan-run · escalated · P2.1 требует зелёный validate до owning P3.6 repair discovery: plans/.claude и plans/__pycache__ дают 6 ERROR |
| 2026-08-08 | gpt-5.6/high | plan-run · in-progress · discovery repair выполнен в owning P2.1; validate снова зелёный |
| 2026-08-08 | gpt-5.6/high | plan-run · closed-green · P2.1: resolver v1/v2, carrier consumers, v1 parity and package validation green; D128-D129 record acceptance-command corrections. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-deviations · P2.2: immutable decisions и четыре deterministic views; Validation literal требует PYTHONPATH по D129. |
| 2026-08-08 | gpt-5.6-terra/medium | plan-run · blocked · предписано implementation/high, сессия implementation/medium |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-deviations · P2.3: v2 index/spec/state parser; literal full-unittest требует PYTHONPATH, validator green. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-green · stable v2 core and generated owner status view |
| 2026-08-08 | gpt-5.6/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6/high | plan-run · closed-deviations · Базовый state-редьюсер и --check; полное active_context deferred. |
| 2026-08-08 | gpt-5.6/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6/high | plan-run · closed-deviations · history view готов; literal unittest без корневого PYTHONPATH падает на старых imports core, validate.sh зелёный |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · escalated · P2.7: frozen phase-closure path conflicts (.closed.md vs .closure.md); needs plan-design. |
| 2026-08-08 | gpt-5.6-terra/high | plan-design · in-progress · Owner-prioritized local-repair policy and P2.7 closure-path reconciliation design. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · D130 repair-now завершён; начата реализация closure projection |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-deviations · Closure projection и status-aware resolution реализованы; literal discover требует PYTHONPATH. |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · escalated · Four items exceed frozen read-budget v1 threshold; owner-approved redesign required. |
| 2026-08-08 | frontier/high | plan-design · in-progress · ТЗ item'а доведено до DoR |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-green · Lossless v1→v2 migration and honest D2 baseline verified; final admission deferred to P2.9/P2.10. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-green · Session: implementation/high (gpt-5.6-terra); migration and 603-test validation verified; write-site: pre_mutation: allow · pre_final: allow. |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-green · Session: gpt-5.6-sol/high; read-budget 1.1.0 stage-aware admission и bounded plan-lint carriers; bash packages/task/scripts/validate.sh: 612 tests (на 3f478fa7) green; self-host ready, D2(a)+D2(b) pass; DIAGNOSTIC-PARITY-OK; write-site: pre_mutation: allow · pre_final: allow. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · escalated · ARTIFEX dry-run: missing ## Обсуждение; resume /task:plan-design 2026.08.07-PLAN-ECONOMY P2.10 |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · Resumed after owner-authorized local converter compatibility repair; source plan remains read-only. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-green · Session: gpt-5.6-terra/high; P2.10 read graph, D74 and read-only ARTIFEX projection verified; task validate: 616 tests green on 06f60871; write-site: pre_mutation: allow · pre_final: allow. |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-green · Session: gpt-5.6-sol/high; bundle v1 contract + five-code taxonomy + one example committed at 31cf532b; item Validation and task validate green at 31cf532b; write-site: pre_mutation: allow · pre_final: allow; deviation: P3 phase-start exposes two pre-existing DoR false-positive WARN. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · escalated · Frozen bundle v1 schema cannot carry required unresolvable_entry class while schema-valid; plan-design required. Session: gpt-5.6-terra/high. |
| 2026-08-08 | gpt-5.6-terra/high | plan-design · in-progress · Owner-approved same-session local reconciliation: D132 preserves Bundle v1 schema and derives unresolvable_entry in P3.4. Session: gpt-5.6-terra/high. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-green · Session: gpt-5.6-terra/high; deterministic Bundle v1 builder, lifted byte-identical schema, CLI bundle modes and atomic unresolvable refusal committed at 6cfb9d6a; task validate: 619 tests green on 6cfb9d6a; write-site: pre_mutation: allow · pre_final: allow; deviation: owner-authorized D132 same-session reconciliation. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-green · Session: gpt-5.6-terra/high; D2 read-budget hard-gate for ready layout-v2 items committed at 2381ac2d; task validate: 625 tests green on 2381ac2d; write-site: pre_mutation: allow · pre_final: allow. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · escalated · Validation calls unsupported plan-views.py all; plan-design must reconcile the closed generator surface |
| 2026-08-08 | gpt-5.6-terra/high | plan-design · in-progress · Owner-approved same-session repair: make P3.4 validation use existing explicit plan-views modes and materialize committed bundles |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-green · Session: gpt-5.6-terra/high; bundle freshness gate and committed active-phase artifacts committed at 08af02ac; task validate: 629 tests green; write-site: pre_mutation: allow · pre_final: allow; deviation: owner-authorized D133–D135 same-session reconciliation. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-green · Session: gpt-5.6-terra/high; read-path declaration gate committed at eeec7463; task validate: 631 tests green; write-site: pre_mutation: allow · pre_final: allow. |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · in-progress · — |
| 2026-08-08 | gpt-5.6-terra/high | plan-run · closed-deviations · Session: gpt-5.6-terra/high; P3.6 registry and v2 continuity committed at 0a1597c7; 3 focused tests and detailed v1 diagnostic parity green; deviations: literal unittest/core path and 4 pre-existing plan-lint errors; write-site: pre_mutation: allow · pre_final: allow. |
| 2026-08-08 | gpt-5.6-terra/medium | plan-run · blocked · предписано frontier/high (gpt-5.6-sol/high), сессия implementation/medium (gpt-5.6-terra/medium) |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · коррекция: config.load.model ошибочно принят за selector активной сессии; фактический Session gpt-5.6-sol/high |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · closed-deviations · Session: gpt-5.6-sol/high; downstream-gate v1 at 5632a221; 10 focused/644 full + validate green via repo PYTHONPATH. Deviations: literal unittest imports; false route-block journal; ARTIFEX/read-budget + mktemp and docs index scope — findings/19. write-site: pre_mutation: allow · pre_final: allow. |
| 2026-08-08 | implementation/low | plan-close · closed-deviations · фаза P3 закрыта: сверены 7 терминальных items и known deviations |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · in-progress · Required Read D50 проверяется перед заморозкой return-fingerprint v1 |
| 2026-08-08 | gpt-5.6-sol/high | plan-run · escalated · Required Read D50 обрывается; immutable decision нельзя восстанавливать внутри P4.1, нужен plan-design |

## Owner Gates

- P0.1: known deviation
- P0.2: known deviation
- P0.3: known deviation
- P1.4: known deviation
- P2.2: known deviation
- P2.3: known deviation
- P2.5: known deviation
- P2.6: known deviation
- P2.7: known deviation
- P3.1: known deviation
- P3.2: known deviation
- P3.4: known deviation
- P3.6: known deviation
- P3.7: known deviation
- P4.1: escalation
