# HANDOFF — 2026-07-26 — after P2.10

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.11

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `—` |
| Context | `same-session — item` |
| Model | Claude Sonnet 5 |
| Thinking | `high` |
| Суть | Замкнуть границу pre-final: бинарный гейт (`n/a` — красное, не зелёное), маршрут ИСПОЛНИТЕЛЯ на pre-final по лестнице D75, исполняемая граница в шаге 7 `plan-exec.md`, тест на РАЗЛИЧАЮЩИЙ предикат (D79), `plan-protocol@2.14.0`/`skiller@0.7.0`/`task@0.9.0`. Второй из двух ремонтных items разбора D75–D79; закрывает `P2.10 → P2.11 → P2.8 → P2.9` до P2.8 |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P2.11

РЕЖИМ: исполнение нового item'а (не реопен, не детализация) — ТЗ P2.11 доведено до DoR
  design-заходом 2026-07-26, развилки закрыты D75–D79.
ВХОД: `plans/2026.07.24-AGENT-RELIABILITY/research/08-pre-final-boundary-semantics.md`
  §§1–5, §7 → cold-start read ПЕРВЫМ; затем `findings/14-write-site-boundary-measurement.md`
  целиком и `plan.md` §5 D75–D79.
СКОУП: 1) `plan-close.md` шаг 4 — бинарный гейт `pre_mutation == "allow" and pre_final ==
  "allow"`, `n/a` — строка код→действие с дословной расшифровкой контракт-SSOT (сессия
  заблокирована, объявлять сдачу нечего), НЕ зелёное; 2) маршрут на pre-final — маршрут
  ИСПОЛНИТЕЛЯ по лестнице D75 (Completion Notes → журнал `actor` → неразрешимо/расхождение
  = СТОП с ПРОХОДОМ), не пин закрывающей команды; 3) `plan-exec.md` шаг 7 получает тот же
  исполняемый вызов границы pre-final (шаг 2 не трогается); 4) `plan-run.md` — синхронизация
  третьего отличия (сессионный маршрут И ЕСТЬ маршрут исполнителя); 5) `plan-audit.md` —
  чек-строка на напечатанные коды ОБЕИХ границ; 6) в обоих чекпоинтах названа граница
  предиката (`pre_final` — свойство ФОРМЫ спеки, не факт исполнения); 7) §13 канона (RU+EN)
  переписан под починенный факт → `plan-protocol@2.14.0`; 8) литеральный тест на
  РАЗЛИЧАЮЩИЙ предикат (D79 — каждый новый ассершен обязан краснеть на СТАРОМ тексте
  команды, `git show d11c3b74:<path>`, `git stash` запрещён для команд); 9) публикация
  `plan-protocol@2.14.0`/`skiller@0.7.0`/`task@0.9.0` по ритуалу P2.2/P2.7; 10)
  self-conformance на ≥3 items ЭТОГО плана (один 🟢, один 🟠 — P2.10 годится, текущий) И
  ≥1 легаси-плане корня.
