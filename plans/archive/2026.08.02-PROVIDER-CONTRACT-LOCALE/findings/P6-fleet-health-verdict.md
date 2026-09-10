# P6 fleet health verdict

**Aggregate:** `non-green`  
**Evidence contract:** `provider-health-v1` / `1.0.0`  
**Project set:** 23 sealed P0 projects; 22 live bindings  
**Two-run semantic comparison:** match  
**P7 release authorized:** no

## Verdict

Both fresh read-only scans used the same committed source, frozen health contract, D85 evidence-set
schema, provider manifest, P0 set and P5 convergence inputs. Claude, Codex and shared-plane rows
remain separate. Every project stays non-green because P5 migration is held unresolved; no green
provider or available project masks a required peer.

One sealed project is absent from the current public mAInd registry and is therefore represented by
explicit unavailable rows: `project-1bb1c2eba307e990`. This is evidence, not repair authority.

## Optional integration evidence

Optional non-green projects remain in the exact health scans but are excluded only from
project-scoped release blockers: `project-6fe9a81f902e79a2`.
Required and global blockers remain release-gating.

## Release blockers

### Global

- `P5_ROLLOUT_NOT_AUTHORIZED`

### Required projects

- `MEMORY_CLEANUP_NON_GREEN:project-1bb1c2eba307e990`
- `PROJECT_NON_GREEN:project-014a1283da270bd6`
- `PROJECT_NON_GREEN:project-034bc815af5bcfbb`
- `PROJECT_NON_GREEN:project-1bb1c2eba307e990`
- `PROJECT_NON_GREEN:project-1cf3a711c12e6a9b`
- `PROJECT_NON_GREEN:project-2f270a6fe5f0bbcc`
- `PROJECT_NON_GREEN:project-383351c63aaf37ac`
- `PROJECT_NON_GREEN:project-48590a32ed307abd`
- `PROJECT_NON_GREEN:project-4f583bba1e3d6be8`
- `PROJECT_NON_GREEN:project-62eb4ffd9db923d9`
- `PROJECT_NON_GREEN:project-6fcbd71ebeedc92c`
- `PROJECT_NON_GREEN:project-7ff99b78a82ce1bf`
- `PROJECT_NON_GREEN:project-83c5b3c93ffe31c0`
- `PROJECT_NON_GREEN:project-8c234a131487ede5`
- `PROJECT_NON_GREEN:project-ab471cd0f1c85b97`
- `PROJECT_NON_GREEN:project-ae6cf52cbe90f84b`
- `PROJECT_NON_GREEN:project-b06bcd38ed385da6`
- `PROJECT_NON_GREEN:project-b1b34c916a75d8c9`
- `PROJECT_NON_GREEN:project-b90c0f619b100582`
- `PROJECT_NON_GREEN:project-c9e6c8c25f188930`
- `PROJECT_NON_GREEN:project-cf305f1c831a36e2`
- `PROJECT_NON_GREEN:project-d12b43a6d74056cf`
- `PROJECT_NON_GREEN:project-ffddc862898a8984`
- `PROJECT_UNAVAILABLE:project-1bb1c2eba307e990`


## Privacy and cleanup

The bundle contains stable IDs, states, diagnostics and digests only. It excludes roots, raw command
output, memory text/IDs, settings, environment values, credentials and transcripts. Disposable
memory probes were forgotten for every bound project; the unavailable project has no probe residue.
The exact P0/P5 project-set differences are empty; migrated set is empty and all 13421
P5 action rows remain unresolved.
