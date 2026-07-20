# P1 provider compatibility matrix

**Producer:** P1.4 · **Contract:** provider-config v1.0.0 (D70) · **Tree anchor:** item commit recorded in the P1.4 Completion Notes

## Canonical resolver cases

| Case | Input layers | Expected effective selection / outcome | Provenance or diagnostic assertion |
|:--|:--|:--|:--|
| C1 | no operation/project/fleet layers | legacy `claude-code=true`, `codex=false` | both enabled leaves are non-explicit legacy winners; only `PCFG_LEGACY_DEFAULT_APPLIED` |
| C2 | fleet defaults | explicit defaults are applied without a write | no legacy fallback diagnostic |
| C3 | fleet project | fleet-project selection overrides legacy | fleet-project layer is accepted for target project only |
| C4 | project | project selection overrides legacy | project source is `.swissknife.json#/providers` |
| C5 | operation | operation selection overrides legacy | operation source is never persisted |
| C6 | explicit Claude-only | Claude remains enabled and Codex remains legacy-disabled | missing Codex remains distinct from an explicit disable |
| C7 | explicit Codex-only | Claude explicitly disabled, Codex enabled | explicit false is retained as a winning leaf |
| C8 | explicit dual selection | both providers enabled | both provider identities are materialized |
| C9 | fleet defaults plus project false | project explicit false wins | higher-rank project provenance wins |
| C10 | unknown provider | no effective config | `PCFG_UNKNOWN_PROVIDER` |
| C11 | unsupported Codex capability true | no effective config | `PCFG_CAPABILITY_UNSUPPORTED` |
| C12 | non-boolean selection value | no effective config | `PCFG_SCHEMA_INVALID` |
| C13 | unknown provider-selection field | no effective config | `PCFG_UNKNOWN_FIELD` |
| C14 | unknown capability | no effective config | `PCFG_UNKNOWN_CAPABILITY` |
| C15 | extension owned by another provider | no effective config | `PCFG_EXTENSION_PROVIDER_MISMATCH` |
| C16 | duplicate fleet project records | no effective config | `PCFG_DUPLICATE_FLEET_PROJECT`; input remains unchanged |

`core/tests/test_provider_config.py` owns C1–C15 as the table-driven canonical resolver
fixture. `packages/maind/tests/test_config.py` covers C16 through its actual fleet carrier
adapter. The suite also verifies deterministic error ordering, compound map leaf provenance,
and input immutability.

## Legacy carrier no-write evidence

Tests pass only synthetic mappings or `TemporaryDirectory` files. The skiller test loads every
current non-provider `.swissknife.json` key, resolves the legacy result, and compares the input
bytes. The maind test writes a synthetic `config.json`, calls its real loader plus adapter, and
compares the same file bytes. Neither test names the repository root `config.json` nor a consumer
project path.

Protected-path snapshot is captured before and after validation with:

```text
git status --short -- config.json plans/2026.07.18-FOREMAN
sha256sum config.json
find plans/2026.07.18-FOREMAN -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
find /home/vostrikov/projects -mindepth 1 -maxdepth 2 -type f -name config.json -not -path '/home/vostrikov/projects/packages/swissknifeman/config.json' -print | sort
```

The initial repository-root `config.json` SHA-256 is
`52f632bf796a48a2085485299d168954db2c6e1f8571983cafc01c2d4cd379c5`. The FOREMAN tree
aggregate is `18062affa90b37759e8fb858f53dd7bc374310dfe1ff0562a9c83f4109b58802`; its two
pre-existing owner modifications remain baseline dirt and are not changed by P1.4. The external
fleet-root discovery returned no `config.json` candidates under `/home/vostrikov/projects` at the
snapshot anchor. The final post-validation snapshot must exactly match these values and status.
