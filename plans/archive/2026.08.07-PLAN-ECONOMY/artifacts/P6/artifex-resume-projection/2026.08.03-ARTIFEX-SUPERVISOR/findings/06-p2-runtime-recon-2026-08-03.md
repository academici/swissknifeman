# P2 runtime/durability recon — 2026-08-03

## Live reuse boundary

The current `packages/harness/bin/harness run <PLAN-ID> <Pn> --dry-run --json` is a
read-only process boundary over the live plan reader. It returns phase order, terminal exclusions,
resolved Task Contract route, the literal `Exec` cell and named refusals. On the P2 skeleton it
returned a non-degraded queue and correctly refused all five items because their required Task
Contract fields were still `—`. The prototype compiler can therefore consume this boundary and
the canonical `task.task_contract build` output instead of importing Harness internals or parsing
plan Markdown a third time. RAG:— (repo-grounded: `packages/harness/lib/harness/run/plan_reader.py`,
`packages/harness/lib/harness/run/__init__.py`, and the local dry-run on 2026-08-03).

The dry-run driver remains only a reader/reuse donor. Its live execution path is Claude-only,
sequential, has no durable run folder, retry/authority arbiter, crash reconcile or Codex adapter.
P2 must not call its worker/gate/journal loop or reinterpret `drivable=false` as an Artifex
authority decision. RAG:— (repo-grounded: `packages/harness/docs/reference/exec-wave.md`).

## Existing primitives and non-reuse decisions

- `packages/task/lib/task/task_contract.py` is the sole compiler for Task Contract route,
  authority, evidence, portability and content hash. P2 consumes its process output and never
  duplicates its predicates.
- `core.io.atomic_write_json` provides temp-file plus `os.replace`, but does not fsync the file or
  parent directory. It is not sufficient as the supervisor WAL/snapshot durability boundary.
- `core.io.read_ndjson_iter` deliberately skips malformed/non-dict lines. That tolerance is useful
  for analytics but forbidden for a recovery SSOT: P2 needs strict streaming refusal at the first
  malformed, truncated, reordered or hash-invalid record.
- `packages/task/lib/task/journal.py` owns plan-command history, not side-effect WAL. P2 links to it
  through run/item identities but does not write or replace its schema.

RAG:— (repo-grounded reads on 2026-08-03).

## Python 3.12 API verification

The local runtime is Python `3.12.3`. A version-matched official-doc query confirms:

- `fcntl.flock` is Unix-only advisory inter-process locking; it supplies cooperating-writer
  exclusion, not atomicity or durability.
- `os.replace` atomically replaces the destination name on success; atomic replacement is not a
  durability guarantee.
- `os.fsync` flushes the file descriptor; a buffered Python file must be flushed before fsync.

Sources: [Python 3.12 `fcntl`](https://docs.python.org/3.12/library/fcntl.html),
[Python 3.12 `os.replace`](https://docs.python.org/3.12/library/os.html#os.replace),
[Python 3.12 `os.fsync`](https://docs.python.org/3.12/library/os.html#os.fsync), checked
2026-08-03; confidence medium (one primary documentation set). The Python reference did not make
a filesystem-independent promise for parent-directory fsync/power-loss persistence. P2 therefore
records directory-fsync support as an observed capability and refuses to claim stronger physical
durability than the host proves.

## Environment honesty

`codex doctor --json`, `harness doctor`, mAInd health and the incoming plan lint were green. The
effective no-write Codex hook plan still reports status `warning` with
`harness.codex.lifecycle.hooks` and `.handler` as `stale-source → update`; exit code 0 is not
treated as a green hook verdict. Final provider-runtime discovery also found zero enabled
`task@swissknifeman` entries in `codex plugin list --json`, so the generated adapter's installed
plugin-root lint command could not resolve a runtime copy (`expected one enabled ...`, then no
script was run). The worktree-local canonical linter remains the trusted validation path for this
pass and is reported separately; neither environment defect is repaired here.

## Проверка (verification status)

- RAG: Context7 resolved Python but had no exact 3.12 corpus; version-mismatched docs were not used.
  Perplexity Web ×1 returned the three official Python 3.12 pages above; local repo/CLI recon was
  read directly.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: filesystem-specific power-loss guarantees and parent-directory
  fsync semantics remain empirical P4 evidence; P2 records capability/limitations instead of
  promoting them to a guarantee.
- Обходки/[POSSIBLE-DEFECT]: none introduced; the stale-source hook state remains a named external
  environment defect. Worktree-local plan lint is the explicit validation fallback because the
  Task plugin is not installed/enabled in Codex runtime discovery.
