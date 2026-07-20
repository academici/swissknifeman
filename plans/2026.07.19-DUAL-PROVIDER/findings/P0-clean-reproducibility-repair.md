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

## D64 sealed external-path correction

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

## Commit and validation attribution

- Canonical prerequisite: `9394e19d73f2739bc9c9443fd0a184de15291b48`.
- Plan-evidence item commit: recorded by the following plan-only bookkeeping commit.
- Bookkeeping commit: recorded by the following plan-only bookkeeping commit.
- Clean detached item/bookkeeping replay and canonical `0 ERROR / 0 WARN — new 0` lint results
  are recorded by that same bookkeeping carrier after both committed trees exist.

## Reproduction

```bash
python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-provider-inventory.py --check
python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-command-surface-correction.py --check
python3 packages/task/scripts/plan-lint.py plans/2026.07.19-DUAL-PROVIDER --baseline HEAD
```

The helpers fail closed for a missing tree, malformed anchor, wrong finding/input digest,
changed roots, or any missing/extra/changed sealed external path.
