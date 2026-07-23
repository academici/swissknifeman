# HANDOFF — 2026-07-23 — after P0.1

P0.1 переоткрыт для attempt 3: downstream enumeration исправлен, но generated
`core` source остаётся thin и теряет canonical runtime support files.

**Next:** run-items: task:plan-run 2026.07.23-FLEET-DUAL-PROVIDER P0.1

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | skills.repository |
| Context | same-session — item |
| Суть | Исправить owning Codex generator: generated core и внешний carrier должны содержать runtime tree. |

```
$ task:plan-run 2026.07.23-FLEET-DUAL-PROVIDER P0.1
```

**Done:** Attempts 1–2 сохранили selected parity, ownership, explicit install boundary, downstream runtime enumeration и symlink containment; independent audit отверг self-contained claim для generated `core`.
**Remaining:** P0.1 attempt 3 — generator regression test/fix, regeneration, package gates и повторный independent audit. P0.2 не начат.
**Sources of truth:** `plan.md` · `phases/P0.md` · `findings/P0.1-attempt2-independent-audit.md` · `findings/P0.1-root-review-runtime-assets.md` · `packages/skiller/lib/skiller/publication.py` · `packages/skiller/tests/test_codex_publication.py`.
**Open risks:** Generated core lock и checked-in adapter cache должны перечислять runtime files детерминированно; downstream carrier обязан перенести тот же набор без maintenance leakage.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: реальные consumer writes и repair остаются за P1; P0.2 не начат.
- open_questions: —
