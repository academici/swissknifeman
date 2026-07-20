# D71 provenance/bookkeeping repair — 2026-07-20

## Scope and disposition

This finding records a contract-neutral repair before the substantive P1.2 Owner
gate. It does not implement P1.2, change `core/**` or frozen product semantics,
mutate the retained stash, or alter authority over FOREMAN, fleet, provider outputs,
or live carriers.

## Journal timestamp correction

At repair baseline `4b4e0051333cffb77f3f9e6bd9744afd4f60a527`, the final physical
P1.2 journal event was line 66 (raw SHA-256
`1e38657c1429d0f2f1de9a14d94344708d2f6778d7c77dd22c3eb0da24f61bd9`). Its recorded
timestamp `2026-07-20T14:00:00Z` is future-dated against the repair preflight at
`2026-07-20T13:36:21Z`.

The historical bytes remain untouched. The chronological Git evidence is:

| Evidence | Authoritative Git time |
|:--|:--|
| false-block commit `c09f8764d8eaf823395fd88d4e4e7ecaa96a7547` | `2026-07-20T13:13:01Z` |
| recovery commit `c68defce78111cf655ab0394768e06b8594fd330` | `2026-07-20T13:17:47Z` |
| proposal commit `1e9fa8de0768423316e8e5e8e8ddf728193207e6` | `2026-07-20T13:20:36Z` |
| whitespace commit `9fb9f1412c6b9dd195831212d16b63aa06f29029` | `2026-07-20T13:21:02Z` |

The new journal event is appended by the worktree-local `task.journal` module with
its actual UTC clock. It repeats attempt 2, `in-progress`, and
`["deviation", "retry"]` solely as a compensating provenance event. Its note names both
the erroneous row timestamp and the authoritative recovery-commit timestamp.

## Runtime route versus static doctor

The exact D71 worker startup banner is runtime process evidence:
`gpt-5.6-terra/high`, approval `never`, sandbox `danger-full-access`. It is the
authoritative route evidence for that worker. Static `codex doctor --json` instead
reports persisted `config.load.details.model = gpt-5.6-sol` and does not report an
effective reasoning effort. That mismatch remains the disclosed D56 environment
anomaly; it neither disproves the D71 runtime banner nor blocks the prescribed route.

## Retained stash

The retained stash is left exactly as found:
`72505e4d8bef2a58f4ed555cc5b6014450aee3a9`. `git show` establishes its authoritative
commit time as `2026-07-20T13:26:51Z` (`2026-07-20T16:26:51+03:00`). Its subject contains
`2026-07-20T12:00:00+03:00`; that operator label is not timestamp evidence. No rename,
drop, pop, apply, or other stash mutation is authorized or performed.

## Required verification

- Historical journal prefix through the prior final line is byte-identical.
- The appended event validates under `task.journal` and target `plan-lint` remains 0/0.
- `git diff --check` is clean; the diff is limited to the explicit plan evidence paths.
- The P1.2 contribution-review proposal stays SHA-256
  `01152ecb876d5f8299134c579218538268b453aca765857e8c69f422aab687df`.
- The retained stash OID remains present with its authoritative Git commit time.
