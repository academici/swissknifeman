# P7.1 capability manifest / production gates / provider docs conformance

**Tree anchor:** `4177967cc363e6160c5fc42164e663f3addd7a15`

**Observed:** 2026-07-22

**Item state:** GREEN — D99 approved the manifest/API/SemVer, D100 corrected the
production-caller allowlist, and D101 repaired only the inherited stale test assertion.
All mandatory P7.1 validations pass without changing production P6 bytes or semantics.

## Owner approval and manifest identity

Owner D99 approved exactly:

```text
APPROVE P7.1 D99 CAPABILITY-MANIFEST SHA256:4c479c697c708cfea8d36589c435338094d894bcf428687709987975b13b6ce1
SETS-API-SEMVER AS WRITTEN
```

| Field | Observed |
|:--|:--|
| Contract / catalog | `1.0.0` / `1.0.0` |
| Canonical JSON SHA-256, no LF (D99 identity) | `4c479c697c708cfea8d36589c435338094d894bcf428687709987975b13b6ce1` |
| Carrier SHA-256, canonical bytes plus terminal LF | `32975d675cf252bba87b06aaee53bfe37e63a9a97dc74cb7a12a8a2b0c0394eb` |
| Providers / common capabilities / support records / Native Extensions | `2 / 35 / 70 / 0` |
| Level totals | `native=19`, `adapted=31`, `unsupported=20` |
| Claude Code totals | `native=10`, `adapted=22`, `unsupported=3` |
| Codex totals | `native=9`, `adapted=9`, `unsupported=17` |

The canonical digest intentionally excludes the carrier LF; tests assert both hashes and
the exact relation `carrier == canonical_bytes + b"\n"`.

## Independent exact-set and requirement report

`scripts/provider-docs.py` derives the expected set independently from the terminal task
routing catalog (8 IDs), harness surface catalog (23), instruction requirements (1), and
the three frozen analytics contract sections (3). Their union is exactly 35.

```json
{
  "missing": [],
  "extra": [],
  "duplicates": [],
  "matrix_missing": [],
  "matrix_extra": [],
  "native_extensions": [],
  "requirement_failures": [],
  "task_mapping_missing": {"claude-code": [], "codex": []},
  "task_mapping_extra": {"claude-code": [], "codex": []},
  "analytics_contract_missing_sections": [],
  "green": true
}
```

All 170 named production requirement occurrences (including command-specific repetitions)
resolve to exactly one provider support record at an accepted level, or to an explicit
manifest-owned `unsupported` row where the doctor/audit consumer requires visibility.
Every common capability has exactly one Claude Code and one Codex record.

## Production gate switch

| Consumer | Manifest-backed pre-output behavior | Focused evidence |
|:--|:--|:--|
| core | Pure strict v1-major parser, aggregate deterministic diagnostics, explicit-path loader, immutable rich model, canonical hash, P1/support projections. | provider-focused core suite `60/60` GREEN; compatible v1 SemVer preservation, next-major refusal, lossless tagged-array round-trip, canonical display names, frozen negative matrix and no-write loader covered. |
| skiller | Distribution config projects the root manifest; both publication renderers select through `AdapterCatalog` before bytes. | P7-focused tests `11/11` GREEN; missing, unsupported and catalog mismatch refuse without writes. |
| task | Provider mappings replace carrier support values with manifest projection; render/invocation production calls use that projection and preserve observed capability catalog version. | P7-focused tests `18/18` GREEN; missing and unsupported/level mismatch return zero results. |
| harness | Provider audit and every direct profile-catalog consumer load the repo-owned manifest before catalog/projection work, require the complete surface matrix and compare named activation evidence to manifest levels. | conformance tests `15/15` GREEN; default-path non-bypass, missing, support mismatch and accepted-level mismatch covered. |
| maind | Config selection projects the manifest; deployment requires `mcp.catalog` before render; the D100 caller uses the manifest-backed config seam. | provider-deploy tests `16/16` GREEN; missing/unsupported fail before rendered output. |

Mandatory production grep is GREEN:

```text
! rg -n 'ProviderConfigCatalog\(' packages --glob '*.py' --glob '!**/tests/**'
```

## Generated docs / no-write evidence

- `PYTHONPATH=. python3 scripts/test-provider-docs.py`: `4/4` GREEN.
- `python3 scripts/provider-docs.py --write` twice: both runs emitted zero bytes on the
  converged tree; the second run was empty.
- `python3 scripts/provider-docs.py --check`: exit `0`; generated target hashes before
  and after remain `README.md=4ad9355aa7311cbc3c7d7ff660cf6906edf5e9e829c78135dca803b310a6f4b5`
  and `docs/provider-support.md=b1e3536dece71e9a854bcd385a597aab7d1673ee005b8fd6edc876826d0d0c8b`.
- README marker tests prove bytes outside the generated block are preserved.
- All internal Markdown links in generated README/guide output resolve.
- Examples keep native syntax separate: Claude Code `/task:fix`; Codex `$ task:fix`.
- Trust, approval and sandbox remain independent; full access is documented only as the
  exact trusted `self-host-apply`/`repo:` operation, never a project/fleet default.

## Full validation matrix

| Validation | Result |
|:--|:--|
| `bash packages/skiller/scripts/validate.sh` | GREEN (`410` tests; registry drift empty) |
| `bash packages/task/scripts/validate.sh` | GREEN (`228` tests; plan-lint 0 errors) |
| `bash packages/harness/scripts/validate.sh` | GREEN (`410` tests) |
| `bash packages/analyst/scripts/validate.sh` | GREEN (`211` tests) |
| `PYTHONPATH=. python3 -m unittest discover -s core/tests` | GREEN (`218` tests) |
| `bash packages/maind/scripts/validate.sh` | GREEN (`459` tests) |
| P7 plan lint | Pre-close GREEN; final attributed count is recorded by bookkeeping after handoff rewrite. |

### Owner-approved inherited baseline repair

The initial full mAInd run exposed one contradiction already present at base
`c9265ebf71a34d859d2bd0c26a20dbe8f5985196`:

```text
FAIL: test_creates_mcp (test_deploy.TestDeploy.test_creates_mcp)
expected: ${MAIND_BIN:-maind}
actual:   maind
```

Owner D101 authorized only the stale assertion/comment correction. Commit
`6805ca261bcfc14a3967c9dedf069c7948fa6bbd` changes
`packages/maind/tests/test_deploy.py` to expect the already-committed bare `maind` carrier;
production source and rendered output have zero delta in that repair. The focused deploy
suite and full mAInd validation are GREEN afterward.

## Scope / protected-path proof

- D100 added the actual manifest-hardcode caller
  `packages/maind/lib/maind/provision/deploy.py` to P7.1 Files so the mandatory grep could
  become GREEN. D101 added only the stale `packages/maind/tests/test_deploy.py` assertion.
  Both are owner-authorized/spec-correcting inputs to green closure, not product-semantic
  deviations.
- No live provider output was rendered/applied/repaired; docs write touched only README's
  generated marker block and `docs/provider-support.md`.
- `plans/2026.07.18-FOREMAN/**`, `plans/ACTIVE.md`, `.agents/**`, `.codex/**`,
  `.claude/**`, `.claude-plugin/**`, `.codex-plugin/**`, `.swissknifeman/**`, root MCP
  carriers and root fleet `config.json` have zero P7.1 delta.
- No tag, push, fleet action, FOREMAN action or P7.2+ execution occurred.

**Aggregate:** GREEN — exact manifest, production gates, deterministic docs, full package
validation and protected-path proof all pass on the anchored implementation tree.
