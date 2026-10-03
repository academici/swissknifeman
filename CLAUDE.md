<!-- swissknifeman:instructions:root:claude-code:common:begin -->

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

<!-- maind:healthcheck hash=9046a1eafbee (managed by maind — do not edit manually) -->
## ⚠ PRIORITY №1 — connection with mAInd (shared memory + graph)

Before starting work, make sure that the project is connected to the hub **mAInd**. This is critical:
without communication changes this session **will not hit** to shared memory and the graph to history
development, irreparable gaps will appear, and further connections will not be drawn.

1. Check connection: `maind health --cwd`
2. If the status `partial` / `standalone` — fix: `maind health --cwd --fix`
   (will raise the memory daemon and add MCP-hub servers to this project).
3. Proceed with the task only when the status `connected`.

Memory **general** (demon mAInd), scope of this project - `project:swissknifeman`; facts about the entire ecosystem - in
scope `global`. Project connections with others: `maind graph --project swissknifeman`.
<!-- /maind:healthcheck -->

<!-- swissknifeman:hub:start -->
<!-- swissknifeman hub: stub — skills and task-commands are connected natively; index and priority rules are not duplicated here. -->
<!-- swissknifeman:registry sha=00a04505cea0 skills=232 -->
<!-- Full index: `skiller status` or generate-hub.sh --target <dir> --full-index. -->
<!-- swissknifeman:hub:end -->
