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
