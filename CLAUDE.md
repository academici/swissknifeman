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

<!-- maind:healthcheck hash=72f8dd8bbc55 (managed by maind — не редактировать вручную) -->
## ⚠ ПРИОРИТЕТ №1 — связь с mAInd (общая память + граф)

Перед началом работы убедись, что проект подключён к хабу **mAInd**. Это критично:
без связи изменения этой сессии **не попадут** в общую память и граф — в истории
разработки появятся невосстановимые пробелы, и дальнейшие связи будет не вывести.

1. Проверь связь: `maind health --cwd`
2. Если статус `partial` / `standalone` — почини: `maind health --cwd --fix`
   (поднимет демон памяти и допишет MCP-серверы хаба в этот проект).
3. Приступай к задаче только при статусе `connected`.

Память **общая** (демон mAInd), scope этого проекта — `project:swissknifeman`; факты всей экосистемы — в
scope `global`. Связи проекта с остальными: `maind graph --project swissknifeman`.
<!-- /maind:healthcheck -->

<!-- swissknifeman:hub:start -->
<!-- swissknifeman hub: stub — скиллы и task-команды подключаются нативно; индекс и правила приоритета здесь не дублируются. -->
<!-- swissknifeman:registry sha=5b8274432dfe skills=232 -->
<!-- Полный индекс: `skiller status` или generate-hub.sh --target <dir> --full-index. -->
<!-- swissknifeman:hub:end -->
