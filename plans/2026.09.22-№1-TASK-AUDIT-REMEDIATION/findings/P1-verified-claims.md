# P1 verified claim ledger

## Verification frame

- Repository commit: `8ee2f718d130876ef4eb05088a622d594b7bcebd` (`main`).
- Runtime: Python `3.12.3`; Node `v24.12.0`.
- The pre-run worktree was already dirty in Harness, Skiller, Task, root
  documentation, roadmap and this untracked plan. Those paths are a preserved
  baseline, not P1 evidence and not P1 output.
- Production callers and existing tests were inspected before probing. The local
  reproducer used direct library calls and CLI subprocesses against the committed
  files, with all mutable fixtures under temporary directories. It returned the
  17 expected distinguishing results; no product or consumer file was written.
- Severity means reachable impact in the current repository, not the audit's
  hypothetical maximum. `High` blocks a trustworthy Task release; `Medium`
  requires repair but has a narrower precondition or reconstructable consequence.
  None of the reproduced paths establishes a current P0/critical impact.

## Evidence registry

Local evidence:

- `L-CALLERS`: symbol/caller/test scan of `task_contract.py`,
  `plan_context.py`, `plan_authority.py`, `journal.py`, `plan_decisions.py`,
  `plan_projection.py`, both route adapters, the five corresponding test modules,
  and `.github/workflows/test.yml`.
- `L-PROBE`: one temporary-directory Python harness at the pinned commit. Its
  discriminators were: CLI exit status; empty/tampered chunk acceptance; forged
  provider-state materialization; fabricated completed prefix; declared-only
  validation; injected view-build failure; unrelated proposed decision; raw
  transcript privacy declaration; external input disappearance; repeated
  authorization/response without stores; claimed-vs-observed authority; a
  synchronized two-writer terminal barrier plus malformed history; workflow
  step/path inventory; missing owner digest; invalid metrics; impossible date;
  and instrumented `fsync`/symlink checks.
- `L-LINES`: current anchors include `plan_context.py:149`,
  `task_contract.py:312,773,910,1130,1274,1387,1533,1565`,
  `plan_authority.py:251,284,339`, `journal.py:167,309,458`,
  `plan_decisions.py:119`, `plan_projection.py:67`, and
  `.github/workflows/test.yml:27-47`.

Perplexity second-opinion records (fresh queries, never used as authority):

- `PPLX-G1`: contract/context/batch. Confirmed the mechanisms; rated the CLI
  status contextual rather than intrinsically critical and required content-bound
  attestations and derived completion state.
- `PPLX-G2`: owner attestation/authority. Distinguished same-principal workflow
  evidence from an authentication boundary; recommended prepare/verify/activate,
  durable replay state, observed claims and one canonical action envelope.
- `PPLX-G3`: journal/durability. Recommended accepted current scoped exceptions,
  one lock domain, fail-closed corrupt history, strict RFC 3339/finite metrics and
  calendar parsing.
- `PPLX-G4`: privacy/portability. Classified untrusted path escape as high and
  local-only use as medium; recommended a frozen policy, logical names, canonical
  containment and symlink/special-file refusal.
- `PPLX-G5`: CI/projection. Rated omission of shipped critical runtime from CI as
  high and projection durability as medium/high; distinguished atomic rename from
  crash durability.

Ordinary-search primary sources:

