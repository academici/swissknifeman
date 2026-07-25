# HANDOFF — 2026-07-26 — after P1

**Шаг-не-item:** `/task:plan-design 2026.07.24-AGENT-RELIABILITY P1.4` — ТЗ терминального
item'а фазы доведено до DoR. Ни один item не закрыт, Status Board не менялся
(P1.4 остаётся `⬜ Not started`). Плановые пути этого захода коммитятся бухгалтерией
следом; собственный хеш в этот файл не вписывается.

**Что решено.**

Handoff after P1.5 оставил владельцу open question «принимает ли Owner `🟠` P1.5 как
достаточный вход P1.4». По D50 (authority E) развилка закрыта записью, а не вопросом:

- **D62 — вход P1.4 «terminal», а не «green».** `🟠 Done with deviations` — канонический
  терминальный статус этого плана (так уже закрыты P0.4 и P1.2, оба служили входами
  следующих items). Все 16 failures красной `build_effective_inventory.py
  --check-collision-owners` разложены поимённо (6 → P1.2 `589c320e`, 6 → P1.3 `c1c4a1f9`,
  4 → P1.5 `0a87a4e5`), каждое — прямое предписанное следствие Implementation Rules своего
  item'а; краснота вызвана point-in-time-семантикой скрипта, а не остаточным дефектом
  каталога. Команда не входит в Validation P1.4. **Долг не списан:** P1.4 обязан эмитить
  `artifacts/P1.4/effective-carrier-set.json` (post-remediation карта identity→носители) и
  машинно классифицировать КАЖДУЮ замороженную запись `remediation-map.json` как
  `still-measured` / `resolved` / падение гейта. Fix-item на `check_collision_owners` и поле
  `resolved_by` отклонены: обе правят замороженный артефакт P1.1 вне Scope (§10 → вопрос
  владельцу) и воспроизводят audit/fix-loop без продукта.
- **D63 — найден и закрыт ТЗ более жёсткий блокер, ранее не названный.** Замер на
  `HEAD=a579cd21`: committed-байты канона class B
  `packages/skiller/skills/general/workflow-craft/SKILL.md` дают sha256 `a6dff90f…`, а
  ЧЕТЫРЕ committed-артефакта провенанса (`remediation-map.json::class_b`,
  `root-bootstrap-extension-map.json`, `publication-lock.json` 27 records и сама проекция
  `.agents/skills/workflow-craft/SKILL.md`) пинят `a0d26c8d…` — байты грязного рабочего
  дерева. P1.4 доказывает ХОЛОДНУЮ установку, то есть committed-состояние, — на нём
  цепочка провенанса class B разорвана. ТЗ получило шаг (0b): сверка `git show
  HEAD:<canonical>` против пина по всем 27 записям + чистота `git status --porcelain` по
  путям канонов/проекций/lock/configs, fail closed с обоими хешами и владельцем действия.

**Next:** exec-item: `task:plan-exec 2026.07.24-AGENT-RELIABILITY P1.4`

