# P6 design baseline — 2026-09-09

## Repository observations

RAG:— (worktree-local CLI and source inspection on 2026-09-09).

- `packages/skiller/bin/skiller budget --target . --provider codex --json` reports 37 listed
  skills and 8,578 raw listing characters against an 8,000-character budget.
- `packages/skiller/bin/skiller budget --first-turn --with-plugins --target . --json` reports
  project total 7,133, plugin listing 1,727 and session total 8,860 characters; the Brain plugin is
  also reported broken. These are listing estimates, not observed provider input tokens.
- `codex plugin list --json` reports locally installed `core@0.13.1` and `task@0.13.3` disabled,
  while the authoring session exposes their skills. P6.1 must reproduce and classify this mismatch
  in fresh processes before a mutation is admissible.
- `codex exec --help` exposes JSONL output, ephemeral execution, ignored user config/rules and
  output-schema controls. None is treated as proof of a clean room; the exact argv and inherited
  source inventory remain evidence.
- `packages/skiller/lib/skiller/quality/eval.py` already owns deterministic assertions/statistics
  for skill evaluation, but its ordinary runner is Claude-specific. It has Codex presence probes,
  not a native matched context evaluator.
- Harness instruction ownership is split between the common catalog/fragments and
  `packages/harness/lib/harness/instructions.py`; bootstrap publication is owned by
  `packages/skiller/configs/repository-bootstrap-skills.json` plus Skiller registry/publication
  code. Generated AGENTS and `.agents/skills/**` are outputs, not edit sites.

## Design consequences

1. Freeze actual sources and cases before baseline calls.
2. Separate raw provider events from deterministic normalization/reduction.
3. Permit one candidate maximum and preserve current behavior on invalid, tied or incomplete data.
4. Express any accepted Codex difference as additive provider delivery metadata/filtering over the
   shared canon, then regenerate through owners.
5. Treat listing characters, provider input usage, wall time, restarts and behavioral invariants as
   separate axes; no one proxy is a verdict.

## Open defects and unknowns

- `[POSSIBLE-DEFECT]` Installed-plugin status and live skill exposure disagree. Owner: P6.1.
- `[POSSIBLE-DEFECT]` First-turn budget reports a broken Brain plugin. It is captured but outside
  P6 mutation scope unless it prevents valid Codex observations.
- Exact effective provider input for each source cannot be inferred statically. Owner: native P6
  evaluation; unknown observations yield `insufficient`.

External behavior used by this design was verified separately in
`research/07-p6-codex-economy.md` against official OpenAI documentation on 2026-09-09.
