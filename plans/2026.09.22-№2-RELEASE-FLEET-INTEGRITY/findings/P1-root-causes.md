# P1 root causes

1. Release attestation obtained a unit version from a generated Codex manifest and generated the expected snapshot from the same value. It checked byte consistency, but had no independent expected-version policy. Claude-only plugin units were absent from the inventory.
2. Task version ownership was split: `command-routing.json` generated Codex/Cursor surfaces while the Claude manifest was a second input. Nothing required both to match the owner-approved unit version.
3. `doctor --vendor-drift` planned only the default Claude channel and ignored managed drift, invalid provenance, relocation and planning errors. Provider distribution did not pass the selected plugin set to its planner.
4. Legacy cleanup resolved only the currently configured `skills_path`; after the three-provider migration changed that path it no longer inspected the historical `.claude/skills` managed manifest.
5. `maind sync --json` printed failed rows and still exited zero. Separately, four wrapper provisioners set `changed=rc==0`; their dry-run therefore reports 83 changes on every successful invocation and cannot serve as an idempotence proof.
6. Package/plugin divergence was possible because maind, analyst and harness plugin units were not related to their package version in attestation policy.

