# ADR 0013: Orchestration scenarios and execution through a prepared brief

## Status

Accepted

## Context

An executor needs the whole task context, but compression loses constraints (measured retention of constraints is
far lower than that of facts), and the context budget must not simply disappear in orchestration.

## Decision

A scenario is a run-policy profile in the `orch` configuration: stages, role and model class per stage, required and
optional parts, review, rounds and stage budgets. Stages: (1) brief preparation: code copies the mandatory parts
verbatim (goal, scope, acceptance with ids, constraints, decisions, interfaces, open questions) and a cheap model
compresses only optional material with links to the originals; the brief is an artifact of the item, addressed by
digest; (2) the executor works from one file and opens originals by link when unsure; (3) checks are executed
commands with evidence; (4) an optional reviewer from another provider, rework by a strong model, at most two
review rounds and one correction; (5) a registrar prepares the closing record, and code decides `done` from
evidence, with escalation on ambiguity. The default scenario comes from the item class in the planner
configuration and can be overridden per item; small items default to solo work in the current session.

## Alternatives considered

- Give the executor only a cheap-model summary: rejected, constraints are lost.

## Consequences

- The context budget becomes stage limits in run-policy; the planner context-pack budget still serves single-session work.
- The engine that runs scenarios is outside this change; contracts, scenario configuration, the brief artifact and
  scenario selection are in scope.

## Supersedes

None.
