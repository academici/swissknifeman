# How work flows: diagrams

The pictures of this page follow one piece of work from the plan to its commit: who takes it, which roles touch it,
where the conductor decides and where it stops. The text under each picture says what it shows; the reference of each
step stays in [Conductor](conductor.md), the contract of the plan side in [Work source](work-source.md).

## 1. The parts and how they talk

```mermaid
flowchart LR
  owner([Owner / observer agent])
  subgraph planner [planner: the plan]
    plan[(plans/ID/plan.json)]
    planpy[plan.py]
  end
  subgraph bridge [bridges/planner-orch]
    ws[work-source plugin]
  end
  subgraph orch [orch]
    conductor[conductor<br/>conduct.py]
    source[orch.py source ...]
    catalog[launch catalog<br/>run-policy packs]
  end
  subgraph roles [roles: child processes]
    scout[context-scout]
    executor[executor]
    reviewer[reviewer]
    triager[triager]
    registrar[registrar]
  end
  git[(git: tree and commits)]

  owner -- "run --plan P --items A B" --> conductor
  conductor -- "claim / brief / register / commit" --> source
  source -- "work-source/v1" --> ws
  ws --> planpy --> plan
  conductor -- "routes" --> catalog
  catalog --> scout & executor & reviewer & triager & registrar
  executor -- "edits" --> git
  conductor -- "changed paths, diff" --> git
```

The conductor decides nothing by itself: it branches on exit codes, on the closed results of the roles
(`schemas/conductor/v1`) and on the limits of the run options. It never reads the plan: every plan operation goes
through `orch.py source …`, which calls the work-source plugin of the bridge, which calls `plan.py`. Every role is a
child process started from the launch catalog; models are used only in these narrow roles.

## 2. One piece, end to end

```mermaid
sequenceDiagram
  autonumber
  participant C as Conductor
  participant W as Work source (planner via bridge)
  participant S as Scout
  participant E as Executor
  participant K as Checks
  participant R as Reviewer
  participant T as Triager
  participant G as git

  C->>W: claim (run id, actor, scenario)
  W-->>C: claimed: ref, scenario, route, attempt_id
  C->>W: brief
  W-->>C: execution-input (digest, base revision)
  C->>W: prepare
  W-->>C: launch-plan of the pack (routes)
  opt pack has a scout stage
    C->>S: input
    S-->>C: context map (+ expected write set)
  end
  loop executor rounds
    C->>E: input, context map, rules, correction package
    E->>G: edit files
    E-->>C: stage-report (done | done_with_deviations | blocked)
    C->>G: changed paths (git, not the report)
    C->>K: acceptance and impact checks
    K-->>C: exit codes + evidence files
  end
  opt review by pack, risk score or batch strategy
    C->>R: diff against base + check results
    R-->>C: review-findings
    C->>T: findings
    T-->>C: confirmed (with correction package) / rejected (with reason)
  end
  C->>W: register (status, report, evidence)
  W-->>C: recorded + gate verdict
  C->>W: commit (changed paths + artifacts)
  W->>G: commit
```

Every numbered step has a key in `state.json`; a step that closed is never run again by `resume` (it prints
`stage.skip`). What changed is always read from git after each executor round; the union over the rounds becomes
`changed_paths` of the report and the paths of the commit.

## 3. The plan side: life of an item

```mermaid
stateDiagram-v2
  [*] --> todo
  todo --> in_progress: claim (start)
  in_progress --> done: register green
  in_progress --> done_with_deviations: register + deviation issue
  in_progress --> blocked: register blocked (escalation)
  in_progress --> todo: release (no work began)
  blocked --> in_progress: reopen, then resume --retry
  done --> in_progress: reopen (owner)
  todo --> skipped: accepted decision
  done --> [*]
  done_with_deviations --> [*]
  skipped --> [*]
```

`claim` starts the item in the plan (`in_progress`); only `register` ends it. A run that stopped before any executor
round gives the claim back (`release`, `CLAIM_RELEASED`). A blocked item does not satisfy dependencies; a dependency
that is in progress in the same batch counts as met.

## 4. Inside the piece: rounds, corrections and limits

