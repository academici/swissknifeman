# P7 postarchive continuation design

## Inputs and synthesis boundary

This synthesis consumes the owner refinement in `brief/01-refinements.md`, raw working-tree
inventory `findings/29-P7-postarchive-working-tree-inventory.md`, exact baseline
`artifacts/P7/working-tree-baseline-v1.json`, and the hash/disposition tables under
`artifacts/roadmap-snapshots/`. No external facts support the design. RAG:— (repo-grounded:
the named carriers).

## Decomposition

| Item | Stable product boundary | Why it is a separate fresh session |
|:--|:--|:--|
| P7.0 | backward-compatible terminal/audit lint activation | ordinary Task dispatch is fail-closed by the candidate linter itself; a manual bootstrap fresh root must repair the admission seam without rewriting history |
| P7.1 | route provenance, run receipt, journal terminal admission and generated state contract | it establishes the execution/terminal primitives consumed by every later slice; mixing delivery or prose projections would hide which invariant failed |
| P7.2 | subject-aware delivery plus audit/terminal lint enforcement | it consumes P7.1 journal/state semantics and owns a separate fail-closed public diagnostic surface |
| P7.3 | scope-aware block reducer, phase-audit terminal policy and material-only candidate fingerprint | schema/rubric/reducer safety has a distinct regression corpus and must not be coupled to generated provider output |
| P7.4 | canonical Task commands, plan-protocol, package docs and owning provider/registry generators | generated carriers are updated only after runtime semantics are committed; Task and Skiller source-of-truth rules meet here |
| P7.5 | root roadmap disposition, `[Unreleased]`, full Task/Skiller/docs gates and archive readiness | staged removals and aggregate gates are accepted only after the four product slices are stable; this item does not mint a release |

All rows are `solo` because the owner requires separate fresh sessions and each row ends in an
explicit product/bookkeeping commit boundary. P7.0 is a manual bootstrap exception documented in
finding 30; all later rows use normal Task dispatch. The sequence is strict: P7.1 depends on P7.0; P7.2 depends on P7.1;
P7.4 depends on P7.1–P7.3; P7.5 consumes all preceding terminal states. RAG:— (repo-grounded:
`plan.md` Routing, working-tree groups in the baseline artifact).

## Acceptance topology

```text
P7.0 lint admission
  → P7.1 runtime core
  → P7.2 delivery/lint
  → P7.3 audit/block safety
  → P7.4 canon + owning generators
  → P7.5 aggregate validation + roadmap closeout
  → task:plan-audit ... P7
  → task:plan-close ... P7
  → task:plan-close archive ...
```

Each item validates the current candidate rather than assuming the existing diff is correct.
Focused tests are mandatory before its product commit. P7.4 regenerates, never hand-edits,
provider/registry outputs. P7.5 repeats package and docs gates on the committed union and repairs
only bounded mismatches within the declared P7 path set. Red required validation stays
nonterminal. RAG:— (repo-grounded: release-discipline, docs-maintenance, Task plan-protocol).

## Roadmap and release verdict

- The two still-active features (`plan-views history` and authoritative batch admission) are
  preserved as roadmap work and excluded from P7 code scope.
- Partial records retain only their measured residue; historical snapshots remain in plan
  artifacts.
- Current substantive changes remain under root `CHANGELOG.md [Unreleased]`.
- No version cut, annotated tag, push, GitHub release or registered-project rollout is authorized.
- Documentation is required because Task execution/audit/terminal process semantics changed;
  canonical package docs and the umbrella build are therefore P7.4/P7.5 acceptance, not an
  optional follow-up. RAG:— (repo-grounded: `CHANGELOG.md`, `packages/task/docs/`,
  release-discipline and docs-maintenance).

## Owner-intent traceability

| Owner thought | Carrier / enforcement |
|:--|:--|
| Continue the archived plan from current working tree | D32, baseline artifact, P7.0–P7.5 |
| Use roadmap snapshots as evidence | finding 29, snapshot README/catalog, P7.5 hash gate |
| Separate fresh sessions | six `solo` Routing rows and per-item cold-start handoffs |
| Execute nothing in design session | every product validation/commit remains in P7 items; design runs only plan generators/lint |
| Return plan to archive after full close | phase contract and explicit audit → close → archive chain |
