# P0 RED remediation design — clean committed reproducibility

## Inputs

- `phases/P0.md` → `## Audit P0 — 2026-07-20`.
- `findings/P0-red-reproducibility-preflight-2026-07-20.md`.
- D51 historical exception contract and `research/14-journal-schema-exception-remediation.md`.
- Historical P0.1/P0.5 helpers and findings; their bytes remain immutable evidence.

## Decision surface

The permitted solution must satisfy all three audit findings in one sequential repair item:

1. a fresh checkout runs the committed canonical linter with no package overlay;
2. P0.1/P0.5 checks resolve explicit committed inputs/trees, not live ignored files, HEAD,
   or worktree status;
3. append-only bookkeeping publishes the historical item/bookkeeping pairs and canonical
   clean-tree lint attribution.

### Alternatives

1. **Canonical exception prerequisite + anchored plan evidence (selected, owner-gated).**
   Implement the already-decided D51 exception semantics in the owning task/plan-protocol
   sources from a clean committed worktree, then make both plan helpers consume one committed
   anchor manifest. This preserves history and keeps the strict gate.
2. **Rewrite historical journal/finding bytes (rejected).** It can make one checkout green,
   but destroys append-only provenance and violates the audit anti-scope.
3. **Plan-local linter wrapper or skip (rejected).** It leaves the canonical
   `packages/task/scripts/plan-lint.py` red, creates a second gate carrier, and cannot prove G01.

RAG:— (repo-grounded: audit block, committed `task.journal`/`plan_lint.py`, D51).

## P0.6 authority and commit topology

P0.6 is one sequential repair item, but its first commit is a separately authorized shared-
package prerequisite. No package write starts without an Approval Owner D# that accepts the
exact file allowlist, `plan-protocol` minor bump, `task` plugin minor bump, documentation/
CHANGELOG consequence, and one of the dirty-ownership dispositions below.

The current main worktree is not an implementation surface for that prerequisite. The owner
must choose one:

- **A — owner-cleared main:** the owner first commits/moves/resolves the existing dirty
  package paths; the executor proves the P0.6 allowlist is clean before editing.
- **B — isolated delivery:** the executor creates a dedicated clean worktree/branch from the
  committed P0.6 design, authors and commits there, and leaves the dirty main worktree
  untouched. P0.6 remains non-terminal until the owner integrates that commit into a clean
  target and the executor repeats all checks there.

After approval, close topology is:

1. **Prerequisite commit** — exact package canon/writer/linter/tests/docs/generated outputs.
2. **Item commit** — plan anchor manifest + the two helper repairs + new repair finding;
   this is the final Scope commit whose hash enters handoff.
3. **Bookkeeping commit** — P0.6 status/notes, P0 Status Board, append-only Update Log rows,
   journal, roadmap and handoff only. P0 is then reclosed by `plan-close`, followed by a fresh
   independent P0 audit; the current RED verdict is never overwritten by P0.6 itself.

## Exact package prerequisite contract

The hand-authored allowlist is limited to:

- `packages/task/lib/task/journal.py`
- `packages/task/lib/task/plan_lint.py`
- `packages/task/tests/test_journal.py`
- `packages/task/tests/test_plan_lint.py`
- `packages/task/commands/plan-design.md`
- `packages/task/.claude-plugin/plugin.json`
- `packages/skiller/skills/general/plan-protocol/SKILL.ru.md`
- generated `packages/skiller/skills/general/plan-protocol/SKILL.md`
- `packages/skiller/skills/general/plan-protocol/snippets/journal-template.md`
- `docs/task/plan-structure.md`
- `CHANGELOG.md`

Deterministic `skiller registry` outputs are allowed only as named derived artifacts:
`packages/skiller/skills.json`, `packages/skiller/skills/_index.md`,
`packages/skiller/docs/guide/{graph,budget}.md`,
`packages/skiller/skills/general/.claude-plugin/plugin.json`, and
`.claude-plugin/marketplace.json`. The executor stages only paths with an actual derived
byte delta and publishes the exact list. No other package, generated output, plan, FOREMAN,
fleet, or user-owned path may enter this commit.

The prerequisite implements D51 narrowly: v1 exempts only exact `friction` schema errors;
target line/raw SHA-256/canonical plan ID/exact invalid-field set/existing owner D# are
mandatory; duplicates, valid or malformed targets, hash/plan mismatch and inexact error sets
fail closed. The sidecar is not an event/status/Next carrier. A CLI append path is tested, and
the linter consumes only fully valid exceptions. No existing dirty byte is staged or claimed.

## Committed anchor contract for P0.1/P0.5

P0.6 adds `artifacts/p0-evidence-anchors.json` with schema version 1. Each evidence row pins:

- source tree used by the historical observation;
- item and bookkeeping commits;
- finding path and raw SHA-256;
- exact explicit roots and collection mode;
- redacted external input values plus canonical JSON SHA-256 when the input was ignored.

For P0.1, the only external snapshot is the 25 project IDs already published in the
historical finding; no path, secret, or other `config.json` field is copied. For P0.5, all
inputs come from the five tracked non-recursive roots at its stored source tree.

Both existing helpers keep their historical findings byte-identical. Their no-argument
`--check` resolves the committed anchor manifest by default, uses git object reads rather
than live HEAD/status, recomputes the semantic path/count sets, verifies the raw finding
digest and fails closed on missing commits, missing/malformed inputs, digest mismatch or
semantic drift. `--anchor-file` exists only for deterministic negative probes. `--write`
must not silently rewrite historical evidence; a new live snapshot requires a new finding.

## Validation and attribution

The item is green only when:

- task and skiller validation, translation freshness, registry regeneration and tests pass
  on the clean prerequisite commit;
- both helpers exit 0 in clean detached worktrees at the item commit and again at the
  bookkeeping commit, with no `config.json` present;
- canonical `plan-lint --baseline HEAD` returns `0 ERROR / 0 WARN — new 0` in those clean
  worktrees using only committed sources;
- historical P0.1/P0.5 findings and journal lines 1–50 are byte-identical to `1544cfe`;
- D53/D55/D59 vocabulary/contracts/ADR and P0.2–P0.4 item bodies are byte-identical to
  `1544cfe`;
- append-only Update Log rows publish P0.1 `f4d230e`/`d8ac22c`, P0.5
  `56239e9`/`566719e`, the prerequisite/item commit hashes, and the anchored clean lint count.

## Owner decision required

The owner must approve or reject the exact prerequisite and choose dirty ownership A or B.
Rejection is legitimate, but no current-scope fallback exists: P0 stays RED, P1.1 stays
closed, and a new owner decision would have to supersede D51 or the immutability boundary.
