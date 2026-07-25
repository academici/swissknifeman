# P3.4 bundled fail-closed remediation

## Inputs and boundary

- `findings/P3.5-provider-b-unmanaged-partial-success-2026-07-20.md` and D78 repair
  `c367335`;
- P3.5 retry evidence recorded in `journal.jsonl:113` and the independent synthetic
  probes of 2026-07-21;
- frozen `root/contracts/provider-{artifact,skill-publication}-contract.md` v1.0.0;
- `packages/skiller/lib/skiller/skillset.py::{plan_sync,do_sync,sync_skillset}`.

P3.5 has not made a conformance claim.  The probes found two more missing checks in
the same P3.4 vendor planning seam, so D80 owns one bounded re-open of P3.4 instead
of a second per-symptom cycle.  This does not change publication identities,
selection, plugin/cache delivery, lock grammar, P3.1, P4+, FOREMAN, fleet, or a live
target.

## Confirmed defects

1. A managed selected Codex `SKILL.md` whose bytes are edited after a successful
   sync remains in `keep`: `plan_sync()` compares only the registry source hash to
   the old lock, not the installed managed bytes.  A subsequent ordinary sync can
   therefore report clean rather than `managed-drift`.
2. A corrupt `skills-lock.json` is warned about, reconstructed from the manifest,
   and then overwritten by ordinary dual sync.  That is a provenance-invalid state,
   not a recoverable empty lock, and must refuse before config materialisation,
   provider writes, lock writes, or registration.

The D78 selected-provider unmanaged conflict remains part of the same aggregate
preflight and is retained as a regression case; it is not reimplemented.

## Minimal repair

Keep the existing provider resolver, `plan_sync()` output, `skills-lock.json` schema,
and `--force` ownership-conflict path.  Add only private classification data to the
already computed vendor plan:

- For every existing managed directory, hash the installed `SKILL.md` before
  source-envelope comparison.  When its hash differs from the lock's recorded
  managed hash, classify it as `managed-drift`, not `update` or `keep`.  When it
  matches the lock but the registry source/content envelope differs, retain the
  existing `stale-source`/ordinary update path.  This preserves the frozen priority:
  managed bytes before source staleness.
- Validate the existing `skills-lock.json` before `materialize_skillset_config()` or
  any selected-provider plan/apply.  JSON/shape/version/provider-map/provenance
  invalidity is `provenance-invalid` and produces provider/channel/target-qualified
  `SPUB_OWNERSHIP_CONFLICT`; it is never reconstructed, adopted, or overwritten by
  a normal sync.
- Aggregate every selected provider's `conflicts`, `managed-drift`, and invalid-lock
  classification before the first `_do_sync_provider()` call.  Any default failure
  leaves Claude/Codex skill directories, `skills-lock.json`, project config and
  project registration byte-identical.
- Preserve the existing `sync` command and add only its explicit `--repair` mode;
  it is not a new command or a new contract.  `--force` remains exclusively the
  explicit owner overwrite path for an unmanaged ownership conflict.  `--repair`
  may repair only a matching manager-owned drift after a clean aggregate preflight;
  it must save the exact pre-image beside the replaced `SKILL.md` using the existing
  recoverable `.provider-artifact.bak` convention, print/provider-record the
  observed, expected and source hashes, and recheck the resulting lock/bytes.  It
  must not repair corrupt provenance, boundary failures, or unowned targets.

The implementation stays in `skillset.py` and its existing distribution tests.  It
does not add a resolver, a new public module/symbol, a provider-specific branch, or
a second lock format.  The existing P2 hash spelling (`sha256:<lowercase-hex>`) is
used in diagnostics and repair evidence.

## Acceptance matrix

All cases use a `TemporaryDirectory` with an already-existing vendor config and a
dual provider selection.

| Case | Default result | Explicit result | No-write / evidence assertion |
|:--|:--|:--|:--|
| unmanaged selected Codex directory | qualified ownership refusal | existing `--force` only | D78: no Claude/Codex copy, lock or registration before refusal |
| managed Codex `SKILL.md` manually edited | `managed-drift` refusal | `--repair` restores expected source bytes | saved pre-image equals observed bytes; diagnostic records observed, expected and source hashes; post-repair replan is clean |
| source changes while installed bytes match old lock | stale-source update | ordinary sync applies update | no repair backup; expected source/rendered hashes advance together |
| malformed/structurally invalid/newer-provenance lock | qualified provenance refusal | none | no config creation, skill/lock write, backup or registration |

The tests calculate all three hashes from actual fixture bytes; they must not hardcode
renderer output.  They assert the pre-image bytes/hash equal the observed hash and
the copied canonical `SKILL.md` hash equals the expected hash.

## Validation and resume

The P3.4 repair runs only the targeted distribution and skillset regressions plus
`py_compile`/static forbidden-branch check.  Per D80, full package validation,
registry check, documentation/release assessment, phase close and independent audit
run once after P3.5 has completed the full P3 parity matrix.  P3.5 resumes only
after the repair is committed and its targeted acceptance matrix is green.

RAG:— (repo-grounded: frozen P2/P3 contracts, current `skillset.py`, P3.5 synthetic
evidence, D78); no external capability claim is used.
