# HANDOFF — 2026-07-25 — after P1

`P1` в заголовке — реопен фазы P1 по §3 plan-protocol (bounded repair A3 под
Owner authority E, D50). Ни один item не исполнялся: все 22 остаются
`⬜ Not started`. **Изменилось главное: `G-EXEC` выдан** (D50) — исполнение
self-host P0–P3 больше не требует отдельного человеческого гейта.

**Committed post-repair tree: `7d597c696089fc6ee4372a22c2336212be39a9a0`**
(bookkeeping-коммит D55: весь ремонт v1.9.0 + v1.10.0 вместе с
`findings/10`–`findings/13`; этот файл проставляет его хеш вторым коммитом
ровно одного файла — собственный хеш в собственный коммит не вписать). Любая
холодная сессия работает от этого коммита, а не от рабочего дерева.

**Next:** exec-items: task:plan-exec 2026.07.24-AGENT-RELIABILITY P0.1

| Параметр | Значение |
|:--|:--|
| Model class | implementation (Claude `sonnet` · Codex `gpt-5.6-terra`) |
| Effort | medium |
| Capabilities | `command.subagents` |
| Context | `NEW SESSION` |
| Суть | Первый исполняемый item плана: проверить immutable bundle всеми четырьмя режимами, выдать item-owned semantic proof-class отчёт, записать `artifacts/P0.1/pre-plan-sha.txt` (D45) |

````
/task:plan-exec 2026.07.24-AGENT-RELIABILITY P0.1
````

Codex-проекция того же carrier'а — `roadmap.md` § «P0.1 — verify immutable
integrity + semantic closure» (native `NEW SESSION` блок). Acting provider не
назначен ни одной authority: рендерер выбирается из §3 Routing.

**Done:** ремонт A3 F1–F6 + внедрение authority E —

- **D50 — authority E.** Владелец: «пакет разрабатывается ИИ для ИИ, участие
  минимальное, разруливай сам». Переписана §10: персональные слоты A0–A3 —
  исторические факты, а не механизм; действует канон «два аудита на фазу,
  третий → решение»; `G-EXEC` выдан для self-host P0–P3; G0 после P0.3
  принимает агент D-записью; за владельцем остаётся ровно **G1** в P4.3
  (tag/push/release, fleet и 17 подключённых проектов, consumer-репозитории,
  `2026.07.18-FOREMAN`). Обоснование: шесть RED и пять design pass при НУЛЕ
  исполненных items — воспроизведение на самом плане того failure mode, который
  план создан лечить.
- **F1 → D51.** Объявлен состав позитивной фикстуры P1.4: все publishable units
  репозиторного marketplace МИНУС ровно три донорских бакета (`general`,
  `research`, `oss-dev`), материализуется как
  `artifacts/P1.4/fixture-unit-set.json` с машинной сверкой. Девять пар
  `core`↔донор и `workflow-craft`↔`unit:general` — **диагностика D42, а не
  гейт**: доказываются отдельным негативным прогоном поимённо. Разбор четырёх
  вариантов состава — `research/04-p1.4-fixture-composition.md` (собственный
  перезамер: с донорами 10 коллизий, без доноров — 0).
- **F2 → D52.** `phases/P2.md` P2.2 и `phases/P4.md` P4.3 читают
  `repository-bootstrap@0.2.0` и **27** проекций; `0.1.0`/26 остались только
  там, где описывают состояние ДО P1.5.
- **F3 → D52.** Deliverables P1.4: **30** exactly-once IDs с обязательным
  выводом по формуле `13 + 1 + 6 + 6 + 4`; тест падает при расхождении формулы
  с фактическим каталогом.
- **F4 → D55.** Ремонт закоммичен (`7d597c69`), хеш проставлен здесь.
- **F5 → D53** (решено агентом, владельцу не выносилось). Метрика §8 —
  «0 в объявленной фикстуре»; живая пара `core`+`research` даёт диагностику с
  названным Owner-действием, а не floor. Правка user-owned enabled-множества
  осталась вне границ плана (D42).
