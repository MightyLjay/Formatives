"""Distributional model + possession-level Monte Carlo produce valid P(2H > line)."""
import numpy as np

from model.distributional import NormalTotalModel, benchmark_against_line
from model.montecarlo import HalfSimConfig, distribution_summary, prob_over, simulate_second_half


def test_normal_model_prob_over_bounds_and_monotonic():
    m = NormalTotalModel(sigma=9.0)
    p_low = m.prob_over(100.0, 110.0)   # mean below line -> < 0.5
    p_mid = m.prob_over(110.0, 110.0)   # mean == line -> 0.5
    p_high = m.prob_over(120.0, 110.0)  # mean above line -> > 0.5
    assert 0.0 <= p_low < p_mid < p_high <= 1.0
    assert abs(p_mid - 0.5) < 1e-9


def test_normal_model_fits_sigma_from_residuals():
    rng = np.random.default_rng(0)
    mean_pred = rng.normal(105, 5, 2000)
    actual = mean_pred + rng.normal(0, 7.0, 2000)
    m = NormalTotalModel().fit(mean_pred, actual)
    assert 6.0 < m.sigma < 8.0  # recovers the ~7-point residual sd


def test_benchmark_against_line_reports_loglosses():
    rng = np.random.default_rng(1)
    n = 3000
    over_hit = rng.integers(0, 2, n)
    p_model = np.clip(over_hit * 0.6 + 0.2 + rng.normal(0, 0.05, n), 0.01, 0.99)
    p_line = np.full(n, 0.5)
    out = benchmark_against_line(p_model, over_hit, p_line)
    assert "model_log_loss" in out and "line_log_loss" in out
    assert isinstance(out["model_beats_line"], bool)


def test_montecarlo_distribution_and_prob_over():
    cfg = HalfSimConfig(home_ppp=1.02, away_ppp=0.98, home_poss=33, away_poss=33)
    totals = simulate_second_half(cfg, n_sims=4000, seed=0)
    summ = distribution_summary(totals)
    # Expected 2H total ~ 33*1.02 + 33*0.98 = 66.
    assert 60 < summ["mean"] < 72
    p = prob_over(totals, summ["mean"])
    assert 0.3 < p < 0.7  # the mean sits near the median of a roughly symmetric distribution
    assert prob_over(totals, 1e6) == 0.0
    assert prob_over(totals, -1e6) == 1.0
