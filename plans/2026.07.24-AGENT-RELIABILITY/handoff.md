# HANDOFF — 2026-07-26 — after P1

**Next:** `/task:plan-design 2026.07.24-AGENT-RELIABILITY P2.1`

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — контракты state-machine/authority, не bookkeeping |
| Context | NEW SESSION — шаг-не-item |
| Суть | Запечатать execution state/authority contract (P2.1) — детализация ТЗ item'а фазы P2 |

```
/task:plan-design 2026.07.24-AGENT-RELIABILITY P2.1
```

**Done:**

- Фаза **P1 закрыта** (2026-07-26): все пять items терминальны — P1.1 🟢 ·
  P1.2 🟠 · P1.3 🟢 · P1.5 🟠 · P1.4 🟢 (терминальный gate фазы).
- Identity/ownership contract запечатан (P1.1); 13 class-A bootstrap skills
  канонизированы, skiller/root/core publication исправлена (P1.2);
  task/harness projection и runtime dedup исправлены (P1.3); newly measured
  collisions (D40–D43) закрыты — 16 root↔installed + 1 installed↔installed
  по ownership (P1.5); cold effective-runtime conformance gate введён и
  зелёный: 216 Codex/204 Claude identity, 0 catalog-wide коллизий, 0
  undeclared root, негативная D42-фикстура (9 именованных пар +
  precondition-ошибка class-B `workflow-craft`) воспроизведена точно,
  D62-сверка с `remediation-map.json` — 11 `resolved`, 18 `still-measured`,
  0 `unowned-or-unexplained` (P1.4).
- Известные отклонения — агрегат в `phases/P1.md` § Phase Handoff (P1.2 (1)-(3),
  P1.5 (1)-(3), P1.4 (1)-(4); P1.1/P1.3 пусты).
- Docs-sync: не требуется (внутренние doctor/registry/publication seam'ы,
  без нового пользовательского процесса/установки/схемы).
- `## 4. Phase Index & Status Board` (`plan.md`) синхронизирован: P1 →
  5/5, статус `🟠 Done with deviations` (агрегат фазы — есть 🟠-items).
- `plans/README.md` счётчик items плана актуализирован (`0/22` → `5/22`).

**Remaining:**

17/22 items открыто. P0 (4, терминальна ранее) → **P1 терминальна** (5/5)
→ P2 (5, ⬜) → P3 (5) → P4 (3). Следующий шаг — P2.1 (детализация ТЗ,
`Exec = plan-design`: item определяет state-machine/authority-контракты,
код не пишет — согласно `Scope Excluded` P2.1 "code implementation").

**Sources of truth:**

`plan.md` v1.13.1 (§0 Meta, §4 Phase Index, §6 Update Log) ·
`phases/P1.md` § Phase Handoff (полный агрегат) ·
`phases/P2.md` § P2.1 (следующее ТЗ) · `journal.jsonl`.

**Open risks:**

- **`check_collision_owners` структурно несовместим с фазовой ремедиацией** —
  назван P1.1/P1.5/P1.4 трижды, владелец «отдельный proposal/ADR по D23» так
  и не назначен. Не блокирует P2, но и не исчезает.
- Прежний долг без изменений: `command.interactive-user-input` вне каталога
  capability; Claude enabled-set остаётся `unknown`; Claude-проекция
  `workflow-craft` (нужен `skiller budget --first-turn`); три находки A2;
  A1 F11; расхождение провенанса harness-CLI ↔ maind-адаптера (P0.4).

**Workarounds/Deferred/Open questions:**

- **workarounds:** нет новых.
- **deferred:** структурный фикс `check_collision_owners`/`remediation-map.json`
  под фазовую ремедиацию (D23 proposal/ADR, владельца нет);
  `command.interactive-user-input`; Claude-проекция `workflow-craft`;
  расхождение провенанса harness-CLI ↔ maind-адаптера.
- **open_questions:** нет открытых для владельца.
