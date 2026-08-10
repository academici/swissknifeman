# P4 recovery, worktree, security, and observability recon — 2026-08-03

## Scope and evidence boundary

This pass designs P4 only. P0–P3 are still unexecuted, so their contracts, candidate modules,
provider records and manifests are terminal preconditions rather than present evidence. No worker,
fault campaign, worktree integration or provider mutation was run. Repository reads and external
documentation establish interfaces; P4 items must create the empirical evidence.

## Recovery and security owners already present

- P2.2 owns the strict journal, lock, snapshot and local cut-point seams; P2.4 owns deterministic
  scheduler intent/observation/acceptance ordering; P2.5 owns `resume`/`reconcile`/`report`. P4 must
  attack and, if necessary, repair those owners rather than create a second recovery state machine.
  RAG:— (repo-grounded: `phases/P2.md` and `research/08-p2-prototype-design.md`).
- P3.4 is the sole provider process owner. P4 can inject process death and malformed/bounded fake
  provider records through that seam, but timeout, kill, redaction and activity acceptance may not
  drift into a second provider runner. RAG:— (repo-grounded: `phases/P3.md` and
  `research/09-p3-provider-adapter-design.md`).
- The public `task.task_contract.bundle_lint` function computes evidence-bundle member equality and
  scans actual bytes for secret, chain-of-thought, tool-payload and raw-transcript classes. It has no
  CLI subcommand. P4's independent security validator may import that public function under an
  explicit `PYTHONPATH`; candidate runtime must not copy its signatures or trust a declaration.
  RAG:— (repo-grounded: `packages/task/lib/task/task_contract.py:497-620`).
- `core.runs.EventEnvelope` and Analyst Unified Agent Trace are downstream normalized analytics
  carriers, not supervisor WAL or provider-raw owners. P4 may cross-check their privacy vocabulary;
  it must not publish into them or use their tolerant readers for resume. RAG:— (repo-grounded:
  `core/runs.py` and `packages/analyst/lib/analyst/trace.py`).

## Git linked-worktree boundary

The local client is Git `2.43.0`. Current official Git documentation says a repository may have one
main and multiple linked worktrees. A linked worktree has its own working tree and per-worktree
administrative state such as `HEAD` and index, while it shares the repository's remaining state.
Therefore linked worktrees isolate file/index lanes but are not a process, credential, hook, config,
object-store or security sandbox. RAG:✅ 2026-08-03, Context7 `/git/htmldocs` → official
[`git-worktree`](https://git-scm.com/docs/git-worktree), confidence high.

The same source documents:

- `git worktree add --detach --lock --reason <reason> <path> <commit-ish>` as a detached linked
  worktree with retained administrative metadata;
- `git worktree list --porcelain -z` as the stable machine-readable inventory;
- ordinary `git worktree remove` only for a clean worktree, with `--force` required for unclean or
  locked removal;
- `git worktree prune` as cleanup of stale administrative entries for missing worktree paths.

P4 therefore uses exact ownership metadata and never `--force` or broad `prune`. A candidate-owned
attempt worktree is created at a pinned base, locked with run/slice/attempt identity, and removed only
after it is demonstrably clean and matches that identity. Integration is serialized into a clean,
exact-base controlled repository using the attempt commit; any drift/conflict aborts and verifies the
preimage or enters OWNER. This is an internal policy built on the documented CLI semantics, not a Git
guarantee of transactionality or security. RAG:✅ source above; RAG:— for the fail-closed policy.

## External fact classes inherited without expansion

1. Current Codex/Claude non-persistence, permission, tool/child and structured-output controls are
   already verified from first-party sources in
   `findings/07-p3-provider-runtime-recon-2026-08-03.md`. P4 does not add a new provider flag or
   claim; it attacks the terminal P3 argv/event boundary. Confidence high on documented controls,
   empirical terminal records remain P0.3/P3 evidence.
2. Python 3.12 `flock`, `fsync` and `replace` limits are already verified from version-matched
   official docs in `findings/06-p2-runtime-recon-2026-08-03.md`. Filesystem-specific power-loss and
   parent-directory durability remain empirical capability evidence, not a portable guarantee.
3. Worker/subagent context isolation and total-token caution are already verified first-party in
   `findings/01-external-agent-runtime-2026-08-03.md`. P4 measures bounded returns and records unknown
   accounting; it does not issue an economy verdict.

## Preflight integrity observation

- `codex doctor --json` is green and reports model `gpt-5.6-sol`, approval `Never`, unrestricted
  filesystem sandbox and the current repository root.
- `packages/maind/bin/maind health --cwd --json` is connected and its memory round-trip plus both
  provider trust rows are green. The obsolete form `--cwd .` fails with `лишние аргументы: .` because
  `--cwd` is a boolean selector; this was a preflight invocation defect, not a failed health result.
- `.codex/hooks/lifecycle.py` compiles and returns the expected observer system message on a valid
  synthetic SessionStart payload; `.claude/maind-memory.sh` passes `bash -n`.
- The effective absolute-target dry-run remains non-green:
  `packages/harness/bin/harness hooks --target /home/vostrikov/projects/packages/swissknifeman
  --provider codex --observer --trusted --dry-run` exits 0 but reports `Статус: warning` with both
  lifecycle hook and handler `stale-source → update (source-changed)`.

P4.4 must preserve that warning as a security-readiness refusal until a separately authorized scoped
repair makes the effective dry-run green. Syntax and direct-handler success do not override the
stale-source verdict. RAG:— (direct local observation 2026-08-03).

## Verification status

- RAG: Context7 `/git/htmldocs` ×1 focused official-doc query; same-day first-party provider/Python/
  long-horizon findings reused without adding new claims; local Git/repository/preflight reads.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: physical power-loss durability, exact terminal P0–P3 shapes,
  real crash/reconcile outcomes, worktree conflict rollback, provider-auth availability and the
  effective hook repair remain execution-time P0–P4 evidence.
- Обходки/[POSSIBLE-DEFECT]: no workaround is accepted. The correct boolean `maind health --cwd`
  invocation replaces the bad preflight form; the persistent hook `stale-source` warning remains an
  open environment defect and blocks a fully-green P4 security verdict.
