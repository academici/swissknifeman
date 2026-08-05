# HANDOFF — 2026-08-05 — after P3.5

**Next:** design-item: task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P3.5

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | repository-plan-write · evidence-reconciliation |
| Context | NEW SESSION — шаг-не-item |
| Суть | Разрешить foreign `scheduler.py` deviation P3.5 до P3.6; D98 audit 11 не запускает |
| Команда | `$ task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P3.5` |

| Model | Thinking | Approval policy | Sandbox | CWD | Context | Суть | Команда |
|:--|:--|:--|:--|:--|:--|:--|:--|
| gpt-5.6-sol | high | never | danger-full-access | `/home/vostrikov/projects/packages/swissknifeman` | `NEW SESSION — шаг-не-item` | Resolve only the recorded P3.5 scope deviation | `codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'NEW SESSION: Run $ task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P3.5. Read plan.md, phases/P3.md P3.5, roadmap.md and handoff.md. D98 forbids task:plan-audit design. Resolve the foreign scheduler.py deviation before P3.6; preserve frozen carriers and unrelated dirty worktree.'` |

**Done:** P3.5 item commit `b7c7c1a0` binds explicit CLI provider dispatch to the exact indexed admission, exact parity registry, adapter preflight and bounded worker normalization. Targeted activity tests passed 3 tests and full supervisor discovery passed 56 tests on `b7c7c1a0`.

**Remaining:** Resolve P3.5's foreign `scheduler.py` item-commit path through plan-design, then continue P3.6→P3.8. No pre-exec design audit is authorized by D98.

**Sources of truth:** phases/P3.md P3.5 Completion Notes and Known Deviations · plan.md D98/Update Log · roadmap.md current execution launch · item commit `b7c7c1a0`.

**Open risks:** The otherwise green P3.5 implementation has a material `Files` deviation: `scheduler.py` was changed in `b7c7c1a0` to expose the activity observation. Do not silently revert or expand scope; P3.5 plan-design owns the decision. Effective Codex lifecycle hooks remain `stale-source → update`, owned by P4.6/P4.4.

**Workarounds/Deferred/Open questions:**

- workarounds: none; D98 continues to forbid audit 11;
- deferred: P3.6 evidence/hash work waits on the scope decision; P4.6 owns hook repair;
- open_questions: whether a forward correction restores the P2 scheduler return shape or adds `scheduler.py` explicitly to a remediation item's Files.
