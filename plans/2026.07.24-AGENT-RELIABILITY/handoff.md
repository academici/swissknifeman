# HANDOFF — 2026-07-26 — after P2

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.1

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Context | `same-session — item` |
| Суть | Запечатать три контракта P2.1 (state machine · risk/review/loop budget · plan portability) как надстройку над замороженным P0.2 |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P2.1

РЕЖИМ: исполнение детализированного item'а (P2.1 ⬜, фаза P2 не начата — не реопен, не повторный дизайн).
ВХОД: plans/2026.07.24-AGENT-RELIABILITY/research/06-p2.1-contract-boundary.md (граница, множества, потребители) → phases/P2.md § P2.1 (ТЗ) → plan.md §5 D64–D68.
СКОУП: 1) precondition-гейт (P0/P1 терминальны; `git diff --exit-code` чист по замороженным входам P0.2/acceptance/source-evidence); 2) три контракта в root/contracts/ с секцией `## Frozen upstream` и ссылками file:line вместо пересказа P0.2; 3) artifacts/P2.1/state-transition-cases.json — объявленные множества (9/15/6/3/4/2), тотальные 135 ячеек, проекция на 6 статусов и 8 journal RESULT_VALUES, 5 кейсов корпуса, ≥5 позитивных routine-кейсов (F14), mutations; 4) artifacts/P2.1/validate_state_cases.py — stdlib, доказательство тотальности перебором, doc↔data сверка по маркерам `<!-- declared-set: … -->`; 5) закрытие по канону: item-коммит пяти Files + bookkeeping-коммит.
НЕ ТРОГАТЬ: замороженные контракты P0/P1 и их артефакты; `packages/**` и канон plan-protocol (владелец — P2.2); enum тиров portability, классы authority, 12+3 кода предикатов, slice, cold-start, значения context (владелец — P0.2, только ссылки); `artifacts/P2.1/base-sha.txt` и `assert_generated_scope.py` (P2.1 нет в baseline_owners); планы FOREMAN и ECO-OPT (уведомление — строками §7 Exported); workflow-скрипт (D67).
```

Плановые пути этого захода закоммичены одним bookkeeping-коммитом (D55);
собственный хеш в этот файл физически не вписывается — следующий шаг работает по
`git log -1 -- plans/2026.07.24-AGENT-RELIABILITY`. P2.1 остаётся `⬜ Not started`.

**Done:**

- Фаза **P1 закрыта** (2026-07-26): P1.1 🟢 · P1.2 🟠 · P1.3 🟢 · P1.5 🟠 · P1.4 🟢.
  Фаза **P0** терминальна ранее. Исполнено 5/22 items.
- **P2.1 доведён до DoR** (этот заход, plan-design): все 16 полей переписаны под
  уровень «исполнитель не задаёт вопросов»; 22 упорядоченных Required Reads;
  precondition-гейт; объявленные множества; расширенная Validation с печатью
  покрытия. `Files` не расширены — пины downstream (P2.2/P2.3/P2.4 Required Reads
  на `artifacts/P2.1/state-transition-cases.json`) остались валидны.
- **D64–D68** зафиксированы: граница с замороженным P0.2 (надстройка, не копия) ·
  объявленные множества и тотальность 135 ячеек · потребители FOREMAN P2/P5 и
  ECO-OPT P9 → решающая функция + машинный словарь · долг A2 о workflow-carrier
  закрыт измерением критерия `plan-protocol` §7 · субъект cap как профиль
  authority + F14-гейт позитивных кейсов.
- Слой 2: `research/06-p2.1-contract-boundary.md` (граница, множества, потребители,
  три закрытые развилки, названные границы И1–И3). Слой 1 не требовался — все
  утверждения repo-grounded.
- `roadmap.md`: carrier P2.1 синхронизирован с D64–D68; снят stale-указатель шапки
  (`v1.10.0` → `v1.14.0`) и стартовая строка «старт с P0.1».

**Remaining:**

17/22 items. P2 (5, ⬜) → P3 (5) → P4 (3). Следующий шаг — **исполнение** P2.1
(`Exec = manual`, frontier/high ⇒ `task:plan-run`, не `plan-exec`). Остальные items
P2 уже детализированы; повторный дизайн-заход по ним не требуется.

**Sources of truth:**

`plan.md` v1.14.0 (§3 Routing, §4 Status Board, §5 D64–D68, §7 Contracts) ·
`phases/P2.md` § P2.1 (ТЗ) · `research/06-p2.1-contract-boundary.md` (слой 2) ·
`roadmap.md` § P2.1 · `journal.jsonl`.

**Open risks:**

- **Три новых контракта — новая публичная поверхность.** D23 требует внутри каждого
  зафиксировать потребителей, ≥2 альтернативы и SemVer/ADR-результат; пропуск этого
  выявится только аудитом фазы.
- **`check_collision_owners` структурно несовместим с фазовой ремедиацией** —
  назван трижды (P1.1/P1.5/P1.4), владелец «отдельный proposal/ADR по D23» не
  назначен. P2 не блокирует.
- Прежний долг без изменений: две находки A2 (порядок capture `base-sha` —
  владельцы P2.2/P2.3; `research/01–03` без ссылок на слой 1); A1 F11;
  `command.interactive-user-input` вне каталога capability; Claude enabled-set
  `unknown`; Claude-проекция `workflow-craft` (нужен `skiller budget --first-turn`);
  расхождение провенанса harness-CLI ↔ maind-адаптера (P0.4).

**Workarounds/Deferred/Open questions:**

- **workarounds:** нет новых.
- **deferred:** структурный фикс `check_collision_owners`/`remediation-map.json`;
  `command.interactive-user-input`; Claude-проекция `workflow-craft`; расхождение
  провенанса harness-CLI ↔ maind-адаптера; две находки A2 (§ Open risks).
- **open_questions:** нет открытых для владельца — по D50 развилки этого захода
  закрыты записями D64–D68.
