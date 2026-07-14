"""The kill criteria are executable and they bite: a no-edge world gets killed."""
import numpy as np

from eval.kill import clv_kill, run_kill_checks, spa_kill


def test_clv_kill_waits_for_enough_snapshots():
    d = clv_kill(np.random.default_rng(0).normal(0, 1, 100), min_n=500)
    assert d.killed is False
    assert "not yet decisive" in d.reason


def test_clv_kill_fires_on_zero_clv():
    clv = np.random.default_rng(1).normal(0.0, 1.0, 600)  # true CLV = 0
    d = clv_kill(clv, min_n=500)
    assert d.killed is True
    assert "no CLV" in d.reason


def test_clv_kill_survives_positive_clv():
    clv = np.random.default_rng(2).normal(0.15, 1.0, 600)  # solidly positive CLV
    d = clv_kill(clv, min_n=500)
    assert d.killed is False


def test_spa_kill_fires_on_no_edge():
    perf = np.random.default_rng(3).normal(0.0, 1.0, size=(400, 100))
    d = spa_kill(perf, n_bootstrap=600)
    assert d.killed is True


def test_run_kill_checks_returns_nonzero_when_killed():
    clv = np.random.default_rng(4).normal(0.0, 1.0, 600)
    perf = np.random.default_rng(5).normal(0.0, 1.0, size=(300, 80))
    code = run_kill_checks(clv_values=clv, strategy_perf=perf)
    assert code == 1  # KILL
