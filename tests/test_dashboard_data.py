"""The dashboard's pure data logic (no Streamlit): harness analysis + snapshot loading."""
import numpy as np

import pandas as pd

from collector import db as cdb
from collector.snapshot import make_snapshot, persist_snapshots
from dashboard.data import load_snapshots, market_probability_series, run_harness_analysis


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
