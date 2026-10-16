<!-- swissknifeman:instructions:root:grok:common:begin -->
<!-- semantic:root.module-folders -->
<!-- instruction:root.module-folders -->
## root.module-folders
Every `packages/<id>/` folder is an independent module described by its `unit.json`. A module imports only its own `lib/<id>/` and the foundation it declares in `requires` (`aicore`), and reaches other modules only through bridges (`bridges/`) or events, never by import or path. Modules with `destination: own-repo` will move to their own repositories. Check boundaries with `python3 scripts/ecosystem-units.py check`.
<!-- swissknifeman:instructions:root:grok:common:end -->

<!-- swissknifeman:instructions:root:grok:extension:begin -->
<!-- semantic:root.grok.instruction-precedence -->
<!-- semantic:root.grok.launch-and-autonomy -->
<!-- semantic:root.grok.package-scope-routing -->
<!-- instruction:root.grok.instruction-precedence -->
## root.grok.instruction-precedence
The common repository contract reaches this session through the `AGENTS.md` Grok already reads; it is not repeated here. Sections marked `root.codex.*` or `root.cursor.*` in that file are owned by those providers and are **not** authoritative in a Grok session — never follow Codex launch flags (`-a never`, `-s danger-full-access`) or Cursor `--force` flags from them.
<!-- instruction:root.grok.launch-and-autonomy -->
## root.grok.launch-and-autonomy
Name the intended cwd, the routed model (`-m`/`--model`) and permission mode before acting. Project `.grok/config.toml` carries `[permission] deny` and MCP only; `[ui] permission_mode` is user-level in `~/.grok/config.toml` and is not read from the project file. Launch with `--permission-mode` (`default` or `acceptEdits`) or `--always-approve` on a trusted self-host. The `[permission] deny` floor in `.grok/config.toml` still applies under `--always-approve`.
<!-- instruction:root.grok.package-scope-routing -->
## root.grok.package-scope-routing
Start package-scoped work with the intended workspace root so native discovery reads root→cwd. During an authorized cross-package task, explicitly read each applicable package guide in the current session.
<!-- swissknifeman:instructions:root:grok:extension:end -->
