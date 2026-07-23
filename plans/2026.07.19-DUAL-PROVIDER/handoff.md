# HANDOFF — 2026-07-23 — after P6.12

**Next:** manual: frontier/high

| Parameter | Value |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | plan-design |
| Native model | `gpt-5.6-sol` |
| Reasoning effort | `high` |
| Approval policy | `never` |
| Sandbox | `danger-full-access` |
| CWD | `/home/vostrikov/projects/packages/swissknifeman` |
| Context | `NEW SESSION — design gate` |
| Суть | Design only the bounded owning repair for D121 rollback backup residue; no live retry. |

| Native model | Reasoning effort | Approval policy | Sandbox | CWD | Context |
|:--|:--|:--|:--|:--|:--|
| `gpt-5.6-sol` | `high` | `never` | `danger-full-access` | `/home/vostrikov/projects/packages/swissknifeman` | `NEW SESSION` |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access 'Read AGENTS.md, CLAUDE.md, packages/maind/CLAUDE.md, and plans/2026.07.19-DUAL-PROVIDER/{plan.md,handoff.md,phases/P6.md,phases/P7.md,artifacts/P6-d108-independent-conformance.md,artifacts/P7-self-host-e2e.md}. Run task:plan-design 2026.07.19-DUAL-PROVIDER P6.12. Design only the bounded owner/source repair for D121 rollback leaving `.codex/hooks.json.provider-artifact.bootstrap-transfer.bak` and `.mcp.json.provider-artifact.bootstrap-transfer.bak`: preserve D104/D108/D110 targets, preimages, bindings, lock semantics and fail-closed admission. Do not delete or normalize live residue, execute P7.2, apply/repair/rollback, enter P7.3+, FOREMAN/fleet, tag/push/cleanup, or change AGENTS.md, .serena/project.yml, package source/tests, or unrelated dirt.'
```

**Done:** P6.12 D122 independent evidence is committed in `f8d46602`. In disposable roots,
the exact two-group managed post-apply form makes the second D108 chain all `noop`, its apply
calls the writer `0` times, and its SHA inventory is unchanged. Reordered, extra, changed and
malformed observer variants refuse before a writer. Focused maind provider/deploy (`53`) and
core provider-lock (`26`) regressions and `py_compile` passed at source anchor `5830e631`.

**Remaining:** P6.12 is blocked on bounded design of the D121 rollback backup lifecycle. The
public real-root D108 dry reader is still writer `0` and leaves its protected inventory
unchanged, but correctly refuses `bootstrap-backup-present` while the two ignored exact backup
files remain. A fresh P7.2 must begin from first preflight only after redesign, implementation
and a rerun of independent P6.12 evidence.

**Sources of truth:** `phases/P6.md` P6.12; `artifacts/P6-d108-independent-conformance.md`;
`artifacts/P7-self-host-e2e.md`; D104/D108/D110/D121/D122; `core/provider_lock.py` backup
admission and rollback paths.

**Open risks:** Removing the residue manually would violate the fail-closed ownership and
rollback boundary. The retained backup bytes exactly match the sealed target preimages, but
their presence prevents a new initial D108 admission as designed.

**Workarounds/Deferred/Open questions:**

- workarounds: none; no live normalization is authorized.
- deferred: bounded design, implementation, independent P6.12 rerun, then fresh P7.2 first preflight.
- open_questions: which transaction-owned rollback seam removes only transaction-created backups while preserving the existing D104/D108 failure recovery contract.