- `OS-01`: [SLSA source requirements](https://slsa.dev/spec/v1.2/source-requirements)
  and [verification summary](https://slsa.dev/spec/v1.2/verification_summary) bind
  a verified statement to subject, policy and input digests.
- `OS-02`: [RFC 9449](https://www.rfc-editor.org/info/rfc9449/) requires binding a
  proof to its request and describes nonce/unique-ID replay controls.
- `OS-03`: [CWE-345](https://cwe.mitre.org/data/definitions/345) distinguishes
  possession/integrity of bytes from verification of their origin.
- `OS-04`: [Python `os`](https://docs.python.org/3/library/os.html#os.fsync)
  documents `fsync`; `replace` supplies rename semantics, not the omitted file and
  directory synchronization protocol.
- `OS-05`: [Python `datetime`](https://docs.python.org/3/library/datetime.html#datetime.date.fromisoformat)
  provides calendar-valid ISO parsing; [Python `json`](https://docs.python.org/3/library/json.html)
  documents non-finite-number behavior and strictness controls.
- `OS-06`: [GitHub's Python CI guide](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)
  shows tests and Ruff as explicit workflow steps; code in the repository is not
  covered merely by existing beside tested packages.
- `OS-07`: [CWE-22](https://cwe.mitre.org/data/definitions/22) and
  [CWE-59](https://cwe.mitre.org/data/definitions/59) cover absolute/relative path
  escape and unintended link resolution.

## Frozen ledger

| Claim | Local verdict and distinguishing evidence | Reachability, impact and prerequisite | Severity | Owner | External evidence | Required acceptance tests | Compatibility and rollback |
|:--|:--|:--|:--|:--|:--|:--|:--|
| N-01 | **confirmed**. `L-PROBE` produced `pre_mutation=allow`, `pre_final=block:*`, process exit `0`; the all-allow control also exited `0`. | Public CLI is callable by shell/automation. A consumer relying only on `$?` can false-green; no current workflow caller proving an irreversible action was found. | High | P2 | `PPLX-G1`; `OS-06` | Negative: mixed allow/block exits non-zero. Positive: all-allow exits zero and JSON stays stable. | Keep `check` as full gate; add explicit stage commands if needed. Roll back command split while retaining non-zero-on-block invariant. |
| N-02 | **confirmed**. `L-PROBE` passed empty content with a claimed terminal `next_offset`; implementation validates metadata flow, not snapshot bytes. | Any caller of chunk validation can falsely claim complete context. Requires ability to construct chunk records, already part of the agent boundary. | High | P2 | `PPLX-G1`; `OS-01` | Negative: altered/empty/gapped/repeated/post-terminal/path/hash chunks reject. Positive: exact contiguous bytes reconstruct and hash to every member. | Tightening rejects legacy metadata-only chunks. Version the chunk schema; rollback accepts old schema only in explicit diagnostic mode, never admission. |
| N-03 | **confirmed**, original P0 downgraded. A synthetic `CODEX_HOME`, thread state and environment produced accepted provider evidence and an owner grant. | The agent and forged evidence share one OS principal, so the current mechanism is a workflow guard, not authentication. Security impact exists only where callers mistake it for a higher-principal authorization boundary. | High | P3 | `PPLX-G2`; `OS-02`, `OS-03` | Negative: forged Codex/Claude state, replay, expiry and cwd/plan/item mismatch reject. Positive: provider-issued, nonce-bound, unexpired attestation activates once. | Preserve transcript evidence for diagnostics. Protected actions fail closed without a provider trust channel; reversible local workflow degrades honestly to a labelled guard. |
| N-04 | **confirmed**. A mandatory receipt with fabricated `completed_prefix` admitted continuation without terminal evidence. | Any holder/editor of a receipt can skip required members; prerequisite is batch continuation through the public contract path. | High | P2 | `PPLX-G1`; `OS-01` | Negative: edited prefix, missing terminal, other plan/spec/routing digest reject in both branches. Positive: prefix derived from matching terminal events admits next suffix. | Introduce a versioned receipt and derive prefix server-side. Roll back representation only, never acceptance of caller-authoritative completion. |
| N-05 | **confirmed**. `build()` labelled declared validation `cross-checked`; `pre_final` allowed without execution. | Every compiled item with validation clauses is reachable. Impact is false final evidence unless a later layer independently supplies real receipts. | High | P2 | `PPLX-G1`; `OS-01` | Negative: declared-only, non-zero, stale-HEAD or wrong-contract receipt blocks. Positive: successful bound runtime receipts satisfy final. | Add `declared` proof class and version runtime receipts. A feature flag may read old bundles, but final must remain blocked until upgraded evidence exists. |
| N-06 | **confirmed**. Injected derived-view failure left owner-message/decision carriers that a later resolver treated as granted. | Materialization is a production caller. Failure or concurrency between preparation and derived outputs can expose partial activation. | High | P3 | `PPLX-G2`; `OS-04` | Negative: any prepare/verify failure leaves no active grant; concurrent calls activate at most one. Positive: fully verified transaction publishes one authoritative activation last. | Readers temporarily support old decisions as legacy inactive records. Roll back new projections, not activation-last semantics; recovery can rebuild derived views. |
| N-07 | **confirmed**. A filename with a matching decision prefix was sufficient although the decision was proposed and unrelated. | Journal exception path is reachable when callers request validation bypass. It can authorize malformed history with any colliding carrier. | High | P4 | `PPLX-G3`; `OS-03` | Negative: proposed/rejected/superseded/unrelated/wrong-target decisions reject. Positive: one accepted current item-bound typed grant permits only its target hash/fields. | New typed marker makes old exceptions invalid until migrated. Rollback is removal of an exception, never broad filename fallback. |
| N-08 | **confirmed**. A raw transcript passed bundle lint when caller declared `minimized=false` and `excluded_classes=[]`. | Bundle authors control both bytes and declaration. Confidentiality impact becomes high only when bundles cross a trust boundary; it is still a policy failure locally. | High | P5 | `PPLX-G4`; `OS-07` | Negative: secrets/transcripts/tool payloads, path escape, duplicates, symlinks and special files reject independent of declarations. Positive: policy-allowed minimized regular files pass. | Freeze `BundleInputPolicy/v1`; stage existing bundles through a report-only scanner, then enforce. Roll back individual allowlist entries, not caller-owned policy. |
| N-09 | **confirmed**. `/tmp/secret.json` disappeared from `execution_inputs`, after which portability allowed the mixed bundle. | Any item parser input can carry external absolute/URI/home/UNC/symlink dependencies. Impact is non-reproducible or escaping execution. | High | P5 | `PPLX-G4`; `OS-07` | Negative: POSIX, drive, UNC, `file:`, home/env and outward symlink paths remain represented and reject. Positive: canonical in-root logical inputs pass. | Preserve every input with a classified kind. A migration report lists newly rejected specs; rollback classification UI, not silent dropping. |
| N-10 | **confirmed**. Two no-store authorization calls did not aggregate scope, and the same response was accepted in two independent no-store applications. | CLI/default APIs make stores optional. Replay and fragmented commitment are reachable across processes. | High | P3 | `PPLX-G2`; `OS-02` | Negative: repeated response and cumulative scope overflow reject across processes. Positive: a fresh action is atomically recorded and consumed once. | Make durable store mandatory only in enforced mode; retain explicit stateless evaluation for diagnostics. Rollback backend implementation while preserving unique consume key. |
| N-11 | **confirmed**. A request self-reporting reversible/non-contract-changing facts delegated without any observed diff/carrier evidence. | Every authority request controls the predicates used to authorize itself. Hashing proves canonical bytes, not truth. | High | P3 | `PPLX-G2`; `OS-03` | Negative: claimed-safe but observed-risky action requires approval; unverifiable facts never auto-delegate. Positive: trusted analyzers reproduce safe predicates and delegation. | Add claimed/observed/verified fields additively, then stop consuming claims for policy. Rollback analyzer rollout by requiring approval, not trusting claims. |
| N-12 | **confirmed**. A synchronized two-writer probe appended two terminals; malformed non-empty JSONL was skipped and append proceeded. | Parallel runners and damaged journals are realistic production states. Duplicate/conflicting terminal history breaks lifecycle authority. | High | P4 | `PPLX-G3`; `OS-04` | Negative: corrupt history blocks; concurrent same/conflicting terminals yield one event or typed conflict. Positive: one locked durable append succeeds and rereads. | One lock domain for journal and exception sidecar; add repair tooling separately. Rollback hash/index features while retaining fail-closed corruption and locked append. |
| N-13 | **confirmed**. Workflow inventory found neither Task tests nor Task Ruff paths while adjacent packages are explicit. | Every push/PR using the displayed workflow is affected. This is an assurance gap, not proof all branch protection omits Task. | High | P2 | `PPLX-G5`; `OS-06` | Negative: a seeded Task test/lint failure fails CI. Positive: Task test suite and Ruff run on the supported Python matrix. | Add a separate job first; avoid changing existing jobs. Roll back matrix breadth if costly, never total Task coverage. |
| N-14 | **confirmed**, constrained. Materialization accepted provider evidence with the digest removed; current adapters normally emit it. | Mainly adapter drift/interface misuse; not a standalone exploit, and the same-principal trust defect dominates today. | Medium | P3 | `PPLX-G2`; `OS-01`, `OS-03` | Negative: missing/extra/mismatched canonical attestation fields reject. Positive: exact schema binds action, subject, nonce, policy and adapter version. | Version the envelope and accept legacy only as non-authoritative diagnostics. Roll back schema version, not exact-field validation for protected actions. |
| N-15 | **confirmed**. Invalid timestamp, negative duration/cost, float turns and non-finite values passed relevant validation paths. | Any journal writer can corrupt ordering/telemetry. Impact is reporting and lifecycle ambiguity rather than direct authority escalation. | Medium | P4 | `PPLX-G3`; `OS-05` | Negative: non-UTC/invalid, negative, non-integral, NaN/infinite and terminal-before-start reject. Positive: finite non-negative values and strict UTC time pass. | Tighten new writes; report legacy invalid rows before migration. Roll back chronology cross-check only if legacy data blocks, not primitive validation. |
| N-16 | **confirmed**. An impossible calendar date matching the regex loaded successfully. | Decision authors or generators can create invalid chronology. Downstream sorting/temporal reasoning is affected. | Medium | P4 | `PPLX-G3`; `OS-05` | Negative: impossible/non-ISO dates reject. Positive: leap-day and normal ISO dates parse; optional monotonic rule has explicit legacy test. | Calendar validation is compatible for valid files. If monotonic IDs are enforced, stage it separately and provide a migration report. |
| N-17 | **confirmed**. Instrumentation observed zero `fsync` calls; check mode accepted a symlink with matching bytes. | Generated projections are reconstructable, limiting current impact. Crash loss or unintended external resolution requires crash/untrusted path conditions. | Medium | P4 | `PPLX-G5`; `OS-04`, `OS-07` | Negative: symlink/special target rejects; crash injection never reports durable success before file+directory sync; concurrent writers serialize. Positive: regular same-directory temp/replace/sync persists exact bytes. | Use a shared durable writer and retain check-only diagnostics. Roll back lock strategy if necessary, not no-follow and acknowledged-durability semantics. |

## STRIDE boundary analysis for the owner-authority cluster

| Actor / asset | Spoofing and tampering | Repudiation / replay | Information disclosure / denial / elevation | Required boundary |
|:--|:--|:--|:--|:--|
| Owner | A locally manufactured owner message can impersonate intent. | No independently issued, single-use proof currently binds the owner turn. | A forged intent can elevate the agent only where consumers treat the workflow guard as authorization. | Provider-issued proof over exact action; owner identity is not inferred from agent-writable bytes. |
| Agent principal | Controls shell, environment and ordinary local files; therefore hashes it computes prove integrity only. | Can replay stateless responses and split commitments across processes. | Can read diagnostic transcripts already available to the same principal; this does not create a higher trust channel. | Treat as the constrained principal; it must not possess the issuer secret or nonce store. |
| Provider adapter | A new/buggy adapter can omit fields or reinterpret the action. | Version drift can make old envelopes replayable or ambiguous. | Adapter failure can deny work; it must never silently widen authority. | Exact versioned envelope and independently checked issuer/subject/action binding. |
| Local filesystem and environment | Selectors and transcript paths are mutable by the agent; partial writes can tamper with apparent state. | Local files without durable unique consumption do not prevent replay. | Path mistakes can expose unrelated bytes; crashes can leave ambiguous activation. | Selectors only, no trust-root role; containment, no-follow, lock, activation-last and durability. |
| Nonce / store | Missing or optional state permits reuse and fragmented cumulative scope. | Duplicate consume must be an atomic conflict across processes. | Store outage must deny protected action rather than downgrade. | Durable, issuer-controlled, expiring unique key bound to plan/item/action/version. |
| Activation record | Prepared owner/decision carriers can be mistaken for an active grant. | Multiple records can contradict or obscure which action was authorized. | A partial failure can elevate a later resolver. | Exactly one authoritative record published last after all verification; derived views are reconstructable. |

## Security conclusion

The current owner gate is retained only as a workflow guard. It must not be
described as a security boundary while its trust root is writable by the same
agent principal. Protected, irreversible or external actions fail closed when an
out-of-principal provider attestation is unavailable. Reversible local workflow
may continue under an explicitly labelled degraded mode that grants no security
claim. This resolves the external/local disagreement without averaging it: the
mechanisms reproduce, but their maximum audit severity was not demonstrated in
the current caller graph.
