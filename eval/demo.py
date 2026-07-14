"""End-to-end run of the falsification harness on synthetic data.

Mirrors the NBA control story: a "model" that ties the closing line, a hunt across many strategies,
and a harness that refuses to be fooled. By default the synthetic world has NO edge (the market is
unbiased), so nothing should survive — and the harness says so, with p-values.

    python -m eval.demo            # honest no-edge world; harness finds nothing (as it should)
    python -m eval.demo --edge     # inject one tiny real edge; watch the harness isolate it

Every number printed carries a p-value or an interval. A backtest without one is a story.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy import stats

from .bootstrap import monthly_stability, roi_bootstrap_ci
from .deflated_sharpe import deflated_sharpe_ratio
from .kill import run_kill_checks
from .metrics import BREAKEVEN_AT_MINUS_110, profit_per_unit, roi, sharpe
from .multiple_testing import benjamini_hochberg
from .reality_check import spa_test
from .walkforward import PurgedWalkForward


def simulate(n_games: int = 4000, n_strategies: int = 60, inject_edge: bool = False, seed: int = 1):
    """A season-like stream of 2H totals. The market is unbiased; strategies are noise signals.

    Returns (df, strat_bets) where strat_bets[k] is a boolean 'won' array for strategy k.
    """
    rng = np.random.default_rng(seed)
    # Games spread over ~5 months.
    t0 = np.sort(np.datetime64("2026-01-01") + rng.integers(0, 150, n_games).astype("timedelta64[D]"))
    closing_line = rng.normal(104.0, 6.0, n_games)
    # Market is unbiased: actual 2H total = line + mean-zero noise.
    actual = closing_line + rng.normal(0.0, 9.0, n_games)
    over_hit = (actual > closing_line).astype(int)

    df = pd.DataFrame({"t0": t0, "line": closing_line, "actual": actual, "over": over_hit})

    # Each strategy is a random noise "signal" that selects games and a side to bet. All null.
    strat_bets = []
    for k in range(n_strategies):
        sig = rng.normal(0.0, 1.0, n_games)          # a pure-noise feature
        thr = rng.uniform(0.5, 1.5)
        pick_over = sig > thr
        pick_under = sig < -thr
        bet_mask = pick_over | pick_under
        side_over = pick_over
        # Did the bet win? over bet wins if over_hit; under bet wins if not.
        won = np.where(side_over, over_hit == 1, over_hit == 0)
        won = np.where(bet_mask, won, np.nan)        # NaN where no bet
        strat_bets.append(won)

    if inject_edge:
        # One strategy with a genuine, comfortably-significant edge on the games it selects.
        sig = rng.normal(0.0, 1.0, n_games)
        bet_mask = sig > 0.5
        true_win = rng.random(n_games) < 0.58
        won = np.where(bet_mask, true_win.astype(float), np.nan)
        strat_bets[0] = won  # replace strategy 0

    return df, strat_bets


def run(n_games=4000, n_strategies=60, inject_edge=False):
    df, strat_bets = simulate(n_games, n_strategies, inject_edge)

    print("=" * 72)
    print(f"Falsification harness — synthetic world  (edge injected: {inject_edge})")
    print(f"{n_games} games, {n_strategies} strategies hunted. Breakeven at -110 = "
          f"{BREAKEVEN_AT_MINUS_110:.4f}")
    print("=" * 72)

    # --- 0. Leakage-safe walk-forward split (demonstrated on the market itself) ---
    wf = PurgedWalkForward(n_splits=5, embargo=0.01)
    folds = list(wf.split(df["t0"].to_numpy()))
    print(f"\n[walk-forward] {len(folds)} purged & embargoed folds; "
          f"train sizes {[len(tr) for tr, _ in folds]}, test sizes {[len(te) for _, te in folds]}")
    # Verify no train observation's time reaches into its test window (leakage check).
    leaked = 0
    for tr, te in folds:
        if len(tr) and len(te):
            if df["t0"].to_numpy()[tr].max() >= df["t0"].to_numpy()[te].min():
                leaked += 1
    print(f"[walk-forward] folds with train/test time overlap: {leaked} (must be 0)")

    # --- 1. Per-strategy ROI, binomial p-value, per-bet excess-return series ---
    rows = []
    perf_cols = []          # per-bet performance (profit at -110), aligned by padding, for SPA
    trial_sharpes = []
    max_len = 0
    per_bet_profit = []
    for k, won in enumerate(strat_bets):
        mask = ~np.isnan(won)
        w = won[mask].astype(int)
        n = w.size
        if n < 30:
            per_bet_profit.append(np.array([]))
            continue
        wins = int(w.sum())
        r = roi(w)
        # One-sided binomial test: is win rate > breakeven?
        p_binom = stats.binomtest(wins, n, BREAKEVEN_AT_MINUS_110, alternative="greater").pvalue
        pnl = profit_per_unit(w)
        rows.append((k, n, w.mean(), r, p_binom))
        per_bet_profit.append(pnl)
        trial_sharpes.append(sharpe(pnl))
        max_len = max(max_len, n)

    res = pd.DataFrame(rows, columns=["strat", "n", "win_rate", "roi", "p_binom"]).sort_values("roi", ascending=False)
    print("\n[per-strategy] top 5 by ROI (this is the seductive table — read the p-values):")
    with pd.option_context("display.float_format", lambda v: f"{v:.4f}"):
        print(res.head(5).to_string(index=False))

    # --- 2. Benjamini-Hochberg across every strategy's binomial p-value ---
    bh = benjamini_hochberg(res["p_binom"].to_numpy(), alpha=0.05)
    print(f"\n[Benjamini-Hochberg] strategies surviving FDR<0.05: {bh.n_rejected} / {len(res)}")

    # --- 3. White's Reality Check / Hansen SPA on the best of N ---
    # Build a (T, K) performance matrix; pad shorter series by resampling to a common length.
    valid = [p for p in per_bet_profit if p.size >= 30]
    K = len(valid)
    T = min(min(p.size for p in valid), 800)
    rng = np.random.default_rng(0)
    P = np.column_stack([rng.choice(p, size=T, replace=True) for p in valid])
    spa = spa_test(P, n_bootstrap=1000, mean_block=10.0)
    print(f"\n[Reality Check / SPA]  best-of-{K} strategies")
    print(f"    White's Reality Check p = {spa.reality_check_p:.3f}")
    print(f"    Hansen SPA_c        p = {spa.spa_p:.3f}   (H0: best strategy has no edge)")

    # --- 4. Deflated Sharpe Ratio on the best strategy ---
    best_k = int(res.iloc[0]["strat"])
    best_pnl = per_bet_profit[best_k]
    dsr = deflated_sharpe_ratio(best_pnl, trial_sharpes)
    print(f"\n[Deflated Sharpe] best strategy SR={dsr.sharpe:.3f}, deflated benchmark SR*={dsr.sr_star:.3f}")
    print(f"    PSR (vs 0) = {dsr.psr:.3f}   DSR (vs {dsr.n_trials} trials) = {dsr.dsr:.3f}")

    # --- 5. Bootstrap CI on ROI + month-by-month stability of the best strategy ---
    best_won = strat_bets[best_k]
    m = ~np.isnan(best_won)
    ci = roi_bootstrap_ci(best_won[m].astype(int))
    print(f"\n[bootstrap] best strategy ROI = {ci.point:+.4f}  "
          f"95% CI [{ci.lo:+.4f}, {ci.hi:+.4f}]  (n={ci.n})")
    stab = monthly_stability(best_won[m].astype(int), df["t0"].to_numpy()[m])
    print("[stability] month-by-month ROI (a real edge is stable; noise swings):")
    with pd.option_context("display.float_format", lambda v: f"{v:.3f}"):
        print(stab.to_string())

    # --- 6. The kill criteria have the final word ---
    print("\n" + "-" * 72)
    print("KILL CRITERIA")
    print("-" * 72)
    # CLV proxy: with no real book, use per-bet excess return over breakeven as a stand-in signal.
    clv_proxy = np.concatenate([p for p in per_bet_profit if p.size]) if per_bet_profit else np.array([])
    code = run_kill_checks(clv_values=clv_proxy, strategy_perf=P)
    print("\n(Exit code from kill checks:", code, "— non-zero means the project is killed.)")
    return code


def main():
    ap = argparse.ArgumentParser(description="run the falsification harness on synthetic data")
    ap.add_argument("--edge", action="store_true", help="inject one genuine edge to show detection")
    ap.add_argument("--games", type=int, default=4000)
    ap.add_argument("--strategies", type=int, default=60)
    args = ap.parse_args()
    run(n_games=args.games, n_strategies=args.strategies, inject_edge=args.edge)


if __name__ == "__main__":
    main()
