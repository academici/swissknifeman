# analyst — continuous learning ecosystems academici

Deterministic (stdlib-only, **on-demand — without daemon**) layer that accumulates
«hard-won lessons» from task threads Claude Code for all ecosystem projects at once and -
**with a man at the gate** — turns them into reusable knowledge (memory mAInd → skills).
Not a separate analyzer in each project, but ONE layer on top of many packages and projects.

> Implemented circuit: **P1 (MVP)** — `digest` + lessons-store + human `review`/`promote`;
> **P2** — cross-project aggregator `scan`; **P3** — confidence-arithmetic (Beta/decay) +
> numeric state-machine `recompute` + mem0-taxonomy; **P4** — `suggest` → DRAFT skill
> (`SKILL.ru.md` in staging, promoter - person). Further on roadmap: `analyst-capture` + `observe.sh` (P5).
>
> 📖 Documentation: [`docs/`](docs/) (VitePress — standalone + umbrella unit).

## Why is this so (anti-collapse)

Naive «self-learning» calls *model collapse*. Proven antidote - **self-verification**
+ **never throw away ground-truth** (human-verified anchors). Therefore human-gate +
provenance + validate-before-promote — is not caution, but a sufficient condition against degradation.

## Data flow (MVP)

```
<project>/.claude/runs/<sid>.json          (run-report — writes SessionEnd-hook harness)
   │  analyst digest → deterministic candidate extraction (high-precision signals)
   ▼
<project>/.claude/analyst/lessons/{ephemeral,candidate,curated,deprecated}/<id>.json  (LOCAL)
<project>/.claude/analyst/audit.ndjson     (append-only provenance)
   │  analyst review  → list + diff against active (Jaccard, stdlib)
   │  analyst promote <id>  → MAN confirms → state++ → audit
   ▼  (curated) → maind memory → pops up on SessionStart (memory-digest-hook)
```

**Privacy invariant:** raw materials (raw-transcript) — LOCAL-only; goes out only
abstract lesson (trigger+action+evidence). Secrets are by reference only, never by value.

## Commands

```bash
analyst digest    [--cwd | --session UUID]      # run-report → candidates for ephemeral/
analyst review    [--state ephemeral|candidate|curated] [--json]
analyst promote   <id> [--to candidate|curated] [--yes]   # human-gate; curated → memory mAInd
analyst deprecate <id>                          # soft-demo (not deleted - audit)
analyst doctor                                  # environment diagnostics
analyst workflow-scan --output DIR --now ISO    # read-only workflow fleet evidence
```

## Development

```bash
bash scripts/test.sh          # unittest (without network and daemons)
bash scripts/validate.sh      # py_compile + bash -n + JSON + required files + tests
```

stdlib-only; `Env(BaseEnv)` explicit; atomic JSON; messages in Russian. Convention - in `CLAUDE.md`.
