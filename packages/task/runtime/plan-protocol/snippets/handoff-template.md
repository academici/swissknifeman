# Template handoff.md - rolling pointer plans/<PLAN-ID>/handoff.md

Overwritten ENTIRELY each time an item/phase is closed (history in git).
The keys of the Workarounds/Deferred/Open questions block match the run-report
`devloop{workarounds,deferred,open_questions}` - reconciliation with telemetry.

**Title** - two forms (other = ERROR linter; canon - SKILL §8):

| Header form | When |
|:--|:--|
| `# HANDOFF - <YYYY-MM-DD> - after Pn.m` | closed item |
| `# HANDOFF - <YYYY-MM-DD> - after Pn` | closed/audited/re-designed PHASE - step without “last closed item” as destination |

**The `Context`** field for layout v2 is `continue-root` · `isolated-child-return` ·
`cold-start-root`. The latter requires a reason from a private enum:
`context-budget` · `capability-missing` · `owner-pause-no-resume` ·
`whole-plan-independent-audit` · `design-root-terminal`.
`design-root-terminal` is saved only for old handoffs. The completed design uses
`scope-complete` / `continue-root`; the recommendation does not permit implementation. After terminal `task:plan-audit` Context
specifies the saved solution `plan_continuity`, not the command name.

Runnable Next for the actual successor must carry launch-block (the full form and rules of cold-start are
`snippets/launch-block-template.md`, SKILL section 8): launch parameters table
+ provider-rendered invocation with one code-block. `plan-lint` checks for their presence.
For execution Next, the table always carries the `Batch` from Routing, and the command carries the rest
rest of the group. For `recommended:` this is a recommendation that allows a ready subset; historical
and `required:` groups retain the adjacent suffix. A single run is marked `Batch: solo`. For others, Next is `Batch: n/a`.

**Forms `Next`** - private enum (other form = ERROR linter; canon - SKILL §8):

| Form Next | When |
|:--|:--|
| `run-items: task:plan-run <ID> Pn.a[-Pn.b]` | next item(s) detailed, Exec = run (§9); legacy spelling `exec-items: task:plan-exec` stays readable |
| `audit-design: task:plan-audit <ID> design` | pre-exec design audit |
| `design-phase: task:plan-design <ID> Pn` | next phase - skeleton |
| `design-item: task:plan-design <ID> Pn.m` | item is escalated (🔴) or requires re-design |
| `design-finish: task:plan-design <ID> finish` | reconciliation of fully detailed design |
| `design-roadmap: task:plan-design <ID> roadmap` | update execution map without editing technical specifications |
| `audit-phase: task:plan-audit <ID> Pn` | there is a fresh owner-bound `audit-admission/v2` on residual-risk question/candidate/run |
| `close: task:plan-close <ID> Pn[.m]` | only explicitly requested standalone reconciliation; not handoff current result |
| `archive: task:plan-close archive <ID>` | the plan is entirely terminal |
| `terminal: plan closed` | all items are terminal, the next step is outside the protocol |
| `manual: <model-class/effort>` | owner-run step with no command — launch-block carries the route and a BARE item prompt |
| `waiting: <condition> → <target semantic form>` | the step is real, but not executable now - launch-block carries the target carrier with the guard line `# NOT before:` |

Historical `/task:…` declarations remain compatibility inputs. New plans write the semantic
form above; provider renderers emit Claude `/task:…` or Codex `$ task:…` without changing payload.
`plan-run` itself closes the GREEN item and eligible final-item phase; handoff is built after
closure and cannot iterate over the current item or run `plan-close` on it.

Owner-run step outside the command surface:

`````markdown
**Next:** manual: frontier/high — Pn.m (owner-run; no Task command carries it)

| Parameter | Meaning |
|:--|:--|
| Batch | <Batch ID / solo> |
| Model class | frontier |
| Effort | high — <why high+ MANDATORY according to §9> |
| Capabilities | — |
| Context | continue-root |
| Essence | <1 line> |

````
<Item's NAKED PROMPT is not a slash command: what to read, what to do, how to close>
````
`````

“WAITING” form (the step is real, but not executable now - time-gate/data accumulation/gate not
terminal; the condition is structural, launch-block carries the target command with a guard line):

`````markdown
**Next:** waiting: ≥2026-07-16 (baseline usage-trend ≥1–2 weeks) → run-items: task:plan-run <ID> P8.5

| Parameter | Meaning |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | continue-root |
| Essence | <1 line: what the target step will do to remove the gate> |

````
# NOT earlier: baseline usage-trend ≥1–2 weeks, ≥2026-07-16
<provider-rendered invocation for `run-items: task:plan-run <ID> P8.5`>
````
`````

`````markdown
# HANDOFF — <YYYY-MM-DD> — after Pn.m

**Next:** run-items: task:plan-run <PLAN-ID> Pn.k

| Parameter | Meaning |
|:--|:--|
| Model class | <economy / implementation / frontier> |
| Effort | <low / medium / high / xhigh> |
| Capabilities | <semantic capability IDs; `—` if there are no additional ones> |
| Context | <enum §6: continue-root · isolated-child-return · cold-start-root> |
| Essence | <1 line: what the next run does> |

````
<provider-rendered invocation for `task:plan-run <PLAN-ID> Pn.k`; cold-start payload do not change>
````

**Done:** <what is closed since last handoff: items, phases, decisions>
**Remaining:** <what remains until the end of the phase/plan>
**Sources of truth:** plans/<PLAN-ID>/plan.md · plans/<PLAN-ID>/phases/Pn.md · <key code files>
**Open risks:** <open risks; "—" if not>
**Workarounds/Deferred/Open questions:**
- workarounds: <workarounds taken during execution; "—" if not>
- deferred: <consciously deferred; "—" if not>
- open_questions: <questions requiring human decision/plan-design; "—" if not>
`````
