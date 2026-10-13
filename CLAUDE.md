<!-- swissknifeman:instructions:root:claude-code:common:begin -->
<!-- semantic:root.module-folders -->
<!-- instruction:root.module-folders -->
## root.module-folders
Every `packages/<id>/` folder is an independent module described by its `unit.json`. A module imports only its own `lib/<id>/` and the foundation it declares in `requires` (`aicore`), and reaches other modules only through bridges (`bridges/`) or events, never by import or path. Modules with `destination: own-repo` will move to their own repositories. Check boundaries with `python3 scripts/ecosystem-units.py check`.
<!-- swissknifeman:instructions:root:claude-code:common:end -->
<!-- swissknifeman:instructions:root:claude-code:extension:begin -->
<!-- semantic:root.claude-code.native-surfaces -->
<!-- semantic:root.claude-code.context-budget -->
<!-- semantic:root.claude-code.research-routing -->
<!-- instruction:root.claude-code.native-surfaces -->
## root.claude-code.native-surfaces
Keep Claude Code compatibility surfaces in this extension: `.claude*`, `CLAUDE.md`, existing plugin commands, and managed Claude hooks remain provider-owned.
<!-- instruction:root.claude-code.context-budget -->
## root.claude-code.context-budget
Run skiller budget --first-turn; target 16K, warn at 23K, and require an Owner verdict above the gate. Also, run `skiller budget --first-turn --with-plugins` for marketplace plugins and escalate only when the sum crosses 23K.
<!-- instruction:root.claude-code.research-routing -->
## root.claude-code.research-routing
For Claude Code research, use the established `perplexity-web` route before `WebSearch`; this native routing does not replace the common external-claim verification rule.
<!-- swissknifeman:instructions:root:claude-code:extension:end -->

<!-- dev-autonomy:begin (temporary: remove this block when the ecosystem-split plan is closed) -->
## Development mode: agent-owned decisions
This package is under active restructuring on a development branch. The plan and its direction are
already approved by the owner; the agent owns the implementation end to end.

- Make all architectural, design, fix and sequencing decisions yourself. Record them in the plan
  (`plan.py log`; an architectural choice becomes a plan decision) and keep going to the result.
- Scope of the run is exactly the plan item(s) named in the invocation. "To the end" means that item
  is fully done, verified and committed, not that the next items start. Never begin another item or
  phase on your own; after finishing, report and stop.
- Within the item, never ask for confirmation or "which option"; decide, log and finish it.
- Fix every defect you hit right away and properly, even when it exceeds a soft threshold or is not
  strictly in scope; log the deviation. Do not leave known red checks or defer obvious fixes.
- Quality over speed: root-cause fixes, verified by the item's checks and the affected suites.
- Ask the owner only for what only they can do (a command needing their terminal or credentials,
  changes to live machine state, pushes or publishing beyond the plan) or a truly irreversible
  product-level choice.
- Machine-specific rules (paths, pinned tooling) live in the untracked `CLAUDE.local.md` when present.
- Reports stay short: done, verified, next. No "decision for you" blocks.
<!-- dev-autonomy:end -->

<!-- maind:healthcheck hash=70e92d16482a (managed by maind — do not edit manually) -->
## mAInd — temporary project context and graph

Memory defaults to this project's private scope `project:swissknifeman`. Read `ns:*` or `global`
only for an explicit cross-project request and when the scope is authorized.

Store only short useful temporary context: 48-hour default TTL, 72-hour maximum,
800 characters, at most 8 live entries per scope. Use one replaceable `active-handoff`
for continuity, then forget it when work finishes. Keep plans, decisions, progress,
commit history and durable rules in repository artifacts. Empty memory is normal.

Use `maind health --cwd` for connection symptoms or setup changes; repair with
`maind health --cwd --fix`. A memory outage does not block ordinary repository work.
Project connections: `maind graph --project swissknifeman`.
<!-- /maind:healthcheck -->

<!-- swissknifeman:hub:start -->
<!-- swissknifeman hub: stub — skills and task-commands are connected natively; index and priority rules are not duplicated here. -->
<!-- swissknifeman:registry sha=00a04505cea0 skills=232 -->
<!-- Full index: `skiller status` or generate-hub.sh --target <dir> --full-index. -->
<!-- swissknifeman:hub:end -->
