"""Bet sizing: quarter-Kelly max, correlation-aware.

Full Kelly is too aggressive for a fragile, decaying edge measured with noise — cap at quarter-Kelly.
And simultaneous games are NOT independent: a fast pace or a foul-heavy officiating crew pushes many
2H totals the same way. Sizing each bet as if it were alone over-levers the correlated book.
"""
from __future__ import annotations

import numpy as np

from eval.metrics import american_to_decimal


def full_kelly(p: float, decimal_odds: float) -> float:
    """Full-Kelly stake fraction for a single bet. Zero if there's no edge.

    f* = (p*d - 1) / (d - 1), where d is decimal odds. This is edge/odds; negative -> don't bet.
    """
    d = float(decimal_odds)
    if d <= 1.0:
        return 0.0
    f = (p * d - 1.0) / (d - 1.0)
    return max(f, 0.0)


def fractional_kelly(
    p: float,
    odds,
    fraction: float = 0.25,
    cap: float = 0.05,
    american: bool = True,
) -> float:
    """Quarter-Kelly (by default) stake as a fraction of bankroll, hard-capped.

    `fraction` scales full Kelly (0.25 = quarter-Kelly); `cap` is an absolute ceiling per bet.
    """
    d = american_to_decimal(odds) if american else float(odds)
    stake = fraction * full_kelly(p, d)
    return float(min(stake, cap))


def correlation_aware_sizes(
    p: np.ndarray,
    odds,
    corr: np.ndarray,
    fraction: float = 0.25,
    cap_total: float = 0.20,
    american: bool = True,
) -> np.ndarray:
    """Simultaneous-bet sizing accounting for outcome correlation.

    Uses the continuous multivariate-Kelly approximation f* = Sigma^{-1} mu, where mu is the vector
    of per-bet expected returns and Sigma is the covariance of bet returns implied by `corr` and
    each bet's Bernoulli variance. Result is scaled by `fraction`, floored at 0 (no shorting a
    book you can't short), and rescaled so the total staked never exceeds `cap_total`.

    p    : win probabilities, shape (n,)
    odds : American (default) or decimal odds, shape (n,)
    corr : (n, n) correlation matrix of the bet OUTCOMES (win/loss), symmetric, unit diagonal.
    """
    p = np.asarray(p, dtype=float)
    n = p.size
    dec = np.array([american_to_decimal(o) if american else float(o) for o in np.atleast_1d(odds)])
    b = dec - 1.0                                   # net decimal payout on a win

    mu = p * dec - 1.0                              # expected return per unit staked
    # Return of a unit bet is +b on win (prob p), -1 on loss. Variance:
    var = p * (1.0 - p) * (b + 1.0) ** 2            # = p(1-p) d^2
    sd = np.sqrt(np.maximum(var, 1e-12))

    corr = np.asarray(corr, dtype=float)
    Sigma = corr * np.outer(sd, sd)
    Sigma += np.eye(n) * 1e-9                       # ridge for numerical stability

    try:
        f = np.linalg.solve(Sigma, mu)
    except np.linalg.LinAlgError:
        f = mu / np.diag(Sigma)                     # fall back to independent sizing

    f = np.maximum(f, 0.0) * fraction               # no negative stakes; apply fractional-Kelly
    total = f.sum()
    if total > cap_total and total > 0:
        f *= cap_total / total                      # respect the total-exposure cap
    return f
