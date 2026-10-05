# Query

OpenAI Codex GPT-5.x coding agents degrade with long AGENTS.md / overloaded instructions: official OpenAI guidance (Codex prompting guide, AGENTS.md best practices) on instruction length, conflicting rules, and how to structure task context for reliable instruction following.

# Answer

OpenAI’s guidance supports your concern, with an important distinction: it recommends concise, practical instructions, but does not prescribe an ideal token or line count for AGENTS.md. The documented 32 KiB default is a loading cap, not a target; reaching it can mean instruction files stop being added, while shorter but vague or conflicting rules can still make guidance harder to follow.

## What OpenAI says

- Keep AGENTS.md short and accurate. The best-practices guide says it is more useful than a long file full of vague rules. It recommends starting with basics and adding guidance when repeated mistakes reveal a real need.
- Use it for durable, actionable project context: repository layout, build/test/lint commands, engineering conventions, constraints, and what “done” means. For task-specific needs, give Codex the relevant files or docs in the prompt rather than loading every possible rule for every task.
- For a task prompt, state four things: goal, relevant context, constraints, and completion criteria. OpenAI says this helps Codex stay scoped and make fewer assumptions.
- Layer rules deliberately. Global guidance, repository guidance, and narrower directory guidance can be separated by scope. The closest applicable file comes later in the assembled instructions and therefore takes precedence when guidance conflicts.
- The documented size limit is 32 KiB by default. Codex concatenates applicable instruction files from the project root toward the current directory and stops adding files at project_doc_max_bytes; it can be configured, but OpenAI presents splitting guidance across nested directories as an option rather than making a larger limit the default solution.

## Conflicts and precedence

Codex builds the instruction chain from global guidance and then project files, in root-to-current-directory order. Each directory contributes at most one file: AGENTS.override.md takes precedence over AGENTS.md there; an override higher in the tree can also affect what is loaded. Later, more local instructions are intended to override earlier, broader ones.
That hierarchy helps resolve deliberate scope differences, but it does not make contradictory instructions harmless. A root rule saying “always use X” and a local rule saying “never use X” leave the model to interpret which one applies; the official guidance favors concise rules that specify the behavior, scope, and exception clearly. For genuinely different workflows, put the rule near the relevant code, or use an override intentionally.
The Codex prompting guide adds a useful implementation detail: discovered instruction files are injected near the top of the conversation, before the user prompt, as separate user-role messages. This makes them persistent context—not a substitute for a narrowly specified task. The best-practices guide separately warns against overloading the prompt with durable rules that belong in AGENTS.md or a skill, and against putting too much task-specific material into standing instructions.

## A practical structure

A compact root AGENTS.md can answer: “What should apply across this repository?” Keep it to high-value shared facts and rules; put genuinely local conventions in nested files. For each task, add a short prompt with the four parts OpenAI recommends:
```
Goal: Add [specific behavior]. Context: Start with [paths/files]; follow [relevant existing pattern]. Constraints: [Only the constraints that matter for this change.] Done when: [observable behavior]; run [specific tests/checks].
```
For example, a repository-level file might contain the project map, verified test commands, a few cross-cutting conventions, and safety boundaries. A specialized subsystem can have a local AGENTS.md for its own commands or domain rules, rather than making every task inherit those details. This follows OpenAI’s advice to keep the main file practical and split out task-specific or narrower guidance when needed.

## What the sources don’t claim

OpenAI’s published guidance does not establish a universal “good” maximum such as 100 lines, 2 KB, or a certain token count. Treat such numbers as heuristics, not official Codex requirements. The 32 KiB figure is the documented default maximum for the combined discovered instruction content—not a recommended file size and not evidence that a file below the cap will be followed reliably.

Sources:
1. [learn.chatgpt](https://learn.chatgpt.com/guides/best-practices)
2. [learn.chatgpt](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
