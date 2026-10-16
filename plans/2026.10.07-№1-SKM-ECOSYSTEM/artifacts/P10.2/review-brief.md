You are an independent, read-only code reviewer. Do not modify anything; inspect, run commands and report.

Repository: current directory (git, branch ecosystem-split). Review ONLY the uncommitted change of item P10.2 ("orch on aicore"):
tracked changes under these paths (use `git diff -- <paths>`; also `git status --short` for the untracked fixtures dir):
  packages/orch/ (unit.json, scripts/{orch.py,test.sh,validate.sh}, lib/orch/{schema,contracts,catalog,cli}.py, tests/, fixtures/model-catalog/, README.md, docs/)
  scripts/test-aicore-locator.py, configs/ecosystem-units.json, docs/architecture/ownership.md, CHANGELOG.md
Other dirty files in the tree (.agents/, .claude/, bootstrap/, packages/planner/dev-skills/, plans/) belong to the owner: ignore them.
Set PYTHONDONTWRITEBYTECODE=1 for every command (the repository is read-only for you).

Intent of the change:
1. orch `unit.json` requires aicore; bash locator in scripts/test.sh and validate.sh (verbatim from packages/aicore/scripts/aicore-locator.sh); Python locator in scripts/orch.py (verbatim from packages/aicore/scripts/aicore_locator.py); copies registered in scripts/test-aicore-locator.py.
2. lib/orch/schema.py no longer holds a validator copy: it re-exports aicore.util.schema. Verdicts (path, code, message, level) on all exec/v1 fixtures were verified identical to the old copy before the switch (shadow test, then removed). Golden orch-validate-valid / orch-validate-invalid must not be re-captured.
3. contracts.canonical_digest uses aicore.util.digest (canonical_json_bytes + sha256_hex); exec/v1 digest format (bare lowercase sha256 hex, no tag) must NOT change. aicore canonical JSON rejects floats (old code accepted them): execution-input semantic check now reports DIGEST_MISMATCH instead of raising TypeError.
4. lib/orch/catalog.py: Catalog(model_catalog, launch_catalog=None), Catalog.load(path|None) over aicore.provider.models; ROUTING_ENV, find_routing, load_routing, _from_bridges, BRIDGES_DIR, UNAVAILABLE removed; CLI `prepare --model-catalog FILE` replaces `--routing`; error codes CATALOG_UNKNOWN and MODEL_CATALOG_UNAVAILABLE (was ROUTING_UNAVAILABLE).
5. tests/test_boundaries.py allows stdlib + orch + aicore; configs/ecosystem-units.json standalone.foundation_free gains orch.
Out of scope (do not report): bridges/task removal and bridge moves (next item), new exec/v1 fields, the [orch] config.

Look for: correctness bugs, behaviour changes of validate/prepare output vs. before (compare with `git stash`-free means, e.g. `git show HEAD:<file>`), digest-format regressions, locator/runner bugs (REPO_ROOT, PYTHONPATH, HOME isolation), broken standalone use (module copied next to aicore), tests that pass without testing anything, stale docs/messages (README, docs/*.md, CLI help), leftovers of the removed routing discovery anywhere under packages/orch outside bridges/ and docs/research/.
Useful commands: `bash packages/orch/scripts/test.sh`, `bash packages/orch/scripts/validate.sh`, `python3 scripts/test-aicore-locator.py`, `python3 scripts/ecosystem-units.py standalone orch`.

Report format: a list of findings, most severe first. For EACH finding give file:line, the defect in one sentence, and a reproduction (a failing command with its output, or a failing test). A finding without a reproduction is "plausible" at most; say so. If you find nothing, say "no findings". End with a one-line verdict: GREEN (no confirmed findings) or RED.
