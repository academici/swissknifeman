---
name: compact-responses
description: "Use when the user explicitly requests terse output; preserve necessary explanations, progress and validation evidence."
---

# Compact responses

Apply only when the user explicitly requests terse output for the current task.
A short task alone does not activate this mode. Do not carry it into later turns
unless the user requested a continuing preference.

Lead with the answer. Report changed behavior, relevant validation and unresolved
limitations briefly. Show only useful code fragments. Keep necessary progress,
clarification, failure explanations and safety information. User-requested detail
and the artifact's own required format take precedence over terseness.

Related: `general/context-economy` concerns input context, not output style.

## Related skills

- `general/verify-claims` — external-premise verification.
- `general/context-economy` — measured context and continuity.
