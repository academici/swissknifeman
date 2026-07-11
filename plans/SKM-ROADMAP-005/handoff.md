# HANDOFF — 2026-07-11 — after P7.2

**Next:**

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | low — терминальный шаг архивации, механическая работа (перенос в plans/archive/) |
| Context | fresh session — handoff свежий, рекомендован /clear |
| Суть | Архивация плана SKM-ROADMAP-005: `/task:plan-close archive` — перенос в `plans/archive/`, docs-pipeline, правка Meta Status на терминальный |

```
/task:plan-close SKM-ROADMAP-005 archive
```

**Done:** Пакет SKM-ROADMAP-005 закрыт целиком. Фазы **P1** (`settings-doctor`, 6/6 🟢), **P2**
(`wf-status`, 4/5 🟢+🟠), **P3** (`workflow-craft`, 5/5 🟢), **P4** (канон планов, 6/6 🟢), **P5**
(`changelog-discipline`, 3/3 🟢) закрыты ранее. Фаза **P6** (`ecosystem-glossary`) сдана как
механизм: P6.1 закрыт 🟠, P6.2/P6.3 закрыты 🟢; **P6.4 остаётся ⬜ ТАЙМ-ГЕЙТОМ** (D41 — наполнение
term-index после dev-волны ECOSYSTEM P4) — архивация плана его НЕ закрывает, передаётся downstream.
Фаза **P7** закрыта 🟠 (1/2): P7.1 🟢 — стаб `roadmap/ephemeral-discipline.md` удалён, две висячие
ссылки сняты (`plan-homes.md`/`changelog-discipline.md`). **P7.2 закрыт 🟠** — сверка 6 строк
`roadmap/README.md` (settings-doctor · workflow-craft · workflow-status-cli · plan-homes ·
changelog-discipline · ecosystem-glossary): все 6 уже совпадали с фактом §4 плана, правка не
потребовалась. `docs/` без отставания (`grep ephemeral` → 0 хитов). `CHANGELOG.md` подтверждён
permission-deny этой среды (Read/Bash — оба denied, прецедент P2.4/P6) — консолидация НЕ
выполнена, список несведённых строк ниже в Open risks. `plan-lint` — 0 ошибок, 1 ожидаемый WARNING
(phase-first: P6 нетерминальна из-за спроектированного тайм-гейта P6.4 — не дефект). Коммит:
`d8831a1` (сверка витрин, Status Board, Update Log — docs-only, код не менялся).

**Remaining:** Терминальный шаг — архивация плана (`/task:plan-close archive SKM-ROADMAP-005`):
перенос в `plans/archive/`, docs-pipeline, правка Meta `Status` на терминальный. P6.4 (наполнение
term-index) остаётся открытым тайм-гейтом ВНЕ этого плана — подхватывается downstream-волной
ECOSYSTEM P4, архивация SKM-ROADMAP-005 её не закрывает и не блокирует.

**Sources of truth:** plans/SKM-ROADMAP-005/plan.md (Meta, §4 Status Board, Routing, D-лог
D1–D44) · phases/P7.md (P7.1/P7.2 закрыты — эталон Completion Notes) · phases/P6.md (P6.4
тайм-гейт, D41) · roadmap/README.md (витрина, сверена и подтверждена актуальной) ·
packages/skiller/skills/general/plan-protocol/SKILL.md (SSOT протокола 2.1.0) ·
packages/task/lib/task/plan_lint.py (валидатор схемы).

**Open risks:**
- P1.4 Pending Work: проверка №5 даёт ложный `error` на хук-командах с интерпретатор-префиксом
  (`bash …`, `python3 …`). Вне scope P1.
- P1.6 Pending Work: `maind doctor --audit all` падает на измерении `core` (`_present_skills`) на
  части флота. `--audit settings` в изоляции не задет.
