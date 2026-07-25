# P6.5 integrated conformance — RED

**Plan/item:** `2026.07.19-DUAL-PROVIDER` / `P6.5`
**Anchor:** `1ca0c398bf03af898313bf6f7ae128c127f84e64`
**Session:** `gpt-5.6-terra/medium`

| Micro-slice | Evidence | Verdict |
|:--|:--|:--|
| b — isolated dual-provider instruction conformance | Original sibling-resolution RED is retained in `findings/P6-bootstrap-probes-2026-07-19.md`; repair verification produced byte-identical reports (`60686d05…e453e`), no missing sibling diagnostic, dual-provider 12-target projection, 49 common IDs, 18 extensions, and managed-drift/outside-byte proof. | GREEN (repaired seam) |
| c — neutral analytics | Four contract-derived reader/capture tests prove provider provenance, dual-read/single-write, copy+verify idempotence, conflict-safe no-write modes, and unchanged raw sources. | GREEN |
| d.1 — core validation | `PYTHONPATH=. python3 -m unittest discover -s core/tests`: run exactly once, 206 tests. | GREEN |
| d.2 — analyst validation | `bash packages/analyst/scripts/validate.sh`: run exactly once, 211 tests. | GREEN |
| d.3 — maind validation | `bash packages/maind/scripts/validate.sh`: run exactly once; `test_independent_provisioner_provider_matrix_is_complete_and_honest` expected `planned / none`, actual `failed / INSTRUCTION_TARGET_MISSING`. | RED |

The P6.5 terminal sequence stopped at d.3. Harness validation, integrated terminal conformance,
plan lint, diff/protected-delta checks, live probes, and disk/memory checkpoint creation were
not run. The valid core and analyst results remain reusable; the repair invalidates only maind
validation and its downstream terminal consumers. No package source was changed by P6.5.

## Repair 2 continuation

The P6.2 repair commits `93b157bc` and `d7d80c96` invalidate only d.3. Its single rerun is
GREEN (449 tests). The unrun terminal tail is GREEN once: harness (406 tests), integrated
public CLI conformance (providers `claude-code,codex`, 12 instruction targets, 49 common IDs,
managed-drift/outside-byte proof), plan-lint (0 errors and 0 new warnings), diff check, and
protected-delta check (0). Core (206) and analyst (211) remain valid and were not rerun.

The memory-isolation probe is RED: a recall scoped to `project:swissknifeman` also returned
`mem_mrjkvnib_8eaf537d482c` with declared scope `ns:axioma`. The preceding read-only graph,
Serena and Perplexity probes succeeded, but they do not override the isolation failure. No
checkpoint write or P6.5 close is authorized from this state. Only memory-scope repair,
isolation recheck and downstream checkpoint creation are invalidated.

## D93 recovery and checkpoint — GREEN

The D93 worktree-local public MCP recall returns only records declared
`project:swissknifeman` when explicitly scoped. The compact checkpoint
`p6.5-bootstrap-b7373334` is stored once, recalled in the same scope, and matches the disk
payload SHA-256 `22a9c7a82f48ae0e27449ca1be240398b3b8ecd36fbfd50bc2f8bd3a56d60dc9`.

## D94 terminal-audit repair provenance

`0694379c0c62031cee6b428fb1c8eb260f213d44` is the owner-authorized prerequisite before
P6.1 and an ancestor of P6 phase-close `d18bf0bcbc03674272c9b315b88fbee28987ee1b`.
Therefore protected root-bootstrap comparison starts at `0694379c`, not its predecessor:
`.agents/plugins/marketplace.json` has zero delta after that baseline, as do protected
P7/FOREMAN/fleet paths. This corrects audit provenance only; it does not alter any frozen
contract or P6.5 validation result.
