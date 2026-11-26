# ADR 0078: Smoke of the installed form and a CI matrix generated from unit.json

## Status

Accepted

## Context

CI ran the modules from a checkout with hand-written job lists in `test.yml` and `validate.yml`; `brain` and the bridges
were not covered, and nothing exercised the installed form: CLIs from a bin directory and plugins copied into the Claude
Code plugin cache, where files outside the plugin folder are absent.

## Decision

- **Installed-form smoke.** `scripts/smoke-installed.sh` runs inside `scripts/dev-sandbox.sh` only: `install --profile full`
  into the sandbox `HOME`, `--help` of every CLI from an empty directory, `doctor --json` checked against its schema, and
  each marketplace plugin copied from `git archive HEAD` into
  `~/.claude/plugins/cache/swissknifeman/<name>/<version>/` with checks of `${CLAUDE_PLUGIN_ROOT}` paths, of paths that
  leave the plugin root, and of hook launch. The `skills[]` paths of `source: ./` entries are checked in the archive.
- **One source of steps.** `scripts/ci-matrix.py list|steps|run|--check` defines the steps of modules (`lint`, `test`,
  `validate`, `standalone`, `cli-smoke`, `contracts`, `schema-compat`, `secrets`) and bridges (`test`,
  `contracts`) from `unit.json`. Each step runs with a throwaway `HOME`; the tests of a module run once (`validate`
  skips them after a green `test` step, `SKM_VALIDATE_SKIP_TESTS`).
- **Workflow.** `.github/workflows/modules.yml` takes its matrix from `list --json`, tests on Python 3.9 and 3.13, runs the
  tools (`standalone.tools`) with `continue-on-error`, and has a `hub` job.
- **Replacement.** `test.yml` and `validate.yml` are removed after `--check` proves that each of their commands is covered.

## Alternatives considered

- Reusable organisation workflows: deferred until a module moves to its own repository.
- A literal matrix in the workflow: rejected, `--check` fails on it.

## Consequences

- A new module joins CI by having a `unit.json`.
- The same steps run locally with `python3 scripts/ci-matrix.py run`.
- The legacy schemas of skiller (draft-07) get a weaker check than the closed profile of aicore.

## Supersedes

None.
