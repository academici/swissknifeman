# HANDOFF — 2026-07-30 — after P2.9

**Next:** «ЗАПУСК ВРУЧНУЮ: frontier/high»

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — §3 Routing строка P2.1 (`frontier/high`, `Exec = manual`; `/task:plan-exec` пинит sonnet/medium и по гейту п.2 отклонит этот item) |
| Context | continue (/clear) — ручной item |
| Суть | Блок follow-up P2.6–P2.9 закрыт. P2.1 — первый item паритета: поимённый вердикт по 17 записям `unsupported` (закрыть/Claude-only/интенция снята) + выбор дома логики Codex-обработчиков (OQ-6) + закрытие OQ-3 |

````
Исполни item P2.1 плана 2026.07.29-HARNESS-AGNOSTIC вручную (Exec=manual, эта сессия
НЕ /task:plan-exec — та пинит sonnet/medium и по Routing-гейту отклонит P2.1).

Порядок чтения (ровно этот, без повторов):
1) plans/2026.07.29-HARNESS-AGNOSTIC/plan.md — §0 Meta, §1 Context, §2 Execution Rules,
   §3 Routing (строка P2.1), §4 Status Board
2) plans/2026.07.29-HARNESS-AGNOSTIC/handoff.md (этот файл)
3) plans/2026.07.29-HARNESS-AGNOSTIC/phases/P2.md — Phase Context (включая блок follow-up
   P2.6–P2.9, уже терминальный) + P2.1 целиком
4) Required Reads item'а P2.1 (в указанном там порядке)

Дом плана — repo:/home/vostrikov/projects/packages/swissknifeman, но по Execution Rules
(§2) все работы ведутся в worktree swissknifeman-next (ветка next/harness-agnostic) —
запускай эту сессию именно там.

