"""analyst confidence — PURE confidence arithmetic lesson (stdlib, without I/O and hours).

Model (Beta-average × volume-factor × time-decay):

    p          = (S + α) / (N + α + β)      # Beta-average success rate
    volume     = 1 − e^(−N / k)             # penalty for small volume of observations
    decay      = λ ^ days                    # time decay (bucket = 1 day)
    confidence = p × volume × decay          # ∈ [0, 1)

All functions are pure: the same inputs → same output, without clock/files (clock and pars
timestamp'ov live in recompute.py). This makes the recalculation deterministic and
can be restored from logs, and the formula can be tested point by point.

Constants below - TUNING parameters (single source, not local magic): change
here. Values - HEURISTICS, selected according to the shape of the curve (see docs/guide/tuning.md),
and NOT field calibrated false-positive-rate: no real calibration yet
was carried out (simulation + field data - separate research-task in roadmap).
"""
import math

# ── tuning parameters confidence (heuristics, NOT calibrated - see tuning.md) ──
ALPHA = 1.0          # Beta-success priority (Laplace-smoothing: S=N=0 → p=0.5)
BETA = 1.0           # Beta-failure priority
VOLUME_K = 20.0      # volume scale: N≈k → volume≈0.63, N≫k → →1
DECAY_LAMBDA = 0.95  # attenuation per day; half-life ≈ 14 days (ln0.5/ln0.95 ≈ 13.5)
BUCKET_DAYS = 1      # event age granularity in days

# ── application ranges (ECC): threshold confidence → semantics ──────────────────────
TIER_TENTATIVE = 0.3   # tentative — not enforce
TIER_MODERATE = 0.5    # moderate — apply when relevant
TIER_STRONG = 0.7      # strong — auto-surface to memory
TIER_CORE = 0.9        # core — core knowledge


def beta_mean(s, n, alpha=ALPHA, beta=BETA):
    """(S+α)/(N+α+β). When S=N=0 → α/(α+β)=0.5 (neutral prior). S/N are clipped to ≥0."""
    s = max(0.0, float(s))
    n = max(0.0, float(n))
    return (s + alpha) / (n + alpha + beta)


def volume_factor(n, k=VOLUME_K):
    """1 − e^(−N/k) ∈ [0,1): N=0 → 0 (no volume → not sure), N≫k → →1."""
    n = max(0.0, float(n))
    return 1.0 - math.exp(-n / k)


def time_decay(days, lam=DECAY_LAMBDA):
    """λ^days ∈ (0,1]: days=0 → 1; age is growing → →0. days<0 is clipped to 0."""
    d = max(0, int(days))
    return lam ** d


def confidence(s, n, days=0):
    """p × volume × decay ∈ [0,1). Pure lesson confidence recalculation function."""
    return beta_mean(s, n) * volume_factor(n) * time_decay(days)


def tier(conf):
    """Range label for thresholds 0.9/0.7/0.5/0.3. Below 0.3 → 'none' (do not apply)."""
    c = float(conf)
    if c >= TIER_CORE:
        return "core"
    if c >= TIER_STRONG:
        return "strong"
    if c >= TIER_MODERATE:
        return "moderate"
    if c >= TIER_TENTATIVE:
        return "tentative"
    return "none"
