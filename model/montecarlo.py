"""Possession-level Monte Carlo for the 2nd half.

Simulate the 2nd half possession-by-possession, conditioned on the lineup on the floor, pace, and
foul state; 10k sims -> a real distribution of 2H totals. Closer to what sharp shops do than any
single regression, and it gives you the full shape (hence P(2H > line) and any prop) for free.

This is a clean, dependency-light engine. Feed it per-possession scoring rates you trust
(calibrated from the collector); the availability/foul-trouble deltas from `intel/` shift those
rates before you simulate.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class HalfSimConfig:
    home_ppp: float          # home points per possession (2H)
    away_ppp: float          # away points per possession (2H)
    home_poss: float         # expected home possessions remaining in the 2H
    away_poss: float         # expected away possessions remaining in the 2H
    ppp_sd: float = 0.9      # per-possession scoring noise (points)
    poss_sd: float = 3.0     # game-to-game noise in possession count


def simulate_second_half(cfg: HalfSimConfig, n_sims: int = 10_000, seed: int | None = 0) -> np.ndarray:
    """Return an array of simulated 2H totals (home + away points), length n_sims.

    Each sim draws a possession count per team (Normal, floored at 0) and sums per-possession
    outcomes drawn as Normal(ppp, ppp_sd). Simple, fast, and honest about variance — swap in a
    richer per-possession model (make/miss, FT, TOV) without changing the interface.
    """
    rng = np.random.default_rng(seed)
    totals = np.empty(n_sims)
    for i in range(n_sims):
        hp = max(int(round(rng.normal(cfg.home_poss, cfg.poss_sd))), 0)
        ap = max(int(round(rng.normal(cfg.away_poss, cfg.poss_sd))), 0)
        home_pts = rng.normal(cfg.home_ppp, cfg.ppp_sd, size=hp).clip(min=0).sum() if hp else 0.0
        away_pts = rng.normal(cfg.away_ppp, cfg.ppp_sd, size=ap).clip(min=0).sum() if ap else 0.0
        totals[i] = home_pts + away_pts
    return totals


def prob_over(totals: np.ndarray, line: float) -> float:
    """Empirical P(2H total > line) from the simulated distribution."""
    totals = np.asarray(totals, float)
    return float(np.mean(totals > line))


def distribution_summary(totals: np.ndarray) -> dict:
    totals = np.asarray(totals, float)
    return {
        "mean": float(totals.mean()),
        "sd": float(totals.std(ddof=1)),
        "p05": float(np.quantile(totals, 0.05)),
        "p50": float(np.quantile(totals, 0.50)),
        "p95": float(np.quantile(totals, 0.95)),
    }
