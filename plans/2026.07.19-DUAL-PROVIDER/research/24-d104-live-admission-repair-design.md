# D104 live admission — bounded P2/P5/P6 repair design

**Scope:** design only. No package implementation, live apply/repair, P7.2 rerun, P7.3+,
FOREMAN, fleet, tag or push is authorized here.

**Sources:**

- `findings/P6-bootstrap-transfer-live-preflight-2026-07-22.md`;
- `findings/P6-d104-live-admission-root-cause-2026-07-22.md`;
- `research/23-p7.2-live-preflight-remediation-design.md`;
- D103/D104 in `plan.md` and `brief/01-refinements.md`.

## Diagnosis

D104's P2 candidate is admissible in isolation. The live command does not select it because the
effective provider set contains only `claude-code`; it then collapses the ordinary `.mcp.json`
ownership conflict into the same stable diagnostic. P5's direct lifecycle command correctly
remains an ordinary non-selector.
Therefore neither widening the D104 target set nor teaching P5 to adopt the hooks file is a
valid repair. RAG:— (repo-grounded:
`findings/P6-d104-live-admission-root-cause-2026-07-22.md`).

## Owning route

| Owner | Decision | Repair obligation |
|:--|:--|:--|
| P2 | Keep terminal; do not reopen. | Existing `plan_bootstrap_transfer` is the sole admission oracle. Its admitted/refused actions and `artifact_dry_run` projection are sufficient; no API, contract, lock grammar or target expansion is needed. |
| P5 | Keep terminal; do not reopen. | The direct observer dry-run remains a required negative control: the unmanaged whole-file target must refuse. P5 supplies only the D104 fragment/handler bytes to P6 and gains no CLI flag or adoption path. |
| P6 | Add P6.9 then P6.10. | P6.9 preserves effective selection, reports the D104 transfer as `not-selected`/admitted/refused separately from the ordinary provider plan, and preflights every selected required plan before write. P6.10 independently proves the split verdict and zero-write behavior. |

RAG:— (repo-grounded: D104, `phases/P2.md` P2.6, `phases/P5.md` P5.8,
`phases/P6.md` P6.7–P6.8).

## Acceptance semantics

The repaired no-write report distinguishes three facts without changing any of them:

1. live `bootstrap_transfer = not-selected` while Codex is not effective; a selected temporary
   operation reports `planned` only when the exact D104 two-action plan is admitted;
2. the ordinary provider aggregate remains non-green for the live unmanaged `.mcp.json`;
3. the direct P5 lifecycle dry-run remains non-green as the ordinary-path negative control.

The whole live operation is therefore still blocked. P6.10 does not open P7.2; it hands the
remaining `.mcp.json` ownership decision back as a separate new-authority boundary. A future
decision may adopt that path or change provider selection, but neither is inferred from D104.
RAG:— (owner-grounded: D104 anti-scope; repo-grounded:
`findings/P6-d104-live-admission-root-cause-2026-07-22.md`).

## P6.9 implementation shape

- Preserve the P1 effective-provider gate. Build the D104 transfer plan only when Codex is
  selected, and build it plus the ordinary provider plan/check before calling `apply_plan`.
- Project bootstrap actions with the existing P2 no-write projection; do not reconstruct or
  reclassify them in P6.
- Return/report bootstrap selection/status separately from provider rows. `not-selected`,
  admitted and refused are distinct; a later ordinary refusal must not overwrite them, and an
  admitted transfer must not make the whole operation green.
- In write mode, any refused required subplan stops before backup, hooks, handler, lock or MCP
  target writes. Only when all preflights are green may the existing transfer-then-provider apply
  order execute.
- Do not pass transfer artifacts through an ordinary P2 check against the pre-transfer root to
  manufacture a false green; that state has not happened yet.

RAG:— (repo-grounded: `packages/maind/lib/maind/{provider_deploy.py,provision/deploy.py}`,
`core/provider_lock.py`).

## Independent proof P6.10

Temporary roots must cover exact admission + clean ordinary provider targets, exact admission +
unmanaged `.mcp.json`, changed hooks preimage, existing handler and pre-existing lock. The
selected-Codex live-shaped unmanaged-MCP fixture must show an admitted bootstrap row, a non-green
ordinary row and zero writes even through the write-mode facade under a writer spy. The actual
live Claude-only command must show `not-selected`, the non-green ordinary row and zero delta.
These split verdicts replace the impossible “both readers GREEN” P6.8 criterion.

## Pre-mortem

| Failure in 6–12 months | Mitigation / owner |
|:--|:--|
| An admissible candidate or green selected-bootstrap row is mistaken for permission to enable Codex/apply. | Selection is explicit, whole-operation aggregate remains non-green and P6.10 keeps P7.2 closed; owner: P6.9/P6.10. |
| P6 applies the transfer before discovering another unmanaged provider target. | All required plans are computed before the first write; writer-spy and snapshot regression are mandatory; owner: P6.9. |
| P5 gains a convenient second adoption path. | Direct harness refusal is a pinned negative control; owner: P5 invariant consumed by P6.10. |
| D104 silently expands to `.mcp.json` or provider config. | Exact P2 target/artifact set remains byte-stable; any expansion escalates for a new Owner D#; owner: P2 invariant. |
