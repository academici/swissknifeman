# HANDOFF — 2026-07-23 — after P7.4

**Next:** Owner resolution only: P7.4 ATTENTION keeps FOREMAN closed; authorize or decline the
bounded P7.3 evidence-only correction. Per D126, this handoff intentionally contains no launch
block.

**Done:** P7.4 evidence commits `ff4b89c3` / `f1998246` independently reproduced the full
functional release bundle and close artifact hygiene. Capability/provider/instruction exact
sets, public Claude/Codex apply/noop/repair,
frozen hashes, D123 rollback, privacy, protected paths and package/core tests are GREEN. Target
plan-lint has the exact two D126 no-launch errors and zero new findings.

**Remaining:** The literal verdict is `ATTENTION`, not GREEN. P7.3's committed cleanup evidence
says `.agents/skills/**` has `16` tracked `agents/openai.yaml`; `git ls-tree` proves `17` at both
P7.3 item commit `d43f9549` and P7.4 baseline `b8e2c12a`. The aggregate `.agents` hash matches
and no unsafe cleanup occurred, but the inaccurate provenance count forbids the release gate.

**Sources of truth:** `artifacts/P7-release-audit.md`; `phases/P7.md` P7.4 Completion Notes;
`artifacts/P7-bootstrap-cleanup.md`; `artifacts/P7-release-manifest.md`; D126 in `plan.md`.

**Open risks:** FOREMAN, fleet, tag, push, publication and cleanup remain closed. The only
bounded proposal is an owner-authorized P7.3 evidence correction (`16` → `17`) plus independent
ownership/hash recheck and a later fresh P7.4. This session authorizes and executes none of them.
Unrelated dirty `AGENTS.md` and `.serena/project.yml` remain excluded.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: any bootstrap removal still requires matching managed provenance and dual-provider
  without-file smoke; no deletion is open.
- open_questions: Owner acceptance or authorization of the bounded P7.3 evidence-only correction.
