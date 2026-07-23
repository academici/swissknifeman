# HANDOFF — 2026-07-23 — after P6

**Next:** manual: implementation/high

| Parameter | Value |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Native model | `gpt-5.6-terra` |
| Reasoning effort | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| CWD | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION — P6.11` |
| Суть | Implement only D123 exact explicit D108 rollback-backup lifecycle, then stop for independent P6.12. |

| Native model | Reasoning effort | Approval policy | Sandbox | CWD | Context |
|:--|:--|:--|:--|:--|:--|
| `gpt-5.6-terra` | `high` | `never` | `danger-full-access` | `/home/vostrikov/projects/packages/swissknifeman` | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'Read AGENTS.md, CLAUDE.md, packages/maind/CLAUDE.md, and plans/2026.07.19-DUAL-PROVIDER/{plan.md,handoff.md,phases/P6.md,phases/P7.md,artifacts/P6-d108-independent-conformance.md,artifacts/P7-self-host-e2e.md}. Execute task:plan-run 2026.07.19-DUAL-PROVIDER P6.11. Implement only D123 in core/provider_lock.py, core/__init__.py, packages/maind/lib/maind/provider_deploy.py, and focused core/maind tests: explicit D108 rollback removes only the two verified D121 transaction backups after exact state/hash verification, then restores the recorded carrier. Preserve D104/D108/D110; no generic *.bak cleanup/adoption, live retry/normalization, P7.2+, FOREMAN/fleet, tag/push/cleanup, or unrelated dirt. Commit and stop for independent P6.12.'
```

**Done:** P6.12 D122 independent evidence is committed in `f8d46602`. In disposable roots,
the exact two-group managed post-apply form makes the second D108 chain all `noop`, its apply
calls the writer `0` times, and its SHA inventory is unchanged. Reordered, extra, changed and
malformed observer variants refuse before a writer. Focused maind provider/deploy (`53`) and
core provider-lock (`26`) regressions and `py_compile` passed at source anchor `5830e631`.

**Remaining:** D123 reopens P6.11 only for an explicit completed-D108 rollback lifecycle.
The owner has removed only the two named D121 backup residues after confirming each equals its
sealed preimage; this exact cleanup is evidence, not a generic cleanup mechanism. P6.12 must
independently prove the source repair before any fresh P7.2 first preflight.

**Sources of truth:** `phases/P6.md` P6.12; `artifacts/P6-d108-independent-conformance.md`;
`artifacts/P7-self-host-e2e.md`; D104/D108/D110/D121/D122; `core/provider_lock.py` backup
admission and rollback paths.

**Open risks:** The one owner-authorized evidence cleanup does not replace D123. Any source
repair must still refuse all non-exact, missing, extra, symlinked or byte-different backups.

**Workarounds/Deferred/Open questions:**

- workarounds: none; no live normalization is authorized.
- deferred: D123 implementation, independent P6.12 rerun, then fresh P7.2 first preflight.
- open_questions: —
