"""Sizing: Kelly formula, quarter-Kelly cap, and correlation-aware de-leveraging."""
import numpy as np

from exec.kelly import correlation_aware_sizes, fractional_kelly, full_kelly


def test_full_kelly_formula():
    # p=0.55 at even money (decimal 2.0): f* = (0.55*2 - 1)/(2-1) = 0.10.
    assert abs(full_kelly(0.55, 2.0) - 0.10) < 1e-12
    # No edge -> no bet.
    assert full_kelly(0.50, 2.0) == 0.0
    assert full_kelly(0.40, 2.0) == 0.0


def test_fractional_kelly_scales_and_caps():
    # Quarter of full Kelly, under the cap.
    q = fractional_kelly(0.55, +100, fraction=0.25, cap=1.0)
    assert abs(q - 0.025) < 1e-9
    # Cap bites when the raw stake is large.
    capped = fractional_kelly(0.90, +100, fraction=1.0, cap=0.05)
    assert capped == 0.05


def test_correlation_reduces_total_stake():
    p = np.array([0.55, 0.55, 0.55])
    odds = np.array([+100, +100, +100])
    indep = correlation_aware_sizes(p, odds, np.eye(3), fraction=0.25, cap_total=1.0)
    corr = 0.6 * np.ones((3, 3)) + 0.4 * np.eye(3)  # 0.6 pairwise correlation
    correlated = correlation_aware_sizes(p, odds, corr, fraction=0.25, cap_total=1.0)
    # Correlated bets on the same side should be sized DOWN in aggregate vs independent ones.
    assert correlated.sum() < indep.sum()
    assert np.all(correlated >= 0)


def test_total_exposure_cap_respected():
    p = np.array([0.7, 0.7, 0.7, 0.7])
    odds = np.array([+100, +100, +100, +100])
    sizes = correlation_aware_sizes(p, odds, np.eye(4), fraction=1.0, cap_total=0.2)
    assert sizes.sum() <= 0.2 + 1e-9
