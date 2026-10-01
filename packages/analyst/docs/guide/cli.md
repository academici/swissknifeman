# CLI and commands

CLI — `analyst <command> [args]` (thin bash-launcher → `python3 -m analyst`). Also available as
plugin Claude Code (`/analyst:*`) and through the root router `swissknifeman analyst …`. All commands -
deterministic, on-demand, without daemon; messages in Russian.

## `analyst digest`

```
analyst digest [--cwd | --session UUID] [--project ID] [--dry-run] [--json]
```

Deterministically extracts candidate lessons from fresh `run-report` run on high-precision signals
(**resolved-failure** «command crashed and then passed»; explicit **dev-loop workarounds**) →
`.claude/analyst/lessons/ephemeral/` (LOCAL). `--dry-run`/`--json` — preview without recording.

## `analyst scan` (P2)

```
analyst scan [--min-projects N] [--namespace NS] [--threshold T] [--no-prune] [--dry-run] [--json]
```

Cross-project aggregator: bypasses the registry `config.json:projects[]`, reads per-project lessons,
greedy-Jaccard-clusters and detects patterns that repeat in **≥N projects** (default 3),
→ draft-sentences in `~/.swissknifeman/analyst/suggestions/` + index `index/by_pattern/`.
**Namespace-isolated**. Reconciliation: orphaned artifacts are removed **strictly in scope run**
(`--no-prune` turns off, `--dry-run` shows). More details - [Life cycle](./lifecycle).

## `analyst workflow-scan`

```
analyst workflow-scan [--project ID] --output DIR|FILE.json --now ISO [--json]
```

Read-only inventory workflow-scripts only from explicit ones `local_path`/`vault_path` plan-root
enabled-projects. The command hashes the bytes before parsing, saves aliases mirrors, believes Rule of
Three on different plans and compares static features with four Task templates. JavaScript
not executed, absolute paths, prompts and script bodies are not included in the report. Result
`workflow-fleet-report/v1` can only offer a proven refinement of an existing slot;
fifth template-family and changing the stage matrix remain `report-only`.

## `analyst suggest` (P4)

```
analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]
```

Cross-project pattern (`index/by_pattern/`) → **DRAFT** skill `SKILL.ru.md` + `draft.meta.json`
in `~/.swissknifeman/analyst/drafts/<pattern_id>/`. **NOT** writes in `skills/`, **NOT** generates EN-canon,
**NOT** registers - the promotion to the bucket is made by a person. Re-suggest protected from manual edits
(`--force` overwrites); orphaned drafts - warning, not deletion. Details -
[suggest →](./suggest).

## `analyst review`

```
analyst review [--state ephemeral|candidate|curated|deprecated] [--project ID]
```

Show lessons by condition + structured diff against active (Jaccard) + mem0-recommendation
(`ADD`/`UPDATE`/`NOOP`/`CONFLICT`). Read-only.

## `analyst recompute` (P3)

```
analyst recompute [--now ISO] [--dry-run]
```

Deterministic recalculation confidence from append-only `events.ndjson` (Beta-average × volume × decay)
→ numeric state-machine (auto `ephemeral→candidate`; `curated` — human only; drawdown →
soft-deprecate). Restore from logs at fixed `--now`. There is no demon.

## `analyst promote` / `deprecate`

```
analyst promote <id> [--to candidate|curated] [--supersedes ID] [--force] [--yes]
analyst deprecate <id>
```

Advance lesson through pipeline `ephemeral→candidate→curated`. **Go to `curated` requires consent
person** (`confirm` on tty or `--yes`) and pops up in memory [mAInd](/maind/guide/memory).
Conflict with active lesson → **flag-and-ask** (auto-resolve disabled: resolve `--supersedes` or
`--force`). `deprecate` — soft-demo (not deleted, auditable).

## `analyst status`

```
analyst status [--json]
```

Read-only summary of a hundred lessons: counters by state, `curated-ready` (numbers for curated yes -
need a person), `promote_failed` (memory was unavailable - sent `promote --retry-failed`), number
events, dates of last `digest`/`recompute`. Doesn't change anything.

## `analyst compact`

```
analyst compact [--before ISO] [--dry-run] [--json]
```

Reduce old events `events.ndjson` (older `--before`, or ALL) into one snapshot-event for the lesson.
Amounts (S/N/tests) and the age of the last event are preserved, so [`recompute`](#analyst-recompute-p3)
before and after gives **the same** confidence. `--dry-run` — show, do not write anything. Provenance of the operation -
in `audit.ndjson`.

## `analyst sessions`

```
analyst sessions [--project P] [--weeks N] [--json]
```

Weekly ISO-median `first_turn_overhead`/`fresh-per-turn` from LIVING jsonl-session transcripts
(`~/.claude/projects/<encoded-cwd>/*.jsonl`, separate source from `usage-trend.ndjson` —
he feeds `analyst token-report`); `--project P` resolve `local_path` by id from the node registry,
without flag - current directory. Warn in stderr as the week's median increases >20% to previous (calendar
adjacent) week - signal context-economy-relapse (permanent alternative to one-time measurement
`skiller budget --first-turn` / `maind doctor --context`).

## `analyst doctor`

```
analyst doctor
```

Environment diagnostics (python / core / maind).