- **F6.** Required Reads P1.4 #4 — Completion Notes P1.2/P1.3/**P1.5**.
- **DUAL-PROVIDER → D54.** §7 Consumed переклассифицирован в
  low-trust/verify-before-use; P1.2/P1.3/P1.5 обязаны доказывать поведение
  затронутых seam'ов характеризационным тестом на месте (Code Guidance + три
  Codex-carrier'а roadmap).

**Remaining:** вся исполнительская работа — 22/22 items `⬜`. Порядок фаз
P0 → P1 → P2 → P3 → P4; внутри P1 — P1.1 → P1.2 → P1.3 → **P1.5** → P1.4 (D41).
Первый шаг — P0.1.

**Sources of truth:** `plan.md` v1.10.0 (§2 Execution Rules, §5 D50–D55, §7, §9,
§10) · `phases/P0.md` (P0.1 pre-plan baseline) · `phases/P1.md` (5 items,
declared fixture P1.4) · `phases/P2.md` (P2.2 self-conformance) · `phases/P3.md`
(P3.4 `PRE_PLAN_SHA` + effort) · `phases/P4.md` (P4.3 G1 packet) · `roadmap.md`
(22 carriers, exec boundary) · `findings/13-design-audit-a3.md` ·
`findings/12-effective-collision-remeasure.md` ·
`research/04-p1.4-fixture-composition.md` · `brief/01-refinements.md`
§§ «Owner authority E» и «Решения ремонта A3» · `index.md` · `journal.jsonl`.

**Open risks:**
- **Ремонт A3 уходит в исполнение без седьмого независимого design-аудита** —
  принятый риск D50, назван в §9. Первая независимая проверка — канонический
  аудит фазы P0, а не ещё один design-заход. Если владелец хочет иначе, он
  говорит это до старта P0.1.
- **Толкование authority E шире буквы директивы.** Владелец сказал «разруливай
  сам»; из этого выведены `G-EXEC` для self-host, G0 агенту и снятие
  audit-рационирования. Толкование записано в D50 и `brief/01-refinements.md`
  дословно, чтобы его можно было отклонить одной фразой.
- **Три находки A2 не отремонтированы** (были вне authority D, остались вне
  скоупа A3-ремонта): порядок capture `base-sha` по D36 против канонического
  порядка `plan-exec`/`plan-run` — касается P1.2/P1.3/P1.5/P2.2/P2.3 одинаково;
  отсутствие workflow-carrier у заявленной автономной цепочки; `research/01–03`
  без ссылок на слой 1 и без RAG-маркеров.
- **Claude enabled-set не измерялся** read-only → класс `unknown`, не green
  (`findings/12`); Codex-измерение полное. Числа фикстуры для Claude
  (~205 identity) — repo-derived, не observed.
- P1.5 исполняется ПЕРЕД P1.4 при монотонной нумерации — риск, что холодный
  исполнитель возьмёт следующий item по номеру; смягчено fail-closed Inputs
  P1.4, порядком в Карте/Phase Status/§3 Routing и текстом в Title.
- Чужой незакоммиченный дифф (архив-переносы старых планов + `tmp/`) и
  параллельный план `2026.07.25-ECO-OPT` живут рядом; foreign-commit атрибуция
  (D47) описана, но ещё не исполнена — первый реальный прогон будет в P1.2.

**Workarounds/Deferred/Open questions:**
- workarounds: —;
- deferred (названный долг, старт не блокирует): три находки A2; A1 **F11**
  (нет готового launch-block'а для acting provider вне Codex-проекций;
  неидемпотентность шага (0) описана только через D36); зеркальная
  `Consumed`-строка в `plans/2026.07.25-ECO-OPT`; Claude-проекция
  `workflow-craft` (нужен `skiller budget --first-turn`); read-only измерение
  Claude enabled-set; `findings/P1.5-collision-closure.md` вне Required Reads
  P2.1/P2.5/P3.4 (их ТЗ вне скоупа ремонта);
- open_questions: —.
