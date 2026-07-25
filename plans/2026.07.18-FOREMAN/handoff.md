# HANDOFF — 2026-07-25 — after P1.4

**P1.4 закрыт 🟠 по git-фактам** (D50): его работа была исполнена ещё 2026-07-19
(`c37b3379` — plan-protocol 2.9.0 с journal/index + lint + snippets; bootstrap-журнал
`9844f499`), но осталась незакрытой из-за перехвата ACTIVE планом DUAL-PROVIDER.
Не выполнен один Deliverable — re-пин контракта P0.2; он вынесен в новый item **P1.5**.

**Мёртвый гейт снят.** Прежний `Next` ждал «`2026.07.19-DUAL-PROVIDER` P7.4 GREEN» —
тот план терминален со статусом **🟠**, его P7.4 остался literal `ATTENTION`, условие
не наступит никогда. Заменено реальной зависимостью (D49).

**Очередь экосистемы (D49):** этот план идёт ПОСЛЕ `2026.07.24-AGENT-RELIABILITY`
(`Paused By` обновлён). Регистр очереди и владения поверхностями —
`plans/README.md` § «Очередь планов и владение поверхностями».

**Next:** run-items: task:plan-run 2026.07.18-FOREMAN P1.5

| Параметр | Значение |
|:--|:--|
| Model | Sonnet (`implementation`) |
| Thinking | high — сверка якорей parse-контракта против канона, вердикт breaking/non-breaking |
| Context | `NEW SESSION`, запускать ИЗ репо `~/projects/packages/swissknifeman` |
| Гейт | **fail closed, пока фаза P2 плана `2026.07.24-AGENT-RELIABILITY` не терминальна** — она уводит `plan-protocol` на `2.12.0` и переписывает все пять команд; пин на промежуточную версию запрещён |
| Суть | Re-пин `root/contracts/driver-plan-protocol.md` (сейчас отстал: `v2.8.0 @ 2cf26e8` против живых `2.11.0`) + построчная сверка четырёх якорей §1–§4 |

```
# НЕ раньше: фаза P2 плана 2026.07.24-AGENT-RELIABILITY терминальна (🟢/🟠 в её Status Board)
/task:plan-run 2026.07.18-FOREMAN P1.5
```

(Cold-start reads: `phases/P1.md` P1.5 (все 16 полей) + P1.4 Completion Notes/Known Deviations;
`root/contracts/driver-plan-protocol.md` целиком; `packages/skiller/skills/general/plan-protocol/SKILL.md`
frontmatter + §§1–4; `plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md` P2.2 Completion Notes;
`plan.md` §5 D47/D49/D50.)

**Пере-скоуп P2/P5 — решение владельца от 2026-07-25 (D49), исполняется отдельным заходом.**
Artifex становится ТОНКОЙ обвязкой над контрактами `2026.07.24-AGENT-RELIABILITY`
(`execution-state-machine-v1`, `risk-review-loop-budget-v1`, `unified-agent-trace-v1`), а не
собственным движком решений: CLI-запуск headless-сессий и Telegram-эскалация остаются, движок
next/retry/escalate — потребляется. Design-заход по P2/P5 запускать только когда те контракты
заморожены (после P2/P3.1 того плана), иначе проектирование против движущейся цели.

**Done:** **P1.3 закрыт 🟢** (Exec под sonnet/high, plan-run):
- Реализован `lib/task/journal.py` (stdlib-only): `validate_entry`/`new_entry`/`append`
  (append-only NDJSON, один `write()` на строку) + CLI `python3 -m task.journal append`.
- Шаг записи журнала врезан в close-протокол ВСЕХ 5 команд `plan-{exec,run,close,audit,design}.md`
  (D21): старт+финал у exec/run, финал у close (item- и phase-режим)/audit/design.
- SessionEnd-backstop-хук: design уже в контракте P1.1 (§«Дом записи», D26) — включение вне Scope
  (owner-review, MVP без него).
