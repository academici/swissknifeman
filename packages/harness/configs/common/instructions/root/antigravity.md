<!-- instruction:root.antigravity.instruction-precedence -->
## root.antigravity.instruction-precedence
The common repository contract reaches this session through the `AGENTS.md` Antigravity already reads; it is not repeated here. Sections marked `root.codex.*`, `root.cursor.*` or `root.grok.*` in that file are owned by those providers and are **not** authoritative in an Antigravity session — never follow Codex launch flags (`-a never`, `-s danger-full-access`) or Cursor `--force` flags from them.
<!-- instruction:root.antigravity.launch-and-autonomy -->
## root.antigravity.launch-and-autonomy
Name the intended cwd, the routed model (`--model`) and mode before acting. Use the installed `agy --help`: `--mode plan|accept-edits|auto`, `--effort` and session-only `--settings` are the CLI surfaces. `--dangerously-skip-permissions` requires an explicitly trusted invocation. Harness renders `.antigravity/config.toml` as a policy projection; the file alone does not prove native CLI enforcement. Verify actual enforcement separately; never infer a sandbox or effective deny floor from rendered TOML. Do not pass Grok's `--permission-mode` or `--always-approve` flags to AGY.
<!-- instruction:root.antigravity.package-scope-routing -->
## root.antigravity.package-scope-routing
Start package-scoped work with the intended workspace root so native discovery reads root→cwd. During an authorized cross-package task, explicitly read each applicable package guide in the current session.
