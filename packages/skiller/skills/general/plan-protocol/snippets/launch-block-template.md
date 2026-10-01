# Launch-block template - fixed form of “what to launch next”

Each output of the real next step is handoff.Next and report finals
plan-run/plan-close/plan-audit - must have this form (SKILL section 6):
semantic carrier + requirements table WITHOUT command + separate copyable command block
active provider adapter.

`````markdown
**Next:** <kind>: task:<plan-command> <PLAN-ID> <arguments>

| Parameter | Meaning |
|:--|:--|
| Batch | <Routing Batch ID / solo; n/a only for design/audit/close/archive> |
| Model class | <economy / implementation / frontier> |
| Effort | <low / medium / high / xhigh> |
| Capabilities | <minimum set of semantic capability IDs; `—` if there are no additional ones> |
| Context | <enum: continue-root · isolated-child-return · cold-start-root (+ one reason)> |
| Essence | <1 line: what startup does> |

**Provider-native command:**

```text
<provider-rendered invocation>
```
`````

**Command is always out of table.** Active provider adapter defines the form: Claude Code
prints a native slash command in a `text` block, Codex - full run of `codex ...` in a `bash` block,
Cursor - `agent --workspace ... --model ... --force ...` in the `bash` block (see provider-model-roles).
Don't print multiple native forms. One physical line is preferred; if the shell command is intentional
is broken, each continued line except the last ends with `\`. Visual transfer
Markdown is not considered a continuation of a shell command. Executable Next without fenced command block
incomplete; the final cannot end with "done" if the next run exists.
GREEN item and eligible final-item phase are closed before Next is evaluated: launch cannot be printed for
`plan-close` the current result or repeat `plan-run` the current item.

A separate block can carry a provider invocation OR a bare prompt:

- **owner-run step** (`manual:` Next) — no single command expresses it: the fenced block carries
  a BARE item prompt (or a `/model`+`/effort`+`/task:plan-run` sequence);
- **scope-payload** (finds/reopen, see below) - code-block carries invocation PLUS
  four lines `MODE:`/`INPUT:`/`SCORE:`/`DO NOT TOUCH:`, not in one row of the table
  fits;
- **form `WAITING:`** (below) - code-block carries the guard line `# NOT before: ...`.

Legacy row of the `Team` table remains readable for old plans, but new handoffs
is not output. The canonical command carrier is fenced block only.

`````markdown
<!-- example: an ordinary run item whose next step is fully expressed by one command -->
**Next:** run-items: task:plan-run <PLAN-ID> Pn.k

| Parameter | Meaning |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | continue-root |
| Essence | close Pn.k |

**Provider-native command:**

```text
/task:plan-run <PLAN-ID> Pn.k
```
`````

Rules:

- **Self-sufficiency (cold-start).** The team is required to work from a cold session:
  plan-ID + input dock paths (cold-start reads) + built-in gate assertion,
  if the execution is gated. Links like “this session” are only as an addition.
- **Scope-payload - launch-block carrying FINDS** (§8, D-canon 2026-07-17): verdict
  `plan-audit` `RED`/`ATTENTION` and the C3/D6 fix clause cannot be naked. Rule
  entirely in SKILL section 8 (the only SSOT), here the form is four lines under the command
  in the same code-block, the order is fixed:

  `````
  <provider-rendered invocation>

  MODE: <reopen by §3 (4 steps) | detailing | remediation>
  INPUT: <file → block with finds; cold-start read>
  SCORE: <numbered list: what to do>
  DO NOT TOUCH: <anti-scope: what to leave as is>
  `````

  `plan-audit` puts this launch-block with the `###What to launch` subsection at the end of its block
  `## Audit Pn` - the chat is not checked by the machine, the disk is checked. `plan-lint` gates presence
  of all four lines (date plans from 07.2026.16 - ERROR, older ones - WARNING). `GREEN` finds
  does not carry - it does not require payload.
- **Model class/Effort** - from the Routing plan (SSOT matrix - SKILL section 9); deviation
  from the matrix is located there, not in the launch-block.
- **Batch** - from the Routing plan. For execution Next, the group ID or `solo` is specified, and the command
  addresses the entire adjacent-suffix of the group that has not yet been closed. The field does not disappear with a new handoff;
  `n/a` is only valid for the design/audit/close/archive step without item execution.
- **Capabilities** are checked before invocation/work/write. The orchestra is obliged to list
  `command.subagents` and `command.workflow-carrier`; missing/unknown/unsupported blocks launch.
- **Context** - private enum of THREE values ​​SKILL §6; is selected by the boundary, not the command:
  - `continue-root` - normal sequential work and local repair;
  - `isolated-child-return` - one limited reviewer/worker returns evidence to root;
  - `cold-start-root` - with only one reason: `context-budget`, `capability-missing`,
    `owner-pause-no-resume`, `whole-plan-independent-audit` or `design-root-terminal`.
    `design-root-terminal` saved for old handoffs. After design use
    `scope-complete` / `continue-root` if there is no real new session boundary;
    the recommendation itself does not allow execution of successor.
    Terminal `task:plan-audit` does not select Context by command name; use its persisted
    `plan_continuity` decision.
- **owner-run step** → “MANUAL START” form — the rule lives in SKILL section 8 (single SSOT).
  Reminder: `Model class` = the Routing class, the fenced block is REQUIRED and carries a
  **BARE item prompt** (or a `/model`+`/effort`+`/task:plan-run` sequence)
  instead of an invocation, `Context` = `continue-root` if there is no actual hard boundary.
- **Form “EXPECTATION: `<condition>` → `<target form>`” (§8, D8)** - step is real, but impossible
  now (time-gate/data accumulation/cross-plane-gate is not terminal; NOT defect `🔴`, NOT terminal
  “plan closed”). The entire rule is in SKILL section 8; here is a reminder: the condition is STRUCTURAL
  (date/gate), first line of code-block - **guard `# NOT before: <condition>`**, `Model class`/`Effort`/
  `Context` - **target step**. Do not write a prosaic disclaimer in the ad (`plan-lint` marks C2).
- `plan-lint` checks semantic `Next`, table with `| Model class |` and fenced block below;
  legacy string `| The |` command is accepted only for backward compatibility of old plans.
