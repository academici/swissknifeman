# Single read limit: two media gates and probe procedure

The `Read` tool of this environment carries **TWO independent gates**, not one. Both recorded
machine-readable artifact `packages/task/configs/read-limit.json` because both are properties
A SPECIFIC environment on a specific date, not a protocol constant (D15 plan
): a hardwired literal will lie in the first other environment.

## Two gates

| | Gate A - file size | Gate B - Reading Contents |
|:--|:--|:--|
| Unit | bytes of file on disk | Harness counter tokens by RENDERED output |
| Behavior | hard refusal, zero content | three shapes, see below |
| Region | read-only ENTIRE file | any returned slice |
| Bypass | `offset`/`limit` removes gate | cannot be removed: the cut is also measured |
| Checked | first | second |

A file exceeding both thresholds gives a **byte** message - gate A is checked before gate B.
Values are not converted into each other: on prose plans, gate B is triggered much earlier
gate A, on dense ASCII (hex/base64) the ratio is the opposite, but A is still checked first.
There is no fixed multiplier between the gates - manage both gates with separate artifact fields
required (`limits.size_bytes` / `limits.tokens`; scalar `limit_tokens` does not start).

## Three shapes of Gate B

1. **Page Trim** (multiline file, whole read): line prefix + marker
   `showing lines 1-N of M total (T tokens, cap 25000)`. There is no refusal - quiet partial delivery.
2. **Character-by-character trimming** (file with very long lines): character prefix + marker
   `showing the first N of M characters (T tokens, cap 25000); … cannot be paginated by line`.
3. **Hard failure** (`offset`/`limit`, the cutoff of which itself exceeds the cap):
   `File content (T tokens) exceeds maximum allowed tokens (25000)`.

Forms 1–2 - the performer silently receives a subset of the file with the sentence “read it yourself”: exactly
defect for which the limit is generally measured as an environmental parameter. Acceptance condition `D2(b)` plan
 is read strictly: the required file is read in ENTIRELY WITH ONE call,
page-by-page reading does not satisfy the condition.

## Probe procedure - cheap and reproducible

Key property: **environment score and cap are obtained without paying for content** - form 3 of gate B
returns zero content and says both numbers at once. Two required steps, each worth it
some context:

1. **Gate A.** Take an existing file larger than the current value `limits.size_bytes` (good
   large `plan.md` fleet) and read it WHOLE, without `offset`/`limit`. Write down verbatim
   refusal, file size in bytes and declared cap. Message unit - KiB: `bytes / 1024`
   must match the number “KB” in the text; does not match - the environment thinks otherwise, this is recorded
   separately and escalated.
2. **Gate B.** Generate a one-line dense file obviously higher than the cap value `limits.tokens`
   and read it with `limit=1`:

   ```python
   import hashlib, pathlib
   pathlib.Path("/tmp/read-limit-probe.txt").write_text(
       "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(2000)) + "\n")
   ```

   Failure will return both the file account by the environment and cap. Write down verbatim; this is where the couple comes in
   `cross_check` (file symbols → environment score → estimate `task.token_estimate` on the same text) -
   it is NOT a calibration point (D15 plan): read environment counter and tokenizer
   P0.1 calibrations are different meters, mixing them in one artifact is prohibited.

Gate B shapes 1-2 (trimming) when probed **not intentionally reproduced**: each costs full
context page (up to `limits.tokens` tokens), but does not give a new number - the cap has already been received by step 2.

Border bisection is not needed for any gate - the environment names both numbers itself.

## Signs of a change in environment

Any discrepancy with the recorded artifact - different cap number, different unit in the message,
the disappearance of one of the forms, the appearance of a third gate means that the environment has changed. Reaction -
**re-measuring and new version of the artifact**, rather than manually editing the number: `limits.*` lives only through
regeneration (canon `root.generated-artifacts`).

## Artifact

`packages/task/configs/read-limit.json` carries both gates as separate typed fields
(`limits.size_bytes`, `limits.tokens`), probe environment (`environment`), verbatim texts of both
bounces (`probe.size_gate.refusal_message`, `probe.token_gate.refusal_message`) and a couple
`cross_check`. It is committed to the repository and read by the tool for measuring the weight of the mandatory
read (`packages/task/lib/task/plan_weight.py`, P0.3) - absence or incompleteness of any of the two
gates fail-closed, silent default is prohibited.
