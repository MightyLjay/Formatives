"""Bootstrap confidence intervals on ROI, and month-by-month stability.

A real edge is stable. On the NBA control the best threshold swung from -9% to +27% season to
season — noise, not edge. These helpers put an honest interval around ROI and expose the
month/season breakdown so a swinging series can't masquerade as a system.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import profit_per_unit, roi


@dataclass
class BootstrapCI:
    point: float
    lo: float
    hi: float
    level: float
    n: int


def roi_bootstrap_ci(
    won,
    american: float = -110.0,
    n_boot: int = 5000,
    level: float = 0.95,
    seed: int | None = 0,
) -> BootstrapCI:
    """Percentile-bootstrap CI for ROI over a set of graded bets."""
    won = np.asarray(won, dtype=float)
    n = won.size
    if n == 0:
        return BootstrapCI(0.0, 0.0, 0.0, level, 0)
    pnl = profit_per_unit(won, american)
    rng = np.random.default_rng(seed)
    boot = rng.choice(pnl, size=(n_boot, n), replace=True).mean(axis=1)
    a = (1.0 - level) / 2.0
    lo, hi = np.quantile(boot, [a, 1.0 - a])
    return BootstrapCI(point=float(pnl.mean()), lo=float(lo), hi=float(hi), level=level, n=n)


def monthly_stability(won, timestamps, american: float = -110.0, freq: str = "ME") -> pd.DataFrame:
    """ROI and bet count grouped by period. `freq` is a pandas offset alias (default month-end).

    Returns a DataFrame indexed by period with columns [n, win_rate, roi]. A stable edge shows a
    tight band of positive ROI here; a swinging one does not.
    """
    won = np.asarray(won, dtype=float)
    ts = pd.to_datetime(pd.Series(timestamps)).reset_index(drop=True)
    df = pd.DataFrame({"won": won, "ts": ts})
    out = (
        df.groupby(df["ts"].dt.to_period(_period_from_freq(freq)))
        .apply(
            lambda g: pd.Series(
                {"n": len(g), "win_rate": g["won"].mean(), "roi": roi(g["won"].to_numpy(), american)}
            ),
            include_groups=False,
        )
    )
    return out


def _period_from_freq(freq: str) -> str:
    f = freq.upper()
    if f.startswith("M"):
        return "M"
    if f.startswith("Y") or f.startswith("A"):
        return "Y"
    if f.startswith("W"):
        return "W"
    if f.startswith("Q"):
        return "Q"
    return "M"
