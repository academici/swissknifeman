# Workflow template builder

4 canonical parameterizable template scripts for multi-agent orchestration. Constructor -
is a **portable template library, not a code generator** (RAG:✅ P5.1 §4: DSL builders
were not consolidated; The workflow script is already a DSL). Usage: copy template to
`plans/<ID>/workflows/` plan, fill slots (`// SLOT:`), run via `scriptPath`.
Prototypes - working scripts ECOSYSTEM P5 (`wf-p5-research.js` corresponds to template 1,
`wf-p5-author.js` - template 2).

## When which template

| Template | Orchestration | Slots |
|:--|:--|:--|
| `wf-research-fanout.js` | N topics × research → adversarial verify (pipeline, no barrier) | `TOPICS[]`, diagrams, model/effort |
| `wf-author-by-spec.js` | spec → N file tasks × author → self-check (pipeline) | `FILES[]` (file+TK+validation), pipeline-commands |
| `wf-audit-adversarial.js` | M finders → dedup → adversarial verify → verdicts | `DIMENSIONS[]`, severity-enum, constitution (artifact-review) |
| `wf-dev-slice.js` | slice → impl → tests-to-green → risk-adaptive review | `SLICES[]`, gates |

Combined: plan pipeline = research-fanout → (design in main loop) → author-by-spec
or dev-slice → audit-adversarial. We do not intentionally cover the design stage with a template - it
lives in the main loop of an expensive model (model routing: expensive for design, cheap for mechanics).

## Rules for filling slots

1. **Slots are only constants in the script header.** Everything is parameterizable (`TOPICS`, `FILES`,
   `DIMENSIONS`, `SLICES`, paths, model/effort, schemes) are declared constant's before orchestration.
   `// SLOT:`-markers **recommended** (readability), their absence in itself is not a defect.
   Do not touch the orchestration logic when filling - if the template does not fit, it is a different template
   or main loop, not a logic fork (the logic fork is the only real defect here,
   regardless of markers).
2. **Embedded-config instead of args-string.** Named-workflow passes `args` as a string - trap:
   the structural config cannot be pulled through it. The config is built into the script and launched via
   `scriptPath`. Paths are absolute only (the subagent's cwd is reset between calls).
3. **Structured-summary according to the scheme - required for control-flow agents.** Agent whose result
   rules the branch/loop/verify stage, returns data according to the JSON schema, not prose
   (RAG:✅ P5.1 §4 artifact-centric handoff, CONFIRMED); the final line of the prompt -
   “Final text = schema data, not a message to the person”; circuit core
   (`load_bearing`/`failure_scenario`/`tests_green`) do not trim. Action/mechanical agents
   (open/state/commit/fix/gate) CAN return prose - legitimate economy (D6), not defect;
   the prose of the control-flow agent remains a defect.
4. **Judge-panel - slot only for high-stakes stages.** 3+ independent verdicts + consensus
   (`JUDGE_PANEL` in template 3) enable only for fiscal/payments/tenant-isolation/core
   ecosystems - single-agent matches 60%+ tasks, default panel = token burning
   (RAG:✅ P5.1 §4: judge panel selective, CONFIRMED).
5. **Max-iteration is required for any loop-until.** Each loop “repeat until green/
   to clean" has a numerical ceiling (`MAX_GREEN_ITERATIONS` in pattern 4); exhaustion =
   pipeline stop + escalation in the main loop, not another iteration. Infinite loop -
   is an agent that fits tests to code.
6. **Execution/review separation.** Review-capable workflows require an explicit reviewer slot
   filled from the owner's `--reviewer provider/model` selection; `wf-dev-slice` refuses an
   unfilled REVIEWER before any author call. Executor calls own code/tests, reviewer calls own
   read-only verdicts, and the orchestrator owns the handoff. A finding returns one owning
   correction and stops the review stream; never recursively fix/re-audit in the reviewer.
   Systemic findings retain `(risk_class, area)` across files/drivers and check the shared model.
   Cross-provider item review uses Task's bounded review-packet transport and receipts; workflow
   resumes must retain that history, never reset caps with a global cache-bust marker.
   `plan-run --reviewer` can be the owning orchestrator for one-command automatic operation:
   separate reviewer sessions do not require another manual owner command.

General template invariants: fan-out - via `pipeline()` without barrier (verify/self-check
starts immediately after its element, does not wait for the entire wave); audit/review agents - strictly
read-only; authors commit only the files of their task (git status before add); dropped out
elements (`null` from `agent()`) do not fail the run - they are collected in `dropped`/`failed` for
reassembly in main loop; top-level `return report` at the end of the script is an authorized idiom
runtime (the body of the workflow script is executed as an async wrapper of the Workflow tool), not a defect.

Combat hardening (canon, recorded in 4 templates - findings P1-recon §1.3):

- **`safeAgent(prompt, opts)`** — try/catch wrapper over **bare** `await agent()` (outside
  `parallel()`/`pipeline()`, where throw is already caught by runtime and returns `null` - the wrapper there
  is redundant, do not add): without it, the agent's roll drops the entire run instead of the controlled one
  `null`, which then catches the existing `if (!res)`.
- **REPO/path-invariant.** Any absolute path SLOT constant (`REPO`, `SPEC`,
  `TARGET.paths`, ...) - mandatory absolute path (subagent cwd is reset between
  calls); opt. runtime-assert `X.startsWith('/')` catches relative path live
  run, does not work on an empty template (the placeholder `/abs/path/to/…` itself is absolute).
- **guarded-optional-args.** Optional slot field - typeof/length-guard with explicit default
  (e.g. `CONVEYOR.length ? … : null`, `typeof s.risk === 'string' ? s.risk : 'medium'`), not
  bare appeal without verification; pattern from `wf-agentools-drive` L195 (cross-ref, do not vendor).
- **Per-item cache-bust.** `agent()` caches by `(prompt, opts)` - to `resumeFromRunId`
  ONE conveyor/slice element without global invalidator, add opt. field `asOf`
  (date/tag) into the element object and mix it into the prompt/`label` - only it is invalidated by the cache,
  not the entire wave (pattern - roadmap note dterema-p4, canonized here).

## Background run status

Background workflow run detail status - `swissknifeman wf status`, DO NOT advise
`/workflows` (there is no such command in the environment). The command parses the transcript directory
runs deterministically (journal.jsonl + script meta) and prints a fixed report
(`--json` - machine, `--watch` - reprint); retransmit its output, don't parse it again.

Methodology and examples: `docs/task/workflows.md`.
