# Finding 21 — Task worktree-local CLI path is not executable

**Status:** open · environment/instruction defect · non-product

Root worktree-safety instructions require package writes and checks through
`packages/<name>/bin/<cli>`. For Task that resolves to `packages/task/bin/task`, but the package is
plugin-only and that path does not exist in the current trusted worktree. The attempted local help
command failed with exit 127 before any plan validation ran.

This audit closeout therefore used the actual worktree-local scripts under `packages/task/scripts/`
and did not count the missing launcher attempt as green evidence. The owning instruction source or
Task package routing documentation must reconcile the generic package-CLI rule with Task's explicit
plugin-only boundary; this is outside P0 product scope and does not justify another P0 audit.
