"""h2-totals-lab dashboard — run with:  streamlit run dashboard/app.py

Light theme by deliberate choice: the categorical palette (Okabe-Ito) is validated against the
light surface (CVD separation OK; contrast WARN relieved by direct labels + tables). Pure data
logic lives in dashboard/data.py (no Streamlit import, unit-tested).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make repo packages importable

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data
from eval.kill import clv_kill
from market.config import load_dotenv

load_dotenv()

PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#000000"]
GOOD, CRIT, INK, MUTED = "#009E73", "#D55E00", "#1a1a19", "#6b6b68"

# Friendly labels -> The Odds API keys (so nobody types "basketball_wnba" / "totals_h2").
LEAGUES = {
    "WNBA (in season now)": "basketball_wnba",
    "NBA": "basketball_nba",
    "Men's College — NCAAB (Nov–Apr)": "basketball_ncaab",
    "Women's College — WNCAAB": "basketball_wncaab",
    "EuroLeague": "basketball_euroleague",
}
MARKETS = {
    "Full-game total (over/under)": "totals",
    "1st-half total": "totals_h1",
    "2nd-half total": "totals_h2",
}

st.set_page_config(page_title="h2-totals-lab", page_icon="🏀", layout="wide")

# ---------- shared settings live in the sidebar, set once ----------
with st.sidebar:
    st.header("⚙️ Settings")
    league_label = st.selectbox("League", list(LEAGUES), index=0)
    sport = LEAGUES[league_label]
    market_label = st.selectbox("Bet type", list(MARKETS), index=0)
    market = MARKETS[market_label]
    intl = st.checkbox("Include international books (may add Pinnacle)", value=True,
                       help="Pinnacle is the sharp anchor. US-only feeds are all soft books.")
    regions = "us,us2,eu" if intl else "us,us2"
    db_path = st.text_input("Data file", value="data/odds.sqlite",
                            help="where the monitor saves collected odds")
    st.divider()
    if os.environ.get("ODDS_API_KEY"):
        st.success("🔑 API key detected")
    else:
        st.warning("No ODDS_API_KEY. Set it in the terminal or a .env file to use live tabs.")
    st.caption("Paper-trade only. Nothing here places a real bet.")

st.title("🏀 h2-totals-lab")
with st.expander("▶ How to use this (read me first)", expanded=False):
    st.markdown(
        "- **Find a bet** — type the fair line and the number you see on **1xbet**; it says BET or PASS.\n"
        "- **Live odds** — see every book's number for a game right now, and who's off the consensus.\n"
        "- **Line movement** — watch a game's line (and implied over/under) move over time.\n"
        "- **CLV & results** — did your picks beat the closing number? The metric that actually matters.\n"
        "- **Reality check** — proof that a good-looking backtest can be pure noise.\n\n"
        "The honest bottom line lives in FINDINGS.md: most 'edges' are noise. Track **CLV** over ~200 "
        "bets before trusting anything, and **paper-trade** the whole way."
    )

tab_find, tab_live, tab_move, tab_clv, tab_harness = st.tabs(
    ["🎯 Find a bet", "📡 Live odds", "📈 Line movement", "🧾 CLV & results", "🧪 Reality check"]
)


# ============================================================ FIND A BET (1xbet vs fair)
with tab_find:
    st.subheader("Your book (1xbet) vs the fair line")
    st.markdown(
        "Type the **fair line** (grab it from the *Live odds* tab, or your own sharp source) and the "
        "number you see on **1xbet** for the same bet. We tell you whether it's worth it."
    )
    c1, c2, c3 = st.columns(3)
    fair_line = c1.number_input("Fair line (sharp / consensus)", value=104.5, step=0.5)
    your_line = c2.number_input("Line on 1xbet", value=104.5, step=0.5)
    matchup = c3.text_input("Game (label, optional)", value="", placeholder="e.g. Fire @ Sun")
    c4, c5, c6 = st.columns(3)
    over_odds = c4.number_input("1xbet OVER price (American)", value=-110, step=5)
    under_odds = c5.number_input("1xbet UNDER price (American)", value=-110, step=5)
    sigma = c6.slider("σ — spread of outcomes", 4.0, 25.0, 10.0,
                      help="rough width of the total's variance; 2H≈9, full game≈12")

    rec = data.recommend_bet(fair_line, your_line, over_odds, under_odds, sigma)
    if rec["verdict"] == "BET":
        st.success(
            f"### ✅ BET {rec['side'].upper()} {your_line:g} on 1xbet\n"
            f"**{rec['edge_points']:.1f} pts** off fair · est. win **{rec['p_win']*100:.0f}%** · "
            f"value **{rec['prob_edge']*100:+.1f}%** after the price"
        )
    else:
        st.info(
            f"### ⏸ PASS\n1xbet's {your_line:g} is only {rec['edge_points']:.1f} pts off fair "
            f"(value {rec['prob_edge']*100:+.1f}% — not enough after the vig). Wait for a bigger gap."
        )

    if st.button("Log this as a paper bet", disabled=(rec["verdict"] != "BET"), type="primary"):
        data.log_paper_bet(
            db_path, game_id=(matchup or None), matchup=matchup, market=market, book="1xbet",
            side=rec["side"], your_line=your_line, your_odds=rec["price"], fair_line=fair_line,
            edge_points=rec["edge_points"], prob_edge=rec["prob_edge"],
        )
        st.success("Logged — paper only, nothing placed.")

    st.divider()
    st.markdown("#### Your paper bets")
    bets = data.load_paper_bets(db_path)
    if bets.empty:
        st.caption("None yet. Log one above when 1xbet is meaningfully off the fair line.")
    else:
        summ = data.paper_bet_summary(bets)
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Logged", summ["n"])
        b2.metric("Avg edge (pts)", f"{summ['avg_edge_points']:.1f}")
        b3.metric("Avg value", f"{summ['avg_prob_edge']*100:+.1f}%")
        b4.metric("ROI (graded)", "—" if summ["roi"] is None else f"{summ['roi']*100:+.1f}%")
        cols = [c for c in ["placed_dt", "matchup", "market", "side", "your_line", "fair_line",
                            "edge_points", "prob_edge", "result"] if c in bets.columns]
        st.dataframe(bets[cols], use_container_width=True, hide_index=True)
        st.caption("An edge is only real if these beat the CLOSING number over ~200 bets — and even "
                   "then, 1xbet may limit or void a winning account. Paper-trade until CLV proves it.")


# ============================================================ LIVE ODDS
with tab_live:
    st.caption(f"League: **{league_label}** · Bet: **{market_label}** (change on the left)")
    if st.button("List games on the board"):
        try:
            st.session_state["live_events"] = data.list_live_events(sport, regions)
        except Exception as e:
            st.session_state["live_events"] = []
            st.error(f"{e}\n\nCheck your API key, the league, and your network.")

    events = st.session_state.get("live_events", [])
    event_id = None
    if events:
        labels = {
            f"{e.get('away_team','?')} @ {e.get('home_team','?')}  ·  {str(e.get('commence_time',''))[:16]}": e["id"]
            for e in events
        }
        pick = st.selectbox(f"{len(events)} games on the board — choose one", list(labels))
        event_id = labels[pick]

    if st.button("Pull odds", type="primary"):
        try:
            snap = data.live_market_snapshot(sport, market, regions, event_id)
        except Exception as e:
            st.error(f"{e}")
            snap = None
        if snap is not None:
            ev = snap.event
            st.subheader(f"{ev.get('away_team','?')} @ {ev.get('home_team','?')}")
            if snap.quotes_df.empty:
                st.warning("No quotes right now. Half/2nd-half lines are in-play — they appear once a "
                           "game is live at halftime. This is normal pre-game, not a failure.")
            else:
                if snap.has_sharp_anchor:
                    st.success(f"Fair line **{snap.fair.line:.1f}** (anchor: {snap.fair.anchor}, a sharp "
                               f"book) — copy this into the **Find a bet** tab.")
                else:
                    st.warning(f"Fair line **{snap.fair.line:.1f}** is a **soft consensus** — no sharp "
                               "book here. Turn on 'international books' on the left to try for Pinnacle.")
                left, right = st.columns([3, 2])
                with left:
                    q = snap.quotes_df
                    base = alt.Chart(q)
                    pts = base.mark_point(size=160, filled=True).encode(
                        x=alt.X("line:Q", title="total line", scale=alt.Scale(zero=False)),
                        y=alt.Y("book:N", sort="x", title=None),
                        color=alt.Color("book:N", scale=alt.Scale(domain=list(q["book"]),
                                        range=(PALETTE * 3)[:len(q)]), legend=None),
                        tooltip=["book", "line", "over", "under", "sharp"],
                    )
                    labels_ = base.mark_text(dx=12, align="left", color=INK).encode(
                        x="line:Q", y=alt.Y("book:N", sort="x"), text=alt.Text("line:Q", format=".1f"))
                    rule = alt.Chart(pd.DataFrame({"fair": [snap.fair.line]})).mark_rule(
                        strokeDash=[5, 5], color=INK).encode(x="fair:Q")
                    st.altair_chart((pts + labels_ + rule).properties(height=max(160, 42 * len(q))),
                                    use_container_width=True)
                with right:
                    st.dataframe(snap.quotes_df, use_container_width=True, hide_index=True)
                st.markdown("**Books off the consensus** (edges that need no model):")
                st.dataframe(snap.opportunities if not snap.opportunities.empty
                             else pd.DataFrame([{"note": "no book far enough off consensus"}]),
                             use_container_width=True, hide_index=True)
    else:
        st.info("Click **List games on the board**, choose a game, then **Pull odds**.")


# ============================================================ LINE MOVEMENT
with tab_move:
    st.caption(f"Reading collected snapshots from **{db_path}**")
    st.info("Collect a game first (leave this running during a live game):\n\n"
            f"`python -m collector.monitor --sport {sport} --market {market} --interval 60 "
            "--events <eventId> --db data/odds.sqlite`")
    try:
        snaps = data.load_snapshots(db_path)
    except Exception as e:
        st.error(f"Could not read {db_path}: {e}")
        snaps = pd.DataFrame()

    if snaps.empty:
        st.caption("No snapshots yet.")
    else:
        games = sorted(snaps["game_id"].unique())
        game = st.selectbox("Game", games, index=len(games) - 1)
        g0 = snaps[snaps["game_id"] == game].copy()
        markets = sorted(g0["market"].unique())
        mkt = st.selectbox("Market", markets, index=0) if len(markets) > 1 else markets[0]
        g = g0[g0["market"] == mkt].copy()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Books", g["book"].nunique())
        m2.metric("Snapshots", len(g))
        m3.metric("Line spread (pts)", f"{g['line'].max() - g['line'].min():.1f}")
        m4.metric("Latest consensus", f"{g.groupby('captured_at')['line'].median().iloc[-1]:.1f}")

        st.markdown(f"**`{mkt}` line over time** — each book (the market's estimate)")
        books = sorted(g["book"].unique())
        line = alt.Chart(g).mark_line(point=True, strokeWidth=2).encode(
            x=alt.X("captured_dt:T", title="time"),
            y=alt.Y("line:Q", title="total line", scale=alt.Scale(zero=False)),
            color=alt.Color("book:N", scale=alt.Scale(domain=books, range=(PALETTE * 3)[:len(books)]),
                            legend=alt.Legend(title="book")),
            tooltip=["book", "line", "over_odds", "under_odds", "captured_dt"],
        ).properties(height=340).interactive()
        st.altair_chart(line, use_container_width=True)
        st.caption("Books disagreeing at the same moment = a bet on the outlier. The consensus jumping "
                   "while a book lags = steam. Neither needs a prediction.")

        st.markdown("**Market's implied chance of going OVER a reference number**")
        st.warning("This curve is the **bookmaker's** probability reflected back — NOT your edge. "
                   "Betting the likely side at the book's price pays the vig and loses.")
        consensus0 = float(g.groupby("captured_at")["line"].median().iloc[0])
        cc1, cc2 = st.columns(2)
        reference = cc1.number_input("Reference total", value=round(consensus0, 1))
        psigma = cc2.slider("σ", 4.0, 25.0, 10.0, key="move_sigma")
        prob = data.market_probability_series(g, reference, psigma)
        if not prob.empty:
            pc = alt.Chart(prob).mark_line(point=True, strokeWidth=2, color=PALETTE[0]).encode(
                x=alt.X("captured_dt:T", title="time"),
                y=alt.Y("p_over_ref:Q", title=f"P(final > {reference:g})",
                        scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
                tooltip=[alt.Tooltip("consensus_line:Q", title="consensus"),
                         alt.Tooltip("p_over_ref:Q", format=".1%"), "captured_dt"])
            half = alt.Chart(pd.DataFrame({"y": [0.5]})).mark_rule(
                strokeDash=[4, 4], color=MUTED).encode(y="y:Q")
            st.altair_chart((pc + half).properties(height=260), use_container_width=True)


# ============================================================ CLV & RESULTS
with tab_clv:
    st.markdown("**Closing line value is the metric that matters.** Did our picks beat the closing "
                "number? CLV needs ~200 bets; win-rate needs ~2,000. A 'pick' = the earliest book "
                "≥ 1.5 pts off the consensus — pure book-shopping, no prediction.")
    try:
        clv_snaps = data.load_snapshots(db_path)
    except Exception as e:
        st.error(f"Could not read {db_path}: {e}")
        clv_snaps = pd.DataFrame()

    if clv_snaps.empty:
        st.info("No snapshots yet — collect a game with the monitor (see the Line movement tab).")
    else:
        cmk = st.selectbox("Market", sorted(clv_snaps["market"].unique()), key="clv_market")
        if st.button("Fetch final scores (last 3 days)"):
            try:
                st.session_state["clv_results"] = data.fetch_final_totals(sport, 3)
            except Exception as e:
                st.error(f"scores fetch failed: {e}")
                st.session_state["clv_results"] = {}
        results = st.session_state.get("clv_results", {})
        if cmk != "totals" and results:
            st.caption("Grading works for the full-game `totals` market only — a 2H/1H total also needs "
                       "the period score, which /scores doesn't give.")
        per_game, summ = data.clv_and_results(clv_snaps, cmk, results)
        if per_game.empty:
            st.info(f"No outlier picks in `{cmk}` yet (no book ≥ 1.5 pts off consensus).")
        else:
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Picks", summ["n_picks"])
            k2.metric("Mean CLV (pts)", f"{summ['mean_clv']:+.2f}")
            k3.metric("Beat-close rate", f"{summ['beat_close_rate']*100:.0f}%")
            k4.metric("Graded", summ["graded"])
            k5.metric("ROI", "—" if summ["roi"] is None else f"{summ['roi']*100:+.1f}%")
            kd = clv_kill(per_game["clv_points"].to_numpy())
            (st.error if kd.killed else st.success)(kd.line())
            bars = alt.Chart(per_game).mark_bar().encode(
                x=alt.X("game_id:N", sort=None, title=None, axis=alt.Axis(labelLimit=90)),
                y=alt.Y("clv_points:Q", title="CLV (points)"),
                color=alt.condition("datum.clv_points >= 0", alt.value(GOOD), alt.value(CRIT)),
                tooltip=["game_id", "book", "side", "entry_line", "closing_line",
                         alt.Tooltip("clv_points:Q", format="+.2f"), "result"]).properties(height=300)
            st.altair_chart(bars, use_container_width=True)
            st.dataframe(per_game, use_container_width=True, hide_index=True)


# ============================================================ REALITY CHECK (harness)
with tab_harness:
    st.markdown("Proof the discipline works: a great-looking +ROI strategy that **dies under every "
                "test**. Tick *inject a real edge* to watch it correctly find one.")
    cc1, cc2, cc3 = st.columns([1, 1, 2])
    n_strats = cc1.slider("Strategies hunted", 20, 200, 60, step=10)
    edge = cc2.checkbox("Inject a real edge", value=False)
    run = cc3.button("Run", type="primary")
    if run or "harness" not in st.session_state:
        st.session_state["harness"] = data.run_harness_analysis(n_strategies=n_strats, inject_edge=edge)
    r = st.session_state["harness"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Best strategy ROI", f"{r['best_roi']*100:+.2f}%",
              help=f"95% CI [{r['ci_lo']*100:+.2f}%, {r['ci_hi']*100:+.2f}%]")
    k2.metric("Hansen SPA p-value", f"{r['spa_p']:.3f}")
    k3.metric("Deflated Sharpe", f"{r['dsr']:.3f}")
    k4.metric("Survives BH FDR<0.05", f"{r['bh_rejected']} / {r['n_strategies']}")
    if r["spa_killed"]:
        st.error("### => KILLED — the best strategy is not significant (SPA p ≥ 0.05). "
                 "'But it was profitable in the backtest' is exactly what noise looks like.")
    else:
        st.success(f"### Significant (SPA p = {r['spa_p']:.3f} < 0.05). On synthetic data this only "
                   "happens when a real edge was injected.")
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Month-by-month ROI** — a real edge is stable; noise swings")
        bars = alt.Chart(r["monthly"]).mark_bar().encode(
            x=alt.X("ts:N", title=None), y=alt.Y("roi:Q", title="ROI", axis=alt.Axis(format="%")),
            color=alt.condition("datum.roi >= 0", alt.value(GOOD), alt.value(CRIT)),
            tooltip=["ts", "n", alt.Tooltip("roi:Q", format=".3f")]).properties(height=300)
        st.altair_chart(bars, use_container_width=True)
    with right:
        st.markdown("**Top strategies by ROI** — read the p-values")
        show = r["per_strategy"].head(10).copy()
        show["roi"] = (show["roi"] * 100).round(2)
        show["win_rate"] = (show["win_rate"] * 100).round(1)
        show["p_binom"] = show["p_binom"].round(3)
        st.dataframe(show, use_container_width=True, hide_index=True)
