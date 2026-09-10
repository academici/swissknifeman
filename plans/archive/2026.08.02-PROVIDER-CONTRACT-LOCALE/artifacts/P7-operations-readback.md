# P7 operations readback

**Scope:** P7.3 non-mutating operator evidence, captured 2026-08-17 from the repository root.
No provider, consumer, fleet, Brain, tag, push, or publication action was performed.

## Exit classes

| Command | Exit | Readback |
|:--|:--:|:--|
| `python3 scripts/provider-docs.py --write` (twice) | 0 / 0 | Second write was byte-stable: `README.md` `3468283271475fb540b17cb661c5817f247665e368dc50dcaea20242cba04213`; `docs/provider-support.md` `807e6cf2a10f7345aa91dbd289b4617c8efb1be28f71a239c4ce89af6f551395`. |
| `python3 scripts/provider-docs.py --check` | 0 | Generated README block and provider-support page are current. |
| `python3 scripts/test-provider-docs.py` | 0 | Five deterministic checks passed. |
| `packages/harness/bin/harness doctor --provider-audit --json` | 0 | Provider-qualified audit returned the committed catalog and diagnostics; unsupported rows remain explicit rather than inferred green. |
| `packages/skiller/bin/skiller connect --dry-run` | 0 | Claude Code marketplace projection was planned only; no write was requested. |
| `packages/skiller/bin/skiller sync --target . --dry-run` | 1 (expected boundary) | This marketplace project has no `.swissknifeman/config.json` in `mode=vendor`; the command correctly refused vendor sync. Use it only in a selected vendor project. |
| `packages/maind/bin/maind sync --project swissknifeman --dry-run --json` | 0 | The plan reported its provider-qualified non-green/unmanaged and dry rows without applying them. Those rows are diagnostics, not release evidence. |
| `packages/harness/bin/harness instructions plan --target . --provider codex --json` | 0 | All Codex instruction targets were `clean`/`noop`; plan mode wrote nothing. |
| `skiller connect --help`, `skiller sync --help`, `maind sync --help`, `harness instructions --help` | 0 | The documented apply/update/repair surfaces and their explicit authority arguments are present. |
| `bash packages/maind/scripts/validate.sh`, `npm --prefix packages/maind run docs:build`, and aggregate `npm --prefix packages/skiller run docs:build` | 0 / 0 / 0 | After the owner-authorized one-line deploy-link repair, the previously invalidated mAInd and aggregate documentation gates are green. |

## Operational boundary

Use the generated provider matrix to select the desired provider and then run help, plan, check,
or dry-run first. `apply`, `repair`, and `adopt` are separate authority-bearing operations. On a
mismatch, retain the non-green diagnostic, restore only the declared owned preimage or generator
output, then perform readback and a second no-write reconcile. A successful diagnostic evaluator
does not grant release authority.

## Privacy

The evidence retains only command names, exit classes, stable hashes, and public diagnostic
classes. It intentionally excludes raw settings, absolute host paths, credentials, provider
payloads, and unredacted command output.
