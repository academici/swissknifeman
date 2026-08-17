# P7 release-candidate manifest

**Candidate:** `2026.08.02-PROVIDER-CONTRACT-LOCALE P7.3`
**Status:** non-published, non-releasable
**Decision:** D89 accepts a truthful non-releasable candidate; it does not authorize a release exception, tag, push, publication, fleet rollout, or provider repair.

## Repository identity

| Field | Value |
|:--|:--|
| Repository HEAD | `519af66def68027738a0158142cf7a19050d3983` |
| Dirty-worktree observation | `5df291d3a6f842f4278489d3d8f8bd912866b22cfcb4b3f91af0e096f7ef109a` immediately before P7.3 mutations; this is an observation, not a release tree or commit. |
| Commit available for candidate provenance | `519af66def68027738a0158142cf7a19050d3983` only; P7.3 changes are deliberately uncommitted because this shared worktree already contained unrelated changes. |
| Package versions | skiller `0.13.0`; harness `0.4.0`; maind `0.3.0`; analyst `0.2.0`; task publication adapter `0.13.2` |

## Contract, catalog, and generated renders

| Carrier | SHA-256 |
|:--|:--|
| `root/contracts/provider-control-plane-v1.md` | `f959cb9a7dfd672c7a208942e52a63c51cb64b9af8c72ed85d6d174439e91772` |
| `root/contracts/locale-resolution-v1.md` | `365214ea0c98c7c9224c994158be7f80eafb6def83123159fd1026aedb74a8e2` |
| `root/contracts/english-authoring-overlay-v1.md` | `8fe3d3eca71e489306e2fd8a021214f8c107e92d93c1cae0c9f985565cfeab4c` |
| `root/contracts/locale-authoring-review-v1.md` | `93fe79a7d933be43a614e641895d6c77bcbf8dc1d86abcae75f815732c7f9e5f` |
| `root/contracts/provider-health-v1.md` | `09bef7896250d24f1a057e69b94936dd635be5c28c125ecace9e65038f5723ab` |
| `configs/provider-capabilities.json` | `2b3bd60cade123c1f390c2c3fe3e1db0029bf2d2f7946ed3394620366c8f387d` |
| `scripts/provider-docs.py` | `f2cab4382836a1724690d4dc1574fa0eeed8789b29c29d067287e063b1a6860a` |
| generated `README.md` provider block carrier | `3468283271475fb540b17cb661c5817f247665e368dc50dcaea20242cba04213` |
| generated `docs/provider-support.md` | `807e6cf2a10f7345aa91dbd289b4617c8efb1be28f71a239c4ce89af6f551395` |

## Pinned language registry provenance

| Field | Value |
|:--|:--|
| Vendor path | `core/locale/data/language-subtag-registry.txt` |
| File-Date | `2026-06-14` |
| SHA-256 | `be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a` |
| Provenance | `core/locale/data/upstream.json` (`038df39a5b43384c09dc892090a5316d7de33bf2b3af673c3a80f85d0ae64fd0`) |
| Update producer | `scripts/update-iana-language-subtag-registry.py` |

## Validation and rollback pointers

- Provider-doc generation wrote twice with byte-stable second output; `--check` and its five-test
  checker passed. The complete non-mutating command receipt is
  [`P7-operations-readback.md`](./P7-operations-readback.md).
- Core/P7.1/package validation, citations, and all required standalone/aggregate documentation
  builds are green. The initial mAInd standalone `/deploy` failure was repaired under the explicit
  owner-authorized, one-line scope extension recorded below. It is not added to the frozen P7.1
  blocker payload, which remains an exact copy.
- Provider docs rollback: repair the canonical generator input and run
  `python3 scripts/provider-docs.py --write`; never edit generated output. Managed provider or
  instruction rollback restores only the declared owned preimage through its corresponding command
  boundary. This candidate has no external state to roll back.

## Exact residual blockers

Source: `artifacts/P7.1/evidence/release-blockers.json`, SHA-256
`f23721271c91c236c0e256842fa5fbe92b4868fb948719978863381f423c12fa`.

```json
{"deferred":{"claude_code":"documented-not-live-verified","codex_replay":"diagnostic-not-release-efficacy","decision":"D88","p5_rollout":"not-authorized-external-operation","p6_required_project_release_blockers":["MEMORY_CLEANUP_NON_GREEN:project-1bb1c2eba307e990","PROJECT_NON_GREEN:project-014a1283da270bd6","PROJECT_NON_GREEN:project-034bc815af5bcfbb","PROJECT_NON_GREEN:project-1bb1c2eba307e990","PROJECT_NON_GREEN:project-1cf3a711c12e6a9b","PROJECT_NON_GREEN:project-2f270a6fe5f0bbcc","PROJECT_NON_GREEN:project-383351c63aaf37ac","PROJECT_NON_GREEN:project-48590a32ed307abd","PROJECT_NON_GREEN:project-4f583bba1e3d6be8","PROJECT_NON_GREEN:project-62eb4ffd9db923d9","PROJECT_NON_GREEN:project-6fcbd71ebeedc92c","PROJECT_NON_GREEN:project-7ff99b78a82ce1bf","PROJECT_NON_GREEN:project-83c5b3c93ffe31c0","PROJECT_NON_GREEN:project-8c234a131487ede5","PROJECT_NON_GREEN:project-ab471cd0f1c85b97","PROJECT_NON_GREEN:project-ae6cf52cbe90f84b","PROJECT_NON_GREEN:project-b06bcd38ed385da6","PROJECT_NON_GREEN:project-b1b34c916a75d8c9","PROJECT_NON_GREEN:project-b90c0f619b100582","PROJECT_NON_GREEN:project-c9e6c8c25f188930","PROJECT_NON_GREEN:project-cf305f1c831a36e2","PROJECT_NON_GREEN:project-d12b43a6d74056cf","PROJECT_NON_GREEN:project-ffddc862898a8984","PROJECT_UNAVAILABLE:project-1bb1c2eba307e990"]},"package_blockers":[]}
```

The fenced payload is byte-for-byte equal to the source and is retained as the exact residual
blocker identity for the P7.4 audit.

## Derived releasability

`blockers == []` is **false**. Therefore `releasable = false`. The non-empty residual set is an
accepted P7.3 result under D89, never an exception.

## P7.3 scope extension

The owner authorized completion after the exact P7.3 scope gap was reported. The one-line repair
in `packages/maind/docs/guide/systemd.md` replaces a root-site-relative link with the canonical
repository source URL, which works in the standalone and aggregate sites. The owner response and
initial reproduction are recorded in
[`artifacts/execution/P7.3/owner-response-maind-docs-scope.json`](./execution/P7.3/owner-response-maind-docs-scope.json)
and [`findings/P7.3-maind-standalone-docs-build.md`](../findings/P7.3-maind-standalone-docs-build.md).
