"""Purged & embargoed walk-forward cross-validation (Lopez de Prado, *Advances in ML Finance*).

Never `train_test_split`. Never shuffle. Two failure modes this guards against:

1. **Look-ahead across time.** Test always lies strictly in the future of train (expanding window).
2. **Label overlap / serial-correlation leakage at the fold boundary.** Each observation `i` is
   decided at time `t0[i]` (halftime) and its label resolves at `t1[i]` (game end). A training
   observation whose label window `[t0, t1]` reaches into the test period leaks — it is *purged*.
   A configurable *embargo* additionally drops training observations that sit just before the test
   block, where autocorrelation would otherwise bleed information backward.

The splitter yields integer positional index arrays and is agnostic to the estimator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np
import pandas as pd


@dataclass
class PurgedWalkForward:
    """Expanding-window walk-forward splitter with purge + embargo.

    Parameters
    ----------
    n_splits : number of sequential test folds.
    embargo : fraction of the total time span to embargo *before* each test block
        (0.0 disables). Expressed as a fraction so it scales with the dataset.
    min_train : minimum number of training observations required to emit a fold.
    """

    n_splits: int = 5
    embargo: float = 0.01
    min_train: int = 50

    def split(
        self, t0: np.ndarray | pd.Series, t1: np.ndarray | pd.Series | None = None
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Yield (train_idx, test_idx) positional arrays, ordered by decision time `t0`.

        `t0` : decision timestamps (when the bet is placed / features are known).
        `t1` : label-resolution timestamps (when the game ends). Defaults to `t0` (point labels).
        """
        t0 = _to_datetime_array(t0)
        t1 = t0.copy() if t1 is None else _to_datetime_array(t1)
        if t1.shape != t0.shape:
            raise ValueError("t0 and t1 must have the same length")
        if np.any(t1 < t0):
            raise ValueError("label end t1 must be >= decision time t0 for every observation")

        n = len(t0)
        order = np.argsort(t0, kind="mergesort")  # stable; positional order by decision time
        t0_s, t1_s = t0[order], t1[order]

        span = t0_s[-1] - t0_s[0]
        embargo_td = span * float(self.embargo) if span > np.timedelta64(0) else np.timedelta64(0)

        # Contiguous test blocks over the time-ordered observations.
        fold_bounds = np.array_split(np.arange(n), self.n_splits)
        for block in fold_bounds:
            if block.size == 0:
                continue
            test_start_time = t0_s[block[0]]

            # Train = everything decided strictly before the test block starts ...
            candidate = np.arange(block[0])
            if candidate.size == 0:
                continue
            # ... PURGE: drop train obs whose label resolves at/after the test block start.
            keep = t1_s[candidate] < test_start_time
            # ... EMBARGO: drop train obs within `embargo_td` before the test block start.
            if embargo_td > np.timedelta64(0):
                keep &= t0_s[candidate] < (test_start_time - embargo_td)
            train_local = candidate[keep]

            if train_local.size < self.min_train:
                continue

            yield order[train_local], order[block]


def walk_forward_predict(
    X: pd.DataFrame,
    y: np.ndarray,
    t0: np.ndarray,
    fit_predict,
    t1: np.ndarray | None = None,
    n_splits: int = 5,
    embargo: float = 0.01,
) -> pd.DataFrame:
    """Run a leakage-safe walk-forward and collect out-of-sample predictions.

    `fit_predict(X_tr, y_tr, X_te) -> y_hat_te` is any callable; it never sees test labels.
    Returns a DataFrame indexed by original position with columns [fold, y, y_hat, t0].
    """
    y = np.asarray(y)
    splitter = PurgedWalkForward(n_splits=n_splits, embargo=embargo)
    rows = []
    for fold, (tr, te) in enumerate(splitter.split(t0, t1)):
        y_hat = np.asarray(fit_predict(X.iloc[tr], y[tr], X.iloc[te]))
        for pos, yh in zip(te, y_hat):
            rows.append((fold, int(pos), y[pos], float(yh), t0[pos]))
    out = pd.DataFrame(rows, columns=["fold", "pos", "y", "y_hat", "t0"]).set_index("pos")
    return out.sort_index()


def _to_datetime_array(x) -> np.ndarray:
    if isinstance(x, pd.Series):
        x = x.to_numpy()
    arr = np.asarray(x)
    if np.issubdtype(arr.dtype, np.datetime64):
        return arr
    # Accept numeric "time index" too (e.g. game sequence numbers) by treating as days.
    if np.issubdtype(arr.dtype, np.number):
        return arr.astype("timedelta64[s]") + np.datetime64("1970-01-01")
    return pd.to_datetime(pd.Series(arr)).to_numpy()
