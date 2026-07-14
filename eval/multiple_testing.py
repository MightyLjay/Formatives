"""Multiple-testing correction. The more strategies you test, the more spurious "edges" appear.

On the NBA control run, three edge thresholds showed positive ROI and every one was noise. With
full power you test hundreds. Benjamini-Hochberg controls the false-discovery rate across a whole
family of strategies at once; use it on every p-value you generate, not just your favourite.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BHResult:
    pvalues: np.ndarray          # original, in input order
    qvalues: np.ndarray          # BH-adjusted, in input order
    rejected: np.ndarray         # bool, in input order
    alpha: float
    n_rejected: int


def benjamini_hochberg(pvalues, alpha: float = 0.05) -> BHResult:
    """Benjamini-Hochberg FDR control.

    Returns adjusted q-values and a rejection mask at level `alpha`. q-values are the standard
    step-up adjusted p-values (monotone, in [0, 1]).
    """
    p = np.asarray(pvalues, dtype=float)
    n = p.size
    if n == 0:
        return BHResult(p, p.copy(), np.zeros(0, dtype=bool), alpha, 0)

    order = np.argsort(p, kind="mergesort")
    ranks = np.arange(1, n + 1)
    p_sorted = p[order]

    # Adjusted p-values via the cumulative-min-from-the-top step-up procedure.
    q_sorted = np.minimum.accumulate((p_sorted * n / ranks)[::-1])[::-1]
    q_sorted = np.clip(q_sorted, 0.0, 1.0)

    # Rejection: largest k with p_(k) <= (k/n) * alpha, reject all up to k.
    below = p_sorted <= (ranks / n) * alpha
    if below.any():
        kmax = np.max(np.nonzero(below)[0])
        reject_sorted = np.arange(n) <= kmax
    else:
        reject_sorted = np.zeros(n, dtype=bool)

    q = np.empty(n)
    reject = np.empty(n, dtype=bool)
    q[order] = q_sorted
    reject[order] = reject_sorted
    return BHResult(p, q, reject, alpha, int(reject.sum()))
