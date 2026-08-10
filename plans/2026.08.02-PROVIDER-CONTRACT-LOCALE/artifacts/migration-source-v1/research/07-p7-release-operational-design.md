# P7 release and operational design

## Inputs

This synthesis derives from `findings/11-p7-release-acceptance-recon-2026-08-02.md`,
`research/01-target-architecture.md`, `research/04-p4-locale-migration-implementation-design.md`,
`research/05-p5-consumer-migration-design.md`, and
`research/06-p6-health-parity-design.md`. Planned P1–P6 outputs remain execution gates rather than
facts claimed by this authoring pass.

## Four-stage release boundary

P7.1 makes acceptance explicit. Its expected set comes from frozen desired contracts and the
capability manifest; observed rows come from package public outputs and P6.3. Shared semantics are
joined by stable capability ID. Native or unsupported behavior retains provider-qualified
expectations. The bundle is complete even when non-green, but a non-empty blocker set stops release.

P7.2 turns each acceptance invariant and negative case into a permanent repository regression. It
does not repair a semantic defect inline: a failure returns to the owning earlier phase/contract with
a scope-payload. This keeps P7 from silently changing the standard it is supposed to test.

P7.3 is an operations and release-candidate step. Documentation is generated or extended at its
owner, every command is read back through help/check/dry-run/synthetic execution, and the release
manifest cites committed hashes. It updates the single root CHANGELOG but does not version, tag,
push or publish.

P7.4 is cold and adversarial. It recomputes exact sets and hashes, reruns deterministic gates and
checks the brief line by line. Its decision crosswalk denominator is parsed from every current
Decision Log D# immediately before verdict; the committed P7.1 verifier requires exact equality
with one crosswalk row per D# and refuses missing/extra/duplicate/post-snapshot rows. It writes
findings and asks for an Owner verdict; it never fixes what it audits. GREEN authorizes only a
later explicit release operation.

## Execution shape

The phase is sequential: P7.2 consumes P7.1, P7.3 consumes P7.2, and P7.4 consumes the release
candidate. Four items therefore do not satisfy the independent-scope orchestration criterion. Broad
cross-package acceptance/regression/release work is `implementation/high`, manual and full-review;
the final audit is `frontier/xhigh`, manual and cold-start.

## Pre-mortem

| Failure after release | Detection / mitigation | Owner |
|:--|:--|:--|
| One provider's GREEN masks the other's missing row | exact provider/capability/axis sets and non-masking aggregate | P7.1 |
| Provider-native strengths are forced into byte parity | provider-qualified expectation rows from frozen manifest | P7.1 |
| Locale selection leaks between response/plan/diagnostics | vary one surface and prove other two unchanged | P7.2 |
| Repo-local bootstrap makes Codex discovery falsely green | isolated external consumer and explicit SKIP semantics | P7.2 |
| Generated docs drift from capability source | owning generator, source hash, second-write stability and `--check` | P7.3 |
| Release is assembled from dirty or stale evidence | committed manifest, release-tree/worktree separation and cold audit | P7.3/P7.4 |
| Auditor fixes its own finding or waives a blocker | audit is read-only; ATTENTION/RED carries scope-payload and Owner D# | P7.4/Owner |
| A later D# is omitted by a stale final checklist | dynamic Decision Log exact-set crosswalk plus missing/extra/duplicate gate | P7.1/P7.4 |

## Verification

- **RAG:** no new query; all load-bearing decisions are repo-grounded.
- **Unverified → repeat pass:** terminal producer paths/versions/hashes and live exact sets must be
  rebound during execution; any mismatch returns to plan-design.
- **Workarounds/[POSSIBLE-DEFECT]:** none.
