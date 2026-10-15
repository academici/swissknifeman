<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/planner/commands/make-workflow.md
Canonical SHA-256: sha256:9086b1ae53826a71b9e422a7fcf71025dc5c932cb7364a5f48ac84ee75dd90dd
Adapter: planner.codex-command/1.0.18
-->
Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:make-workflow` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
Activate only for an explicit request to create a workflow script. Ordinary development and research do
not need this path. User input: `$ARGUMENTS`. The route is pinned to implementation/high.

Read optional reviewer selection from `--reviewer provider/model`; its absence does not add
external review or prevent generation. A requested reviewer is a fresh read-only session
under that selected route, not the workflow author's own evaluation.
Accept optional context/effort suffixes and trailing `/` through `planner.review_selection.reviewer`:
`provider/model/500k/`, `provider/model/high/`, `provider/model/500k/high/` (`hight` = high).
Fill model and effort slots from the parsed values, not the entire slash expression. Preserve
context as a provider-proven capacity requirement; never reinterpret it as a spend budget.

Read `references/reviewer-selection.md` for requested review and exact native route selection.
Copy and fill a canonical template; do not write orchestration from scratch.

## 1. Load the authoring contract

Use a workflow-craft skill, when installed, as the source of truth for template matching, the design/dev stage matrix,
and slot rules. Do not duplicate its rules in the generated workflow.

## 2. Select a template

Match the request to one or a pipeline of the four templates in `packages/planner/workflows/README.md`:

- `wf-research-fanout.js`
- `wf-author-by-spec.js`
- `wf-audit-adversarial.js`
- `wf-dev-slice.js`

Classify the request as `design-only` or `dev` using the `workflow-craft` matrix. If neither one template
nor a pipeline fits, return to the main loop; do not fork template logic for the task.

## 3. Resolve slots

Fill facts available from the request and repository. Use a spec-interview skill, when installed, only for a missing
product decision or authority boundary:

- Ask one question at a time and branch on the answer.
- Read paths, contracts, and slice risks from the repository instead of asking the user.
- Recommend one answer with a short rationale.

Ask only template-specific questions such as slice gates, risk, frozen contracts, high-stakes judge-panel
eligibility, absolute paths, and slot contents. Do not ask whether required review or verification stages
should exist; the stage matrix decides that.

## 4. Generate from the template

Copy the selected template to `plans/<ID>/workflows/` and fill its slots:

- Keep parameters as constants in the header; `// SLOT:` markers are recommended.
- Embed structured configuration. Do not pass it through the named-workflow `args` string; launch by
  `scriptPath`.
- Use absolute paths because subagent working directories do not persist across calls.
- Require schema-backed structured summaries from control-flow agents.
- Give every loop-until a numeric iteration limit and escalate on exhaustion.
- Use a judge panel only for high-stakes fiscal, payment, tenant-isolation, or core-system stages.

## 5. Run a read-only static review

Check the generated script against exactly the invariants below. With `--reviewer`, have one
fresh read-only reviewer inspect, not execute, it against the invariants in
`packages/planner/workflows/README.md` and the `workflow-craft` stage matrix. It must check:

- Orchestration logic still matches a canonical template; task-specific logic was not forked.
- Configuration is embedded, paths are absolute, and control-flow agents retain the required schema core.
- Fan-out uses `pipeline()` without a whole-wave barrier.
- Review and audit agents are read-only; authors stage only their own files.
- Dropped `agent()` results are collected instead of aborting the run.
- Top-level `return report` is accepted as the workflow runtime idiom.
- A `dev` workflow contains slice, implementation, tests-to-green, explicitly requested review, inter-slice gates,
  and commit stages.
- A `design-only` workflow contains retrieval, design in the main loop, self-check/DoR gate,
  optional requested read-only audit and owning corrections within `policy.corrections_max`; a bounded re-audit needs changed evidence. It contains no
  implementation, test, or SemVer stage.

The verdict is `GREEN` or `RED` with concrete invariant, location, and failure details. `RED` blocks delivery:
return at most `policy.corrections_max` owning corrections and allow at most `policy.review_rounds_max` completed
review passes (`plan.py config show`; defaults 1 and 2). A repeated systemic
class/area changes the shared model; exhaustion needs an explicit bounded decision in the main loop.
Only `GREEN` releases `plans/<ID>/workflows/wf-<code-name>-<purpose>.js`.

Return the script path, workflow type, and self-check or requested reviewer verdict. For `RED`, return violations and repair status
without presenting the script as ready.
