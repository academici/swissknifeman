# HANDOFF — 2026-07-21 — after P3

**Next:** `/task:plan-run 2026.07.19-DUAL-PROVIDER P3.3`

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high |
| Context | NEW SESSION — P3.3 D83 repair |
| Суть | Restore the committed Codex core cache/lock from the committed semantic catalog in an isolated clean worktree; add the focused regression only. |

```text
Execute only reopened P3.3 D83 repair for 2026.07.19-DUAL-PROVIDER on gpt-5.6-terra/high.

Read AGENTS.md, CLAUDE.md, packages/skiller/CLAUDE.md, plan.md, handoff.md, phases/P3.md
(Audit P3 and P3.3), research/21-p3-codex-core-registry-remediation.md, frozen
root/contracts/provider-skill-publication-contract.md, then the P3.3 Required Reads in order.

The audit proved on clean tree a1ff88f that registry --check fails because the cache-contained
Codex core plan-protocol copy and publication-lock are stale relative to committed canonical
source. Work in an isolated clean worktree; verify the worktree-local package/repo root before
writes and invoke only ./packages/skiller/bin/skiller. Do not use, edit, stage, restore, stash,
or regenerate from the dirty main worktree.

Implement only D83: regenerate and stage only the proven changed Codex core cache/lock artifacts
from the committed semantic catalog, plus one focused test comparing current renderer-derived
Codex core artifacts (including lock) to repository cache bytes. Expected data must not derive
from the cache; demonstrate the test fails for a deliberately stale temporary cache copy. Preserve
P3.1 frozen contract, Claude outputs, publication/registry behavior, provider selection/distribution,
root .agents/skills, P4+, FOREMAN, fleet, user-global state and all owner dirt.

Run only the D83 targeted tests, py_compile, clean-tree registry --check twice and diff check.
Commit the scoped repair and plan bookkeeping separately. Then update handoff so P3.5 resumes;
do not run P3.5, phase-wide validation, G03 or create a PR in this task.
```

**Done:** G03 attempt 1 found the P3.3-owned stale Codex `core` cache-contained projection and
provenance lock on clean tree `a1ff88f`. D83 has formally reopened P3.3; P3.5 is blocked rather
than falsely terminal.

**Remaining:** D83 P3.3 targeted repair → independent P3.5 rerun → one terminal P3 validation and
clean-tree registry check → fresh G03. A P1–P3 review PR and P4 are prohibited until literal GREEN.

**Sources of truth:** `phases/P3.md` Audit P3 and P3.3; D83 in `plan.md`;
`research/21-p3-codex-core-registry-remediation.md`; frozen
`root/contracts/provider-skill-publication-contract.md`; `packages/skiller/lib/skiller/{publication,registry}.py`.

**Open risks:** The dirty main worktree currently has owner-owned canonical `plan-protocol` and
generated-output changes that mask the clean-tree defect. Any repair that reads or stages those
paths would corrupt provenance. Isolated clean-worktree evidence is mandatory.

**Workarounds/Deferred/Open questions:**

- workarounds: none; do not weaken `registry --check`.
- deferred: P3.5, terminal P3/G03, P1–P3 review PR and P4.
- open_questions: none.