- **CHANGELOG-строки НЕ внесены** (permission-deny среды, прецедент P2.4/P6/P7.2 — кто-то со
  свободным доступом к `CHANGELOG.md` обязан внести перед следующим релизом): items P3.1–P3.5
  (`workflow-craft` + `/task:make-workflow`), консолидированная строка фазы P4 (репо-дом,
  `supersedes`, датовые ID, дом workflow-скриптов, `plan_lint` warning-проверки, `ecosystem-map`),
  P5.1/P5.2/P5.3 (`changelog-discipline`: скилл-секция, opt-in commit-гейт harness, `skiller
  release`/`swissknifeman release`), P6.2/P6.3 (glossary-conformance в `task:review` + скилл-указатель
  `axioma-glossary`).
- D16 (канон имён планов) внедрён в P4 — этот план НЕ переименовывается (back-compat D24).
- `plan-lint` даёт pre-existing WARNING на других планах (SKM-AUDIT-004, SKM-MASTER-002/003) —
  вне scope этого плана. Плюс НОВЫЙ ожидаемый WARNING на самом SKM-ROADMAP-005 (phase-first:
  P7 закрыт, а P6 нетерминальна из-за P6.4 тайм-гейта) — спроектированное состояние (D41), не
  дефект; сохранится до заведения архитектуры архивации с открытым downstream-хвостом.
- **`plan-lint` даёт ERROR** на этом `handoff.md`: «Next не содержит /task:plan-exec …» — валидатор
  не распознаёт `/task:plan-close … archive` как честный Next и не считает план «закрытым» при
  намеренно нетерминальном P6.4 (D41). Правка `plan_lint.py` — публичный контракт (вне scope P7.2,
  sonnet/low). Ожидается, что ошибка снимется на самом шаге архивации (следующая команда) либо
  требует отдельного future item на доработку валидатора под кейс «архивация с открытым
  downstream-хвостом» — если `/task:plan-close archive` тоже упрётся в эту ошибку, эскалировать
  владельцу как правку публичного контракта `plan_lint`.
- P6.1 Known Deviations: `domain-modeling` вендоренный (`upstream.json` strategy=notify) →
  `check-translations.sh --stamp` его не касается, авто-staleness слепа; политика vendored-vs-
  bilingual для этого скилла — открытый вопрос владельцу (OQ1, не блокирует).
- P6.3 Known Deviations: текст Validation плана (`grep "axioma-glossary" marketplace.json`) не
  совпадает с реальной bucket-granular архитектурой connect-канала.
- P7.1 Known Deviations: Routing-adherence — исполнено sonnet/medium вместо sonnet/low, эффекта
  на результат не имело.
- P7.2 Known Deviations: Routing-adherence — исполнено sonnet/medium вместо sonnet/low
  (пин команды `plan-exec`), эффекта на результат не имело; item закрыт 🟠 из-за
  CHANGELOG-permission-deny (см. выше), не из-за качества сверки.

**Workarounds/Deferred/Open questions:**
- workarounds: семантика слияния `permissions.additionalDirectories` неизвестна → проверка №8
  per-layer (D15); полнота списка hook-событий не подтверждена → неизвестное событие даёт `info`;
  маркер оркестрации в plan_lint консервативен (без бумерного `fan-out`) — против ложных warning
  (P4.6); P6.1 `ru-source-sha256` проставлен вручную (вендоренный скилл, инструмент не стампит).
- deferred: opt-in `UserPromptSubmit`-хук settings-doctor (D12); авто-починка `--fix`; часть 2
  `workflow-craft` fleet-синтез (D1); `skill-rules-sidecar`, остаток `self-learning-memory`,
  default-on `mcp-config-example-emit` (D1); P1.4/P1.6 Pending Work; CHANGELOG-строки P3+P4+P5+
  P6.2+P6.3 (permission-deny, см. Open risks); maind-провижионер `plans-doc` авто-раскатки
  CLAUDE.md во флот (D30); P6.4 наполнение term-index (тайм-гейт D41, после dev-волны ECOSYSTEM
  P4 — переживает архивацию этого плана).
- open_questions: политика vendored-vs-bilingual для `domain-modeling` — OQ1 (`open-questions.md`).