- Commits: item `94eada8` (lib/task/journal.py + 5 команд + test_journal.py — ТОЛЬКО пути Files
  item'а, `plan-audit.md` выделен из параллельного диффа владельца вручную); bookkeeping — см.
  §6 Update Log (хеш появится этой сессией после текущего коммита).
- Validation: `compileall` OK; `unittest tests.test_journal` — 16 passed; `bash
  packages/task/scripts/validate.sh` — OK (0 ошибок, 56 warning — все на чужих планах);
  `plan-lint plans/2026.07.18-FOREMAN` — 0 ошибок/0 предупреждений (без `--baseline`).
- **Known Deviations:** — (чистое закрытие; факт-заметка про первый коммит плана в git-историю
  swissknifeman — в Completion Notes, не отклонение).
Ранее: **P1.1/P1.2 закрыты 🟢** (схемы журнала/индекса sealed v1, исполнялись в Brain); **P1
reconcile** (D46/D47); **P0 6/6 ТЕРМИНАЛЬНА**.

**Remaining:** P1.5 (re-пин P0.2 — закрывает фазу P1) → пере-скоуп P2/P5 отдельным
design-заходом → P2→P7 phase-first по roadmap.md. Всё — после терминальной P2 плана
`2026.07.24-AGENT-RELIABILITY` (D49). Открыто 24 items из 33.

**Sources of truth:** исполнительская карта — `roadmap.md`; фаза — `phases/P1.md`; журнал —
`root/contracts/plan-journal-schema.md` (P1.1 sealed v1) + `lib/task/journal.py` (реализация,
P1.3); §3 Routing — модель/effort per item; §7 Contracts — Consumed sealed (plan-protocol
v2.8.0@2cf26e8, P1.4 бампает на v2.9.0), Exported sealed (policy v1, run-folder v1, журнал v1,
индекс v1), draft (decision-лог P5.4); D-лог — `plan.md §5` (D1–D48); контракты —
`root/contracts/{plan-journal-schema,plan-index-schema,artifex-run-folder,artifex-policy-schema,
driver-plan-protocol}.md`; OQ — `open-questions.md`.

**Open risks:**
- **Repo↔Brain sync (новый, P1.3):** P1.3 — ПЕРВЫЙ item, чей код-коммит лёг в git-историю репо
  swissknifeman (Home плана — `brain`, P0–P1.2 исполнялись там же со своей git-историей — разные
  репозитории). Штатный `brain sync` не прогнан этой сессией (вне scope P1.3, Execution Rules
  относят его к владельцу/отдельному шагу) — до синка Brain-зеркало плана не видит P1.3-правок.
- **plan-audit design:** P0 исполнена без явной отметки о прохождении `/task:plan-audit design`
  (roadmap-гейт). При желании владельца pre-exec-ревью P1 — его гейт (не блокирует P1.4).
- **Owner-гейты посреди волны** (не пропускать): P1.4 (канон, эта фаза) · rulebook P5.3 ·
  contribution harness P6.1/OQ-6 · вердикт пилота P6.3 · канон P7.3 · дом скилла P7.4/OQ-7.
- **Реconcile-долг P5.4↔P0.6:** decision-событие run-folder ↔ decision-лог — полный reconcile при
  детализации/exec P5.
- **Остаток rename вне плана:** repo-код `packages/artifex/` ещё не создан (P2 exec); `docs/
  reference.md` SKM — при касании.
- **Посторонний дифф в дереве** (владелец правит параллельно, НЕ трогать): `packages/task/
  commands/plan-audit.md` (scope-payload launch-block, вкраплён в файл — выделен из него П1.3-
  правка, остальное нетронуто) + `packages/task/lib/task/plan_lint.py` + `packages/task/tests/
  test_plan_lint.py` + `packages/skiller/skills/general/plan-protocol/{SKILL.md,SKILL.ru.md,
  snippets/launch-block-template.md}` + `packages/skiller/scripts/check-translations.sh` (та же
  scope-payload волна) + `docs/reference.md` SKM + AzGuard/docs+plans + CoreX/COREX-CORE +
  `plans/2026.07.15-TOKEN-ECON-P6/plan.md` + `.maind-feature-log.last`.
- **MAX base-URL** (P4.1): миграция platform-api→platform-api2, дедлайн 2026-07-19 — сверить
  перед кодом P4.1.

**Workarounds / Deferred / Open questions:**
- workarounds: —
- deferred: генератор index.md (P1.2 follow-up, опц.) — MVP ручной по шаблону P1.4; Layer 3/
  defer-resume (OQ-2) — по данным пилота P6.3; корневой супервизор D11 (OQ-4) — v2.
- open_questions: OQ-6 (дом rollout-конфигов, гейт P6.1); OQ-7 (дом Brain-скилла, гейт P7.4);
  философия-ЗНАЧЕНИЯ P0.3 (owner-гейт P0.5); D13-находка (ось process-governance) —
  owner-решение.
