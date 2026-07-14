"""Scoring primitives. Everything downstream (CLV, ROI, log-loss) is defined here once.

Conventions
-----------
- A *bet* has an American price (default -110) and a boolean `won`.
- ROI is profit per unit staked. At -110, a win returns +100/110 units, a loss returns -1.
- Probabilistic forecasts are scored by log-loss and Brier; calibration is what we bet on.
"""
from __future__ import annotations

import numpy as np

BREAKEVEN_AT_MINUS_110 = 110.0 / 210.0  # 0.5238... — the vig line you must clear.


def american_to_decimal(american: float) -> float:
    """American odds -> decimal odds (payout multiple incl. stake)."""
    american = float(american)
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def american_to_prob(american: float) -> float:
    """American odds -> implied probability (with vig; not de-vigged)."""
    return 1.0 / american_to_decimal(american)


def profit_per_unit(won: np.ndarray, american: float | np.ndarray = -110.0) -> np.ndarray:
    """Per-bet profit in units of stake. Win -> (decimal-1), loss -> -1."""
    won = np.asarray(won, dtype=float)
    dec = np.vectorize(american_to_decimal)(np.broadcast_to(american, won.shape))
    return np.where(won > 0, dec - 1.0, -1.0)


def roi(won: np.ndarray, american: float | np.ndarray = -110.0) -> float:
    """Mean profit per unit staked. Positive means you beat the vig."""
    pnl = profit_per_unit(won, american)
    if pnl.size == 0:
        return 0.0
    return float(np.mean(pnl))


def win_rate(won: np.ndarray) -> float:
    won = np.asarray(won, dtype=float)
    return float(np.mean(won)) if won.size else 0.0


def log_loss(y_true: np.ndarray, p: np.ndarray, eps: float = 1e-12) -> float:
    """Binary log-loss (natural log). Lower is better; the benchmark is the closing line's."""
    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(p, dtype=float), eps, 1.0 - eps)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def brier(y_true: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    return float(np.mean((p - y) ** 2))


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(y_true, float) - np.asarray(y_pred, float))))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    d = np.asarray(y_true, float) - np.asarray(y_pred, float)
    return float(np.sqrt(np.mean(d * d)))


def sharpe(returns: np.ndarray, ddof: int = 1) -> float:
    """Sharpe ratio of a per-bet (or per-period) return series. Not annualized."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    sd = r.std(ddof=ddof)
    if sd == 0:
        return 0.0
    return float(r.mean() / sd)
