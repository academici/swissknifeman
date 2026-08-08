# P3 control-plane implementation reconnaissance

**Date:** 2026-08-02

## Repository facts

- `core/provider/config.py` is a pure resolver over already-read operation, project,
  fleet-project and fleet-default layers. It produces `ResolvedProviderConfig` and
  field-level provenance, but it has no control-plane desired/observed/status envelope.
- `core/provider/manifest.py` projects the capability manifest into the existing config
  catalog; `core/provider/registry.py` selects an adapter only after capability gates;
  `core/provider/artifact.py` and `lock.py` already implement deterministic renders,
  ownership boundaries, no-write planning and explicit apply/repair classification.
- Package provider seams are distinct: Harness has provider render/audit/trace modules;
  Maind has provider configuration layers and deployment planning; Skiller owns project
  connection/publication/update paths; Task owns command rendering. These seams are
  adapters, not replacements for `core/provider` domain ownership.
- The present worktree contains unrelated or unclassified changes in those areas, including
  an untracked `core/provider/runtime.py`. P3 execution must classify its exact item scope
  against terminal P0 evidence and must never stage foreign paths.

## Preflight observations

- `python3 packages/task/scripts/plan-lint.py plans/2026.08.02-PROVIDER-CONTRACT-LOCALE`
  returned `OK (1 план(ов), 0 ошибок, 0 предупреждений)` before P3 edits.
- `packages/maind/bin/maind health --cwd` was green for project `swissknifeman`, memory
  round-trip, the maind hook and Claude/Codex trust.
- `codex doctor --json` returned `overallStatus=ok`, but its runtime record names
  `gpt-5.6-terra` and exposes no observable effort mapping. This conflicts with the
  command's requested `frontier/high` provenance and must remain P0.1 evidence; it does
  not authorize changing global defaults or claiming a verified route.
- `packages/harness/bin/harness hooks --target <repo> --provider codex --observer --trusted
  --dry-run` reported `warning`: `harness.codex.lifecycle.hooks` and
  `harness.codex.lifecycle.handler` are `stale-source → update (source-changed)`. The
  dry-run performed no write. This is a P0 inventory/recovery input, not P3 repair scope.

## Verification

- Repository claims were checked by reading the named modules and their tests.
- No new library, service, provider API or best-practice claim is introduced by P3 design;
  desired/observed and versioned-upgrade external rationale is the already captured
  `findings/05-p1-contract-verification-2026-08-02.md`.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: P0.1 must capture the actual runtime model/effort mapping
  and hook artifact ownership in the sealed fleet evidence before P3 execution.
- Обходки/[POSSIBLE-DEFECT]: none; no attempted repair was made.