```mermaid
flowchart TD
  start([executor round N]) --> report{stage-report<br/>valid?}
  report -- "no" --> heal[heal by rule<br/>RESULT_HEALED]
  heal --> fixer{still invalid?}
  fixer -- "yes" --> repair[report-fixer<br/>RESULT_REPAIRED]
  repair --> again{still invalid?}
  again -- "yes" --> retry[repeat the role<br/>limits.retries]
  retry --> start
  again -- "no" --> paths
  fixer -- "no" --> paths
  report -- "yes" --> blockedq{status blocked?}
  blockedq -- "yes" --> regb[register blocked]
  blockedq -- "no" --> paths[changed paths from git<br/>outside write set: deviation or block]
  paths --> checks[checks of the round]
  checks --> red{red?}
  red -- "yes" --> fixes{check_fixes left<br/>or progress below ceiling?}
  fixes -- "yes" --> corr1[correction round<br/>with the red checks] --> start
  fixes -- "no" --> regc[blocked CHECKS_RED]
  red -- "no" --> review{review this piece?}
  review -- "no" --> reg[register + commit]
  review -- "yes" --> rv[review → triage]
  rv --> conf{confirmed at or above<br/>correct_min_severity?}
  conf -- "no" --> reg
  conf -- "yes" --> rounds{corrections and rounds left<br/>or progress below ceiling?}
  rounds -- "yes" --> corr2[correction round<br/>with the findings] --> start
  rounds -- "no" --> regr[blocked REVIEW_LIMIT]
```

Limits are targets, not walls: past a target a round still runs while the last correction made progress (other or
fewer red checks, fewer findings), up to `limits.ceiling_factor` times the target, and every such round prints
`LIMIT_OVER` and leaves a plan note. A correction that changed nothing, or the ceiling, blocks the piece. Findings
below `review.correct_min_severity` (default `Major`) are not corrected: they travel as notes in the report.

## 5. Does this piece get a review?

```mermaid
flowchart TD
  a[piece finished its rounds] --> batch{batch with<br/>review.strategy?}
  batch -- "groups / single / none" --> group[no review of its own<br/>the group is read after its last piece]
  batch -- "each or a single piece" --> pack{pack has a review stage?}
  pack -- "yes" --> rev[review → triage → correction]
  pack -- "no" --> off{review.dynamic off<br/>or review_rounds 0?}
  off -- "yes" --> none[no review]
  off -- "no" --> score[risk.score: paths, schema, security,<br/>shared, diff size, red first, deviation,<br/>outside write set, executor asks]
  score --> crit{critical feature<br/>e.g. security?}
  crit -- "yes" --> added[REVIEW_ADDED] --> rev
  crit -- "no" --> thr{score ≥ dynamic_threshold<br/>default 60?}
  thr -- "yes" --> added
  thr -- "no" --> none
```

The risk score is a pure function of facts read from git and from the closed results; no model is asked. A change of
the code that confines the roles (sandbox, launch catalog, run policies, hooks, CI workflows, `install.sh`) is
`security`, which is critical: it gets a review whatever the score.

## 6. A batch: one session, pieces in order, a common review

```mermaid
sequenceDiagram
  participant C as Conductor
  participant W as Work source
  participant E as Executor (one shared session)
  participant R as Reviewer
  C->>W: claim --batch A, B, C (all in progress)
  C->>C: review strategy (strategist or rules): groups [A,B] [C]
  loop each piece in order
    C->>E: piece X (the session already knows the batch)
    E-->>C: report X
    C->>C: checks X, register X, commit X
  end
  Note over C,R: after the last piece of each group
  C->>R: commits of group [A,B] (production diff)
  R-->>C: ## Findings ... or none
  alt Blocker or Major found
    C->>C: group-review-1.followup.json
    Note right of C: run --input followup --commit corrects them in a commit of its own
  else malformed reply or no commit
    C->>C: GROUP_REVIEW_FAILED (never a clean review)
  end
```

`--batch` is the default for `--items A B C`: one executor session carries the pieces in order and builds each on the
earlier ones; checks, register and commit stay per piece. A stop gives no piece back: all stay in progress and
`resume` goes on.

## 7. Questions of the executor and the advisor

```mermaid
flowchart TD
  q[stage-report has a question] --> blocking{blocking?}
  blocking -- "no" --> assume[assumption issue in the report<br/>work goes on]
  blocking -- "yes" --> mode{conductor.questions}
  mode -- "queue" --> queued[blocked QUESTION<br/>orch conduct answer → resume --retry]
  mode -- "deny" --> denied[blocked QUESTION_DENIED]
  mode -- "defaults" --> def{has a default<br/>not used before?}
  def -- "yes" --> once[answered once by policy<br/>executor round asked again]
  def -- "no" --> queued
  mode -- "advisor" --> adv[advisor: one opinion]
  adv --> gate{needs_owner or a<br/>human_gate category?}
  gate -- "yes" --> queued
  gate -- "no" --> applied[answered by advisor<br/>round asked again with # Answers]
```

