# HANDOFF — 2026-07-26 — after P2.8

**Next:** /task:plan-exec 2026.07.24-AGENT-RELIABILITY P2.9

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `medium` |
| Capabilities | `—` |
| Context | `continue (/clear) — ручной item` |
| Model | Claude Sonnet 5 |
| Thinking | `medium` |
| Суть | Свести запись фазы P2: почини неисполнимый литерал Validation P2.4 №3, дострой неотчитанные пункты, назови пропущенные отклонения (F6/F7/F10–F15), свяжи коммиты с items. Последний ремонтный item реопена — бухгалтерия без мутаций кода |

```
/task:plan-exec 2026.07.24-AGENT-RELIABILITY P2.9
```

**Done:**

- **P2.6 закрыт 🟢 Done** (item-коммит `a13614db`): `task_contract.build`/`bundle_lint`,
  `review_policy.LoopBudget.from_committed`, `canonical_actor` с моделью (D72), `task@0.6.0`.
- **P2.7 закрыт 🟠 Done with deviations** (item-коммит `d11c3b74`): write-site pre-mutation в
  `plan-exec.md`, `plan-run.md`/`plan-audit.md`, `snippets/source-evidence-template.md`, §13
  канона + литеральный тест, публикация `plan-protocol@2.13.0`/`skiller@0.6.0`/`task@0.7.0`.
- **P2.10 закрыт 🟠 Done with deviations** (item-коммит `668012bd`): закрытый набор заголовков
  §3 Routing (канон + легаси `Model/effort`/`Model/Effort`), типизированный отказ вместо
  `ValueError` по обеим осям и обеим сторонам маршрута (D74/D78 закрыты), `task@0.8.0`.
- **P2.11 закрыт 🟢 Done** (item-коммит `abd53b4b`): бинарный гейт `pre_mutation == "allow" and
  pre_final == "allow"` (D76 — `n/a` НЕ зелёное), маршрут `actual_route` на pre-final —
  маршрут ИСПОЛНИТЕЛЯ по лестнице D75, `plan-exec.md` шаг 7 получил исполняемую границу (М5),
  различающий тест (D79), публикация `plan-protocol@2.14.0`/`skiller@0.7.0`/`task@0.9.0`.
- **P2.8 закрыт 🟠 Done with deviations** (item-коммит `a36d489b`): `artifacts/P2.5/generate_transcripts.py`
  (committed, детерминированный) гоняет реальные seam'ы (`task.task_contract.build`/
  `pre_mutation`/`pre_final`/`bundle_lint`/`portability_lint`/`classify_tier`,
  `task.review_policy`, `task.route_evidence`, `task.command_catalog`/`command_render`,
  прямые чтения `artifacts/P1.4/effective-carrier-set.json`, `.codex/hooks.json` +
  `.swissknifeman/provider-artifacts.lock.json`, `skiller registry --check`) для всех 31
  кейсов банка. Перепрогон `run_bank.py candidate` от закоммиченного входа даёт **те же
  30/31** (`first_pass_success 0.9677`), теперь независимо пересчитываемо третьим лицом
  (`git diff --exit-code` после регенерации поверх коммита → exit 0). Все 12 категорий Code
  Guidance честно `covered`, каждая — с названным `файл::функция` предикатом
  (`findings/P2.5-scenario-results.md` §4); `portability-privacy-rawbulk` зеленеет ТОЛЬКО
  через реально работающий `task_contract.bundle_lint` (P2.6, фикс F4). `result-manifest.json`
  несёт новый `input_provenance` (генератор/sha256/якорь дерева). Material-отклонений нет
  (Scope Included исполнен полностью); три process-отклонения (детали — Known Deviations
  phases/P2.md P2.8): (1) два Validation-литерала докомплектованы очевидным явным флагом
  (`--results` у `run_bank.py candidate`, `--transcripts`/`--generator` у
  `verify_result_manifest.py`); (2) генератор не печатает `FAIL:`-строки как в
  `validate_state_cases.py` (эквивалентное fail-closed поведение, другая форма); (3)
  pre-mutation-гейт и старт-запись журнала исполнены постфактум, не строго до первой
  мутации (маршрут сессии совпадал с предписанным на всём протяжении, гейт вернул
  allow/allow).

**Remaining:**

- **P2.9** ⬜ — ПОСЛЕДНИЙ ремонтный item реопена (этот launch-block): бухгалтерия F6, F7,
  F10–F15 без мутаций кода.
- После терминальных P2.6–P2.11 (включая P2.8/P2.9) — `task:plan-close … P2` (снимает маркер
  «УСТАРЕЛ», пересобирает Phase Handoff), затем аудит фазы **заход 2/2**.
- **P3–P4** ⬜ — не стартуют до терминальной P2.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.16.3), §3 Routing (строки P2.6–P2.11), §4 Status Board
  (P2 = `5/11 🟢-counted, 10/11 терминален`), §6 Update Log (последняя строка — P2.8).
- `findings/P2.5-scenario-results.md` — переписан под P2.8: провенанс входа, честный
  `covered` по 12 категориям с `файл::функция`, воспроизводимость.
- `phases/P2.md` — ТЗ P2.9 целиком; P2.8 Completion Notes/Known Deviations (числа, команды,
  вывод); блок `## Audit P2 — 2026-07-26` (находки F6/F7/F10–F15, предмет P2.9).
- `roadmap.md` — carrier'ы P2.6–P2.11; `journal.jsonl` — прогоны (P2.8: старт + `closed-deviations`).
- **Дерево, на которое смотрит этот handoff (D55): item-коммит `a36d489b`** — bookkeeping
  этого закрытия коммитится СЛЕДОМ (шаг 6, plans/-carve-out); холодная сессия стартует с
  committed-дерева после bookkeeping-коммита.

**Open risks:**

- **Cap аудитов.** `## Audit P2` — заход 1 из двух; третий заход — решение владельца, не
  автоматический раунд.
- **Дрейф генерируемых деревьев вне owner-карты.** P2.6–P2.11 отсутствуют в
  `remediation-map.json::baseline_owners` → `assert_generated_scope.py` не запускается для
  них; компенсация — ручная сверка `git show --stat <item-коммит>` против `Files` (для
  P2.8: 6 файлов, точное совпадение `Files`, без companion-коммита).
- **Third-party проверка F4-фикса.** `bundle_lint` (P2.6) теперь реально управляет
  `privacy-rawbulk-negative`; независимая ре-верификация (не этой же сессией) остаётся
  желательной, но не блокирующей — это стандартный residual любого self-attested прогона.

**Workarounds / Deferred / Open questions:**

- **F9 (Minor) не чинится** — вне скоупа реопена, названный долг с `PROMOTE-CANDIDATE`.
- **Обобщение D79** — `PROMOTE-CANDIDATE` в канон `plan-protocol`; владелец продвижения —
  отдельная D-запись после терминального P2 (терминален — открыт вопрос продвижения).
- **Fresh-subagent dispatch** — недоставленная позиция Scope P2.2; владелец — **P3.4**.
- **Docs-sync `packages/task/CLAUDE.md`** — долг остаётся, владелец **P3.1**.
- **`plan.md` §4, строка фазы P0** — предсуществующий дефект бухгалтерии P0.4, владелец —
  `task:plan-close … P0`.
- **WARN `plan-lint` на `plan.md`** (длина строки Update Log P1.4) — предсуществующий, не
  блокер.
- **`trace-record-missing`** — единственный честный residual P2.5/P2.8; владелец **P3.1/P3.2**
  (unified trace ещё не существует).
