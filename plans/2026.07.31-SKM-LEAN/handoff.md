# HANDOFF — 2026-08-01 — after P4.3

**Next:** manual: `implementation/high` — P4.4 `Exec = manual` (`plan.md` §3, `roadmap.md`
строка P4.4: solo, батч запрещён критерием §9 — P4.4/P4.6 сцеплены с ним по данным).

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | `gate` — `plan-lint` + git-проверка двух коммитов → три исхода (GREEN/ATTENTION/RED) |

````
Прочитай plans/2026.07.31-SKM-LEAN/phases/P4.md item P4.4 целиком (Intent, Why, Scope
Included/Excluded, Inputs, Files, Required Reads, Implementation Rules, Code Guidance,
Validation, Deliverables) и исполни его строго по ТЗ. ПЕРВЫМ Required Read —
plans/2026.07.31-SKM-LEAN/root/contracts/driver-plan-protocol-v2.md §«событие → класс
вердикта» и §якорей breaking-детекта. Пометь item 🟡 In progress до начала практической
работы, затем закрой по правилам plan-protocol (Task Contract pre-mutation/pre-final,
Completion Notes, Known Deviations, журнал, два коммита).
````

**Done:** Этим заходом — **P4.3** (`worker`, `manual`-путь, сессия sonnet/high), третий
item фазы P4.

- Реализован `packages/harness/lib/harness/run/worker.py` (item-коммит **`cbb3a5d9`**) —
  запуск ОДНОГО item'а процессом `claude -p "/task:plan-exec <ID> <Pn.m>" --output-format
  json` под таймаутом: argv собирается одной функцией (`build_argv`) из
  committed-носителя `packages/task/configs/command-routing.json` (селекторы модели/effort
  и шаблон инвокации, конкретные имена моделей в модуле не хардкодятся), таймаут —
  константа модуля (30 минут, обоснование в докстринге), `claude --version` фиксируется
  ДО прогона.
- Дефенсивный разбор JSON-конверта в закрытый enum исходов ПРОГОНА (не вердикт по
  item'у — это P4.4): `ok` / `transport` / `timeout` / `quota` / `error`. Успех РОВНО
  `type=="result"` И `is_error==false` И exit 0 (донорское правило, единственное
  унаследованное дословно). Битый/пустой/не-`result` JSON и любое НЕИЗВЕСТНОЕ сочетание
  полей → `transport` с честной причиной (догадка о классе запрещена).
- Фейковый бинарь `tests/fixtures_data/run/fake-claude/` — 6 сценариев (success ·
  transport-broken-json · transport-empty · timeout · quota · permission-denials);
  `permission_denials` непустой → исход остаётся `ok`, поле пробрасывается наружу.
- **Один настоящий прогон на 2.1.220** (`worker.run("sample-plan", "P1.1", …)`, фикстура
  P4.2, `packages/task/configs/command-routing.json` реальный) — envelope: `type=result` ·
  `is_error=False` · `subtype=success` · `exit=0` · `session_id=c14cd420-…` ·
  `total_cost_usd=0.2518689` · `num_turns=3` · `client_version=2.1.220 (Claude Code)`.
  Слэш-команда `/task:plan-exec` через `-p` РАБОТАЕТ на боевом провайдер-нейтральном
  инвойсе (расширяет наблюдение P4.1 за пределы `/core:compact-responses`); `--effort`
  принят без ошибки — **U3 закрыт наблюдением**: флаг применяется в неинтерактивном `-p`
  (сессия завершилась штатно, отказа по неизвестному флагу нет). Прогон целился в
  несуществующий план (`sample-plan` не под `plans/`) — воркер получил штатный
  `ROUTING-BLOCKED`-ответ модели, файловых изменений не произвёл (`git status` до/после
  идентичны за вычетом этого захода).
- **U1/U2 остаются `[UNVERIFIED]`** — боевая квота и реальные коды сбоя клиента этим
  заходом не воспроизводились (наблюдение единственного успешного прогона их закрыть не
  может); адрес закрытия не меняется (первое боевое наблюдение бампает контракт).
- `bash packages/harness/scripts/test.sh` — **573 теста**, зелёный (11 новых
  `test_run_worker.py`); `validate.sh` — `OK`; `grep -rn "sonnet\|opus\|haiku"
  packages/harness/lib/harness/run/worker.py` — пусто (селекторы не захардкожены).
- Task Contract (D76): `pre_mutation: allow`, `pre_final: allow` (actual_route
  `implementation/high`, `source=self-attested`, `model=sonnet`).

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠, терминальна) · **P4 3/6
(🟡 In progress)** · P5 0/9 (⬜) · P6 0/3 (⬜) · P7 0/4 (⬜). Всего 38 items. Следующий —
**P4.4** (`gate`), далее строго последовательно P4.5 → P4.6: items фазы сцеплены по
данным, оркестрация не заявлена.

**Sources of truth:** `packages/harness/lib/harness/run/worker.py` (реализация) ·
`plans/2026.07.31-SKM-LEAN/root/contracts/driver-plan-protocol-v2.md` (§6 конверт, §9
`[UNVERIFIED]`) · `phases/P4.md` P4.3 Completion Notes · `plan.md` §4 доска, §6 Update
Log, `## 0. Meta` · `roadmap.md` (маршрут P4.4 — `Exec = manual`, solo) · `journal.jsonl`.

