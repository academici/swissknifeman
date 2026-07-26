# HANDOFF — 2026-07-26 — after P2.7

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.10

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `—` |
| Context | `same-session — item` |
| Model | Claude Sonnet 5 |
| Thinking | `high` |
| Суть | Компилятор перестаёт ронять `ValueError` и подставлять пустой `required`: закрытый набор заголовков §3 (легаси-форма действующая по §9), имя модели → класс по committed-карте, типизированный отказ, probe охвата, `task@0.8.0`. Первый из двух ремонтных items разбора D75–D79; P2.11 стартует только после него |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P2.10

РЕЖИМ: исполнение нового item'а (не реопен, не детализация) — ТЗ P2.10 доведено до DoR
  design-заходом 2026-07-26, развилки закрыты D75–D79.
ВХОД: `plans/2026.07.24-AGENT-RELIABILITY/findings/14-write-site-boundary-measurement.md`
  (М4/М4.1 — дословный traceback и таблица охвата 11/14) → cold-start read ПЕРВЫМ; затем
  `research/08-pre-final-boundary-semantics.md` §4/§5/§7 и `plan.md` §5 D78.
СКОУП: 1) `_find_routing_row` — закрытый литеральный набор заголовков колонки маршрута
  (`Model class/effort` + легаси `Model/effort`, `Model/Effort`), без фаззи-матчинга;
  2) неразбираемая ячейка → `TaskContractBuildError` с item'ом/полем/значением, пустая пара
  в контракт не попадает никогда; 3) имя модели → класс ТОЛЬКО по committed-карте
  `command-routing.json::mappings.*.class_selectors` через `command_catalog.load_routing_metadata`
  (собственный словарь имён запрещён); 4) `_rank` перестаёт быть источником `ValueError` по
  обеим осям и обеим сторонам маршрута — проверка лестницы ДО предиката, `try/except` вокруг
  `_rank` как ремонт запрещён; 5) probe `artifacts/P2.10/routing_form_coverage.py` (exit 1 на
  любом `EXC`); 6) `task@0.8.0` с полной регенерацией по ритуалу P2.6.
НЕ ТРОГАТЬ: `packages/task/commands/**` и канон `plan-protocol` (владелец — P2.11);
  замороженную схему `task-contract-v1` и лестницы P0.2; содержимое `class_selectors`;
  §3 Routing чужих планов корня (FOREMAN, `plans/archive/**` — компилятор подстраивается под
  канон §9, а не планы под компилятор); tiered-portability lint и D69; `remediation-map.json`;
  `artifacts/P2.5/**` (P2.8); бухгалтерию закрытых items (P2.9); статус P2.7 (уже пересчитан).
  `assert_generated_scope.py` НЕ запускать, `base-sha.txt` НЕ создавать.
