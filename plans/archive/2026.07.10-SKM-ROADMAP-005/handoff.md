# HANDOFF — 2026-07-11 — after P6.4

**Next:** план закрыт (все фазы терминальны). Следующий план выбирает владелец — вне протокола.
Наполнение term-index (бывш. P6.4, ⛔) трекается строкой `ecosystem-glossary` в `roadmap/README.md`.

**Done:** Пакет SKM-ROADMAP-005 закрыт ЦЕЛИКОМ. **P1** (`settings-doctor`, 6/6 🟢), **P2**
(`wf-status`, 🟠), **P3** (`workflow-craft`, 5/5 🟢), **P4** (канон планов, 6/6 🟢), **P5**
(`changelog-discipline`, 3/3 🟢), **P6** (`ecosystem-glossary`, 🟠 — механизм сдан P6.1–P6.3;
P6.4 закрыт ⛔ решением владельца 2026-07-11: ECOSYSTEM P4 закрыта design-only, термины кодом не
закреплены — наполнение term-index передано в roadmap, ТЗ остаётся в phases/P6.md), **P7**
(ephemeral-хвост, 🟠). Meta Status → 🟠 Done with deviations; `plans/ACTIVE.md` сброшен на `—`.

**Remaining:** вне плана — см. roadmap (`ecosystem-glossary` term-index; `workflow-craft` ч.2;
`changelog-discipline` P5.3-механизация) и Open risks ниже (CHANGELOG-строки, P1.4/P1.6).

**Sources of truth:** plan.md (Meta, §4, D1–D44) · phases/P1–P7 (Completion Notes) ·
roadmap/README.md (витрина статусов) · packages/skiller/skills/general/plan-protocol/SKILL.md.

**Open risks:**
- **CHANGELOG-строки НЕ внесены** (permission-deny среды, прецеденты P2.4/P6/P7.2): P3.1–P3.5,
  консолидированная строка P4, P5.1–P5.3, P6.2/P6.3 — внести перед следующим релизом.
- P1.4: проверка №5 ложный `error` на хук-командах с интерпретатор-префиксом (вне scope P1).
- P1.6: `maind doctor --audit all` падает на измерении `core` на части флота.
- P6.1: `domain-modeling` вендоренный — авто-staleness переводов слепа (OQ1 владельцу).
- `plan-lint` pre-existing WARNING на SKM-AUDIT-004 / SKM-MASTER-002/003 — вне scope.

**Workarounds/Deferred/Open questions:**
- deferred: opt-in `UserPromptSubmit`-хук settings-doctor (D12); авто-починка `--fix`;
  `workflow-craft` ч.2 fleet-синтез (D1); `skill-rules-sidecar`, остаток `self-learning-memory`,
  `mcp-config-example-emit` (D1); maind-провижионер `plans-doc` (D30); **наполнение term-index**
  (бывш. P6.4 ⛔ → roadmap `ecosystem-glossary`, гейт: код dev-волны ECOSYSTEM P4).
- open_questions: политика vendored-vs-bilingual для `domain-modeling` — OQ1 (`open-questions.md`).

## Чек-лист миграции (архивация 2026-07-11)

| Что | Куда |
|:--|:--|
| `root/` → docs | — (каталога `root/` в плане не было, мигрировать нечего) |
| `findings/`, `workflows/`, `phases/`, `open-questions.md` | остались в архиве `plans/archive/2026.07.10-SKM-ROADMAP-005/` |
| `plans/ACTIVE.md` | сброшен на `—` (коммит ec30966) |
| Ссылки в живых доках | `roadmap/README.md` → указывает на `plans/archive/2026.07.10-SKM-ROADMAP-005/phases/P6.md` (ТЗ term-index); других ссылок на старый путь нет (grep чист) |
| Открытый хвост | наполнение term-index (бывш. P6.4 ⛔) — roadmap-строка `ecosystem-glossary` |
