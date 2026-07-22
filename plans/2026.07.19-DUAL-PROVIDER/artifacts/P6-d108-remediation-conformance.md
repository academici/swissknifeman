# P6.11 D108 project-carrier conformance

**Scope:** disposable-root focused implementation evidence. No live carrier was read or
written; no P7.2 action was invoked.

| Check | Result |
|:--|:--|
| existing valid carrier preserves non-provider siblings and provider capability leaves | GREEN |
| `claude-code.enabled=false` becomes `true`; Codex is added as `enabled=true` | GREEN |
| second project-carrier plan is empty | GREEN |
| non-object carrier and non-`swissknifeman` project reject before a writer | GREEN |
| public D108 dry facade passes normalized configured `local_path`, never maind `env.root` | GREEN |
| Claude-only current selection derives the exact planned Claude Code + Codex P5 tuple from the carrier | GREEN |
| foreign public D108 project refuses before the D108 writer | GREEN |
| existing D104 refusal, ordinary unmanaged target and no-write provider regressions | GREEN |
| legacy deploy suite | GREEN |

## Commands

```text
cd packages/maind
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=../..:lib:../harness/lib \
  python3 -m unittest -v tests.test_provider_deploy tests.test_deploy
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  lib/maind/provider_deploy.py lib/maind/provision/deploy.py
git diff --check
```

The focused test command passed `49` tests on the D112 P6.11 retry tree. The carrier
implementation and public-facade regressions use only temporary roots. Full package validation,
release/docs assessment, the independent D108 rollback matrix and all live read-only evidence
remain P6.12/phase gates.
