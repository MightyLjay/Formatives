"""The dashboard's pure data logic (no Streamlit): harness analysis + snapshot loading."""
import numpy as np

import pandas as pd

from collector import db as cdb
from collector.snapshot import make_snapshot, persist_snapshots
from dashboard.data import (
    clv_and_results,
    load_paper_bets,
    load_snapshots,
    log_paper_bet,
    market_probability_series,
    paper_bet_summary,
    recommend_bet,
    run_harness_analysis,
)


def test_recommend_bet_flags_a_real_gap():
    # 1xbet at 108.5 when fair is 104.5 -> its UNDER is generous -> BET under.
    rec = recommend_bet(fair_line=104.5, your_line=108.5, over_odds=-110, under_odds=-110, sigma=9.0)
    assert rec["side"] == "under"
    assert rec["edge_points"] == 4.0
    assert rec["p_win"] > 0.5
    assert rec["prob_edge"] > 0
    assert rec["verdict"] == "BET"


def test_recommend_bet_passes_on_no_gap():
    rec = recommend_bet(fair_line=104.5, your_line=104.5, sigma=9.0)
    assert rec["edge_points"] == 0.0
    assert rec["verdict"] == "PASS"      # 0 points off fair loses to the vig
    assert rec["prob_edge"] < 0


def test_recommend_bet_below_fair_is_over():
    rec = recommend_bet(fair_line=104.5, your_line=100.0, sigma=9.0)
    assert rec["side"] == "over"         # 1xbet's low line -> its OVER is generous
    assert rec["verdict"] == "BET"


def test_paper_bet_roundtrip(tmp_path):
    path = str(tmp_path / "odds.sqlite")
    log_paper_bet(path, game_id="G1", matchup="Fire @ Sun", market="totals_h2", book="1xbet",
                  side="under", your_line=108.5, your_odds=-110, fair_line=104.5,
                  edge_points=4.0, prob_edge=0.05)
    df = load_paper_bets(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["book"] == "1xbet" and row["side"] == "under" and row["result"] == "pending"
    summ = paper_bet_summary(df)
    assert summ["n"] == 1 and summ["avg_edge_points"] == 4.0 and summ["roi"] is None


def test_load_paper_bets_missing_file(tmp_path):
    assert load_paper_bets(str(tmp_path / "nope.sqlite")).empty


def _totals_game(market="totals"):
    # G1: three books. pinnacle+draftkings form a stable ~150 consensus; lazybook posts 155 early
    # (its UNDER is generous). By close everyone is at 154.
    return pd.DataFrame({
        "game_id": ["G1"] * 9,
        "market": [market] * 9,
        "book": ["pinnacle", "draftkings", "lazybook"] * 3,
        "line": [150.0, 150.5, 155.0,   152.0, 152.0, 154.0,   154.0, 154.0, 154.0],
        "over_odds": [-110] * 9,
        "under_odds": [-110] * 9,
        "captured_at": [1000, 1000, 1000, 1060, 1060, 1060, 1120, 1120, 1120],
    })


def test_clv_grades_full_game_totals():
    per_game, summ = clv_and_results(_totals_game("totals"), "totals",
                                     results={"G1": 148.0}, min_gap=1.5)
    assert len(per_game) == 1
    row = per_game.iloc[0]
    assert row["side"] == "under"          # 155 sits above the 152.5 consensus -> under is generous
    assert row["entry_line"] == 155.0
    assert row["closing_line"] == 154.0    # median at the last poll
    assert abs(row["clv_points"] - 1.0) < 1e-9   # under CLV = entry - close = 155 - 154
    assert row["result"] == "win"          # final 148 < 155 -> under wins
    assert summ["graded"] == 1 and summ["hit_rate"] == 1.0
    assert summ["roi"] is not None


def test_clv_is_pending_for_2h_without_period_score():
    per_game, summ = clv_and_results(_totals_game("totals_h2"), "totals_h2",
                                     results={"G1": 148.0}, min_gap=1.5)
    assert per_game.iloc[0]["result"] == "pending"   # /scores can't grade a 2H total
    assert summ["roi"] is None
    assert summ["n_picks"] == 1                       # CLV still computed


def test_clv_no_pick_when_books_agree():
    df = _totals_game("totals")
    df["line"] = 150.0  # everyone identical -> nothing off consensus
    per_game, summ = clv_and_results(df, "totals", results={}, min_gap=1.5)
    assert per_game.empty and summ["n_picks"] == 0


def test_harness_no_edge_is_killed():
    r = run_harness_analysis(n_games=2000, n_strategies=40, inject_edge=False)
    assert r["spa_killed"] is True          # no edge -> SPA fails to reject -> killed
    assert r["spa_p"] >= 0.05
    assert r["bh_rejected"] <= 2            # essentially nothing survives FDR
    assert set(r["per_strategy"].columns) >= {"strat", "n", "win_rate", "roi", "p_binom"}
    assert not r["monthly"].empty


def test_harness_injected_edge_is_detected():
    r = run_harness_analysis(n_games=4000, n_strategies=40, inject_edge=True)
    assert r["spa_killed"] is False         # a real edge -> SPA rejects
    assert r["spa_p"] < 0.05
    assert r["dsr"] > r["sr_star"] * 0 - 1  # sanity: dsr computed


def test_load_snapshots_roundtrip(tmp_path):
    path = str(tmp_path / "odds.sqlite")
    conn = cdb.connect(path)
    persist_snapshots(conn, [
        make_snapshot("G1", "pinnacle", 68.5, -105, -105, captured_at=1000.0),
        make_snapshot("G1", "lazybook", 72.5, -110, -110, captured_at=1000.0),
        make_snapshot("G1", "pinnacle", 69.0, -108, -104, captured_at=1060.0),
    ])
    conn.close()

    df = load_snapshots(path)
    assert len(df) == 3
    assert "captured_dt" in df.columns
    assert set(df["book"]) == {"pinnacle", "lazybook"}
    # newest capture for pinnacle moved the line up 0.5
    piny = df[df["book"] == "pinnacle"].sort_values("captured_at")
    assert piny.iloc[-1]["line"] == 69.0


def test_load_snapshots_empty_db(tmp_path):
    path = str(tmp_path / "empty.sqlite")
    cdb.connect(path).close()
    df = load_snapshots(path)
    assert df.empty


def test_load_snapshots_missing_file_is_friendly(tmp_path):
    df = load_snapshots(str(tmp_path / "never_created.sqlite"))
    assert df.empty  # returns empty, does NOT raise or create a file


def test_market_probability_reflects_the_line():
    # Two polls: consensus rises from 150 to 158. P(final > 150) must increase toward 1.
    df = pd.DataFrame({
        "captured_at": [1000, 1000, 1060, 1060],
        "book": ["a", "b", "a", "b"],
        "line": [149.0, 151.0, 157.0, 159.0],  # medians 150 then 158
    })
    out = market_probability_series(df, reference=150.0, sigma=10.0)
    assert list(out["consensus_line"]) == [150.0, 158.0]
    assert out["p_over_ref"].iloc[0] == 0.5          # consensus == reference -> 50/50
    assert out["p_over_ref"].iloc[1] > 0.5           # consensus moved above reference
    assert (out["p_over_ref"].between(0, 1)).all()


def test_market_probability_empty():
    out = market_probability_series(pd.DataFrame(columns=["captured_at", "line"]), 150.0)
    assert out.empty
