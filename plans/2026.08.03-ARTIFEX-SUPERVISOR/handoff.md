# HANDOFF — 2026-08-04 — after P3.3

**Next:** design-item: task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P3.3

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write |
| Context | cold-start — plan-step |
| Суть | Исправить closed Required Reads P3.3 без изменения frozen contract semantics. |
| Команда | `$ task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P3.3` |

```text
$ task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P3.3

РЕЖИМ: ремедиация
ВХОД: plans/2026.08.03-ARTIFEX-SUPERVISOR/findings/P3.3-required-read-defect-2026-08-04.md → Observation/Required remediation; cold-start read
СКОУП: 1) добавить канонические P1 carrier paths, нужные для exact parity coverage, в Required Reads P3.3; 2) сохранить exact read order и проверяемый acceptance; 3) зафиксировать решение в плане.
НЕ ТРОГАТЬ: P0/P1 frozen contracts and evidence; P3.1/P3.2 sources; P3.3 scope and acceptance unless a new recorded decision is necessary.
```

**Done:** P3.3 started under the verified `gpt-5.6-terra/high` route; the Task Contract pre-mutation predicate returned `allow`. Execution stopped before an implementation write when the closed Required Reads set proved insufficient for the frozen P1 taxonomy.

**Remaining:** Re-design P3.3, then execute it under its manual `implementation/high` route; P3.4–P6.4 remain sequentially pending.

**Sources of truth:** `phases/P3.md` P3.3 · `findings/P3.3-required-read-defect-2026-08-04.md` · `root/contracts/worker-envelope-v1.md` · `artifacts/P1/contract-manifest-v1.json`.

**Open risks:** P3.3 cannot claim exact provider parity while its required execution input excludes the canonical neutral field/exit taxonomy. The known Hook source-drift warning remains deferred to P4.4; today’s effective hook dry run only confirmed a configured `run-report: off` projection.

**Workarounds/Deferred/Open questions:**

- workarounds: none;
- deferred: all P3.3 implementation and validation until the plan supplies the frozen contract carriers;
- open_questions: whether P3.3 also requires the frozen worker-envelope case bank and validator as explicit Required Reads for independent case expectations.
