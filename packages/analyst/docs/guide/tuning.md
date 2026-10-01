# Tuning parameters

All thresholds analyst — **heuristics**, and not values calibrated from field data. Values
selected «by eye» for reasons of curve shape (see column «calibration method»); real
calibration by false-positive-rate more **not carried out** (is a separate research-task - simulation
on activity profiles + field data, see `roadmap`). This page is a single reference: where
the parameter is what it does and in which direction to turn it.

Rule: thresholds change **only in the source module** (single source, not local magic).
After editing - `bash scripts/validate.sh` (determinism of recalculation is tested).

## Confidence-arithmetic

Module: [`confidence.py`](https://github.com/academici/swissknifeman/blob/main/packages/analyst/lib/analyst/confidence.py).
Formula: `confidence = beta_mean(S,N) × volume_factor(N) × time_decay(days) ∈ [0,1)`.

| Parameter | Meaning | What it does | Twist ↑ | Twist ↓ | Calibration method |
|:--|:--|:--|:--|:--|:--|
| `ALPHA` | 1.0 | Beta-success priority (Laplace) | pulls harder `p` to optimism with little N | closer to the observed fraction | neutral prior `S=N=0 → p=0.5`; change only with justification |
| `BETA` | 1.0 | Beta-failure priority | pulls harder `p` down | more optimistic | symmetrical `ALPHA` |
| `VOLUME_K` | 20.0 | volume scale in `1−e^(−N/k)` | is slower to gain confidence (needs more observations) | trusts little ones faster N | curve shape: `N≈k → volume≈0.63`, `N≫k → →1`. Raise if low-observed lessons falsely pop up |
| `DECAY_LAMBDA` | 0.95 | attenuation `λ^days` per day | longer «remembers» (fades out more slowly) | forgets old things faster | `λ=0.95 → half-life ≈14 days (ln0.5/ln0.95)`. Raise for stable domains, lower for rapidly changing ones |
| `BUCKET_DAYS` | 1 | age granularity | rougher (less often age recalculation) | thinner | usually do not touch |

### Application ranges

Thresholds `confidence → semantics` ([`confidence.py`](https://github.com/academici/swissknifeman/blob/main/packages/analyst/lib/analyst/confidence.py), function `tier`):

| Shooting Range | Threshold | Semantics |
|:--|:--|:--|
| `core` | `TIER_CORE` = 0.9 | core knowledge |
| `strong` | `TIER_STRONG` = 0.7 | auto-surface to memory |
| `moderate` | `TIER_MODERATE` = 0.5 | apply when relevant |
| `tentative` | `TIER_TENTATIVE` = 0.3 | not enforce |
| `none` | < 0.3 | do not apply |

Rotate the threshold ↑ — stricter (fewer lessons in the shooting range, fewer false positives, more omissions);
↓ — more liberal (reverse exchange).

## State-machine (recompute)

Module: [`recompute.py`](https://github.com/academici/swissknifeman/blob/main/packages/analyst/lib/analyst/recompute.py).
Numeric gates for auto-state transitions.

| Parameter | Meaning | What it does | Twist ↑ | Twist ↓ | Calibration method |
|:--|:--|:--|:--|:--|:--|
| `CANDIDATE_MIN_N` | 15 | volume of observations for cars `ephemeral→candidate` (**adaptive** for low-activity projects, see below) | stricter - longer in ephemeral | promotes faster (noise risk) | static ceiling; for `Σ sessions < 50` is decreasing in activity |
| `CANDIDATE_MIN_CONF` | 0.6 | minimum confidence for the same transition | stricter | more liberal | link with `VOLUME_K`/`DECAY_LAMBDA`; **co-gate**: when `VOLUME_K=20` requires `N≈19` regardless `CANDIDATE_MIN_N` (see below) |
| `CANDIDATE_MIN_N_FLOOR` | 3 | bottom adaptive bar `CANDIDATE_MIN_N` | promotes less often in very small projects | faster (risk of noise on 1-2 observations) | do not fall below 3 observations |
| `CURATED_MIN_N` | 50 | numeric threshold «ready for curated» (transition - **person**; **adaptive**, see below) | more evidence before offer | used to suggest | is just a threshold **ready**; the transition itself is always human |
| `CURATED_MIN_CONF` | 0.8 | minimum confidence for «ready for curated» | stricter | more liberal | — |
| `CURATED_MIN_PASSRATE` | 0.95 | minimum test pass rate | stricter | more liberal | share `tests_passed/tests_total` |
| `DEPRECATE_CONF` | 0.6 | drawdown below → soft-demo (candidate) / flag (curated) | more aggressive demoutitis | more tolerant of drawdown | does not delete - soft-deprikate/flag for human review |

### Adaptive thresholds N for low-activity projects (D2)

Function `adaptive_thresholds(project_sessions)` in `recompute.py`. `project_sessions` — **total
project activity** = `Σ sessions_total` for all events `events.ndjson` (is stable to `compact`,
it saves the amounts). An inactive project will not physically recruit `N ≥ 15/50` → lessons are stuck in
«eternal ephemeral». Lower the bar in proportion to activity, maintaining the proportion candidate:curated:

```
if project_sessions ≥ CURATED_MIN_N (50):  → (15, 50)          # enough data, static
otherwise:
    candidate = max(CANDIDATE_MIN_N_FLOOR, project_sessions // 5)          # formula D2
    curated   = max(candidate, round(candidate × CURATED_MIN_N / CANDIDATE_MIN_N))
```

Examples: `Σ=40 → (8, 27)` · `Σ=10 → (3, 10)` · `Σ=0 → (3, 10)`. Invariants: threshold is never higher
static; `curated ≥ candidate`; pure deterministic function (same log + the same `--now`
→ same outcome). The same threshold applies `analyst status` (`curated-ready`).

> **Fair limit (not a crutch under the rug):** adaptive **`CANDIDATE_MIN_N`** almost inert -
> his co-gate `CANDIDATE_MIN_CONF=0.6` when `VOLUME_K=20` itself requires `N≈19` (`volume=1−e^(−N/20)≥0.6`),
> which is already stricter than static `N≥15`. That is, a decrease `CANDIDATE_MIN_N` helps only where it
> is indeed a binding gate. Adaptive actually works **`CURATED_MIN_N`**: him N-gate (50)
> links earlier conf-gate (`CURATED_MIN_CONF=0.8` → `N≈32`), therefore downgraded to ~27–30 gives
> low-activity projects achieve `curated-ready`. Complete solution «eternal ephemeral» requires
> adaptations and `VOLUME_K`/`CANDIDATE_MIN_CONF` — this is calibration (D5), moved to research-task.

## Dedup and consolidation (Jaccard)

Token similarity thresholds (`[a-za-z0-9]{3,}`).

| Parameter | Meaning | File | What it does | Calibration method |
|:--|:--|:--|:--|:--|
| `_SIMILAR_CMD` | 0.6 | [`digest.py`](https://github.com/academici/swissknifeman/blob/main/packages/analyst/lib/analyst/digest.py) | threshold «essentially the same command» for pair fail→pass | ↑ — only close commands count as a try; ↓ — more false splices |
| `CONSOLIDATE_TRIGGER_HIGH` | 0.6 | [`lessons.py`](https://github.com/academici/swissknifeman/blob/main/packages/analyst/lib/analyst/lessons.py) | «same situation» (similarity trigger) | ↑ — stricter on duplicates/conflicts; ↓ — glues more aggressively |
| `CONSOLIDATE_ACTION_HIGH` | 0.6 | `lessons.py` | «same action» (for NOOP-take) | link with `CONSOLIDATE_TRIGGER_HIGH` |
| `CONSOLIDATE_ACTION_LOW` | 0.2 | `lessons.py` | below → actions diverge (CONFLICT) | gap `[LOW, HIGH]` — zone UPDATE |

Classification (mem0-taxonomy, always in human-gate): same situation + same action → `NOOP`;
same situation + divergent action (`asim < LOW`) → `CONFLICT`; same situation differently → `UPDATE`;
no relatives → `ADD`. There is no auto-resolution - only a recommendation to a person.

## Calibration - status

Full calibration based on real false-positive-rate **failed** (field data needed +
simulation of shooting ranges based on activity profiles). Before it, all the values above are justified by the shape of the curve
heuristics, unmeasured optima. Optional `scripts/calibrate_confidence.py` (simulation) — in
`roadmap`, is not implemented.
