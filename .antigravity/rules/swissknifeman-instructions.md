<!-- swissknifeman:instructions:root:antigravity:common:begin -->
<!-- semantic:root.module-folders -->
<!-- semantic:root.product-philosophy -->
<!-- instruction:root.module-folders -->
## root.module-folders
Every `packages/<id>/` folder is an independent module described by its `unit.json`. A module imports only its own `lib/<id>/` and the foundation it declares in `requires` (`aicore`), and reaches other modules only through bridges (`bridges/`) or events, never by import or path. Modules with `destination: own-repo` will move to their own repositories. Check boundaries with `python3 scripts/ecosystem-units.py check`.
<!-- instruction:root.product-philosophy -->
## root.product-philosophy
Swiss Knife Man is a local, provider-neutral control layer: typed JSON plans (planner), a deterministic conductor that runs coding-agent CLIs as bounded roles (orch), and a reproducible developer environment (skiller, harness, aicore, workspace, maind). Follow `docs/philosophy.md`: code owns the lifecycle and models propose; every boundary JSON has a schema and is validated; fail closed on authority and degrade loudly; evidence over claims, repair never changes meaning; proportional assurance; bounded autonomy; neutral core with personal content in overlays.
<!-- swissknifeman:instructions:root:antigravity:common:end -->

<!-- swissknifeman:instructions:root:antigravity:extension:begin -->
<!-- semantic:root.antigravity.instruction-precedence -->
<!-- semantic:root.antigravity.launch-and-autonomy -->
<!-- semantic:root.antigravity.package-scope-routing -->
<!-- instruction:root.antigravity.instruction-precedence -->
## root.antigravity.instruction-precedence
The common repository contract reaches this session through the `AGENTS.md` Antigravity already reads; it is not repeated here. Sections marked `root.codex.*`, `root.cursor.*` or `root.grok.*` in that file are owned by those providers and are **not** authoritative in an Antigravity session — never follow Codex launch flags (`-a never`, `-s danger-full-access`) or Cursor `--force` flags from them.
<!-- instruction:root.antigravity.launch-and-autonomy -->
## root.antigravity.launch-and-autonomy
Name the intended cwd, the routed model (`--model`) and mode before acting. Use the installed `agy --help`: `--mode plan|accept-edits|auto`, `--effort` and session-only `--settings` are the CLI surfaces. `--dangerously-skip-permissions` requires an explicitly trusted invocation. Harness renders `.antigravity/config.toml` as a policy projection; the file alone does not prove native CLI enforcement. Verify actual enforcement separately; never infer a sandbox or effective deny floor from rendered TOML. Do not pass Grok's `--permission-mode` or `--always-approve` flags to AGY.
<!-- instruction:root.antigravity.package-scope-routing -->
## root.antigravity.package-scope-routing
Start package-scoped work with the intended workspace root so native discovery reads root→cwd. During an authorized cross-package task, explicitly read each applicable package guide in the current session.
<!-- swissknifeman:instructions:root:antigravity:extension:end -->
