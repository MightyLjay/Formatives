"""Pure data logic for the dashboard — NO Streamlit import, so it's unit-testable.

Three jobs:
  - live_market_snapshot: one live pull -> book quotes, fair line, ranked outliers.
  - load_snapshots:       read the collected time series from the append-only SQLite.
  - run_harness_analysis: the falsification harness on synthetic data, returned as structured
                          results (tables + verdicts) instead of printed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from collector import db as cdb
from eval.bootstrap import monthly_stability, roi_bootstrap_ci
from eval.deflated_sharpe import deflated_sharpe_ratio
from eval.demo import per_game_performance, simulate
from eval.metrics import BREAKEVEN_AT_MINUS_110, profit_per_unit, roi, sharpe
from eval.multiple_testing import benjamini_hochberg
from eval.reality_check import spa_test
from market.fair import FairLine, fair_line
from market.outliers import Opportunity, find_outliers


# ---------- live market ----------

@dataclass
class LiveSnapshot:
    event: dict
    quotes_df: pd.DataFrame
    fair: FairLine
    opportunities: pd.DataFrame
    has_sharp_anchor: bool


def live_market_snapshot(sport: str, market: str, regions: str, event_id: str | None = None) -> LiveSnapshot:
    """One live pull for a game: book quotes, fair line, ranked outliers. Needs ODDS_API_KEY.

    Raises on network/auth errors so the UI can show them. `event_id=None` uses the first event.
    """
    from market.providers import TheOddsAPIProvider  # lazy: needs `requests`

    prov = TheOddsAPIProvider(sport=sport, market=market, regions=regions)
    events = prov.list_events()
    if not events:
        raise RuntimeError(f"no events on the board for {sport!r} (off-season, or nothing scheduled)")
    ev = next((e for e in events if e.get("id") == event_id), events[0]) if event_id else events[0]

    quotes = prov.fetch(ev["id"])
    if not quotes:
        return LiveSnapshot(ev, pd.DataFrame(), None, pd.DataFrame(), False)

    fl = fair_line(quotes)
    opps = find_outliers(quotes, fl, min_gap=1.0)
    q_df = pd.DataFrame(
        [{"book": q.book, "line": q.line, "over": q.over_odds, "under": q.under_odds,
          "sharp": q.is_sharp} for q in quotes]
    ).sort_values("line").reset_index(drop=True)
    o_df = pd.DataFrame(
        [{"book": o.book, "side": o.side, "soft_line": o.soft_line, "gap_points": o.gap_points,
          "price": o.soft_price, "prob_edge": o.prob_edge} for o in opps]
    )
    return LiveSnapshot(ev, q_df, fl, o_df, has_sharp_anchor=any(q.is_sharp for q in quotes))


def list_live_events(sport: str, regions: str) -> list[dict]:
    from market.providers import TheOddsAPIProvider

    return TheOddsAPIProvider(sport=sport, regions=regions).list_events()


# ---------- collected time series ----------

SNAPSHOT_COLUMNS = ["game_id", "book", "market", "line", "over_odds", "under_odds",
                    "captured_at", "source", "captured_dt"]


def market_probability_series(game_df: pd.DataFrame, reference: float, sigma: float = 10.0) -> pd.DataFrame:
    """The MARKET's implied P(final total > `reference`) over time — NOT your edge.

    At each poll, the consensus line (median across books) is the market's own estimate of the final
    total. We model the final total as Normal(consensus, sigma) and read off P(> reference). As the
    game progresses the consensus drifts and this curve heads toward 0 or 1.

    HONESTY: this is the bookmaker's probability, reflected back. Betting the likely side at the
    book's price loses the vig — that is the entire lesson of FINDINGS.md. The edge is never here;
    it is in book *disagreement* (dispersion), the line *moving* before soft books react (steam), and
    *information* the line hasn't priced yet. `sigma` is uncalibrated shorthand, not a real forecast.
    """
    if game_df.empty:
        return pd.DataFrame(columns=["captured_at", "captured_dt", "consensus_line", "p_over_ref"])
    g = (game_df.groupby("captured_at")["line"].median().reset_index()
         .rename(columns={"line": "consensus_line"}))
    g["captured_dt"] = pd.to_datetime(g["captured_at"], unit="s")
    g["p_over_ref"] = 1.0 - stats.norm.cdf((reference - g["consensus_line"]) / max(sigma, 1e-6))
    return g


def load_snapshots(db_path: str) -> pd.DataFrame:
    """Load every stored snapshot as a DataFrame with a real datetime column, ordered by time.

    Returns an empty (typed) frame if the database doesn't exist yet — so the dashboard shows a
    friendly "run the monitor first" message instead of a scary error.
    """
    import os

    if db_path != ":memory:" and not os.path.exists(db_path):
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    conn = cdb.connect(db_path)
    df = pd.read_sql_query(
        "SELECT game_id, book, market, line, over_odds, under_odds, captured_at, source "
        "FROM snapshots ORDER BY captured_at",
        conn,
    )
    conn.close()
    if not df.empty:
        df["captured_dt"] = pd.to_datetime(df["captured_at"], unit="s")
    return df


# ---------- the falsification harness ----------

def run_harness_analysis(n_games: int = 4000, n_strategies: int = 60, inject_edge: bool = False) -> dict:
    """Run the harness on synthetic data and return structured results for charting.

    Mirrors eval.demo.run but returns dataframes + verdicts instead of printing.
    """
    df, strat_bets = simulate(n_games, n_strategies, inject_edge)

    rows, per_bet_profit, trial_sharpes = [], [], []
    for k, won in enumerate(strat_bets):
        w = won[~np.isnan(won)].astype(int)
        n = w.size
        if n < 30:
            per_bet_profit.append(np.array([]))
            continue
        wins = int(w.sum())
        p_binom = stats.binomtest(wins, n, BREAKEVEN_AT_MINUS_110, alternative="greater").pvalue
        pnl = profit_per_unit(w)
        rows.append({"strat": k, "n": n, "win_rate": float(w.mean()), "roi": roi(w), "p_binom": p_binom})
        per_bet_profit.append(pnl)
        trial_sharpes.append(sharpe(pnl))

    res = pd.DataFrame(rows).sort_values("roi", ascending=False).reset_index(drop=True)
    bh = benjamini_hochberg(res["p_binom"].to_numpy(), alpha=0.05)

    # Per-game performance matrix on the shared game index -> joint bootstrap, full sample.
    P = per_game_performance(strat_bets, n_games)
    spa = spa_test(P, n_bootstrap=1000, mean_block=10.0)

    best_k = int(res.iloc[0]["strat"])
    dsr = deflated_sharpe_ratio(per_bet_profit[best_k], trial_sharpes)

    best_won = strat_bets[best_k]
    m = ~np.isnan(best_won)
    ci = roi_bootstrap_ci(best_won[m].astype(int))
    stab = monthly_stability(best_won[m].astype(int), df["t0"].to_numpy()[m]).reset_index()
    stab["ts"] = stab["ts"].astype(str)

    killed = spa.spa_p >= 0.05
    return {
        "per_strategy": res,
        "n_strategies": len(res),
        "bh_rejected": bh.n_rejected,
        "spa_rc": spa.reality_check_p,
        "spa_p": spa.spa_p,
        "best_strat": best_k,
        "best_roi": ci.point,
        "ci_lo": ci.lo,
        "ci_hi": ci.hi,
        "dsr": dsr.dsr,
        "psr": dsr.psr,
        "sr_star": dsr.sr_star,
        "sharpe": dsr.sharpe,
        "monthly": stab,
        "spa_killed": killed,
        "breakeven": BREAKEVEN_AT_MINUS_110,
    }
