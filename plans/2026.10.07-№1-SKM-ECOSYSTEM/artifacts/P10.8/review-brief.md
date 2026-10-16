# Read-only review: orch prepare with digests, decisions, proof, explain, resume guard, skill digests

You are an independent reviewer. The repository is /home/vostrikov/projects/packages/swissknifeman-next (working tree,
uncommitted changes of one item; `git diff` and `git status` show them). Do not edit files; the repository is read-only
for you. You may run tests and commands. Report findings only; the executor fixes them.

## What changed (scope)

Python 3.9 module `packages/orch` (imports only stdlib, orch, aicore) and the bridge `bridges/orch-skiller`.

- `packages/orch/lib/orch/bindings/__init__.py`: `prepare_common` now also records `digests`, `config`, `modules`,
  `decisions` (route per model stage, binding), `policy_decision`, `proof`, refusal `reason_code` and `chain`,
  `submission_id`, stage `delivery.skills`, and the plan `digest` last; `condense` is a model stage; staleness of
  capability records (`capabilities.stale` warn|refuse); `Unmet` carries a reason code.
- `packages/orch/lib/orch/{catalog,settings,port,cli}.py`, new `packages/orch/lib/orch/resume.py` (`verify_resume`),
  `orch.py prepare` (engine from `[orch]` config, `--binding` optional, `--submission-id`, `--skills`) and `orch.py explain`.
- `bridges/orch-skiller/resolve_role.py`: skill `digest` from `skiller describe <id> --json`, warning
  `SKILL_DIGEST_UNKNOWN`, `--all-roles` printing `{role_id: [{name, digest}]}`.
- Tests: `packages/orch/tests/{test_prepare_proof,test_cli_prepare}.py`, `bridges/orch-skiller/tests/test_resolve_role.py`.
- Docs: `packages/orch/docs/{engine-port,contracts,architecture}.md`, README files, root `CHANGELOG.md`.

## Contract (design the code must follow)

1. Hard risk: launch-plan must be deterministic (same inputs and `now` -> same bytes; stable order of `considered`).
2. orch core must not call skiller or any partner: the skills list arrives only as the `--skills` file.
3. A stale capability record must never be accepted silently: `warn` records a `CAPABILITY_STALE` warning, `refuse` refuses.
4. The engine is never replaced when a capability is missing: refusal, not another binding.
5. launch-plan is immutable; the configuration is read once per prepare (`config.digest`).
6. New arguments of `prepare_common` are optional; old calls and tests keep working.
7. `prepare` and `explain` write no files outside `--out` (explain writes none).
8. Product files are English, with no plan IDs, `PLAN<n>` tokens or home paths.

## How to check

Run from the repository root with a temporary HOME:
`export HOME=$(mktemp -d) SKM_HOME=$(mktemp -d) SKM_AICORE_EVENTS__DELIVERY=off`
- `bash packages/orch/scripts/test.sh` and `bash packages/orch/scripts/validate.sh`
- `bash scripts/test-bridges.sh`
- the engine CLI: `python3 packages/orch/scripts/orch.py prepare|explain ...` (see packages/orch/docs/engine-port.md).
`golden.py check` is red only for three files that belong to the owner (planner-development-philosophy SKILL.md x2,
bootstrap/publication-lock.json); ignore that.

## What to report

Only real defects in the changed code: wrong behaviour, a violated contract item above, a missed edge case, a test that
passes without testing anything, a doc statement that disagrees with the code. Skip style preferences.
For EVERY finding give: file:line, one-sentence defect, and a reproduction (a failing test you wrote under a temporary
directory outside the repository, or exact command output). A finding without a reproduction is at most "plausible".
Finish with a one-line verdict: `VERDICT: no findings` or `VERDICT: N findings` (list them first, most severe first).
