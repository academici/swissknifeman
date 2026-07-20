# P1 protected-path fixture evidence

**Producer:** P1.5 · **Gate:** G02 · **Contract:** provider-config v1.0.0 (D70)

## Claim and boundary

The P1 execution paths do not write their supplied synthetic protected carriers. This is a
fixture-backed property only; it does not observe, hash, discover, or make a claim about mutable
owner state.

Each focused test builds all carriers from byte literals committed with the test below one
`TemporaryDirectory`:

| Execution path | Actual call | Protected carriers checked byte-for-byte |
|:--|:--|:--|
| core | `resolve_provider_config` | repository config, protected-plan sentinel, external-fleet config sentinel |
| skiller | `load_config` then `resolve_provider_config` | project config, protected-plan sentinel, external-fleet config sentinel |
| maind | `load_config` then `resolve_provider_config` | repository config, protected-plan sentinel, external-fleet config sentinel |

The canonical C1–C15 resolver table remains in `core/tests/test_provider_config.py`; C16 remains
the real maind fleet-carrier adapter case in `packages/maind/tests/test_config.py`. The no-write
tests add before/after assertions around these real execution paths and do not mock the resolver
or filesystem helpers.

## Committed-tree replay

Run this from a detached worktree whose `HEAD` is the P1.5 item commit. The commands use only the
checked-out tree and create all tested carrier paths inside test-owned temporary directories.

```bash
git worktree add --detach "$(mktemp -d)" "$(git rev-parse --verify HEAD)"
PYTHONPATH=. python3 -m unittest core.tests.test_provider_config
PYTHONPATH=.:packages/skiller/lib python3 -m unittest discover -s packages/skiller/tests -p test_provider_config.py
PYTHONPATH=.:packages/maind/lib:packages/skiller/lib python3 -m unittest discover -s packages/maind/tests -p test_config.py
```

Repeat the three commands once. Every run must pass; every focused no-write assertion performs
the byte comparison itself. This replay contains no ambient-root discovery and no live-path
snapshot procedure.
