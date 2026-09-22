# P1 final report

## Release result

Prepared local candidate `v0.24.1` at the final plan commit; no tag, push or GitHub Release was created. Task remains independently owned at `0.24.0` and is coherent in Claude/Codex manifests, Codex/Cursor publication locks, provider lock and `releases/v0.24.1.json`. maind is `0.4.4`, analyst `0.2.3`, harness `0.5.6`, skiller `0.17.11`.

The attestation now separates snapshot byte consistency, expected unit freshness and provider-surface coherence. The regression reproduces the old circular false green. The post-tag `release-fleet` workflow validates the tag, updates all enabled projects, performs readback, and prunes only unreferenced exact-known caches.

## Project/provider/surface matrix

`✓` means selected and delivered; `A` is an explicit attention item; `B` is owner-blocked. Skills use marketplace/native delivery for all three providers. Root instruction projections are clean for Claude/Codex/Cursor.

| Project | Claude | Codex | Cursor | Skills | MCP | Hooks | Instructions | Agents | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| agelto | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10 | GREEN |
| diabox | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 0 | GREEN |
| flexcrm | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10 | GREEN |
| axiomaerpsdk | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 3 | GREEN |
| azguard | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 14 | GREEN |
| botkit | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 11 | GREEN |
| vaulter | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 11 | GREEN |
| swissknifeman | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 6 | GREEN |
| axiomastudio | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | 0 | GREEN |
| corex | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 11 | GREEN |
| memster | ✓ | ✓ | ✓ | A | ✓ | ✓ | ✓ | 10 | ATTENTION |
| cms | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | A | 8 | ATTENTION |
| edufy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10 | GREEN |
| vintera | ✓ | ✓ | ✓ | A | ✓ | ✓ | n/a | 0 | ATTENTION |
| dterema | ✓ | ✓ | ✓ | A | ✓ | ✓ | A | 17 | ATTENTION |
| dterema-app | ✓ | ✓ | ✓ | A | ✓ | ✓ | A | 5 | ATTENTION |
| sibintek-insiders | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10 | GREEN |
| sova | ✓ | ✓ | ✓ | A | ✓ | ✓ | A | 10 | ATTENTION |
| chatom | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 8 | GREEN |
| perplexity-web-mcp | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | 0 | GREEN |
| loqum | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | 0 | GREEN |
| brain | ✓ | ✓ | ✓ | A | ✓ | ✓ | n/a | 0 | ATTENTION |
| agentools | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | 0 | GREEN |
| themeon | ✓ | ✓ | ✓ | A | B | ✓ | n/a | 0 | BLOCKED |

Themeon is blocked at `.mcp.json`, `.codex/config.toml` and `.cursor/mcp.json`: all three are unmanaged and differ from the maind render. Adoption requires an owner decision; repair intentionally did not overwrite them.

## Final metrics

| Project | skills | Claude tokens | Codex/Cursor chars | tier-0 | tier-1 | tier-2 | first turn | MCP | hooks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| agelto | 53 | 2,178 | 7,250 | 1,938 | 62,746 | 112,532 | 7,725 | 3 | 2 |
| diabox | 26 | 1,439 | 4,814 | 1,183 | 32,071 | 44,030 | 10,339 | 3 | 2 |
| flexcrm | 63 | 2,297 | 7,630 | 2,103 | 68,224 | 124,518 | 8,164 | 3 | 2 |
| axiomaerpsdk | 38 | 2,242 | 7,505 | 1,613 | 44,333 | 59,307 | 6,439 | 2 | 2 |
| azguard | 56 | 2,329 | 7,754 | 2,011 | 58,806 | 100,589 | 7,852 | 3 | 3 |
| botkit | 56 | 2,329 | 7,754 | 2,011 | 58,806 | 100,589 | 5,837 | 3 | 2 |
| vaulter/corex | 57 | 2,118 | 7,379 | — | — | — | 5,724 / 4,778 | 3 | 2 |
| swissknifeman/axiomastudio | 35 | 1,665 | 6,685 | — | — | — | 4,451 / 2,622 | 2 | 2 |
| memster | 86 | 4,286 | 14,314 | — | — | — | 7,235 | 3 | 2 |
| cms | 56 | 2,329 | 7,754 | 2,011 | 58,806 | 100,589 | 18,026 | 3 | 2 |
| edufy/insiders | 41 | 1,594 | 5,297 | — | — | — | 4,539 / 5,101 | 3 / 4 | 2 |
| vintera/dterema-app | 73 | 3,922 | 13,115 | — | — | — | 12,059 / 9,819 | 2 / 3 | 2 |
| dterema/sova | 80 | 3,928 | 13,118 | — | — | — | 7,140 / 25,801 | 3 / 2 | 2 / 1 |
| chatom | 45 | 1,776 | 5,904 | — | — | — | 5,113 | 3 | 2 |
| perplexity-web-mcp | 31 | 1,605 | 5,358 | — | — | — | 2,573 | 2 | 2 |
| loqum | 24 | 1,561 | 5,238 | — | — | — | 3,970 | 2 | 2 |
| brain | 65 | 3,894 | 13,046 | — | — | — | 12,257 | 2 | 2 |
| agentools | 16 | 800 | 2,678 | — | — | — | 2,906 | 3 | 2 |
| themeon | 71 | 3,859 | 12,907 | — | — | — | 5,767 | 3 | 2 |

Exact per-project tier data is retained in `/tmp/fleet-post-metrics.json`; the three projects changed for budget evidence are fully shown above. Azguard fell from 72 to 56 skills, 10,448 to 7,754 listing chars and 8,425 to 7,852 first-turn tokens. Botkit and cms received the same duplicate `oss-dev`/`system` removal. Seven domain-heavy projects remain above 8,000 because removing their frontend/backend/architecture/knowledge skills lacked ownership evidence; they remain ATTENTION.

Physical delivery fell from 9,983 files / 30,436,737 bytes to 7,698 / 23,337,372: 2,285 files and 7,099,365 bytes removed. The six legacy Claude trees lost 341 managed skills; 138 remaining files are project-local or maind-managed and were preserved.

## Gates and blockers

- GREEN: Task generator `--check`, skiller registry `--check`, focused skiller 127 tests, focused maind sync 47 tests, release attestation/transition, `verify-tag.py v0.24.1`, version coherence, vendor drift, provider distribution, root three-provider instruction check, `maind projects status`, `maind verify`, MCP audit.
- KNOWN ENVIRONMENT FAILURE: full skiller suite 718/719; installed `codex-cli 0.155.1` does not discover `task-plan-run` in the isolated consumer acceptance test.
- KNOWN CONFORMANCE FAILURE: full maind suite 574/575; temporary public conformance fixture is not connected when instruction provisioning runs.
- BLOCKED: themeon MCP adoption, exact files listed above.
- ATTENTION: `maind sync --all --dry-run` returns non-zero for themeon and still labels 83 successful wrapper invocations changed because `changed=rc==0`. The new release workflow therefore fails closed instead of reporting idempotence.
- PENDING EXPLICIT APPROVAL: create local `v0.24.1` tag at final `HEAD`, then run `./bin/swissknifeman release-fleet v0.24.1`. That step updates installed provider caches and safely prunes exact-known superseded caches. Push and GitHub Release remain separate actions.