НЕ ТРОГАТЬ: `packages/task/lib/**` (владелец — P2.10, уже закрыт: расхождение с
  производителем — D#-запись и реопен P2.10, не тихая правка здесь); `plan-exec.md` шаг 2
  (pre-mutation — работает честно, анти-скоуп владельца); замороженную схему/лестницы P0.2
  и провайдерскую ось (D73); tiered-portability lint и D69; `repository-bootstrap@0.2.0` и
  его root-проекции (read-only); `remediation-map.json`; `assert_generated_scope.py`;
  `artifacts/P2.5/**` (P2.8); бухгалтерию закрытых items (P2.9); fresh-subagent dispatch
  (P3.4); F9; docs-sync `packages/task/CLAUDE.md` (владелец P3.1); статус P2.7 (уже
  пересчитан этим design-заходом). Чужие планы FOREMAN/ECO-OPT.
```

> **Строгая последовательность ремонта: P2.6 → P2.7 → P2.10 → P2.11 → P2.8 → P2.9.**
> P2.11 без P2.10 чинил бы предикат, который всё равно падает `ValueError` на планах корня
> без легаси-заголовка в закрытом наборе — теперь P2.10 терминален, гейт не заблокирован.
> P2.8/P2.9 читают канон, который до P2.11 сильнее факта. Фоновый workflow-скрипт
> `workflows/wf-agent-reliability-p2-7-9-remediation.js` (не запускался, не проверялся)
> НЕ применим — он написан под старую последовательность P2.7→P2.8→P2.9.

**Done:**

- **P2.6 закрыт 🟢 Done** (item-коммит `a13614db`): `task_contract.build`/`bundle_lint`,
  `review_policy.LoopBudget.from_committed`, `canonical_actor` с моделью (D72), `task@0.6.0`.
- **P2.7 закрыт 🟠 Done with deviations** (item-коммит `d11c3b74`): write-site pre-mutation в
  `plan-exec.md`, `plan-run.md`/`plan-audit.md`, `snippets/source-evidence-template.md`, §13
  канона + литеральный тест, публикация `plan-protocol@2.13.0`/`skiller@0.6.0`/`task@0.7.0`.
  Material-отклонение: из двух чекпоинтов fail-closed только один — детали `phases/P2.md`
  P2.7 Known Deviations.
- **Design-заход 2026-07-26:** перепрогнал дефект review, измерил три новых
  (`findings/14`, М1–М6), закрыл пять развилок D75–D79, завёл items P2.10/P2.11
  (`research/08`).
- **P2.10 закрыт 🟠 Done with deviations** (item-коммит `668012bd`): закрытый набор
  заголовков §3 Routing (канон + легаси `Model/effort`/`Model/Effort`), имя провайдерской
  модели → класс ТОЛЬКО по committed `command-routing.json::class_selectors`, типизированный
  отказ вместо `ValueError` по обеим осям и обеим сторонам маршрута (D74/D78 закрыты со
  стороны производителя), 11 новых тестов (все 10 поведенческих — красные на дереве
  `d42886a8`), закоммиченный probe `routing_form_coverage.py` (BASELINE 6 `EXC`/5
  `typed`/3 `ok` → AFTER 0 `EXC`/5 `typed`/9 `ok`), `task@0.8.0`. Material-отклонение:
  item-коммит несёт диф вне `Files` (`test_route_evidence.py` — companion-фикс двух
  ассершенов/докстринга под новое defense-in-depth поведение `pre_mutation`, тот же
  D69-прецедент) — детали `phases/P2.md` P2.10 Known Deviations.

**Remaining:**

- **P2.11** ⬜ — ПЕРВЫЙ следующий шаг (этот launch-block). Гейт `== "allow"` на обеих осях,
  маршрут исполнителя на pre-final, исполняемая граница в шаге 7 `plan-exec.md`, тест на
  различающий предикат, `plan-protocol@2.14.0`/`skiller@0.7.0`/`task@0.9.0`.
- **P2.8** ⬜ — заблокирован P2.11: закоммиченный детерминированный генератор
  транскриптов, перепрогон замороженного банка P2.5, честный `covered`.
- **P2.9** ⬜ — последний: бухгалтерия F6, F7, F10–F15 без мутаций кода.
- После терминальных P2.6–P2.11 — `task:plan-close … P2` (снимает маркер «УСТАРЕЛ»,
  пересобирает Phase Handoff), затем аудит фазы **заход 2/2**.
- **P3–P4** ⬜ — не стартуют до терминальной P2.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.16.1), §3 Routing (строки P2.6–P2.11), §4 Status Board
  (P2 = `4/11 🟡 In progress`), §5 D75–D79, §7 Contracts (строка `task` plugin/routing
  v0.7.0 → v0.8.0, committed P2.10).
- `findings/14-write-site-boundary-measurement.md` — измерения М1–М6 с командами и якорем
  дерева `c215bd04`.
- `research/08-pre-final-boundary-semantics.md` — семантика границы, раскладка P2.10/P2.11,
  pre-mortem (7 причин провала с митигациями).
- `phases/P2.md` — ТЗ P2.11 целиком; P2.10 Completion Notes/Known Deviations (BASELINE/AFTER
  probe-числа, компаньон-дифф `test_route_evidence.py`); блок `## Audit P2 — 2026-07-26`.
- `roadmap.md` — carrier'ы P2.6–P2.11; `journal.jsonl` — прогоны.
- **Дерево, на которое смотрит этот handoff (D55): item-коммит `668012bd`** — bookkeeping
  этого закрытия коммитится СЛЕДОМ (шаг 6, plans/-carve-out); холодная сессия стартует с
  committed-дерева после bookkeeping-коммита.

**Open risks:**

- **Окно ложной гарантии в опубликованном каноне** сузилось, но не закрылось: `§13` всё ещё
  материально неполон до P2.11 (D76 `n/a`-зелёный, D77 непересечённая граница на штатном
  пути) — теперь по крайней мере вызов не падает `ValueError` на большинстве планов корня.
  Ускорить нечем — P2.11 обязателен следующим.
- **Третий рецидив F1 = incident.** §2 Execution Rules: P2.10/P2.11 — ВТОРОЙ и последний
  ремонт этой находки. Следующий рецидив открывается решением владельца как incident.
- **Cap аудитов.** `## Audit P2` — заход 1 из двух.
- **Дрейф генерируемых деревьев вне owner-карты.** P2.10/P2.11 (как P2.6–P2.9) отсутствуют в
  `remediation-map.json::baseline_owners` → `assert_generated_scope.py` не запускается;
  компенсация — ручная сверка `git show --stat <item-коммит>` против `Files` (выполнена для
  P2.10 — 11 файлов, точное подмножество `Files` + один названный компаньон).

**Workarounds / Deferred / Open questions:**

- **F9 (Minor) не чинится** — вне скоупа реопена, названный долг с `PROMOTE-CANDIDATE`.
- **Обобщение D79** — `PROMOTE-CANDIDATE` в канон `plan-protocol`; владелец продвижения —
  отдельная D-запись после терминального P2.11.
- **Fresh-subagent dispatch** — недоставленная позиция Scope P2.2; владелец — **P3.4**.
- **Docs-sync `packages/task/CLAUDE.md`** — долг остаётся, владелец **P3.1**.
- **`plan.md` §4, строка фазы P0** — предсуществующий дефект бухгалтерии P0.4, владелец —
  `task:plan-close … P0`.
- **WARN `plan-lint` на `plan.md`** (длина строки Update Log P1.4) — предсуществующий, не
  блокер.
