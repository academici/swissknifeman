# P5 consumer migration reconnaissance

**Date:** 2026-08-02

## Repository facts

- `packages/skiller/lib/skiller/update.py` already has fleet fan-out through
  `skiller update --all`, but that loop replays current registry records and package-specific
  discovery. It does not consume the sealed P0 classification/action matrix. Its ordinary
  update path may remove a recognized legacy `packages/task` symlink, and the optional
  `--adopt-codex` path mutates `.swissknife.json`; neither operation is sufficient authority
  for P5 bulk migration by itself.
- The same loop is fail-soft across projects: it catches a project-level `SystemExit`, records
  `failed`, and continues. This is useful operationally but is not a cross-project transaction,
  and it does not provide an exact action-set rollback boundary.
- `packages/maind/lib/maind/provision/sync.py` similarly fans out semantic provisioners and
  preserves per-project failure rows, but the general `maind sync --all` path does not consume
  P0 artifact classifications or freeze a P5 migration manifest. It cannot substitute for the
  P5 admission gate without a new rival source of migration truth.
- P3.2 is already specified to deliver the public `observe → diff → preflighted apply →
  readback` boundary and provider-scoped package adapters; P3.3 is specified to deliver stable,
  redacted ownership/drift/migration diagnostics. P5 should sequence those public surfaces,
  not reproduce their provider or lock semantics in a plan-local helper.
- P0.1 excludes absolute consumer roots from committed evidence and originally said no later
  item reads host state directly. P5 cannot reach live projects from redacted stable IDs alone.
  The safe reconciliation is to use `~/.swissknifeman/projects.json` only as an ephemeral
  locator, then require exact stable-ID, repository identity and preimage agreement with the
  sealed P0 bundle before any project read or write.
- Existing P0 classification has five exclusive states. `local-override` and `ambiguous` are
  not safe repair candidates; `stale-managed-copy` is not automatically deletable merely
  because it is stale. The allowed action therefore needs a second, owner-approved action
  dimension rather than being inferred from the class name.

## Preflight observations

- `pwd`, `git status --short`, `codex doctor --json`, worktree-local `maind health --cwd --json`,
  `harness doctor`, `harness doctor --provider-audit`, and plan lint were run before authoring.
- `codex doctor` reported `overallStatus=ok`, model `gpt-5.6-sol`, approval policy `Never` and
  unrestricted filesystem sandbox. Harness reported the provider audit and installed hooks
  green; effort remains self-attested rather than independently observed.
- `maind health --cwd --json` reported memory round-trip, MCP hygiene and both provider trust
  projections green for SKM. This says nothing about consumer-project migration readiness.
- The active plan and broad P1–P4 implementation surfaces are already dirty/untracked. This
  design pass changes plan files only and does not treat the dirty working tree as shipped
  provider evidence.
- Plan lint was `0 errors / 0 warnings` before P5 edits.

## Verification

- Repository claims were verified from the named source files and actual preflight output.
- P5 introduces no new dependency, third-party API, provider capability claim or external
  migration practice. All decision-bearing claims in this pass are repo/plan-grounded.
- **RAG:** no new query; P5 consumes the already-captured P0/P1 control-plane and P2 locale
  evidence but makes no new external-fact verdict.
- **Unverified → repeat pass:** the terminal P0 classification/recovery artifacts and P3/P4
  public APIs do not yet exist. Every P5 item must stop when their committed identities,
  versions or action vocabulary differ from this design.
- **Workarounds/[POSSIBLE-DEFECT]:** none. A plan-local runner is allowed only as a transaction
  sequencer over frozen public APIs and sealed manifests; it may not become a second provider
  reconciler or migration classifier.
