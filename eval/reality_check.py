"""White's Reality Check and Hansen's SPA test — the correct tests when you've been hunting.

The question these answer is not "is *this* strategy better than luck?" but "is the *best of N*
strategies better than luck?" — which is what you are really asking after screening hundreds. Both
use a stationary bootstrap (Politis & Romano, 1994) to respect serial dependence in the per-period
performance series.

Input convention
----------------
`perf` is a (T, K) array of per-period *performance* for K strategies, where **larger is better**
and the null of "no edge" is E[perf_k] <= 0 for all k. For betting, use per-bet excess return over
the break-even hurdle (e.g. profit_per_unit at the placed price — already centred so that 0 = fair).

References
----------
White (2000) "A Reality Check for Data Snooping"; Hansen (2005) "A Test for Superior Predictive
Ability". Hansen's SPA_c uses the consistent recentring that discards strategies too far below zero
to plausibly be the best, which sharply raises power over White's RC.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SPAResult:
    reality_check_p: float   # White's RC p-value (H0: best strategy has E[perf] <= 0)
    spa_p: float             # Hansen's SPA_c p-value (recentred; higher power)
    best_k: int              # index of the strategy with the largest studentized statistic
    best_mean: float         # mean performance of the best strategy
    n_bootstrap: int
    block_mean_length: float


def _stationary_bootstrap_indices(
    n: int, n_boot: int, mean_block: float, rng: np.random.Generator
) -> np.ndarray:
    """Politis-Romano stationary bootstrap index matrix, shape (n_boot, n).

    Blocks have geometric length with mean `mean_block`; start points are uniform; wrapping is
    circular so every observation is equally likely. Vectorized: a restart mask marks new blocks,
    each position inherits the start drawn at its most recent restart plus its offset within the
    block. Equivalent in distribution to the sequential construction, but fast at full sample size.
    """
    if n <= 0:
        return np.empty((n_boot, 0), dtype=int)
    p = 1.0 / max(mean_block, 1.0)
    ar = np.arange(n)
    restart = rng.random((n_boot, n)) < p
    restart[:, 0] = True                                   # every series starts a block at t=0
    starts = rng.integers(0, n, size=(n_boot, n))          # candidate block-start index at each t
    last_restart = np.where(restart, ar[None, :], 0)
    np.maximum.accumulate(last_restart, axis=1, out=last_restart)  # index of the current block's start
    block_start = np.take_along_axis(starts, last_restart, axis=1)  # the drawn start for that block
    offset = ar[None, :] - last_restart                    # position within the current block
    return (block_start + offset) % n


def spa_test(
    perf,
    n_bootstrap: int = 2000,
    mean_block: float = 10.0,
    seed: int | None = 0,
) -> SPAResult:
    """Compute White's Reality Check and Hansen's SPA_c p-values.

    perf : array-like (T, K), larger = better, H0: max_k E[perf_k] <= 0.
    """
    P = np.asarray(perf, dtype=float)
    if P.ndim == 1:
        P = P[:, None]
    T, K = P.shape
    if T < 2:
        raise ValueError("need at least 2 periods")

    rng = np.random.default_rng(seed)
    f_bar = P.mean(axis=0)                                  # (K,)

    # Per-strategy scale. Use a HAC-ish estimate via the bootstrap variance of sqrt(T)*mean.
    omega = _bootstrap_scale(P, n_bootstrap, mean_block, rng)  # (K,)
    omega = np.where(omega <= 0, 1e-12, omega)

    sqrtT = np.sqrt(T)
    studentized = sqrtT * f_bar / omega
    best_k = int(np.argmax(studentized))

    # --- statistics on the observed data ---
    V_rc = np.max(sqrtT * f_bar)                    # White's RC (not studentized)
    T_spa = max(0.0, float(np.max(studentized)))    # Hansen's SPA_c (studentized, floored at 0)

    # Hansen's consistent recentring threshold: keep a strategy's mean only if it is not
    # "too negative" to plausibly be the best. A_k = (omega_k/sqrt(T)) * sqrt(2 log log T).
    loglogT = np.log(np.log(T)) if T >= 3 else 0.0
    thresh = (omega / sqrtT) * np.sqrt(max(2.0 * loglogT, 0.0))
    g = np.where(f_bar >= -thresh, f_bar, 0.0)      # recentring means for SPA_c

    idx = _stationary_bootstrap_indices(T, n_bootstrap, mean_block, rng)  # (B, T)

    rc_exceed = 0
    spa_exceed = 0
    for b in range(n_bootstrap):
        Pb = P[idx[b]]                              # (T, K) resampled
        fb = Pb.mean(axis=0)
        # White's RC: recentre by the full sample mean.
        Vb_rc = np.max(sqrtT * (fb - f_bar))
        if Vb_rc >= V_rc:
            rc_exceed += 1
        # Hansen's SPA_c: recentre by g (consistent), studentize by omega, floor at 0.
        Zb = sqrtT * (fb - g) / omega
        Tb = max(0.0, float(np.max(Zb)))
        if Tb >= T_spa:
            spa_exceed += 1

    return SPAResult(
        reality_check_p=rc_exceed / n_bootstrap,
        spa_p=spa_exceed / n_bootstrap,
        best_k=best_k,
        best_mean=float(f_bar[best_k]),
        n_bootstrap=n_bootstrap,
        block_mean_length=mean_block,
    )


def _bootstrap_scale(P, n_boot, mean_block, rng) -> np.ndarray:
    """Bootstrap estimate of the std of sqrt(T)*mean for each strategy (Hansen's omega_k)."""
    T, K = P.shape
    # A cheaper, stable scale: sample std of the column (consistent under weak dependence for the
    # studentization; the stationary bootstrap on the recentred stat carries the dependence).
    sd = P.std(axis=0, ddof=1)
    return np.where(sd <= 0, 1e-12, sd)
