# P7 release and acceptance repository recon — 2026-08-02

## Scope and method

Read-only recon for `2026.08.02-PROVIDER-CONTRACT-LOCALE P7`. Sources are repository code,
tests, docs, the archived `2026.07.19-DUAL-PROVIDER` release phase, and this plan's P1–P6
design carriers. No package, provider, fleet, Brain or user-home state was mutated.

## Observed acceptance surfaces

- `configs/provider-capabilities.json` and generated `docs/provider-support.md` already separate
  semantic capability IDs from provider support levels, native bindings, limitations and evidence.
- Provider-focused suites exist across core, Skiller, Task, Harness, mAInd and Analyst. The Skiller
  clean-consumer test explicitly distinguishes repository-local discovery from a real Codex plugin
  publication chain and reports binary absence as SKIP rather than GREEN.
- Each package owns a `scripts/validate.sh`; provider docs have a named generator/checker; the root
  has one `CHANGELOG.md`. These are the existing release surfaces P7 must compose, not replace.
- P6 defines project health as an exact-set composition of package-owned evidence. Therefore P7
  cannot use package conformance or one successful provider as a substitute for P6.3 fleet rows.
- The archived dual-provider P7 demonstrates recurring failure classes: provider-native discovery
  can be masked by repository bootstrap state; generated/reference docs need source provenance;
  cleanup requires positive ownership and rollback; a release audit must be independent.

## Gaps P7 must close

1. No plan-local carrier yet joins the frozen desired capability set, provider-native expectations,
   P6 exact project/provider rows, locale surfaces and release blockers.
2. Current tests are package-owned and valuable, but P7 must map their coverage to the new P1–P6
   contracts and add distinguishing regressions rather than infer coverage from filenames.
3. Existing docs describe provider support, development and multi-provider distribution in separate
   places; P7 must make the operator sequence, migration/rollback boundary and release state coherent
   without hand-editing generated output.
4. A release candidate needs a committed manifest and cold audit; tag/push/publish are not implicit
   consequences of green validation.

## Verification status

- **RAG:** none; no external current fact is load-bearing.
- **Repository evidence:** high confidence, read 2026-08-02 from the paths named above and P1–P6.
- **Unverified → repeat pass:** terminal P1–P6 files, versions, hashes and live provider/fleet rows do
  not exist yet; P7 execution must rebind them and stop on mismatch.
- **Workarounds/[POSSIBLE-DEFECT]:** none.
