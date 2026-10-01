# Claude: comparison of two skills (take?)

You have been given two `SKILL.md`. Decide whether they duplicate each other in purpose, and what
do. Anti-bloat — priority: the new skill is justified only without intersections.

## Analyze
1. **Purpose** — what everyone actually does (by «Context» and body, not by name).
2. **Overlap** — what instructions/outputs match; percentage of intersection by eye.
3. **Boundaries** — is there a part that is unique to everyone.

## Verdict (select one)
- **MERGE** — merge into one; indicate which one to leave as a base and what to move.
- **SPLIT-CLARIFY** — leave both, but separate `description`/boundaries so that the agent
  was not confused when to use which.
- **KEEP** — there is no intersection, both are needed as is.

For MERGE/SPLIT — specific plan: what's in `requires`/`produces_for`, what's in `snippets`,
which lines to delete as a duplicate.
