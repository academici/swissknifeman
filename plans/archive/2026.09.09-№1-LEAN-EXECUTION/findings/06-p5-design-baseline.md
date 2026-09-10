# P5 design baseline — 2026-09-09

RAG:— (repository files, worktree-local Skiller/Maind CLI output and read-only filesystem
reconnaissance on 2026-09-09).

## P5.1 — description trigger debt

- `packages/skiller/scripts/desc-trigger-burndown.txt` contains 61 active debt keys. The validator
  owns membership and already rejects new debt while warning on stale entries.
- `packages/skiller/lib/skiller/quality/audit.py` exposes per-skill `tier0`, direct
  `loaded_count`, resident channel and honest usage notes, but it does not join the ratchet or emit
  a description-debt queue/score.
- `packages/skiller/docs/guide/skill-taxonomy.md` already defines authoring priority as observed
  usage multiplied by the skill's listing share. The implementation gap is machine ownership of
  that join, not another prose rule.
- The worktree-local `skiller bucket-audit --since 30 --json` probe scanned only two projects and
  returned zero direct calls for all 61 debt rows. It also emitted repeated warnings that
  `session-observer` requires excluded `shared-memory`. This run cannot distinguish low demand from
  incomplete visibility and is not a valid rewrite order.

## P5.2 — workflow fleet

The read-only reconnaissance normalized enabled `config.json` project entries, considered explicit
`local_path`/`vault_path` plan roots and their active/archive workflow directories, then grouped
exact file bytes by SHA-256. It observed:

| Measure | Count |
|:--|--:|
| path occurrences before digest deduplication | 55 |
| unique content digests | 40 |
| unique digests containing `export const meta` | 38 |
| unique legacy/no-meta scripts | 2 |

The counts prove that the owner-prioritized fleet-synthesis item has a real corpus, but they are a
dated baseline rather than acceptance constants. Local/vault mirrors repeat identical bytes, and
archive carriers contain most of the historical field evidence; a scanner that counts paths or
only active plans would overstate or miss the corpus.

Current Analyst `scan.py` reads the maind-shaped project registry but only aggregates lesson stores.
Current Task owns four workflow templates plus their type/stage/slot rules. No code path currently
discovers workflow artifacts, statically extracts their test/review/verify structure, deduplicates
mirrors, compares the result with the templates or produces a Rule-of-Three verdict.

## Design constraints derived from evidence

1. Positive direct usage may prioritize description debt; zero/missing usage remains insufficient.
2. `desc-trigger-burndown.txt` and `budget.py` remain the membership and cost owners.
3. Fleet scripts are untrusted input: read bytes and parse conservatively; never execute/import JS.
4. Exact mirrors count once; a reusable pattern needs three distinct plan identities, not three paths.
5. Analyst may propose and report. Cross-project writes, automatic skill promotion and automatic new
   Task template families remain outside the command.
