# Claude Fable 5 — promting

> **Reference:** [Official Guide Anthropic by prompting Fable 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5).

## What is Fable 5

Fable 5 — model from the family **Mythos** (Anthropic). Not to be confused with Sonnet/Opus/Haiku.
Optimized for **long-horizon autonomous tasks**: is capable of working without
interruptions on complex multi-step tasks, delegate independently
subtasks and verify your own conclusions.

## Prompt structure (XML-tags)

```xml
<role>
Expert role description. One sentence. Clearly and without water.
</role>

<context>
Problem context: what kind of project, technologies, limitations.
The more specific the better.
</context>

<task>
The essence of the problem. Can be divided into axes/sections via nested tags:

<axis id="1" name="Axis name">
What exactly to check/do along this axis.
</axis>

<axis id="2" name="Other axis">
...
</axis>
</task>

<output>
Format and structure of the expected result.
Headings, code examples, final summary — describe explicitly.
</output>

<constraints>
What the model should NOT do.
For example: do not change files, only the report, do not invent problems without evidence.
</constraints>
```

## Parameter `effort`

Set **via UI** (selector in the interface), **not a tag in the prompt**.

| Level | When to use |
|---|---|
| `low` | Short questions, quick lookup |
| `medium` | Standard tasks |
| `high` | Code audit, architectural analysis, complex refactoring |
| `xhigh` | Only for extremely voluminous autonomous workflows |

For code reviews and technical audits - **`high` is enough**.

## Mode Thinking (checkbox in UI)

- Enable **optional** for code auditing.
- Fable 5 when `effort=high` is already running in deep mode reasoning.
- Checkbox Thinking in some clients controls **display** internal
  reasoning - not the quality of the answer itself.
- **Don't ask** model «show your reasoning» / «show chain-of-thought» —
  this falls under restrictions reasoning-extraction.

Instead ask:

```
Before reporting each finding, verify it against actual code.
If you are not certain — state that explicitly.
```

## Key differences from regular prompting

| Regular models | Fable 5 (Mythos) |
|---|---|
| Need some hints «think step by step» | Autonomously plans steps itself |
| One long monolithic prompt | XML-sections with clear roles |
| Ask «show your thinking» | Not allowed - prohibited reasoning-extraction |
| `temperature`, `top_p` in the prompt | Only via API-parameters |
| Effort not relevant | `effort` — key quality parameter |

## Practice: Code Audit Template

```xml
<role>
You are a senior [language/framework] architect specializing in [task type].
</role>

<context>
Project: [name]
Repo: [link]
Stack: [list of technologies]
Goal: [what needs to be improved]
</context>

<task>
Conduct a full technical audit across N axes.
For each finding include: file path, line number, severity (critical/major/minor),
concrete fix with code example.
Before reporting each finding, verify it against actual code.
If a module has no issues on an axis, state that explicitly.

<axis id="1" name="Architecture">...</axis>
<axis id="2" name="Reliability">...</axis>
...
</task>

<output>
## Axis N: [Name]
**Issues found:** X (critical: N, major: N, minor: N)

### [SEVERITY] Issue title
**File:** `path/to/File.php:42`
**Problem:** description
**Current code:** ```code```
**Fix:** ```code```

---
## Executive Summary
Top-5 priorities by impact.

## Refactoring Roadmap
Ordered phases with effort estimates.
</output>

<constraints>
- Report findings only — do not modify files.
- Only report issues with evidence in actual code.
- Keep findings actionable: drop details that don't change what the reader does next.
</constraints>
```

> `effort` is set to UI, and not a tag - see above.

## Passing code to the model

Fable 5 does not have direct access to GitHub. Options:

**Collect sources using script:**

```bash
find packages -name "*.php" | while read f; do
  echo "// FILE: $f"
  cat "$f"
  echo -e "\n---\n"
done > source_dump.txt
```

Insert content between tags:

```xml
<codebase>
// FILE: packages/core/src/...
...
</codebase>
```

**Step-by-step analysis:** run the prompt separately for each module - gives more
deep result.

## Client settings

| Parameter | Recommendation |
|---|---|
| Model | Fable 5 / Mythos |
| Effort | `high` |
| Timeout | 5–10 minutes (model can think for a long time) |
| Streaming | enable |
| Thinking checkbox | at your discretion, not critical |
