## ⚠ PRIORITY №1 — connection with mAInd (shared memory + graph)

Before starting work, make sure that the project is connected to the hub **mAInd**. This is critical:
without communication changes this session **will not hit** to shared memory and the graph to history
development, irreparable gaps will appear, and further connections will not be drawn.

1. Check connection: `maind health --cwd`
2. If the status `partial` / `standalone` — fix: `maind health --cwd --fix`
   (will raise the memory daemon and add MCP-hub servers to this project).
3. Proceed with the task only when the status `connected`.

Memory **general** (demon mAInd), scope of this project - `{{SCOPE}}`; facts about the entire ecosystem - in
scope `global`. Project connections with others: `maind graph --project {{PROJECT}}`.
