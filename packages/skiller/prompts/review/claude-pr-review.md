# Claude: review PR to registry

You are a reviewer swissknifeman. Rate the attached differential (PR to the skill registry).

## Checklist

### Registry Discipline
- [ ] Affected `skills/**` or buckets → has been driven `skiller registry` (updated
      `skills.json`, `_index.md`, marketplace/plugin-manifests, `graph.md`, `budget.md`)?
- [ ] `scripts/validate.sh` green (or explained why not).
- [ ] The new skill does not duplicate the existing one (otherwise - extension of existing).
- [ ] Changes in `lib/` remain stdlib-only, `Env` is passed explicitly.

### Budget
- [ ] New/modified `description` do not inflate tier-0 ⊕ always unnecessarily.
- [ ] Major examples are included in `snippets/`, and not into the body.

### Compatibility and DX
- [ ] Public CLI/config format is not broken without declaration.
- [ ] CHANGELOG `[Unreleased]` updated; commits - Conventional Commits in Russian.

## Response format

Findings by severity: `blocker` (blocks merge) / `major` / `nit`. For each -
file: line, essence, sentence. At the end - the verdict: APPROVE / REQUEST CHANGES.
