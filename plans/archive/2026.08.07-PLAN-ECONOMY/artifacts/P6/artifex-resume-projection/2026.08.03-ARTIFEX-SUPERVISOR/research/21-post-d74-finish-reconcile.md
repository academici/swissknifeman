# Post-D74 cross-phase finish reconcile

## Sources and boundary

This pass reads `brief/08-post-d74-finish.md`, D73–D74, the current Status Board, all seven phase
contracts, every item specification, `research/20-p3.4-successor-contract-design.md`, the P3.4
bridge-conflict finding, the current roadmap/handoff and the append-only journal. It changes only
plan design carriers. No product, provider, package, frozen contract or terminal item artifact is
implemented or rewritten. RAG:— (repo-grounded: the named plan files and current worktree).

The design-budget gate is satisfied (`Design Passes: 8/8` plus recorded remediations), and no phase
contains a skeleton or unresolved clarification marker. The current topology contains 34 items:
18 terminal historical producers and 16 open specifications. Routing and the rebuilt roadmap cover
the same item set exactly once.

## Producer/consumer reconcile

| Producer | Output consumed downstream | Reconcile verdict |
|:--|:--|:--|
| P0.1–P0.5 | baseline/reuse, owner mandate, provider evidence, threat bank and acceptance rubric | terminal inputs remain authoritative; no D74 rewrite |
| P1.1–P1.5 | five frozen v1 contracts and original aggregate | terminal bytes/history remain immutable |
| P1.6 | additive `dispatch-admission-v1`, independent cases/validator, bounded P3 smoke grant and six-contract aggregate | sole new contract producer; must close before P2.6 |
| P2.1–P2.5 | compiler, store, authority, scheduler and provider-free CLI candidate | terminal behavior/history remain authoritative |
| P2.6 | admitted projection, grant-backed authority loading and provider-free `dispatch` seam | sole provider-neutral implementation owner; must close after P1 and before P3.4 |
| P3.1–P3.3 | two pure provider mappings and parity evidence | terminal adapters remain unchanged |
| P3.4 | one bounded fresh-process activity binding and minimized smoke/aggregate evidence | consumes only reclosed P1/P2 outputs; cannot synthesize grant, authority or budgets |
| P4–P6 | assurance, pilots/economics and product-home/operations decisions | original sequential contracts remain valid after the P1.6→P2.6→P3.4 insertion |

Every Required Reads path that is absent today is a declared output of an earlier item. No absent
read lacks a producer, and no consumer precedes its producer. The execution order is therefore
`P1.6 → close P1 → P2.6 → close P2 → P3.4 → close P3 → P4.1…P6.4` after a fresh design audit.

## Coupling hotspots

- P1.6 regenerates only the P1 aggregate manifest/validator around an additive sixth contract; the
  five frozen contract/case/validator sets are protected by an unchanged-bytes gate.
- P2.6 extends the existing `authority.py`, `scheduler.py`, `cli.py`, tests and aggregate
  manifest/validator. It owns the new projection and must leave provider code/processes absent.
- P3.4 adds the runner and provider binding at P2.6's injected activity port. Later P4 repairs may
  touch the same candidate modules only through their already-declared validation-driven repair
  scopes; they do not become new semantic owners.
- P6's dynamic integration surface remains finite because terminal P6.1 must emit and validate the
  exact integration inventory before P6.2 may write.

The feasible set is non-empty: each repeated file has one current semantic owner and later repair
items consume, rather than duplicate, its contract. The rejected shortcut remains provider-local
authority/budget synthesis or mutation of terminal frozen contracts. RAG:— (repo-grounded: D74,
P1.6/P2.6/P3.4 specifications and phase contract blocks).

## Definition-of-Ready sweep

- All phases have explicit Included/Excluded scope, producer/consumer boundaries and no skeletons.
- All 34 items carry the 16 canonical fields, concrete Code Guidance and deterministic Validation.
- Routing covers every item post-line; high/xhigh effort makes every open item `Exec = manual`, and
  no phase meets the independent-scope orchestration criterion.
- D74 and this reconcile cover the only changed contract topology; unresolved owner forks are zero.
- P1.6, P2.6 and P3.4 read their layer-0/1/2 carriers first and preserve terminal histories.
- The prior audit GREEN predates D74 and is not execution authority; a new design audit is the next
  structural gate.

## Final verdict

The post-D74 plan is authoring-ready and cross-phase coherent. D63's earlier 32-item finish verdict
is historical and is superseded for execution routing by the 34-item topology above. The roadmap is
rebuilt last from the current statuses: terminal prerequisites and terminal P0–P3 items are marked
closed, while the first possible producer remains P1.6 only after a fresh literal GREEN design
audit. No item execution occurred in this finish pass.

## Проверка (verification status)

- **RAG:** no new external or staleness-sensitive fact class is used by this verdict; all
  decision-bearing claims were verified from repository files. Prior external provider facts stay
  pinned to their existing findings and are re-measured by their assigned empirical items.
- **Непроверено → ПОВТОРНЫЙ ПРОХОД:** provider smoke, crash/recovery and economic outcomes remain
  deliberately unclaimed until P3.4, P4 and P5 execute.
- **Обходки/[POSSIBLE-DEFECT]:** none. The earlier `maind health --cwd .` failure was CLI misuse;
  worktree-local `packages/maind/bin/maind health --cwd --json` is GREEN in this authoring preflight,
  but it does not substitute for P4.4's candidate-specific hook/security evidence.
