# P7 regression matrix

P7.2 converts P7.1's repository acceptance rows into deterministic checks. Live-provider
efficacy remains the D88-deferred P7.1 evidence; this matrix does not reinterpret it as a
deterministic test result.

| Acceptance invariant | Permanent regression locks |
|:--|:--|
| Exact provider status; one provider cannot mask another | `core/tests/provider/test_health.py`, `core/tests/provider/test_status.py`, `packages/maind/tests/test_provider_health.py` |
| Capability manifest, stale/generated output and unsupported-required failures | `core/tests/provider/test_manifest.py`, `packages/task/tests/test_provider_command_parity.py`, `scripts/test-provider-docs.py` |
| Shared core with additive, provider-owned adapters and no cross-provider writes | `core/tests/provider/test_skill_adapter.py`, `packages/skiller/tests/test_provider_distribution.py`, `packages/skiller/tests/test_provider_publication_parity.py`, `packages/maind/tests/test_provider_deploy.py` |
| Independent response, plan and diagnostics locales | `core/tests/locale/test_resolution.py::ResolutionTests.test_each_surface_override_leaves_the_other_surfaces_byte_identical` |
| Clean Codex consumer discovery, separate from repository-local state | `packages/skiller/tests/test_codex_consumer_acceptance.py` |
| Security/trust, malformed evidence and redacted provider traces | `packages/harness/tests/test_provider_security.py`, `packages/harness/tests/test_provider_trace.py`, `packages/analyst/tests/test_provider_readers.py` |
| Worktree-local public hook CLI keeps relative/absolute dry-run planning equivalent and writes nothing | `packages/harness/tests/test_provider_conformance.py::ProviderConformanceTests.test_public_hook_dry_run_normalizes_relative_and_absolute_targets_without_writes` |

## Validation receipt

- `PYTHONPATH=. python3 -m unittest discover -s core/tests -p 'test_*.py'` — green.
- `bash packages/{skiller,task,harness,maind,analyst}/scripts/validate.sh` — green.
- Both required `harness hooks … --dry-run` invocations returned `green` with plan
  `sha256:46826563e47eb9a2362640a8ab435ec8830832480a9af675c4b46a4e36b9c3e8` and left
  `.codex/hooks.json` and `.codex/hooks/lifecycle.py` byte-identical.
- P7.1 exact evidence verifier and P7.2 plan lint — green.
