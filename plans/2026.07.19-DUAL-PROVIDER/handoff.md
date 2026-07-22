# HANDOFF — 2026-07-22 — after P6.12

**Next:** design-item: task:plan-design 2026.07.19-DUAL-PROVIDER P6.11

| Параметр | Значение |
|:--|:--|
| Model | `gpt-5.6-sol` |
| Thinking | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| CWD | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION — шаг-не-item` |
| Суть | Reopen only P6.11 for the RED P6.12 live-reader preflight defect, then specify bounded fix-forward. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.07.19-DUAL-PROVIDER P6.11; read AGENTS.md, CLAUDE.md, plans/2026.07.19-DUAL-PROVIDER/{plan.md,handoff.md,phases/P6.md,artifacts/P6-d108-independent-conformance.md}; reopen only P6.11 to repair its expected-root and pre-carrier dual-projection wiring. Preserve D108-D111, frozen P2 ownership/preimages, P6.12 evidence, no live apply/repair/rollback, P7+, FOREMAN, fleet, tag, push, cleanup and owner AGENTS.md.'
```

**Done:** P6.12 evidence commit `261da27a` independently proves P2.7's 26-test chained rollback
suite and P6.11's 46-test focused package suite. The real root was inspected only through dry
readers: writer spy `0`, three explicit existing-path SHA-256 values unchanged, and no absent
carrier/lock/handler appeared.

**Remaining:** Reopen/repair/reclose P6.11; re-run P6.12 from the independent oracle; then P6
close and fresh independent audit. P7.2 is not runnable.

**Sources of truth:** `artifacts/P6-d108-independent-conformance.md` · `phases/P6.md` P6.11/P6.12 ·
`research/26-p7.2-s1-o1-remediation-design.md` · D108–D111 in `plan.md`.

**Open risks:** The live facade passes its maind package root to the canonical-project gate and
builds projections before the planned D108 dual selection; either defect prevents required live
candidate classification. P5 retains `2 (на HEAD)` inherited DoR/workflow warnings.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: all live apply/repair/rollback and exact live action approval remain P7.2-only after isolated GREEN.
- open_questions: —
