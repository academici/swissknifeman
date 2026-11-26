<!-- instruction:root.claude-code.native-surfaces -->
## root.claude-code.native-surfaces
Keep Claude Code compatibility surfaces in this extension: `.claude*`, `CLAUDE.md`, existing plugin commands, and managed Claude hooks remain provider-owned.
<!-- instruction:root.claude-code.context-budget -->
## root.claude-code.context-budget
Run skiller budget --first-turn; target 16K, warn at 23K, and require an Owner verdict above the gate. Also, run `skiller budget --first-turn --with-plugins` for marketplace plugins and escalate only when the sum crosses 23K.
<!-- instruction:root.claude-code.research-routing -->
## root.claude-code.research-routing
For Claude Code research, use the established `perplexity-web` route before `WebSearch`; this native routing does not replace the common external-claim verification rule.
