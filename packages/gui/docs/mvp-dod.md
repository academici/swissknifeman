# MVP Definition of Done

Each item of the DoD of the owner's source (`ideas/gui`, "MVP DoD") and each hardening item of the last phase points to
the check that proves it: a test file (path from the repository root) and the name of the test or scenario in it.
`packages/gui/tests/test_mvp_dod.py` reads this table, checks that every file exists and that its text contains the name.

- `auto`: the check runs in a normal test pass (Python `unittest`, `vitest`, Playwright in browser mode).
- `owner`: the check needs the owner's toolchain or machine (Rust, Tauri, PyInstaller, signing, installing); the named
  step of `docs/desktop-release.md` is the procedure. Nothing marked `owner` was run by the development environment
  (decision D26).

| # | DoD item | Kind | File | Test or scenario |
|---|----------|------|------|------------------|
| 1 | Fleet dashboard shows the four control-surface layers | auto | `bridges/gui-hub/tests/test_adapter.py` | `test_layers_of_a_project` |
| 1 | Drift and exact fixes (only allowlisted fixes offer a repair) | auto | `bridges/gui-hub/tests/test_adapter.py` | `test_only_allowlisted_sync_fixes_offer_a_repair` |
| 1 | The dashboard opens in the browser after the one-time URL | auto | `packages/gui/frontend/e2e/session.spec.ts` | `the one-time URL signs in once and opens the dashboard` |
| 2 | Config: effective value and provenance of every key | auto | `packages/gui/tests/test_config_service.py` | `test_provenance_and_layer_values_after_a_write` |
| 2 | Config: preview has no side effects | auto | `packages/gui/tests/test_config_service.py` | `test_preview_has_no_side_effects` |
| 2 | Config: a stale revision is a conflict and the file stays | auto | `packages/gui/tests/test_config_service.py` | `test_stale_revision_conflicts_and_leaves_the_file` |
| 2 | Config: edit, preview, confirm, apply, conflict and Reapply in the UI | auto | `packages/gui/frontend/e2e/config.spec.ts` | `edit, preview, confirm and apply; then an outside change is a conflict that Reapply resolves` |
| 3 | Plugin: an extension waits for an explicit enable and a green check | auto | `packages/gui/tests/test_plugin_gates.py` | `test_extension_waits_for_an_explicit_enable_and_a_green_check` |
| 3 | Plugin: garbage answers quarantine it and Release heals | auto | `packages/gui/tests/test_plugin_gates.py` | `test_garbage_answers_quarantine_the_plugin_and_release_heals` |
| 3 | Plugin: enable and disable in the UI, quarantine after three failures | auto | `packages/gui/frontend/e2e/plugins.spec.ts` | `three failures quarantine the plugin and Release brings it back` |
| 4 | Command: dry run | auto | `packages/gui/tests/test_broker.py` | `test_dry_run_appends_its_argument` |
| 4 | Command: confirmation by risk | auto | `packages/gui/tests/test_http_runs.py` | `test_risk_based_confirmation` |
| 4 | Command: audit and frames of a run | auto | `packages/gui/tests/test_broker.py` | `test_echo_succeeds_in_the_project_with_audit_and_frames` |
| 4 | Command: cancel kills the process group | auto | `packages/gui/tests/test_broker.py` | `test_cancel_kills_the_group` |
| 4 | Command: live log in the UI | auto | `packages/gui/frontend/e2e/commands.spec.ts` | `greet runs as a dry run and for real, with its log` |
| 4 | Command: the log stream resumes after a dropped connection | auto | `packages/gui/frontend/e2e/reconnect.spec.ts` | `a dropped event stream resumes without lost or repeated log chunks` |
| 5 | Planner: a domain mutation changes the route or review model | auto | `bridges/gui-planner/tests/test_commands.py` | `test_set_passes_the_exact_argv_and_returns_the_new_revision` |
| 5 | Planner: the change reaches the plan file and the plan stays valid | auto | `packages/gui/frontend/e2e/planner.spec.ts` | `changing the reviewer model changes the plan file` |
| 6 | Crash: runs of an earlier backend become lost, nothing is replayed | auto | `packages/gui/tests/test_http_runs.py` | `test_runs_of_an_earlier_backend_are_lost_at_start` |
| 6 | Crash: a plugin that fails to start is quarantined | auto | `packages/gui/tests/test_plugin_gates.py` | `test_spawn_failures_of_an_argv_command_quarantine` |
| 6 | Crash: a lock held by another process never corrupts a config file | auto | `packages/gui/tests/test_config_service.py` | `test_a_lock_held_by_another_process_is_locked` |
| 6 | Crash: a failed state rebuild leaves `gui.db` as it was | auto | `packages/gui/tests/test_state_admin.py` | `test_failure_in_the_middle_leaves_the_original` |
| 7 | One frontend build: no inline script or style, local assets | auto | `packages/gui/tests/test_frontend_build.py` | `test_no_inline_script_or_style` |
| 7 | One frontend build: the Tauri global selects TauriTransport, HTTP otherwise | auto | `packages/gui/frontend/src/transport/TauriTransport.test.ts` | `uses the Tauri global when present and HTTP otherwise` |
| 7 | The same build runs in the Tauri shell on a clean machine | owner | `packages/gui/docs/desktop-release.md` | `Install check` |
| 7 | The sidecar builds with PyInstaller and starts (`GUI_READY`) | owner | `packages/gui/docs/desktop-release.md` | `Sidecar check` |
| 7 | The signed update installs and a wrong signature is refused | owner | `packages/gui/docs/desktop-release.md` | `Update check` |
| 8 | Terminal is off by default and needs a confirmation per session | auto | `packages/gui/tests/test_http_terminal.py` | `test_disabled_by_default` |
| 8 | Terminal: output only after credit, input, resize and exit | auto | `packages/gui/tests/test_http_terminal.py` | `test_output_only_after_credit_input_echo_resize_and_exit` |
| 9 | Orch runs: the run table, report and sandbox rows | auto | `bridges/gui-orch/tests/test_queries.py` | `test_sandbox_rows_are_the_orch_checks_with_the_caption` |
| 9 | Orch runs: commands are exact argv, no shell | auto | `bridges/gui-orch/tests/test_commands.py` | `test_run_ready_argv_is_exact` |
| 10 | Hardening: `gui state rebuild` keeps the rows of the operator tables | auto | `packages/gui/tests/test_state_admin.py` | `test_rows_survive_and_backup_exists` |
| 10 | Hardening: `gui state rebuild --dry-run` writes nothing | auto | `packages/gui/tests/test_state_admin.py` | `test_dry_run_writes_nothing` |
| 10 | Hardening: a changed sidecar file stops the start (`SIDECAR_TAMPERED`, exit 3) | auto | `packages/gui/tests/test_sidecar_digest.py` | `test_serve_sidecar_exits_3_before_reading_stdin_or_binding` |
| 10 | Hardening: the digest of 500 files is checked in under 2 s | auto | `packages/gui/tests/test_sidecar_digest.py` | `test_five_hundred_files_are_fast` |
| 10 | Hardening: the SBOM is byte-for-byte deterministic | auto | `packages/gui/tests/test_sbom.py` | `test_two_runs_are_byte_equal` |
| 10 | Hardening: xterm is not in the initial bundle | auto | `packages/gui/tests/test_frontend_budget.py` | `test_xterm_in_the_initial_script_fails` |
| 10 | Accessibility: names, one h1, heading order, labelled landmarks on real screens | auto | `packages/gui/frontend/src/a11y.test.tsx` | `accessibility of the real screens` |
| 10 | Accessibility: dialogs take the focus and give it back | auto | `packages/gui/frontend/src/a11y.test.tsx` | `dialogs take the focus and give it back` |

## What is not proven here

- Rows marked `owner`, and every Rust, Tauri, PyInstaller, signing and installation step (`docs/desktop-release.md`,
  "Not checked in the repository").
- Plugin permissions stay advisory: GUI plugin processes run without a sandbox (decision D23); the table proves the gates
  (state, grants, quarantine), not the confinement of a running plugin.
- The sidecar digest is not signed (`docs/security.md`).