```

> **Строгая последовательность ремонта: P2.6 → P2.7 → P2.10 → P2.11 → P2.8 → P2.9.**
> P2.11 без P2.10 чинит предикат, который всё равно падает `ValueError` на 11 из 14 планов
> корня; P2.8/P2.9 читают канон, который до P2.11 сильнее факта. Фоновый workflow-скрипт
> `workflows/wf-agent-reliability-p2-7-9-remediation.js` (не запускался, не проверялся)
> НЕ применим — он написан под старую последовательность P2.7→P2.8→P2.9.

**Done:**

- **P2.6 закрыт 🟢 Done** (item-коммит `a13614db`): `task_contract.build`/`bundle_lint`,
  `review_policy.LoopBudget.from_committed`, `canonical_actor` с моделью (D72), `task@0.6.0`.
- **P2.7 закрыт 🟠 Done with deviations** (item-коммит `d11c3b74`; был `🔴 Blocked` —
  эскалация РАЗРЕШЕНА этим design-заходом, D75–D79). Доставлено и НЕ откатывается: write-site
  pre-mutation в `plan-exec.md`, `plan-run.md`/`plan-audit.md`, `snippets/source-evidence-template.md`,
  §13 канона + литеральный тест, публикация `plan-protocol@2.13.0`/`skiller@0.6.0`/`task@0.7.0`
  (регенерация no-op на `--check`). Material-отклонение: из двух чекпоинтов fail-closed только
  один — детали в `phases/P2.md` P2.7 Known Deviations.
- **Design-заход 2026-07-26 (этот):** перепрогнал дефект review и измерил три новых
  (`findings/14`, М1–М6); закрыл пять развилок D75–D79; завёл items **P2.10** (`lib/**`) и
  **P2.11** (команды/канон/тест/публикация); синтез — `research/08`. Мутаций кода нет.

**Remaining:**

- **P2.10** ⬜ — ПЕРВЫЙ следующий шаг (этот launch-block). Типизированный отказ компилятора и
  легаси-форма §3; `task@0.8.0`.
- **P2.11** ⬜ — заблокирован P2.10. Гейт `== "allow"` на обеих осях, маршрут исполнителя на
  pre-final, исполняемая граница в шаге 7 `plan-exec.md`, тест на различающий предикат,
  `plan-protocol@2.14.0`/`skiller@0.7.0`/`task@0.9.0`.
- **P2.8** ⬜ — заблокирован P2.10/P2.11: закоммиченный детерминированный генератор
  транскриптов, перепрогон замороженного банка P2.5, честный `covered`.
- **P2.9** ⬜ — последний: бухгалтерия F6, F7, F10–F15 без мутаций кода.
- После терминальных P2.6–P2.11 — `task:plan-close … P2` (снимает маркер «УСТАРЕЛ»,
  пересобирает Phase Handoff), затем аудит фазы **заход 2/2**.
- **P3–P4** ⬜ — не стартуют до терминальной P2.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.16.0), §3 Routing (строки P2.6–P2.11), §4 Status Board
  (P2 = `4/11 🟡 In progress`), §5 **D75–D79**, §7 Contracts (строка `plan-protocol@2.13.0`
  помечена «материально неполно до P2.11»).
- `findings/14-write-site-boundary-measurement.md` — измерения М1–М6 с командами и якорем
  дерева `c215bd04`: репро `("allow","n/a")`, охват 11/14 планов корня, непересечённая граница
  на штатном пути, слепой литеральный тест.
- `research/08-pre-final-boundary-semantics.md` — семантика границы, отклонённые варианты B/C,
  раскладка P2.10/P2.11, pre-mortem (7 причин провала с митигациями).
- `phases/P2.md` — ТЗ P2.10/P2.11 целиком; P2.7 Known Deviations (что именно недоставлено);
  блок `## Audit P2 — 2026-07-26` (15 находок).
- `roadmap.md` — carrier'ы P2.6–P2.11 в исполнительском порядке; `journal.jsonl` — прогоны.

**Open risks:**

- **Окно ложной гарантии в опубликованном каноне.** `plan-protocol@2.13.0` уже раздаётся флоту
  через `general`/`core` и утверждает «fail-closed on any code other than `allow`» — факту не
  соответствует до P2.11 (D76), а на 11 из 14 планов корня вызов вообще падает `ValueError`
  (D78). Пока окно открыто, downstream-читатель получает гарантию сильнее факта; сужается
  только терминальным P2.11, ускорить нечем — порядок P2.10 → P2.11 обязателен.
- **Третий рецидив F1 = incident, а не четвёртый fix loop.** §2 Execution Rules: P2.10/P2.11 —
  ВТОРОЙ и последний ремонт этой находки. Следующий её рецидив открывается решением владельца
  как incident, а не как P2.12.
- **Cap аудитов.** `## Audit P2` — заход 1 из двух. Design-заходы и review-заходы cap не
  расходуют; третий аудит-заход — решение, не автоматический раунд.
- **Дрейф генерируемых деревьев вне owner-карты.** P2.10/P2.11 (как P2.6–P2.9) отсутствуют в
  `remediation-map.json::baseline_owners` → `assert_generated_scope.py` не запускается;
  компенсация — ручная сверка `git show --stat <item-коммит>` против `Files`.

**Workarounds / Deferred / Open questions:**

- **F9 (Minor) не чинится** — вне скоупа реопена, названный долг с `PROMOTE-CANDIDATE`.
- **Обобщение D79** («ассершен на наличие идентификатора не защищает утверждение о поведении»)
  — `PROMOTE-CANDIDATE` в канон `plan-protocol`; в этот заход не выносится, чтобы не расширять
  поверхность правки канона; владелец продвижения — отдельная D-запись после терминального P2.11.
- **Fresh-subagent dispatch** остаётся недоставленной позицией Scope P2.2; владелец — **P3.4**.
- **Docs-sync `packages/task/CLAUDE.md`** (не описывает write-site и compiler-модули P2.2–P2.7)
  — долг остаётся, владелец **P3.1**; в P2.10/P2.11 НЕ подбирается (чужая поверхность, И2).
- **`plan.md` §4, строка фазы P0** — `🟡 In progress` при четырёх терминальных items —
  предсуществующий дефект бухгалтерии P0.4, владелец — `task:plan-close … P0`.
- **WARN `plan-lint` на `plan.md`** (длина строки Update Log P1.4) — предсуществующий, чужой
  владелец, не блокер.
