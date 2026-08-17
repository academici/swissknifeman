# HANDOFF — 2026-08-17 — P7.5–P7.6 complete

**Next:** `task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.7`

P7.5 repaired and validated the exact acceptance/crosswalk/tree interfaces. P7.6
committed only the sealed 37-path candidate as `072f806507c0b2672fb393c6fb15812bbb3cddd6`;
the 107 foreign paths remain unstaged and untouched. D89 remains non-releasable and
`release_authorized=false`.

**Provider-neutral plan-protocol command:**

```text
task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.7
```

**Native Codex command:**

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.02-PROVIDER-CONTRACT-LOCALE P7.7'
```

**Evidence:** `artifacts/P7-remediation-manifest.json` ·
`artifacts/P7-candidate-paths.json` · `artifacts/P7-candidate-integration.json`.