Перед мутацией и перед закрытием собери Task Contract (task.task_contract.build +
route_evidence.capture_actual("implementation", "high", source="self-attested",
model="opus") — actual_route ЭТОЙ сессии) и убедись, что pre_mutation/pre_final =
"allow"; красный код — см. таблицу в packages/task/commands/plan-exec.md п.2/п.7
(эскалация или D#-запись по классу).

Исполняй СТРОГО Scope Included P2.1 (см. phases/P2.md), не трогай Scope Excluded.
Пометь Status: 🟡 In progress (item + Phase Status) до работы, journal.append --result
in-progress перед началом.

По завершении: прогони ВСЮ Validation P2.1 построчно, закрой item по топологии
plan-protocol §7 (item-коммит по Files P2.1 → bookkeeping плана → перезапись handoff.md →
plan-lint --baseline HEAD → bookkeeping-коммит), обнови Status Board/Update Log/Last
Updated, append журнал финал-записи (--result closed-green|closed-deviations).
Статус 🟢 при чистом закрытии, 🟠 Done with deviations — если Validation осталась
красной вне скоупа или Scope выполнен не полностью (запись в Known Deviations
обязательна). Заметил конфликт правил / неясный acceptance / замороженный каталог под
вопросом — эскалируй (plan-protocol §8), не импровизируй.

Дай отчёт в формате Expected Output plan-exec (Status/Completed/Pending Work/Files
Changed/Commits/Validation/Lint/Известные отклонения/Escalation Needed/Launch-block
следующего шага — P2.2).
````

**Что сделано этим заходом (exec, `plan-exec` под sonnet/medium).** P2.9 закрыт `🟠 Done with
deviations` (item-коммит `ffda7173`) — последний item блока follow-up. Шесть находок захода 2
закрыты: (A2) дубль строки закрытия P1.7 в `## 6. Update Log` снят (изъята поздняя `7d4f12b7`,
ранняя `a8abbf9e` осталась) — счёт строк закрытия на item **7/7** (`{1:1,…,7:1}`, без `NOHASH`);
(A3) первый пункт `Validation` P1.7 переписан (секция §6 + `\bP1\.[1-7]\b\s+закры` + «ровно одна
на item» + печать вывода), `Pending Work` P1.7 дополнен: пункт закрывался без печати вывода и
по букве старого ТЗ был красным (11 `NOHASH` на `7d4f12b7`, 10 на `003180bf`); (A4) пункт
`lock цел:` `Validation` P1.6 приведён к факту — `len(l['records'])`/`adoption`-подмножество,
`14 7`, ложный fallback `len(l)` снят; (A6) приписка `Last Updated` перестала перечислять
события, несёт только правило (D83), дата машинно равна дате последней строки §6; (A7) ложная
посылка «три `🟠` не проходили ни разу собственный аудит» снята в `phases/P1.md` § «Что дальше»
(вывод о необходимости второго захода сохранён); (A8) подпись `Completion Notes` P1.6 про дубль
`root.docs-build` приведена к факту — три строки, идентичны две, третья длиннее и остаётся
отдельным литералом (106 сырых → 105 уникальных, число не менялось). Один item-коммит
`ffda7173` — детали см. `phases/P2.md` P2.9 Completion Notes.

**Known Deviation (material, статус `🟠`):** фраза-находка A7 (ложная посылка о неаудированности трёх `🟠`-item'ов) остаётся в
`phases/P1.md` в ДВУХ местах вне `Files` этого item'а — историческая цитата в блоке `## Audit P1
— 2026-07-30 (заход 2)` (описывает саму находку A7, не носитель) и архивный launch-block
`### Что запускать` (эхо той же строки research/11 §7). Правка Files P2.9 ограничена тремя
локациями `phases/P1.md` (первый пункт Validation P1.7, `lock цел:` + подпись P1.6, § «Что
дальше») — эти два места вне периметра, трогать их значило бы material-дрейф (дифф вне `Files`).
Итог: grep-проверка целевой фразы A7 по обоим носителям → `0` в `handoff.md` и `2` в
`phases/P1.md` (было `1` и `3` до правки) —
Validation A7 частично красная за пределами Scope, а не молча пропущена.

**Session:** Sonnet 5/medium (implementation/medium, `Exec = plan-exec`, совпадает с §3
Routing — перебора/недобора нет).

**Done:** P0 целиком (5/5 терминальны) · P1 целиком (7/7 терминальны: P1.1/P1.4/P1.6/P1.7
`🟢`, P1.2/P1.3/P1.5 `🟠`) · аудит фазы P1 пройден дважды (заход 1 RED закрыт ремедиацией
P1.6/P1.7, заход 2 ATTENTION — блоком follow-up) · **блок follow-up P2 — все четыре items
терминальны: P2.6/P2.7/P2.8 `🟢`, P2.9 `🟠`**: непротухающий провенанс фикстуры покрытия (A1),
docs-sync поверхности `harness instructions` (A5(1)), дом долга order-sensitivity `--authorize`
(A5(2)/(3)), бухгалтерия захода 2 (A2/A3/A4/A6/A7/A8) закрыты — блок follow-up P2.6–P2.9
исчерпан целиком.

**Карта «item → коммит» (P1–P2; item-коммит | сопутствующие bookkeeping):**
P1.1 `fd5183af` | `340d0846` · P1.2 `e574fdda` | `d1e393af` · P1.3 `b02e48be` | `4ae56350`
(bookkeeping), `5996d92d` (дозапись журнала), `b191a19c` (Known Deviations) · P1.4 `1e0262a4` |
`d5482b37` · P1.5 `c3b3a8a3` (принятие) + `4647ad4b` (гейт) | `d052698f` · P1.6 `d5e01ef7`
(канон+рендер) + `eb64ea6c` (гейт покрытия) | `4416322e` (bookkeeping) · P1.7 `003180bf` (карта
хешей + три подписи) | `a8abbf9e` (bookkeeping), `7d4f12b7` (закрытие фазы) · P2.6 `317622c0`
(сужение+перегенерация) + `23c1090c` (гейт равенства, item-коммит) · P2.7 `e16082a1`
(доки поверхности `harness instructions`, item-коммит) · P2.8 `a264a339` (спека дома долга
`instruction-authorize-order.md`, item-коммит) · **P2.9 `ffda7173` (бухгалтерия захода 2,
item-коммит)**.

**Remaining:** паритет P2.1–P2.5 (5) → P3 (6) → P4 (5) → P5 (3). Итого **19 из 35** items
плана ещё не исполнено.

**Sources of truth:** `plan.md` (§3 Routing — девять строк фазы P2, §5 D1–D85, §6 Update Log с
картой хешей, §7 Contracts, §4 Status Board — P1 `7/7 🟠`, P2 `3/9 🟡`) · `phases/P1.md` (закрыта
`🟠`, два блока аудита, бухгалтерия P2.9 применена) · `phases/P2.md` (Phase Context § блок
follow-up — все четыре items терминальны, P2.9 Completion Notes) · `research/11-p2-followup-audit-p1-round2.md`
(грунт блока: замеры провенанса, исправленные предикаты, дома долгов) ·
`research/10-p1-remediation-canon-and-coverage.md` · `research/05-instruction-canon-routing.md`
(матрица) · `brief/01-refinements.md` Р9/Р10 · `roadmap/instruction-authorize-order.md` (спека
дома долга order-sensitivity `--authorize`) · `packages/harness/docs/reference/instruction-canon.md`
(доки P2.7, механизм канона) · `packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json`
(105 литералов, `fixture_version` `1.1.2`) · `roadmap.md` (v0.10.0, 35 items) · `journal.jsonl`.

**Open risks:**
- **`plan-lint` WARN нового рода на `phases/P2.md`** (surfaced P2.6, подтверждён P2.7/P2.8,
  сохраняется после P2.9): DoR-чеклист фазы цитирует синтаксис маркера уточнения дословно в двух
  пунктах — как только статус фазы P2 покинул `⬜ Not started`, `plan-lint` читает цитату как
  открытый маркер. WARN, не ERROR — гейт `K=0` закрытия не задет; P2.9 не чинил (чужой предмет
  по её же Scope Excluded); правка — кандидат ближайшего design-захода.
- **Фраза-находка A7 (ложная посылка о неаудированности) осталась в двух местах `phases/P1.md`** вне `Files`
  P2.9 (историческая цитата аудита захода 2 + архивный launch-block «Что запускать») — см.
  Known Deviation выше; починка требует либо новой D-записи владельца о праве редактировать
  архивные секции аудита, либо остаётся историческим свидетельством навсегда.
- **Посторонний незакоммиченный дифф в дереве не убран и не тронут:** `roadmap/README.md` (M,
  строка спеки launch-block'а) + untracked `roadmap/2026.07.29-launch-block-command-row.md`.
  P2.8/P2.9 подтвердили живучесть — дифф на месте, не наш предмет.
- **Слепота `_validate_conflicts` к дублю СМЫСЛА** (`obligations` с самореферентным `object`,
  `instructions.py:1005-1022`): зелёный `validate_catalog()` НЕ доказывает отсутствия дубля
  common-правила внутри provider-extension. Дом правки — `roadmap/`, вне скоупа (Р8/Р10); спека
  ЗАХОДОМ НЕ ЗАВЕДЕНА — долг остаётся в этом списке.
- **Фикстурный `provenance` СОВМЕСТИМОСТИ не отражает миграцию P1.2** — нужен отдельный item со
  строкой `packages/harness/tests/test_instruction_compatibility.py` в `Files`; заходом не заведён
  (Р10), долг остаётся открытым.
- **Order-sensitivity `apply_instructions` к порядку `--authorize` (алфавитный по `target_path`)
  и неинформативная диагностика `INSTRUCTION_WRITE_FORBIDDEN` остаются НЕ починены** — P2.8 завёл
  только дом (`roadmap/instruction-authorize-order.md`), реализация отложена по критерию
  (следующий ложный отказ ИЛИ следующая содержательная правка `apply_instructions`).
- **Двенадцать корневых и пакетных руководств УПРАВЛЯЕМЫЕ**: ручная правка блоков между маркерами
  запрещена навсегда — только фрагменты + повторный прогон, иначе `managed-drift` на `[9/9]`.
- **Гейт `[9/9]` живёт только в `packages/harness/scripts/validate.sh`** — `analyst`/`task` в CI не
  покрыты вовсе (OQ-9); локальный прогон ≠ CI (R2).
- **`packages/skiller/scripts/validate.sh` на дереве КРАСНЫЙ** (долг P0.5, material-отклонение
  P1.5); `scripts/test-provider-docs.py` и `scripts/public-hygiene.py` — предсуществующе красные.
- **`vitepress build` в дереве не прогоняется** — `node_modules` отсутствуют; доки P2.7 проверены
  машинными проверками ссылок и регистрации, установка зависимостей вне скоупа item'а.
- **Аудит design-фазы исчерпан** — дефект в ТЗ P2.1–P2.5 и P3–P5 всплывёт на исполнении.
- **Маршруты мягче:** items с `effort high` идут через `plan-run` (D47) — строка
  `Session: <model>/<effort>` в отчёте и в Update Log обязательна.
- Общий state `~/.swissknifeman`/`~/.maind` изоляцией не покрыт — риск принят владельцем (D4).
- **P5.2 — единственная необратимая внутрь граница плана** (R1).
- Портируемость (`plan-portability-v1.md`): host-специфичные пути запрещены в
  `Inputs`/`Required Reads`/`Validation` — действует на P5.1–P5.3.

**Workarounds/Deferred/Open questions:**
- workarounds: правка общего `plans/verify-citations-known-exceptions.json` (D54) — дом
  design-коммит, не `Files` какого-либо item'а.
- deferred: правка `_validate_conflicts`/схемы `obligations` (кандидат `roadmap/`, Р8; спека не
  заведена) · починка order-sensitivity `apply_instructions` + диагностики
  `INSTRUCTION_WRITE_FORBIDDEN` (дом заведён P2.8 — `roadmap/instruction-authorize-order.md`,
  реализация отложена — D84) · фикстурный `provenance` P1.2 · изоляция общего state (OQ-5) ·
  тонкая обвязка супервизора (P4.1, D38) · round-trip гейт живым прогоном Codex · структурный
  перебор листинга Codex (OQ-7) · общий differ канона ролей (OQ-8) · машинные гейты
  PROMOTE-CANDIDATE («Validation прогнана» — четвёртый прецедент в P1, «design-заход в истории»
  D69) · `skiller registry` не прогнан (P0.5) · раскатка на потребителей (D45) · push/PR/тег и
  публикация доков (D41) · расширение CI на `analyst`/`task` (OQ-9) · русский канон скиллов в
  `.gitignore` (Р5) · раскатка adoption-режима на онбордженные проекты · удаление pre-image'ов
  P1.5 (держатся до архивации плана) · починка архивных упоминаний A7 в `phases/P1.md` (вне
  `Files` P2.9 — см. Open risks). **Снято из deferred:** docs-sync `harness
  instructions`/adoption/канона — закрыт P2.7; дом долга authorize-order — закрыт P2.8 (сам
  механизм остаётся deferred); бухгалтерские дефекты захода 2 — закрыты P2.9 (кроме двух
  архивных упоминаний A7 — новый Open risk).
- open_questions: OQ-3 две capability `unsupported` у обоих провайдеров (P2.1) · OQ-6 дом логики
  Codex-обработчиков (P2.1) · OQ-7 структурный перебор бюджета обнаружения (P3.4) · OQ-8 дрейф
  канона ролей (Deferred) · OQ-9 CI не покрывает `analyst`/`task` (Deferred). OQ-2 закрыта D71,
  OQ-1 закрыта D31, OQ-4 закрыта D27. Блок follow-up новых открытых вопросов не добавил (все
  развилки закрыты D80–D85 по режиму Р6/D14).
