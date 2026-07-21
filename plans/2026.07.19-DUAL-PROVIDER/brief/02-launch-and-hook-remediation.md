# Owner refinement — Codex launch and hook remediation

**Date:** 2026-07-20

The root Codex instruction carrier must preserve the important launch lessons accumulated
during the dual-provider bootstrap, with the same discipline used for disputed points in
`CLAUDE.md`: compact durable rules, not an incident dump.

Owner requirements:

1. When a new/restarted Codex session needs the broad trusted self-host boundary, the handoff
   must give a copy-paste launch command with repository cwd, routed model/effort and explicit
   full-access sandbox/approval flags. A bare restart command is insufficient.
2. This full-access form is specific to trusted swissknifeman self-hosting and must not leak
   into FOREMAN or fleet defaults.
3. Hook and command defects observed during launch must be diagnosed and fixed, not merely
   mentioned or worked around. Stable recurrence-prevention rules belong in root `AGENTS.md`;
   incident evidence belongs in `findings/`.
4. Hook integrity is part of cold-start preflight. Missing commands, duplicate registrations
   and non-executable paths are failures even when the main tool call happens to continue.

This refinement does not approve P0.3 contracts, start P0.4, or authorize package/fleet writes.