**Open risks:** без изменений по содержанию от предыдущего handoff, кроме закрытия
пункта про P4.3, плюс:

- **U1/U2 контракта остаются `[UNVERIFIED]` с адресом «первое боевое наблюдение»** — P4.3
  закрыл ТОЛЬКО U3 (применимость `--effort`); U1 (конверт при исчерпании квоты) и U2
  (exit-коды на сбоях) не воспроизводились намеренно (нет способа безопасно форсировать
  боевую квоту/сбой клиента) — при первом реальном наблюдении контракт бампается, а не
  подгоняется заранее.
- **Контракт пинован на `06fefc87`, канон живёт своей жизнью** — перед волной сверяются
  три строки (версия скилла, `git rev-parse HEAD`, `claude --version`); расхождение —
  сверить шесть якорей §8 и бампнуть контракт, невозможность сверить — стоп и эскалация.
  Этим заходом сверено: скилл `2.22.0` (= пин), клиент `2.1.220` (= пин), `git rev-parse
  HEAD` разошёлся (ожидаемо — репозиторий продвинулся штатными item-коммитами P4.2/P4.3,
  ни один из шести якорей §8 контракта не затронут).
- **Два WARN линтера по фазе P4** — латентные ложные срабатывания на ТЕКСТЕ фазы (без
  изменений от предыдущего захода): DoR-строка с буквальной формой маркера-плейсхолдера
  `phases/P4.md:67`; `оркестрац` без понимания отрицания в `:87` и в `Required Reads`
  P4.6. Адрес — `plan-close <ID> P4` либо отдельный fix-item.
- **`worker.py` — единственный источник знания о `command-routing.json` в драйвере** —
  любой новый факт о провайдер-маршрутизации без источника из committed-носителя обязан
  править контракт P4.1, а не расширять `worker.py` вторым чтением того же файла другим
  способом.
- (в силе) остаток `desc-trigger-burndown.txt` 61 запись · 221/229 скиллов без тиров
  `model:`/`effort:` · `paths:` не раскатан (D98) · `disable-model-invocation` только на 4
  пилотных · 14 файлов evals-заглушек · **OQ-9** (`ACCEPTANCE_NOT_PUBLIC` против D77,
  владелец вне плана) · долг **D90** · 3 дефекта в `snippets/` `devops/db-test-preflight`
  · кандидаты под `context: fork` отложены · конфликт правил в ТЗ P3.6 · токен
  `contradictory evidence` вне enum §10 · дефект генератора `.mcp.json.example` ·
  path-scoped rules только на пилоте `dterema/app` · `resolve_active_set` слеп к плагинам
  · Boost/`.ai`-CLAUDE.md флот не покрыт P2.2 · пять секций-кандидатов P2.1 резидентны
  (D89) · гейт размера файла целиком · токенная оценка продублирована в двух пакетах ·
  `closure/P1.json` hash устарел (D87) · остаточная находка `verify-citations` в
  `phases/P2.md` (P2.3).
- **В рабочем дереве есть чужой дифф** (`.gitignore`, удалённый
  `RESEARCH/AUDIT-loqum-findings.md`, неотслеживаемые `.swissknife/`, `audits/`) — этим
  заходом не тронут и не коммитился.

**Workarounds/Deferred/Open questions:** обходных приёмов этим заходом не применялось.
Отложено контрактом явно: U1/U2 (боевое наблюдение), экономика волны (U5 → P4.6),
Codex-водитель (U4 → вне плана, D9). Новых open questions не заведено; открытых остаётся
**три** — OQ-3 · OQ-6 · OQ-8 — плюс OQ-9 (владелец протокола, вне этого плана).
