# P0 clean reproducibility repair

## Scope

This repair replaces only live-input replay for the immutable P0.1/P0.5 evidence. Historical
P0.1/P0.5 findings and journal bytes are read through git objects and are not rewritten.

## Sealed anchors

- P0.1 source tree: `9844f499797faf063aede49b79703c71f7ef666e`; item/bookkeeping:
  `f4d230e6e83aac56ab7fe82a085b7bb18d59d6de` / `d8ac22c04fc4d4219dc95244ee9d181e92553a74`.
- P0.5 source tree: `d8ac22c04fc4d4219dc95244ee9d181e92553a74`; item/bookkeeping:
  `56239e92dfaa3aa7ec51e15727e94783f14c9370` / `566719e2602b2571726c91e72d5f71cec99c441d`.
- Historical finding SHA-256 values remain respectively
  `23f8bccce5fcbfc1841ef0373fad4bf0ed5c341b25b037f797eb3c5695550b88` and
  `39913b25e9dd3a454f311ab69b2e072d117438b1c23c6aa0f1ae54ed4a682996`.

## D64-A sealed external-path correction

P0.1 replay is exactly 53 tracked plugin manifests at source tree `9844f49` plus one sealed
external **path only**:

```text
packages/maind/node_modules/@agentmemory/agentmemory/plugin/.claude-plugin/plugin.json
```

The canonical JSON SHA-256 of that one-element path list is
`d0471d0cbafc3e0889dbf2499493670147bfbb0b8ef83c70998f49b1205c0eb4`. Its provenance is the
immutable P0.1 finding in item anchor `f4d230e`; no content, metadata, node_modules data,
secrets, or extra `config.json` field is committed or read. The helper has no live fallback.

This supersedes only the earlier P0.6 assertion that the 25 redacted project IDs were the sole
external P0.1 snapshot. It does not change runtime/package scope or authorize node_modules.

## Delivery and review attribution

- `9394e19d73f2739bc9c9443fd0a184de15291b48` delivered the owner-approved D63
  shared-package prerequisite: sealed journal-exception v1 and its generated canon/docs.
- `109fda3611749878edf014f2a16ff7169f998aea` delivered the initial P0.6 anchor manifest,
  object-based replay helpers, this repair finding and its index entry.
- Independent item review returned RED: both helpers trusted mutable commit fields and accepted
  unexpected anchor fields; the package prerequisite also emitted an unsafe/muddy diagnostic for
  malformed sidecar field types. No historical evidence or frozen P0 contract was changed.
- `c924fcb2c6ca023dfb7f168c5718ea7fc2fdb443` fixed both helpers with exact recursive shape/type
  checks, canonical per-anchor self-sealing and commit-object existence checks. The post-fix tamper
  matrix rejected all 31 negative probes, including extra fields and changed commit anchors.
- `c8c78bd6c8731f1261d5d103ca557f7c4d062bac` fixed malformed sidecar-type diagnostics and added
  journal/plan-lint regression coverage; the exception remains restricted to exact `friction`.

The final plan-evidence item is the ordered delivery/review/fix chain above plus the commit carrying
this reconciliation. Its terminal SHA is intentionally recorded by the following plan-only
bookkeeping carrier: a commit cannot contain its own hash. This finding does not perform bookkeeping,
change P0.6 status, close P0, or supersede the authoritative RED phase audit.

## Current validation evidence

On the final reconciliation tree (the one-path commit carrying this file):

- both sealed helpers return exit 0 and report object-based P0.1 (`53 tracked + 1 external path`)
  and P0.5 replay with no live fallback;
- `python3 -m py_compile` returns exit 0 for both helpers and task journal/plan-lint modules;
- `bash packages/task/scripts/validate.sh` returns `validate: OK`; its suite runs 189 tests and
  the repository-wide lint has 0 errors (its 76 warnings pre-exist outside this repair scope);
- target `plan-lint --baseline HEAD` returns 0 errors / 1 warning / 0 new: the sole warning is the
  intentionally stale audit `Next` while P0 is reopened, not a P0.6 evidence regression;
- `git diff --check` passes and exact scope is only this finding.

The terminal reconciliation SHA is published in the execution report and then anchored by the
separate plan-only bookkeeping commit.

## Reproduction

```bash
python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-provider-inventory.py --check
python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-command-surface-correction.py --check
python3 packages/task/scripts/plan-lint.py plans/2026.07.19-DUAL-PROVIDER --baseline HEAD
```

The helpers fail closed for a missing tree, malformed anchor, wrong finding/input digest,
changed roots, or any missing/extra/changed sealed external path.
