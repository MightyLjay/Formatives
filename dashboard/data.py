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
from eval.metrics import profit_per_unit, roi
from market.clv import points_clv
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


# ---------- edge checker & paper bets (the "1xbet vs our fair line" workflow) ----------

def recommend_bet(fair_line: float, your_line: float, over_odds: float = -110.0,
                  under_odds: float = -110.0, sigma: float = 10.0,
                  min_prob_edge: float = 0.02) -> dict:
    """Compare a line YOU saw (e.g. on 1xbet) to our fair line and say BET or PASS.

    If your book's number sits above fair, its UNDER is generous; below fair, its OVER is. We model
    the outcome as Normal(fair, sigma) to turn the points gap into an estimated win probability, then
    subtract the price you'd pay. Positive `prob_edge` beyond a threshold => a bet. This is an EV
    estimate against OUR fair line — only as trustworthy as that fair line (needs a sharp anchor).
    """
    from eval.metrics import american_to_prob

    diff = your_line - fair_line
    if diff >= 0:
        side, price = "under", under_odds
    else:
        side, price = "over", over_odds
    z = diff / max(sigma, 1e-6)
    p_win = float(stats.norm.cdf(z)) if side == "under" else float(1.0 - stats.norm.cdf(z))
    prob_edge = p_win - american_to_prob(price)
    return {
        "side": side, "your_line": float(your_line), "fair_line": float(fair_line),
        "edge_points": abs(diff), "price": float(price), "p_win": p_win,
        "prob_edge": prob_edge, "verdict": "BET" if prob_edge >= min_prob_edge else "PASS",
    }


def log_paper_bet(db_path: str, **fields) -> int:
    conn = cdb.connect(db_path)
    rid = cdb.insert_paper_bet(conn, **fields)
    conn.close()
    return rid


PAPER_COLUMNS = ["id", "game_id", "matchup", "market", "book", "side", "your_line", "your_odds",
                 "fair_line", "edge_points", "prob_edge", "placed_at", "closing_line",
                 "final_total", "result", "pnl"]


def load_paper_bets(db_path: str) -> pd.DataFrame:
    import os

    if db_path != ":memory:" and not os.path.exists(db_path):
        return pd.DataFrame(columns=PAPER_COLUMNS)
    conn = cdb.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM paper_bets ORDER BY placed_at DESC", conn)
    conn.close()
    if not df.empty:
        df["placed_dt"] = pd.to_datetime(df["placed_at"], unit="s")
    return df


def paper_bet_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n": 0, "avg_edge_points": 0.0, "avg_prob_edge": 0.0, "graded": 0, "roi": None}
    graded = df[df["result"].isin(["win", "loss"])]
    return {
        "n": len(df),
        "avg_edge_points": float(df["edge_points"].mean()),
        "avg_prob_edge": float(df["prob_edge"].dropna().mean()) if df["prob_edge"].notna().any() else 0.0,
        "graded": len(graded),
        "roi": float(graded["pnl"].mean()) if len(graded) and graded["pnl"].notna().any() else None,
    }


# ---------- CLV & results ----------

def fetch_final_totals(sport: str, days_from: int = 3, regions: str = "us,us2") -> dict[str, float]:
    """{event_id: final_total} for completed games, via The Odds API /scores. Needs ODDS_API_KEY."""
    from market.providers import TheOddsAPIProvider

    prov = TheOddsAPIProvider(sport=sport, regions=regions)
    out: dict[str, float] = {}
    for g in prov.list_scores(days_from=days_from):
        if g.get("completed") and g.get("scores"):
            try:
                out[g["id"]] = float(sum(float(s["score"]) for s in g["scores"]))
            except (TypeError, ValueError, KeyError):
                continue
    return out


def _pick_for_game(game_df: pd.DataFrame, min_gap: float = 1.5) -> dict | None:
    """The earliest outlier 'pick' for one game+market, and its CLV vs the closing consensus.

    Pure book-shopping: at the first poll where a book sits >= min_gap off the consensus, we 'bet'
    that book's generous side at its line. CLV compares that entry line to the closing consensus.
    Needs NO final score — CLV is computable from the line time series alone (the fast, low-variance
    signal). Returns None if no book was ever far enough off the consensus.
    """
    if game_df.empty:
        return None
    cons = game_df.groupby("captured_at")["line"].median()
    closing = float(cons.iloc[-1])
    for t in sorted(game_df["captured_at"].unique()):
        snap = game_df[game_df["captured_at"] == t]
        c = float(cons.loc[t])
        gaps = snap["line"] - c
        far = gaps.abs() >= min_gap
        if far.any():
            i = gaps.abs().where(far).idxmax()
            row = snap.loc[i]
            side = "under" if (row["line"] - c) > 0 else "over"
            price = float(row["under_odds"] if side == "under" else row["over_odds"])
            return {
                "book": row["book"], "side": side, "entry_line": float(row["line"]),
                "entry_price": price, "closing_line": closing,
                "clv_points": points_clv(side, float(row["line"]), closing),
                "entry_at": float(t),
            }
    return None


def clv_and_results(snaps: pd.DataFrame, market: str, results: dict[str, float] | None = None,
                    min_gap: float = 1.5) -> tuple[pd.DataFrame, dict]:
    """Per-game outlier picks with CLV, plus win/loss where a final score is available.

    CLV comes from the line time series (always). Grading (win/loss/ROI) needs the final total and
    only works for the full-game `totals` market — a 2H total also needs the 1st-half score, which
    /scores doesn't provide, so those picks are marked 'pending'.
    """
    results = results or {}
    dfm = snaps[snaps["market"] == market]
    rows = []
    for game_id, gdf in dfm.groupby("game_id"):
        pick = _pick_for_game(gdf, min_gap)
        if pick is None:
            continue
        rec = {"game_id": game_id, **pick, "result": "pending", "pnl": None}
        if market == "totals" and game_id in results:
            final = results[game_id]
            won = (final < pick["entry_line"]) if pick["side"] == "under" else (final > pick["entry_line"])
            rec["result"] = "win" if won else "loss"
            rec["final_total"] = final
            rec["pnl"] = float(profit_per_unit(np.array([1 if won else 0]), pick["entry_price"])[0])
        rows.append(rec)

    per_game = pd.DataFrame(rows)
    if per_game.empty:
        return per_game, {"n_picks": 0, "mean_clv": 0.0, "beat_close_rate": 0.0,
                          "graded": 0, "hit_rate": None, "roi": None}

    clv = per_game["clv_points"].to_numpy(dtype=float)
    graded = per_game[per_game["result"].isin(["win", "loss"])]
    summary = {
        "n_picks": len(per_game),
        "mean_clv": float(clv.mean()),
        "beat_close_rate": float(np.mean(clv > 0)),
        "graded": len(graded),
        "hit_rate": float((graded["result"] == "win").mean()) if len(graded) else None,
        "roi": float(graded["pnl"].mean()) if len(graded) else None,
    }
    return per_game, summary


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
