# What is analyst

**analyst** — package **lifelong learning** ecosystemsy academici. He extracts
«hard-won lessons» from task threads Claude Code (by `run-report` runs) and - **with a person
in the gate** — promotes them to reusable knowledge: first to shared memory [mAInd](/maind/),
then (at the request of the person) in [skills skiller](/skiller/guide/). CLI — `analyst`.

Package **deterministic**: only stdlib Python, **on-demand** (without daemon/networks), read-only by
projects. Same entrance → same output; does not decide anything for a person.

## Two layers (here - only layer-1)

| Layer | What | Where |
|:--|:--|:--|
| **Layer-1 - data/pipeline** | `digest` → lessons-store (state + provenance) → `review`/`promote` → cross-project `scan` → `suggest` | **this package** |
| **Layer-2 - prompt discipline** | skills (`field-feedback-loop` etc.) — how to catch lessons in gray hair | out of package (skiller) |

## Main invariant

> **Auto-recording to skills is prohibited.** analyst only *suggests*: retrieves, displays, ranks.
> Promotit - **person** (`confirm` on tty or `--yes` = conscious input).

The rest of the rules follow from it: transition to `curated` requires consent, `suggest` writes only
staged-draft (not in `skills/`), and only an abstract lesson comes out.

## Privacy

Raw materials (raw-run transcript) — **LOCAL-only**, in `<project>/.claude/analyst/`. Out - into memory
[mAInd](/maind/guide/memory) on `curated` and in cross-project index - goes only **abstracted**
`trigger → action` (+ links to evidence). Secrets - only by reference, not by value.

## Five Pipeline Commands

```
digest    run-report run        → candidate-lessons (ephemeral, LOCAL)
review    show by state     + diff against active
recompute events.ndjson             → confidence + numeric state-machine (P3)
promote   ephemeral→candidate→curated (man-gate) → comes to mind mAInd
scan      project registry            → cross-project patterns (namespace-isolated)
suggest   cross-project pattern      → DRAFT skill (drafts/), promoter - person (P4)
```

Details: [CLI and commands →](./cli) · [Lesson life cycle →](./lifecycle) ·
[Pathology catalog →](./pathologies) · [suggest — skill draft →](./suggest) ·
[Package architecture →](../architecture).
