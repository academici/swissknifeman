# P3.3 Codex core projection registry remediation

## Finding and ownership

G03 attempt 1 reproduces a product defect on the clean detached P3 close tree
`a1ff88f`: `./packages/skiller/bin/skiller registry --check` reports the
cache-contained Codex `core` member
`adapters/codex/core/skills/general/plan-protocol/SKILL.md` and the derived
`publication-lock.json` stale relative to the committed canonical
`skills/general/plan-protocol/SKILL.md`. The P3.3 renderer is the owning seam:
it creates the `core` bundle and lock from the immutable semantic catalog.
P3.5 is its dependent independent proof; it is not an alternate writer or an
appropriate place to mask the defect.

This is a generated-artifact coherence omission, not a change to P3.1's frozen
identity, bundle, lock, source, selection, install, or diagnostic contract.
The current dirty worktree happens to contain a later owner-owned canonical
`plan-protocol` edit plus matching derived local outputs; it must not be used as
the source of the repair or be staged. The repair is designed and verified in
an isolated clean worktree rooted at the current committed repair base.

RAG:— (repo-grounded: `phases/P3.md` Audit P3 2026-07-21, commit `a1ff88f`,
`packages/skiller/lib/skiller/{publication,registry}.py`, frozen
`root/contracts/provider-skill-publication-contract.md`).

## Minimal repair

1. In an isolated clean worktree, invoke only the worktree-local
   `./packages/skiller/bin/skiller registry` after verifying that its resolved
   package/repository root is that worktree. Do not run a global `skiller` and
   do not use the dirty main worktree as an input.
2. Stage only the P3.3 generated Codex cache-contained `core` artifacts whose
   expected bytes changed from the committed semantic catalog: the copied
   `plan-protocol/SKILL.md` and `publication-lock.json`, plus any directly
   regenerated Codex `core` manifest only if byte comparison proves it changed.
   Preserve all unrelated generated outputs and every owner-owned dirty path.
3. Add one repository-facing regression in
   `packages/skiller/tests/test_codex_publication.py`. It builds the current
   semantic catalog through `build_codex_publication()` and byte-compares every
   declared Codex `core` artifact on disk, including `publication-lock.json`,
   with the renderer's expected managed bytes. The expected bytes come from the
   catalog/renderer, never from the cache; mutating a canonical core member while
   retaining the old cache must fail the test.
4. Keep `publication.py`/`registry.py` behavior, P2 provenance grammar and
   `registry --check` unchanged. The existing drift gate already detects the
   defect; the regression makes the cache-contained core member/lock relation a
   focused P3.3 acceptance seam instead of relying only on terminal CLI evidence.

No public symbol, schema, version, frozen contract, provider selection,
distribution behavior, Claude output, root `.agents/skills`, user-global Codex
state, FOREMAN, fleet, or P4 artifact is in scope.

## Acceptance and execution order

Run in the isolated clean worktree, before any phase-wide validation:

```bash
PYTHONPATH=packages/skiller/lib:packages/skiller:. \\
  python3 -m unittest tests.test_codex_publication tests.test_publication
./packages/skiller/bin/skiller registry --check
python3 -m py_compile packages/skiller/lib/skiller/publication.py \\
  packages/skiller/lib/skiller/registry.py
git diff --check
```

The new focused test must fail against a deliberately stale temporary copy of
the cache and pass only when the committed cache and lock are generated from the
same catalog. The normal regeneration must be deterministic: a second
`registry --check` is clean. The scope diff is limited to the existing P3.3
test and the proven generated Codex `core` outputs.

After this targeted repair commits, P3.5 reruns its independent inventory/channel
parity evidence without changing expected data. Only then run one terminal
P3 package validation, clean-tree registry check, phase close, and fresh G03
audit under D80/D81. A review PR and P4 remain prohibited until literal G03
GREEN.

## Why this is the smallest safe route

Changing canonical `plan-protocol` to match the stale cache would violate P3.3
Scope Excluded and consume owner dirt. Relaxing `registry --check`, omitting
the lock, or treating a cache member as a thin adapter would violate frozen S2,
S3 and S6. Regenerating only from the committed catalog restores the already
specified self-contained bundle and gives the focused regression a deterministic
oracle.
