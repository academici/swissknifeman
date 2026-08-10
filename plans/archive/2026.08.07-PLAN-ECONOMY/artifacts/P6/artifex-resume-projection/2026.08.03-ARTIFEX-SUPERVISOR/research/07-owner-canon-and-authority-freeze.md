# P0.2 owner canon and authority freeze

RAG:— (owner-grounded: `brief/00-brief.md`, `brief/01-refinements.md`,
`research/00-user-intent.md`; repo-grounded: root, Task and Harness instructions,
`research/02-authority-and-conflict-policy.md`, current Harness execution policy and the two
named AGENT-RELIABILITY contracts).

## Verdict

The owner mandate is an unsigned, minimized input. It can remove files, tools, providers,
models, budget, validations or action classes from the frozen envelope, but it cannot add or
weaken any of them. The supervisor therefore resolves only routine choices that are already
legal. Agreement frequency, worker confidence, votes and recommendations never create
authority.

`owner-mandate-input-v1.json` freezes the exact source paths and SHA-256 values used for this
verdict. A hash mismatch invalidates the input before a decision is evaluated. The file is
deliberately marked `unsigned-input`: P0.2 does not sign a production mandate.

## Precedence and conflict

| Level | Carrier | Effect |
|:--|:--|:--|
| 1 | system, security and provider hard limits | Cannot be narrowed into permission or bypassed. |
| 2 | root plus applicable Task/Harness instructions | Defines repository and package boundaries. |
| 3 | frozen plan contracts and append-only D# decisions | Defines item lifecycle, finding identity and loop caps. |
| 4 | signed run mandate | May only narrow levels 1–3. |
| 5 | supervisor defaults | Selects among already legal alternatives. |

Different levels are resolved by the highest applicable source. Contradictory directives at the
same level produce `OWNER` before side effect and preserve both source references. A supervisor
default cannot defeat a higher-level refusal. If routine-choice ordering has no unique legal
winner, the result is also `OWNER`; an LLM tie-break is not an authority source.

## Action classes

| Class | Allow condition | Mandatory refusal path |
|:--|:--|:--|
| `AUTO` | Exact scope, reversible/no-write action, known capability, deterministic acceptance and no protected boundary. | Any failed predicate returns `OWNER`. |
| `AUTO-FIX` | All `AUTO` predicates, unchanged finding identity and acceptance, and retry count below the durable cap. | Changed finding/acceptance or exhausted cap returns `OWNER`. |
| `OWNER` | The mandate or a controlling canon requires a decision, including a deliberately narrowed safe action. | No side effect occurs before the decision. |

The protected taxonomy is closed in the mandate: security, destructive, irreversible, external,
public-contract/SemVer, dependency, package-topology, third-state, unknown-capability,
same-level-conflict, unresolved routine choice and exhausted-budget paths are `OWNER`.

## Routine ordering and retry rules

Legal alternatives are compared lexicographically by changed files/behaviour, reuse of an
existing primitive, reversibility, sequential writes, dependency/provider branching,
deterministic-validation strength and measured token/cost. The selected and rejected candidate
identifiers are decision evidence; an exact tie is not guessed.

`same_finding_max` is 2 fix rounds. `AUTO-FIX` keeps the same stable finding identity and the
same acceptance hash. The third occurrence or a retry at/above the cap is
`RETRY_BUDGET_EXHAUSTED`; it is never an inline fourth attempt. Resume uses the durable count.

## Decision evidence

Every decision record has the schema frozen in the mandate: case or run id, requested and
resolved class, allow/refusal boolean, reason code, controlling sources, source-set hash,
mandate hash, selected/rejected alternatives and pre-side-effect timestamp/sequence carrier.
The P0.2 verifier is pure stdlib and derives decisions from case inputs; expected values live in
the independent case bank and are compared after evaluation.

## Fixture coverage

`authority-cases-v1.json` contains positive routine `AUTO` and bounded `AUTO-FIX` cases plus
negative/refusal cases for all three declared classes. It covers every protected boundary,
every narrowing dimension (files, tools, provider, model, effort, budget, validation and action
class), cross-level precedence, same-level contradiction, unique routine ordering, unresolved
tie, changed finding/acceptance, third state, unknown capability and exhausted budget.

No case uses “owner usually agrees”, confidence or voting as an allow predicate.
