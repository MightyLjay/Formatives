"""Executable kill criteria. These are checks, not opinions — they exit non-zero to stop the project.

    - 500 graded snapshots, CLV not positive        -> KILL: no CLV
    - Best strategy fails Hansen SPA at p < 0.05     -> KILL: not significant

"But it was profitable in the backtest" is exactly what noise looks like. The check does not care.

Run `python -m eval.kill` (or `make kill`). With no real data wired in it runs on a synthetic
NO-EDGE series, so the gate *should* fire — that is the mechanism proving itself, not a bug.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np

from .bootstrap import roi_bootstrap_ci  # noqa: F401  (kept for parity of CI-style checks)
from .reality_check import spa_test

MIN_GRADED_SNAPSHOTS = 500
SPA_ALPHA = 0.05


@dataclass
class KillDecision:
    name: str
    killed: bool
    reason: str

    def line(self) -> str:
        tag = "KILL" if self.killed else "OK  "
        return f"[{tag}] {self.name}: {self.reason}"


def clv_kill(clv_values, min_n: int = MIN_GRADED_SNAPSHOTS, level: float = 0.95) -> KillDecision:
    """CLV is the primary metric. Once we have >= min_n graded snapshots, CLV must be positive.

    `clv_values` are per-bet closing-line-value numbers (points beaten, or de-vigged prob edge).
    We require the bootstrap CI lower bound to sit at or above zero — a positive point estimate
    that straddles zero is not evidence.
    """
    clv = np.asarray(clv_values, dtype=float)
    n = clv.size
    if n < min_n:
        return KillDecision("CLV", False, f"only {n}/{min_n} graded snapshots — not yet decisive")

    rng = np.random.default_rng(0)
    boot = rng.choice(clv, size=(5000, n), replace=True).mean(axis=1)
    lo = float(np.quantile(boot, (1.0 - level) / 2.0))
    mean = float(clv.mean())
    if mean <= 0 or lo <= 0:
        return KillDecision(
            "CLV", True, f"no CLV: mean={mean:+.4f}, {int(level*100)}% CI lower={lo:+.4f} <= 0"
        )
    return KillDecision("CLV", False, f"CLV positive: mean={mean:+.4f}, CI lower={lo:+.4f}")


def spa_kill(perf, alpha: float = SPA_ALPHA, n_bootstrap: int = 2000) -> KillDecision:
    """The best of the N tested strategies must beat luck on Hansen's SPA test."""
    res = spa_test(perf, n_bootstrap=n_bootstrap)
    if res.spa_p >= alpha:
        return KillDecision(
            "SPA", True,
            f"not significant: best strategy SPA p={res.spa_p:.3f} >= {alpha} "
            f"(RC p={res.reality_check_p:.3f})",
        )
    return KillDecision(
        "SPA", False, f"best strategy significant: SPA p={res.spa_p:.3f} < {alpha}"
    )


def run_kill_checks(clv_values=None, strategy_perf=None) -> int:
    """Run every wired check. Returns a process exit code (0 = survive, 1 = KILL)."""
    decisions: list[KillDecision] = []
    if clv_values is not None:
        decisions.append(clv_kill(clv_values))
    if strategy_perf is not None:
        decisions.append(spa_kill(strategy_perf))

    if not decisions:
        print("no checks wired — pass clv_values and/or strategy_perf")
        return 0

    for d in decisions:
        print(d.line())
    killed = any(d.killed for d in decisions)
    print("\n=> " + ("PROJECT KILLED — stop and understand why." if killed else "survives, for now."))
    return 1 if killed else 0


def _synthetic_no_edge():
    """A no-edge world: CLV centred on zero, strategies that only look good by luck."""
    rng = np.random.default_rng(0)
    clv = rng.normal(0.0, 1.0, size=600)                 # 600 snapshots, true CLV = 0
    perf = rng.normal(0.0, 1.0, size=(400, 200))         # 200 strategies, 400 bets, all null
    return clv, perf


if __name__ == "__main__":
    print("eval.kill — running on a SYNTHETIC no-edge world (the gate should fire):\n")
    clv, perf = _synthetic_no_edge()
    sys.exit(run_kill_checks(clv_values=clv, strategy_perf=perf))