A question is a saved decision bound to the input it was asked on, never a waiting process. An answer to an input that
changed since is `QUESTION_STALE` and the question is asked again. The advisor is also asked, when enabled, for red
checks past `check_fixes` and for a Blocker or Major finding the triager rejected.

## 8. When a provider fails

```mermaid
flowchart TD
  f[role failed at the provider] --> cls{failure class}
  cls -- "authentication / authorization" --> auth[stop PROVIDER_AUTH / AUTHZ<br/>never repeated]
  cls -- "invalid_request / content_policy" --> ref[stop PROVIDER_REFUSED]
  cls -- "context_limit" --> ctx[stop PROVIDER_CONTEXT]
  cls -- "quota / rate_limit" --> reset{reset within<br/>provider_wait_max_s?}
  reset -- "yes" --> wait[PROVIDER_WAIT, then repeat]
  reset -- "no / unknown" --> fb{admissible<br/>fallback route?}
  fb -- "yes" --> fall[ROUTE_FALLBACK]
  fb -- "no" --> quota[stop PROVIDER_QUOTA<br/>resume after the reset]
  cls -- "transient" --> rep[repeat within limits.retries]
```

An exhausted account quota is also recorded as a capacity gate of the machine, so the next run does not start a role on
that provider before the reset (`orch conduct gates`).

## 9. Stop and recovery

```mermaid
flowchart LR
  stop([run stopped]) --> why{why}
  why -- "provider quota, disk low, timeout,<br/>interrupted (130)" --> resume[resume --run RUN]
  why -- "piece blocked<br/>(checks red, review limit, question)" --> fix[fix the plan / answer] --> retry[reopen, then<br/>resume --run RUN --retry ITEM]
  why -- "dirty tree with an earlier attempt" --> adopt[run --adopt]
  why -- "finished by hand outside the conductor" --> settle[settle --outcome ... --reason ...]
  why -- "stopped before any work" --> release[release --run RUN --all]
  why -- "STATE_CORRUPT" --> inspect[inspect the named file]
```

| State | Command | What is kept |
| --- | --- | --- |
| provider quota | `resume` after the reset | every closed step; no new attempt |
| checks red, review limit | amend the plan, `reopen`, `resume --retry ITEM` | earlier rounds, logs and the work in the tree |
| disk low | free the space, `resume` | the provider side effects already made |
| killed or interrupted | `resume` | the claim of the run (no second owner) |
| finished by hand | `settle` | the journal keeps the reason |
| no work began | `release --all` | nothing to keep; a new run can claim |

A closed step returns its recorded result; the JSON files of a run are written crash-safely (temp file, `fsync`,
rename, `fsync` of the folder), and a torn one stops with `STATE_CORRUPT` naming the file instead of being reset.

## 10. Where a setting comes from

```mermaid
flowchart LR
  d[schema defaults] --> m[machine<br/>~/.config/swissknifeman/config.toml]
  m --> p[project<br/>.swissknifeman/config.toml]
  p --> e[environment<br/>SKM_ORCH_*]
  e --> i[--config FILE]
  i --> fl[flags<br/>--debug, ...]
  fl --> eff([effective orch settings<br/>config_digest in run.json])
```

The most specific layer wins (`swissknifeman config explain orch KEY` names it). The run options of a piece have their own
ladder (defaults → conductor config → pack → plan → phase → item → `--options`), with one floor: a layer of the work
source may tighten the isolation (sandbox, fence, `isolate_roles`) but never loosen it, and never add `extra_paths`
(`OPTIONS_UNTRUSTED`).

## 11. Debug mode

```mermaid
sequenceDiagram
  participant O as Observer agent
  participant C as Conductor
  participant D as run/debug/
  O->>C: run --plan P --items A B (--debug, or [orch] debug = true)
  C->>C: run.start
  C->>D: journal.md, metrics.md, findings.md (once)
  C-->>O: DEBUG_MODE: the layer that set it, protocol orch-debug, journal folder
  O->>O: follow the orch-debug protocol (estimate, watch beacons, measure)
  O->>D: journal entries, metrics rows, findings
  Note over C: roles, prompts and decisions are the same with the mode on or off
```

See [Debug mode](conductor.md#debug-mode) for the three levels (machine, project, `--debug`).
