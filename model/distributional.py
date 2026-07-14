"""Distributional baseline: predict P(2H > line), not E[2H points].

A point estimate throws away the shape of the distribution — which is the entire thing you're
betting on. The honest baseline here models 2H points as Normal(mu, sigma) and reports the tail
probability at the line. `sigma` is fit from out-of-sample residuals so the interval means what it
says. Calibration is what you bet on; benchmark against the closing line's log-loss, nothing else.

Heavier options (NGBoost, LightGBM quantile loss, CatBoost multiquantile, conformal via `mapie`)
slot in behind the same `prob_over` interface — they are in requirements-extra.txt and imported
lazily so the tested core stays dependency-light.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from eval.metrics import log_loss


@dataclass
class NormalTotalModel:
    """2H points ~ Normal(mean_pred, sigma). `sigma` is estimated from residuals via `fit`."""

    sigma: float = 9.0

    def fit(self, mean_pred: np.ndarray, actual: np.ndarray) -> "NormalTotalModel":
        resid = np.asarray(actual, float) - np.asarray(mean_pred, float)
        # ddof=1; floor to avoid a degenerate zero-variance model.
        self.sigma = float(max(resid.std(ddof=1), 1e-6))
        return self

    def prob_over(self, mean_pred, line) -> np.ndarray:
        """P(2H points > line) under Normal(mean_pred, sigma)."""
        mean_pred = np.asarray(mean_pred, float)
        line = np.asarray(line, float)
        z = (mean_pred - line) / self.sigma
        return stats.norm.cdf(z)

    def prob_under(self, mean_pred, line) -> np.ndarray:
        return 1.0 - self.prob_over(mean_pred, line)


def benchmark_against_line(
    p_over_model: np.ndarray,
    over_hit: np.ndarray,
    p_over_line: np.ndarray,
) -> dict:
    """Compare the model's P(over) calibration to the closing line's, by log-loss.

    `over_hit` is 1 if the 2H total went over. `p_over_line` is the market's implied (de-vigged)
    P(over) from the closing 2H number. The model only earns its keep if it beats this.
    """
    return {
        "model_log_loss": log_loss(over_hit, p_over_model),
        "line_log_loss": log_loss(over_hit, p_over_line),
        "model_beats_line": bool(log_loss(over_hit, p_over_model) < log_loss(over_hit, p_over_line)),
    }
