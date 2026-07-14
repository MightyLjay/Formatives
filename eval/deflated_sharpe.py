"""Probabilistic and Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

The Sharpe ratio of your *best* backtest is upward-biased precisely because it was the best of many
trials. The Deflated Sharpe Ratio corrects the Sharpe you would need to clear for significance by
the number of trials that produced it, and by the return distribution's skew and kurtosis. A DSR
below ~0.95 means the result is consistent with luck given how hard you looked.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

EULER_MASCHERONI = 0.5772156649015329


@dataclass
class DSRResult:
    sharpe: float
    psr: float               # P(true SR > sr_benchmark)
    dsr: float               # PSR against the expected-max-of-N-trials benchmark
    sr_star: float           # the deflated benchmark Sharpe
    n_trials: int
    n_obs: int


def probabilistic_sharpe_ratio(
    returns=None,
    sr_benchmark: float = 0.0,
    *,
    sharpe: float | None = None,
    n_obs: int | None = None,
    skew: float | None = None,
    kurtosis: float | None = None,
) -> float:
    """PSR(sr_benchmark): probability the true Sharpe exceeds the benchmark.

    Provide either a `returns` series, or the summary stats (`sharpe`, `n_obs`, `skew`,
    `kurtosis`) directly. Kurtosis is the *non-excess* (normal = 3) fourth moment.
    """
    if returns is not None:
        r = np.asarray(returns, dtype=float)
        n_obs = r.size
        sd = r.std(ddof=1)
        sharpe = 0.0 if sd == 0 else r.mean() / sd
        skew = float(stats.skew(r))
        kurtosis = float(stats.kurtosis(r, fisher=False))
    if None in (sharpe, n_obs, skew, kurtosis):
        raise ValueError("provide `returns`, or all of sharpe/n_obs/skew/kurtosis")
    if n_obs < 2:
        return float("nan")

    denom = np.sqrt(max(1.0 - skew * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe**2, 1e-12))
    z = (sharpe - sr_benchmark) * np.sqrt(n_obs - 1.0) / denom
    return float(stats.norm.cdf(z))


def expected_max_sharpe(sr_variance: float, n_trials: int) -> float:
    """Expected maximum Sharpe across N independent trials with SR variance `sr_variance`.

    Uses the extreme-value approximation from Bailey & Lopez de Prado. `sr_variance` is the
    variance of the Sharpe estimates *across trials*.
    """
    if n_trials < 2 or sr_variance <= 0:
        return 0.0
    z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(sr_variance) * ((1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2))


def deflated_sharpe_ratio(
    best_returns,
    all_trial_sharpes,
) -> DSRResult:
    """Deflated Sharpe Ratio for the best strategy out of a family.

    best_returns : the per-period return series of the selected (best) strategy.
    all_trial_sharpes : the Sharpe ratios of *every* strategy tried (the multiple-testing budget).
    """
    r = np.asarray(best_returns, dtype=float)
    n = r.size
    sd = r.std(ddof=1)
    sr = 0.0 if sd == 0 else r.mean() / sd
    sk = float(stats.skew(r))
    ku = float(stats.kurtosis(r, fisher=False))

    trial_sr = np.asarray(all_trial_sharpes, dtype=float)
    n_trials = max(trial_sr.size, 1)
    sr_var = float(np.var(trial_sr, ddof=1)) if trial_sr.size > 1 else 0.0
    sr_star = expected_max_sharpe(sr_var, n_trials)

    psr0 = probabilistic_sharpe_ratio(sharpe=sr, n_obs=n, skew=sk, kurtosis=ku, sr_benchmark=0.0)
    dsr = probabilistic_sharpe_ratio(sharpe=sr, n_obs=n, skew=sk, kurtosis=ku, sr_benchmark=sr_star)
    return DSRResult(sharpe=sr, psr=psr0, dsr=dsr, sr_star=sr_star, n_trials=n_trials, n_obs=n)
