# HANDOFF — 2026-08-15 — after P3.3

**Next:** run-items: task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.1-P4.2

| Параметр | Значение |
|:--|:--|
| Batch | p4-admission |
| Model class | implementation |
| Effort | high |
| Context | cold-start-root |
| Суть | Implement P4 locale runtime and evidence admission from frozen P2/P3 contracts. |

**Provider-neutral plan-protocol command:**

```text
task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.1-P4.2
```

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P4.1-P4.2'
```

**Done:**

- P3.2: immutable no-write reconciliation and additive open-provider Skill Adapter boundary (`bb80b1e4`, `4f180b93`).
- P3.3: deterministic redacted provider statuses, aggregation, diagnostics and adapter-scoped atomic status writer (`b92ff479`).
- P3.2/P3.3 acceptance checks and plan lint are green; P4.1 bundle is materialized.

**Remaining:** P4.1–P7.4.

**Sources of truth:** `plan.md`; `phases/P4/P4.1.md`; frozen P2/P3 contracts; `core/provider/{reconcile,skill_adapter,status,diagnostics}.py`.

**Open risks:** The root-prefixed P3.3 unittest command has a package `tests.fixtures` import collision; package-local validation remains the valid evidence carrier.

**Workarounds/Deferred/Open questions:** Workarounds: package-local test execution for P3.3. Deferred: fleet migration P5 and live provider replay P7. Open questions: —.
