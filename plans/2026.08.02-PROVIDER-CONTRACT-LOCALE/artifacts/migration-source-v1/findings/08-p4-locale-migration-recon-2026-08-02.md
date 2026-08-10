# P4 locale runtime and canonical-source migration reconnaissance

**Date:** 2026-08-02

## Repository facts

- `packages/skiller/scripts/check-translations.sh --strict` is green on the current working
  tree and reports 173 local skills with 173 `SKILL.ru.md` sources, no missing/stale pair,
  56 external skills and no literal violation. Its documented ownership is still
  `SKILL.ru.md` source → generated compact-English `SKILL.md`, the reverse of plan D18.
- `packages/skiller/lib/skiller/publication.py` records both RU and EN hashes for the 13
  repository-bootstrap identities, but provider projections consume the English file. The
  source-direction change therefore affects provenance and validators, not provider identity.
- `packages/task/lib/task/command_render.py` already owns deterministic Claude/Codex command
  projections, plugin artifacts and provider locks. `packages/task/commands/*.md` is the
  canonical command catalog; all 11 current command files contain Cyrillic prose.
- `core/provider` owns provider configuration/status semantics, while no committed
  `core/locale` package, locale catalog or locale renderer exists. P4 must add a separate
  shared locale domain rather than fold language into a provider adapter.
- A rough Cyrillic inventory over the dirty working tree found code comments/docstrings in
  279 Python files, development documentation in 135 Markdown files, and Cyrillic metadata
  in two plugin manifests. These counts are discovery signals, not an admission ledger:
  generated files, literals, fixtures and user-facing diagnostics need owner-aware
  classification before mutation.
- The relevant generated owners are already explicit: `skiller registry` owns skill/plugin/
  marketplace projections and root bootstrap skills; Task's provider renderer owns task
  command/plugin projections and locks. P4 must invoke those owners and never edit their
  outputs directly.

## Preflight observations

- `pwd` was `/home/vostrikov/projects/packages/swissknifeman`; the worktree was already dirty
  across P1/P2/P3 implementation areas and the active plan directory was untracked.
- `codex doctor --json` returned `overallStatus=ok` and named configured model
  `gpt-5.6-sol`, but exposed no effort mapping. `harness doctor` states effort evidence is
  self-attested. This pass therefore records `gpt-5.6-sol/high` as the requested route, with
  effort not independently observable.
- `packages/maind/bin/maind health --cwd` was green, including memory round-trip and both
  provider trust checks.
- `packages/harness/bin/harness hooks --target <repo> --provider codex --observer --trusted
  --dry-run` remained warning-only: `harness.codex.lifecycle.hooks` and
  `harness.codex.lifecycle.handler` are `stale-source → update (source-changed)`. The dry-run
  wrote nothing; P4 has no authority to repair them.
- `python3 packages/task/scripts/plan-lint.py
  plans/2026.08.02-PROVIDER-CONTRACT-LOCALE` returned 0 errors and 0 warnings before P4
  authoring edits. Because the plan directory is untracked, baseline attribution against
  HEAD is unavailable.

## Verification

- Repository claims were checked from the named source files, package guides and validation
  output. Current counts describe the observed dirty working tree, not shipped HEAD.
- External fact classes used by P4 are limited to BCP 47 normalization/fallback already
  verified in `findings/06-p2-locale-authoring-verification-2026-08-02.md`; P4 selects no new
  runtime library, service or external API.
- **RAG:** no new query; P4 consumes the 2026-08-02 RFC 5646/Unicode evidence captured by P2.
- **Unverified → repeat pass:** the exact frozen P2 overlay/review schemas and P3 resolver
  interfaces do not yet exist; every P4 item must stop if their terminal versions differ
  from the paths or ownership assumptions named in the item.
- **Workarounds/[POSSIBLE-DEFECT]:** none. The rough Cyrillic grep is explicitly not used as
  proof of corpus completeness or semantic review.