> **ПРЕДУСЛОВИЕ ВЛАДЕЛЬЦА, читать до запуска.** Рабочее дерево несёт **63**
> незакоммиченных чужих пути (`docs/*`, staged-deletions `roadmap/*`,
> `packages/harness/**`, `packages/skiller/skills/general/workflow-craft/**`). Пока они не
> закоммичены своим владельцем, гейт (0b) P1.4 падает по построению — и падает ПРАВИЛЬНО.
> Ожидаемое действие: владелец коммитит свой дифф; после этого `HEAD`-байты канона class B
> становятся `a0d26c8d…`, все четыре пина сходятся, и P1.4 идёт без единой правки плана.
> Если дифф вместо коммита откатывается — пины устаревают, владельцем ремонта становится
> P1.5 (реопен по канону `plan-protocol` §3: 4 шага + D#), и запускать P1.4 нельзя.
> Агент чужое не коммитит, не ревертит и не стэшит.

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | NEW SESSION |
| Суть | Терминальный гейт фазы P1: cold per-provider effective-runtime conformance по объявленной фикстуре (D51) + гейт committed-консистентности (0b, D63) + post-remediation перезамер и сверка с замороженной картой (D62) |

```
/task:plan-exec 2026.07.24-AGENT-RELIABILITY P1.4
```

**Done:**

- `phases/P1.md` P1.4 доведён до DoR: Scope Included/Excluded, Inputs, Files, Required
  Reads (26), Implementation Rules (шаги 0 и 0b + сверка D62 + запрет
  `assert_generated_scope.py`), Code Guidance (негативы под 0b и под сверку,
  анти-подгонка, if-then эскалация), Validation (+4 команды), Deliverables.
- `plan.md`: Version 1.12.9 → 1.13.0, Meta Last Updated, §3 Routing строка P1.4,
  §5 D62 + D63, §6 Update Log.
- `findings/P1.4-precondition-evidence.md` — слой 1: разложение всех 16 failures;
  замер committed/worktree расхождения с четырьмя пинами; `baseline_owners` без P1.4.
- `research/05-p1.4-precondition-resolution.md` — слой 2: таблицы альтернатив по обеим
  задачам, границы Scope, два заранее названных исхода предусловия.
- `brief/01-refinements.md` — датированный блок слоя 0 (три решения захода).
- `journal.jsonl` — одна строка `plan-design` / `P1.4` / `in-progress`.

**Remaining:**

15/22 items открыто. Порядок фаз: P0 → P1 (P1.1 ✅ · P1.2 ✅🟠 · P1.3 ✅ · P1.5 ✅🟠 →
**P1.4 — готов к exec, ждёт предусловия владельца**) → P2 → P3 → P4. Закрытие P1.4
закрывает фазу P1 и разблокирует P2 (его `findings/P1.4-effective-runtime-proof.md`
запинен в Required Reads P2.1/P2.5/P3.4).

**Sources of truth:**

`plan.md` v1.13.0 (§0 Meta, §3 Routing, §5 D62/D63, §6 Update Log) ·
`phases/P1.md` § P1.4 (полное ТЗ) и § P1.5 Known Deviations (1)/(3) ·
`findings/P1.4-precondition-evidence.md` · `research/05-p1.4-precondition-resolution.md` ·
`research/04-p1.4-fixture-composition.md` (состав фикстуры, D51) ·
`findings/P1.5-collision-closure.md` ·
`packages/skiller/adapters/repository-bootstrap/publication-lock.json` (27 records) ·
`journal.jsonl`.

**Open risks:**

- **Предусловие (0b) сейчас НЕ выполнено** — см. блок в § Next. Это единственное, что
  отделяет P1.4 от запуска.
- **`check_collision_owners` структурно несовместим с фазовой ремедиацией** — принят как
  названный долг с владельцем «отдельный proposal/ADR по D23» (D62). Не блокирует P1.4,
  но и не исчез: если появится item, правящий замороженные артефакты P1.1, долг его.
- **Правки `doctor.py`/`registry.py` в P1.4 не покрыты drift-гейтом** — P1.4 отсутствует в
  `remediation-map.json::baseline_owners`; принятая и названная граница (D63), фиксируется
  строкой Completion Notes при закрытии, самовольное расширение owner-набора запрещено.
- Прежний долг без изменений: `command.interactive-user-input` отсутствует в каталоге
  capability (D23-гейт); Claude enabled-set остаётся `unknown`; Claude-проекция
  `workflow-craft` (меняет first-turn budget, нужен `skiller budget --first-turn`);
  три находки A2; A1 F11; расхождение провенанса harness-CLI ↔ maind-адаптера (P0.4).
- `plans/README.md` § «Очередь планов» показывает устаревший счётчик item'ов этого плана.

**Workarounds/Deferred/Open questions:**

- **workarounds:** нет новых; class-A `class_a_content_version` (P1.5) продолжает
  развязывать байты 26 class-A проекций от умбрелла-версии `repository-bootstrap`.
- **deferred:** структурный фикс `check_collision_owners`/`remediation-map.json` под
  фазовую ремедиацию (D23 proposal/ADR, владельца нет); `command.interactive-user-input`;
  Claude-проекция `workflow-craft`; read-only измерение Claude enabled-set; расхождение
  провенанса harness-CLI ↔ maind-адаптера.
- **open_questions:** нет открытых для владельца. Обе развилки захода закрыты записями
  D62/D63 по authority E; от владельца требуется не решение, а действие — коммит своего
  диффа (см. § Next).
