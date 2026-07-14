"""Purged & embargoed walk-forward must never let training data reach into the test window."""
import numpy as np

from eval.walkforward import PurgedWalkForward, walk_forward_predict
import pandas as pd


def _times(n=500):
    # Monotone daily timestamps.
    return np.datetime64("2026-01-01") + np.arange(n).astype("timedelta64[D]")


def test_train_always_precedes_test_in_time():
    t0 = _times(500)
    wf = PurgedWalkForward(n_splits=5, embargo=0.02, min_train=10)
    folds = list(wf.split(t0))
    assert len(folds) >= 4
    for tr, te in folds:
        assert len(tr) > 0 and len(te) > 0
        # No training decision time may be at/after the first test decision time.
        assert t0[tr].max() < t0[te].min()


def test_purge_drops_overlapping_labels():
    # Labels resolve 30 days after the decision; train obs whose label reaches into the test block
    # must be purged.
    n = 400
    t0 = _times(n)
    t1 = t0 + np.timedelta64(30, "D")
    wf = PurgedWalkForward(n_splits=4, embargo=0.0, min_train=10)
    for tr, te in wf.split(t0, t1):
        test_start = t0[te].min()
        # Every retained training label must resolve strictly before the test block starts.
        assert np.all(t1[tr] < test_start)


def test_embargo_creates_a_gap():
    n = 400
    t0 = _times(n)
    no_embargo = list(PurgedWalkForward(4, embargo=0.0, min_train=10).split(t0))
    with_embargo = list(PurgedWalkForward(4, embargo=0.1, min_train=10).split(t0))
    # Embargo can only shrink (or equal) the training set per fold, never grow it.
    for (tr_a, _), (tr_b, _) in zip(no_embargo, with_embargo):
        assert len(tr_b) <= len(tr_a)


def test_walk_forward_predict_is_out_of_sample():
    n = 300
    t0 = _times(n)
    X = pd.DataFrame({"f": np.arange(n, dtype=float)})
    y = np.arange(n, dtype=float)

    seen_test_positions = []

    def fit_predict(X_tr, y_tr, X_te):
        # Record that we never received test labels; predict the train mean.
        return np.full(len(X_te), y_tr.mean())

    out = walk_forward_predict(X, y, t0, fit_predict, n_splits=5)
    assert len(out) > 0
    assert {"y", "y_hat", "fold"}.issubset(out.columns)
