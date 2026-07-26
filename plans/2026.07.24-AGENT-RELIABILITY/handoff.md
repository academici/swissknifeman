# HANDOFF — 2026-07-26 — after P2.11

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.8

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `—` |
| Context | `same-session — item` |
| Model | Claude Sonnet 5 |
| Thinking | `high` |
| Суть | Сделать доказательство P2.5 (30/31) воспроизводимым: закоммиченный детерминированный генератор транскриптов, перепрогон замороженного банка от committed-входов, машинный провенанс входа в манифесте, честный `covered`. Третий из четырёх ремонтных items разбора реопена — закрывает `P2.10 → P2.11 → P2.8 → P2.9` |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P2.8

РЕЖИМ: исполнение ремонтного item'а реопена P2 (D70) — ТЗ доведено до DoR design-заходом
  2026-07-26 (реопен), Owner authority E/D50 (`G-EXEC` выдан для self-host P0–P3).
ВХОД: `plans/2026.07.24-AGENT-RELIABILITY/research/07-p2-reopen-remediation.md` §4.3 (ПЕРВЫМ);
  затем `phases/P2.md` § `## Audit P2 — 2026-07-26` находки F3/F4 целиком, P2.5 item целиком
  (Scope, Code Guidance с двенадцатью категориями, Completion Notes, Known Deviations),
  `findings/P2.5-scenario-results.md`.
СКОУП: 1) закоммитить детерминированный генератор транскрипт-сета в `artifacts/P2.5/` (читает
  РЕАЛЬНЫЕ seam'ы — `task.task_contract`, `task.review_policy`, `task.route_evidence`,
  `task.command_catalog`/`command_render` — воспроизводит поведение, а не подгоняет результат;
  два прогона подряд дают побайтово идентичный `transcripts.json`); 2) перепрогнать
  `run_bank.py candidate` от закоммиченного входа, зафиксировать ФАКТИЧЕСКУЮ цифру как есть
  (30/31 подтвердится или изменится — оба исхода корректны, подгонка запрещена); 3) машинный
  провенанс входа в `result-manifest.json` (путь генератора, sha256 `transcripts.json`,
  дерево-якорь), `verify_result_manifest.py` расширяется проверкой хеша; 4) честный `covered`
  для КАЖДОЙ из 12 категорий Code Guidance P2.5 (файл::функция предиката или снятие из
  «covered»); `portability-privacy-rawbulk` зеленеет ТОЛЬКО через реально работающий
  `task_contract.bundle_lint`; 5) обновлённый `findings/P2.5-scenario-results.md`.
НЕ ТРОГАТЬ: `artifacts/reliability-bank-v1/**` (банк/грейдеры/`run_bank.py`/манифест
  заморожены, D30, прямой запрет владельца); `artifacts/source-evidence/**`; пороги/floors
  (D15); `packages/**` (владельцы — P2.6/P2.7/P2.10/P2.11, уже терминальны); статус P2.5 или
  его Known Deviations по сужениям dispatch/temp-roots; F9; docs-sync `packages/task/CLAUDE.md`
  (владелец P3.1); бухгалтерия закрытых items (владелец P2.9, следующий item).
