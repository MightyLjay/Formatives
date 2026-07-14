"""The falsification statistics: BH, White/Hansen SPA, and the Deflated Sharpe Ratio.

The behavioural contract we care about: under a NO-EDGE null they must (almost always) fail to
reject, and under a STRONG real edge they must reject. These are the tests that keep the harness
honest about its own honesty.
"""
import numpy as np

from eval.deflated_sharpe import deflated_sharpe_ratio, probabilistic_sharpe_ratio
from eval.multiple_testing import benjamini_hochberg
from eval.reality_check import spa_test


def test_bh_all_null_rejects_few():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 200)  # uniform p-values under the null
    res = benjamini_hochberg(p, alpha=0.05)
    assert res.n_rejected <= 5  # a handful of false positives at most
    assert np.all((res.qvalues >= 0) & (res.qvalues <= 1))


def test_bh_detects_real_signal():
    # A block of tiny p-values (real signals) mixed into a sea of nulls.
    rng = np.random.default_rng(1)
    p = np.concatenate([rng.uniform(0, 1e-4, 10), rng.uniform(0, 1, 190)])
    res = benjamini_hochberg(p, alpha=0.05)
    assert res.n_rejected >= 10


def test_bh_known_example():
    # Worked example, n=10, alpha=0.05. Threshold at rank k is (k/n)*alpha:
    #   0.001 <= 0.005 (k=1) ok; 0.008 <= 0.010 (k=2) ok; 0.039 > 0.015 (k=3) fails.
    # Largest passing rank is k=2, so exactly the two smallest p-values are rejected.
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216])
    res = benjamini_hochberg(p, alpha=0.05)
    assert res.n_rejected == 2  # 0.001, 0.008
    assert res.rejected[0] and res.rejected[1]
    assert not res.rejected[2]


def test_spa_no_edge_high_pvalue():
    rng = np.random.default_rng(2)
    # 50 strategies, 400 periods, all mean-zero -> best-of-N is just luck.
    perf = rng.normal(0.0, 1.0, size=(400, 50))
    res = spa_test(perf, n_bootstrap=800, seed=3)
    assert res.spa_p > 0.10
    assert res.reality_check_p > 0.10


def test_spa_real_edge_low_pvalue():
    rng = np.random.default_rng(4)
    perf = rng.normal(0.0, 1.0, size=(400, 30))
    perf[:, 7] += 0.25  # one strategy has a genuine positive mean
    res = spa_test(perf, n_bootstrap=800, seed=5)
    assert res.spa_p < 0.05
    assert res.best_k == 7


def test_psr_monotonic_in_sharpe():
    rng = np.random.default_rng(6)
    weak = rng.normal(0.02, 1.0, 500)
    strong = rng.normal(0.20, 1.0, 500)
    assert probabilistic_sharpe_ratio(strong) > probabilistic_sharpe_ratio(weak)


def test_dsr_below_psr_under_many_trials():
    rng = np.random.default_rng(7)
    best = rng.normal(0.05, 1.0, 500)
    trial_sharpes = rng.normal(0.0, 0.05, 300)  # 300 trials -> meaningful deflation
    d = deflated_sharpe_ratio(best, trial_sharpes)
    assert d.sr_star > 0
    assert d.dsr <= d.psr  # deflation can only lower the probability
