# ADR 0008: Only shared skills stay in skiller; module skills move to their module

## Status

Accepted

## Context

`skiller` carries skills that describe other modules (harness, maind, analyst, brain).

## Decision

`skiller` keeps only general skills. A skill about a specific module lives in that module: `system/agent-packs` and
`system/agents` to `harness`; `system/brain-locator` to `brain`; `system/local-topology`,
`system/swissknifeman-locator`, `system/cross-project-coordinator` and `system/shared-memory` to `maind`;
`system/session-observer` to `analyst`. Five `general/*` skills are checked for a module binding when `skiller`
is reduced to shared skills. The full table is in the ecosystem document.

## Alternatives considered

- Keep all skills in `skiller`: rejected, it ties every module to one library.

## Consequences

- Each module ships its own plugin content; bootstrap skills are unchanged.
- Skill content is not changed by the move.

## Supersedes

None.