```

> **Строгая последовательность ремонта: P2.6 → P2.7 → P2.10 → P2.11 → P2.8 → P2.9.**
> P2.8 читает канон `plan-protocol@2.14.0`, который теперь материально ПОЛОН (P2.11 терминален) —
> кейсы `covered` могут ссылаться на границу pre-final честно. P2.9 — последний, бухгалтерия
> без мутаций кода. Фоновый workflow-скрипт
> `workflows/wf-agent-reliability-p2-7-9-remediation.js` (не запускался, не проверялся) НЕ
> применим — он написан под старую последовательность P2.7→P2.8→P2.9.

**Done:**

- **P2.6 закрыт 🟢 Done** (item-коммит `a13614db`): `task_contract.build`/`bundle_lint`,
  `review_policy.LoopBudget.from_committed`, `canonical_actor` с моделью (D72), `task@0.6.0`.
- **P2.7 закрыт 🟠 Done with deviations** (item-коммит `d11c3b74`): write-site pre-mutation в
  `plan-exec.md`, `plan-run.md`/`plan-audit.md`, `snippets/source-evidence-template.md`, §13
  канона + литеральный тест, публикация `plan-protocol@2.13.0`/`skiller@0.6.0`/`task@0.7.0`.
  Material-отклонение: из двух чекпоинтов fail-closed только один — устранено P2.11.
- **P2.10 закрыт 🟠 Done with deviations** (item-коммит `668012bd`): закрытый набор заголовков
  §3 Routing (канон + легаси `Model/effort`/`Model/Effort`), имя провайдерской модели → класс
  ТОЛЬКО по committed `command-routing.json::class_selectors`, типизированный отказ вместо
  `ValueError` по обеим осям и обеим сторонам маршрута (D74/D78 закрыты со стороны
  производителя), `task@0.8.0`. Material-отклонение: item-коммит нёс диф вне `Files`
  (`test_route_evidence.py` — компаньон-фикс) — детали `phases/P2.md` P2.10 Known Deviations.
- **P2.11 закрыт 🟢 Done** (item-коммит `abd53b4b`): бинарный гейт `pre_mutation == "allow" and
  pre_final == "allow"` (D76 — `n/a` НЕ зелёное) заменил `in ("allow", "n/a")`; маршрут
  `actual_route` на pre-final — маршрут ИСПОЛНИТЕЛЯ по лестнице D75 (Completion Notes →
  `journal.jsonl` → СТОП с ПРОХОДОМ), не пин закрывающей команды; `plan-exec.md` шаг 7
  (штатное самозакрытие) получил исполняемую границу, которой не было вовсе (М5); граница
  предиката `pre_final` названа в обоих чекпоинтах (D77); литеральный тест
  `TestPreFinalGateIsBinaryNotGreenlitByNA` — новый класс на РАЗЛИЧАЮЩИЙ предикат (D79), каждый
  ассершен проверен красным на committed-дереве до правки; публикация
  `plan-protocol@2.14.0`/`skiller@0.7.0`/`task@0.9.0`. Self-conformance на P2.1(🟢)/P2.10(🟠)/
  P2.11(текущий) + легаси-плане `2026.07.18-FOREMAN` P0.1 — все `allow`/`allow`, честно (не
  подогнано); регрессионный пробник подтвердил, что старый M1-дефект (`n/a` зеленит) теперь
  недостижим через штатный write-site. Без Known Deviations.

**Remaining:**

- **P2.8** ⬜ — ПЕРВЫЙ следующий шаг (этот launch-block). Закоммиченный детерминированный
  генератор транскриптов, перепрогон замороженного банка P2.5, честный `covered`.
- **P2.9** ⬜ — последний: бухгалтерия F6, F7, F10–F15 без мутаций кода.
- После терминальных P2.6–P2.11 (включая P2.8/P2.9) — `task:plan-close … P2` (снимает маркер
  «УСТАРЕЛ», пересобирает Phase Handoff), затем аудит фазы **заход 2/2**.
- **P3–P4** ⬜ — не стартуют до терминальной P2.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.16.2), §3 Routing (строки P2.6–P2.11), §4 Status Board
  (P2 = `5/11 🟡 In progress`), §5 D75–D79, §7 Contracts (строки `plan-protocol@2.14.0` и
  `task` plugin/routing v0.8.0 → v0.9.0, committed P2.11).
- `findings/14-write-site-boundary-measurement.md` — измерения М1–М6 с командами и якорем
  дерева `c215bd04`.
- `research/08-pre-final-boundary-semantics.md` — семантика границы, раскладка P2.10/P2.11,
  pre-mortem (7 причин провала с митигациями).
- `phases/P2.md` — ТЗ P2.8 целиком; P2.11 Completion Notes/Known Deviations (self-conformance,
  регрессионный пробник); блок `## Audit P2 — 2026-07-26`.
- `roadmap.md` — carrier'ы P2.6–P2.11; `journal.jsonl` — прогоны.
- **Дерево, на которое смотрит этот handoff (D55): item-коммит `abd53b4b`** — bookkeeping
  этого закрытия коммитится СЛЕДОМ (шаг 6, plans/-carve-out); холодная сессия стартует с
  committed-дерева после bookkeeping-коммита.

**Open risks:**

- **Окно ложной гарантии в опубликованном каноне закрыто.** §13 `plan-protocol@2.14.0`
  материально полон: гейт бинарен, `n/a` не зелёное, обе границы закрытия исполняемы — рецидив
  F1 в этом конкретном месте более не воспроизводится (self-conformance + регрессионный
  пробник P2.11 Completion Notes).
- **Третий рецидив F1 = incident.** §2 Execution Rules: P2.10/P2.11 — ВТОРОЙ и последний
  ремонт этой находки, оба терминальны. Следующий рецидив открывается решением владельца как
  incident, а не третьим ремонтным item'ом.
- **Cap аудитов.** `## Audit P2` — заход 1 из двух.
- **Дрейф генерируемых деревьев вне owner-карты.** P2.11 (как P2.6–P2.10) отсутствует в
  `remediation-map.json::baseline_owners` → `assert_generated_scope.py` не запускается;
  компенсация — ручная сверка `git show --stat <item-коммит>` против `Files` (выполнена для
  P2.11 — 35 файлов, точное подмножество `Files`, без companion-коммита).

**Workarounds / Deferred / Open questions:**

- **F9 (Minor) не чинится** — вне скоупа реопена, названный долг с `PROMOTE-CANDIDATE`.
- **Обобщение D79** — `PROMOTE-CANDIDATE` в канон `plan-protocol`; владелец продвижения —
  отдельная D-запись после терминального P2.11 (терминален — открыт вопрос продвижения).
- **Fresh-subagent dispatch** — недоставленная позиция Scope P2.2; владелец — **P3.4**.
- **Docs-sync `packages/task/CLAUDE.md`** — долг остаётся, владелец **P3.1**.
- **`plan.md` §4, строка фазы P0** — предсуществующий дефект бухгалтерии P0.4, владелец —
  `task:plan-close … P0`.
- **WARN `plan-lint` на `plan.md`** (длина строки Update Log P1.4) — предсуществующий, не
  блокер.
