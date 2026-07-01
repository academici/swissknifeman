"""analyst confidence — ЧИСТАЯ арифметика уверенности урока (stdlib, без I/O и часов).

Модель (Beta-среднее × volume-фактор × time-decay):

    p          = (S + α) / (N + α + β)      # Beta-среднее доли успеха
    volume     = 1 − e^(−N / k)             # штраф за малый объём наблюдений
    decay      = λ ^ days                    # затухание по времени (bucket = 1 день)
    confidence = p × volume × decay          # ∈ [0, 1)

Все функции — чистые: те же входы → тот же выход, без часов/файлов (часы и парс
timestamp'ов живут в recompute.py). Это делает пересчёт детерминированным и
восстановимым из логов, а формулу — тестируемой по точкам.

Константы ниже — ТЮНИНГ-параметры (единый источник, не магия по месту): меняются
здесь и калибруются по полевому false-positive-rate, а не выводятся априори.
# verified perplexity 2026-07, tune by false-positive rate
"""
import math

# ── тюнинг-параметры confidence (калибровать по false-positive rate) ──────────
ALPHA = 1.0          # Beta-приор успехов (Laplace-сглаживание: S=N=0 → p=0.5)
BETA = 1.0           # Beta-приор неудач
VOLUME_K = 20.0      # масштаб объёма: N≈k → volume≈0.63, N≫k → →1
DECAY_LAMBDA = 0.95  # затухание за день; полураспад ≈ 14 дней (ln0.5/ln0.95 ≈ 13.5)
BUCKET_DAYS = 1      # гранулярность возраста события в днях

# ── тиры применения (ECC): порог confidence → семантика ──────────────────────
TIER_TENTATIVE = 0.3   # tentative — не enforce
TIER_MODERATE = 0.5    # moderate — применять при релевантности
TIER_STRONG = 0.7      # strong — auto-surface в память
TIER_CORE = 0.9        # core — ядро знания


def beta_mean(s, n, alpha=ALPHA, beta=BETA):
    """(S+α)/(N+α+β). При S=N=0 → α/(α+β)=0.5 (нейтральный приор). S/N клиппуются к ≥0."""
    s = max(0.0, float(s))
    n = max(0.0, float(n))
    return (s + alpha) / (n + alpha + beta)


def volume_factor(n, k=VOLUME_K):
    """1 − e^(−N/k) ∈ [0,1): N=0 → 0 (нет объёма → нет уверенности), N≫k → →1."""
    n = max(0.0, float(n))
    return 1.0 - math.exp(-n / k)


def time_decay(days, lam=DECAY_LAMBDA):
    """λ^days ∈ (0,1]: days=0 → 1; растёт возраст → →0. days<0 клиппуется к 0."""
    d = max(0, int(days))
    return lam ** d


def confidence(s, n, days=0):
    """p × volume × decay ∈ [0,1). Чистая функция пересчёта уверенности урока."""
    return beta_mean(s, n) * volume_factor(n) * time_decay(days)


def tier(conf):
    """Метка тира по порогам 0.9/0.7/0.5/0.3. Ниже 0.3 → 'none' (не применять)."""
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
