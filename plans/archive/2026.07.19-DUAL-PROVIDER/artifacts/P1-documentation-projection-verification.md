# P1 documentation-projection verification

**Owner item:** P1.6
**Validated against:** frozen `provider-config-contract.md` v1.0.0 (D70) and
terminal `core/provider_config.py`
**Historical projection commit:**
`33f35d8618c887a055f79380084574d211af5f05` (phase-close provenance only; not a
P1.6 item-commit rewrite)

## Historical-path ownership

`git show --format= --name-only 33f35d8618c887a055f79380084574d211af5f05 --
packages/skiller/docs/examples/laravel.md packages/maind/docs/guide/config.md`
returns exactly the two paths below.  P1.6 is their explicit validation owner; their
bytes remain unchanged because no contradiction was found.

| Historical documentation path | Validated projection | Contract and implementation support | Verdict |
|:--|:--|:--|:--|
| `packages/skiller/docs/examples/laravel.md` | Optional project `providers` preserves the legacy Claude Code-only result when absent; resolution/validation with provenance has no implicit file change, Codex install, or provider-artifact generation. | Contract **Compatibility**: absent layers produce Claude Code-only, `PCFG_LEGACY_DEFAULT_APPLIED`, and no filesystem write; **Purpose** excludes artifact generation. `resolve_provider_config()` constructs the synthetic legacy selection and performs no filesystem/environment I/O. | supported |
| `packages/maind/docs/guide/config.md` | `providers.defaults` is weaker than `projects[].providers`, which is weaker than project and operation layers; validation/provenance has no implicit provider enablement, artifact generation, or `config.json` mutation. | Contract **Inputs and carriers** ranks fleet defaults below fleet-project, project, and operation; **Precedence and merge** gives the exact order; **Compatibility** forbids writes/implicit Codex enablement; **Purpose** excludes provider outputs. `resolve_provider_config()` applies ranks from legacy upward and has no filesystem/environment I/O. | supported |

## Immutable P1 implementation anchors

| Item | Committed tree / role | Exact commit |
|:--|:--|:--|
| P1.2 | provider-domain implementation | `57b9b2e96f1e56dc06ba4841586e6e4958ac91a8` |
| P1.3 | resolver/carrier-adapter implementation | `8f377e109041a391235d40be9bec73ad6f4d7f89` |
| P1.3 | review-fix tree: absent fleet-project and cross-adapter comparison | `061a2cb822812c30ea5ab1855a4aebef066c2308` |
| P1.4 | C1-C16 compatibility implementation | `58a6f5d202a15e164849b1dc901e98924da8c480` |

The P1.3 review-fix tree is deliberately separate from its implementation tree. These
anchors identify P1 item evidence only; none is substituted with a phase-close or
bookkeeping commit.
