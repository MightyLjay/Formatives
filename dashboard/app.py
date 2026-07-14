"""h2-totals-lab dashboard — run with:  streamlit run dashboard/app.py

Light theme by deliberate choice: the categorical palette (Okabe-Ito) is validated against the
light surface (CVD separation ΔE 17.9, well above the 12 floor); the contrast WARN is relieved by
direct labels + table views throughout. See dataviz notes in the commit.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make repo packages importable

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data
from market.config import load_dotenv

load_dotenv()

# --- validated categorical palette (light surface) + reserved status colors ---
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#000000"]
GOOD, CRIT, INK, MUTED = "#009E73", "#D55E00", "#1a1a19", "#6b6b68"

st.set_page_config(page_title="h2-totals-lab", page_icon="🏀", layout="wide")

st.title("🏀 h2-totals-lab")
st.caption(
    "2nd-half totals: market coverage, live collection, and a falsification-first harness. "
    "The edge is in **information and a worse market**, not a better model — and one snapshot is "
    "never an edge. CLV over ~200 bets is."
)

tab_live, tab_move, tab_harness = st.tabs(
    ["📡 Live odds", "📈 Live game", "🧪 Falsification harness"]
)


# ============================================================ LIVE ODDS
with tab_live:
    c1, c2, c3 = st.columns([2, 2, 1])
    sport = c1.text_input("Sport key", value="basketball_wnba",
                          help="e.g. basketball_wnba, basketball_nba, basketball_ncaab (Nov–Apr)")
    market = c2.text_input("Market", value="totals_h2")
    regions = c3.text_input("Regions", value="us,us2", help="add 'eu' to reach Pinnacle/sharp books")

    if st.button("Pull live odds", type="primary"):
        try:
            snap = data.live_market_snapshot(sport, market, regions)
        except Exception as e:
            st.error(f"{e}\n\nCheck ODDS_API_KEY (env or .env), the sport key, and your network.")
            snap = None

        if snap is not None:
            ev = snap.event
            st.subheader(f"{ev.get('away_team','?')} @ {ev.get('home_team','?')}")
            st.caption(f"event {ev.get('id')} · tip {ev.get('commence_time')}")

            if snap.quotes_df.empty:
                st.warning(
                    f"No **{market}** quotes right now. The 2H total is an in-play line — it usually "
                    "only appears once a game is live at halftime. This is the expected pre-game "
                    "state, not a failure."
                )
            else:
                if snap.has_sharp_anchor:
                    st.success(f"Fair line **{snap.fair.line:.1f}** anchored on **{snap.fair.anchor}** "
                               f"(a sharp book). P(over)={snap.fair.p_over:.3f}")
                else:
                    st.warning(
                        f"Fair line **{snap.fair.line:.1f}** is a **soft consensus** "
                        f"(anchor: {snap.fair.anchor}) — **no sharp book in this feed.** Treat the "
                        "edges below with skepticism; add 'eu' to regions to try to reach Pinnacle."
                    )

                left, right = st.columns([3, 2])
                with left:
                    st.markdown("**Where each book sits vs the fair line**")
                    q = snap.quotes_df
                    base = alt.Chart(q)
                    pts = base.mark_point(size=160, filled=True).encode(
                        x=alt.X("line:Q", title="2H total line", scale=alt.Scale(zero=False)),
                        y=alt.Y("book:N", sort="x", title=None),
                        color=alt.Color("book:N",
                                        scale=alt.Scale(domain=list(q["book"]), range=PALETTE),
                                        legend=None),
                        tooltip=["book", "line", "over", "under", "sharp"],
                    )
                    labels = base.mark_text(dx=12, align="left", color=INK).encode(
                        x="line:Q", y=alt.Y("book:N", sort="x"), text=alt.Text("line:Q", format=".1f")
                    )
                    rule = alt.Chart(pd.DataFrame({"fair": [snap.fair.line]})).mark_rule(
                        strokeDash=[5, 5], color=INK
                    ).encode(x="fair:Q")
                    st.altair_chart((pts + labels + rule).properties(height=max(160, 42 * len(q))),
                                    use_container_width=True)
                with right:
                    st.markdown("**Book quotes**")
                    st.dataframe(snap.quotes_df, use_container_width=True, hide_index=True)

                st.markdown("**Outliers vs the consensus** (edges that need no model)")
                if snap.opportunities.empty:
                    st.info("No book is meaningfully off the consensus right now.")
                else:
                    st.dataframe(snap.opportunities, use_container_width=True, hide_index=True)
    else:
        st.info("Enter a sport and click **Pull live odds**. Needs `ODDS_API_KEY` "
                "(set it in the terminal or a `.env` file).")


# ============================================================ LINE MOVEMENT
with tab_move:
    db_path = st.text_input("Snapshot database", value="data/odds.sqlite",
                            help="the SQLite the monitor writes to (collector.monitor --db ...)")
    try:
        snaps = data.load_snapshots(db_path)
    except Exception as e:
        st.error(f"Could not read {db_path}: {e}")
        snaps = pd.DataFrame()

    if snaps.empty:
        st.info(
            "No snapshots yet. Run the monitor to collect a game's line over time. Track the "
            "**full-game** total live, or the **2H** total:\n\n"
            "`python -m collector.monitor --sport basketball_wnba --market totals --interval 60 "
            "--events <eventId> --db data/odds.sqlite`\n\n"
            "(use `--market totals_h2` for the 2nd-half line)"
        )
    else:
        games = sorted(snaps["game_id"].unique())
        game = st.selectbox("Game", games, index=len(games) - 1)
        g0 = snaps[snaps["game_id"] == game].copy()
        markets = sorted(g0["market"].unique())
        mkt = st.selectbox("Market", markets, index=0) if len(markets) > 1 else markets[0]
        g = g0[g0["market"] == mkt].copy()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Books seen", g["book"].nunique())
        m2.metric("Snapshots", len(g))
        m3.metric("Line spread (pts)", f"{g['line'].max() - g['line'].min():.1f}")
        m4.metric("Latest consensus", f"{g.groupby('captured_at')['line'].median().iloc[-1]:.1f}")

        # ---- 1. the market's evolving estimate: each book's line over time ----
        st.markdown(f"**`{mkt}` line movement** — each book's number over time (the market's estimate)")
        books = sorted(g["book"].unique())
        line = alt.Chart(g).mark_line(point=True, strokeWidth=2).encode(
            x=alt.X("captured_dt:T", title="captured at"),
            y=alt.Y("line:Q", title="total line", scale=alt.Scale(zero=False)),
            color=alt.Color("book:N",
                            scale=alt.Scale(domain=books, range=(PALETTE * 3)[:len(books)]),
                            legend=alt.Legend(title="book")),
            tooltip=["book", "line", "over_odds", "under_odds", "captured_dt"],
        ).properties(height=340).interactive()
        st.altair_chart(line, use_container_width=True)
        st.caption("Where books **disagree** at the same moment is a dispersion edge (bet the outlier). "
                   "Where the consensus **jumps** and a book lags is steam. Neither needs a prediction.")

        # ---- 2. the market's implied P(over a reference) — honestly labelled ----
        st.markdown("**Market's implied probability of going OVER a reference number**")
        st.warning(
            "This curve is the **bookmaker's** probability, reflected back — **not your edge.** "
            "Betting the likely side at the book's price pays the vig and loses (see FINDINGS.md). "
            "It's here to *read the market*, not to beat it."
        )
        consensus0 = float(g.groupby("captured_at")["line"].median().iloc[0])
        c1, c2 = st.columns(2)
        reference = c1.number_input("Reference total (the number you'd bet)", value=round(consensus0, 1))
        sigma = c2.slider("Uncertainty σ (uncalibrated — a rough width, not a forecast)", 4.0, 25.0, 10.0)
        prob = data.market_probability_series(g, reference, sigma)
        if not prob.empty:
            pchart = alt.Chart(prob).mark_line(point=True, strokeWidth=2, color=PALETTE[0]).encode(
                x=alt.X("captured_dt:T", title="captured at"),
                y=alt.Y("p_over_ref:Q", title=f"P(final > {reference:g})",
                        scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
                tooltip=[alt.Tooltip("consensus_line:Q", title="consensus"),
                         alt.Tooltip("p_over_ref:Q", format=".1%"), "captured_dt"],
            ).properties(height=260)
            half = alt.Chart(pd.DataFrame({"y": [0.5]})).mark_rule(
                strokeDash=[4, 4], color=MUTED).encode(y="y:Q")
            st.altair_chart((pchart + half), use_container_width=True)

        with st.expander("Raw snapshots"):
            st.dataframe(g[["captured_dt", "book", "line", "over_odds", "under_odds", "source"]],
                         use_container_width=True, hide_index=True)


# ============================================================ HARNESS
with tab_harness:
    st.markdown(
        "The harness on synthetic data. This is the project's conscience: a seductive +ROI strategy "
        "that **dies under every test**. Flip *inject a real edge* to watch it correctly isolate one."
    )
    cc1, cc2, cc3 = st.columns([1, 1, 2])
    n_strats = cc1.slider("Strategies hunted", 20, 200, 60, step=10)
    edge = cc2.checkbox("Inject a real edge", value=False)
    run = cc3.button("Run harness", type="primary")

    if run or "harness" not in st.session_state:
        st.session_state["harness"] = data.run_harness_analysis(n_strategies=n_strats, inject_edge=edge)
    r = st.session_state["harness"]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Best strategy ROI", f"{r['best_roi']*100:+.2f}%",
              help=f"95% CI [{r['ci_lo']*100:+.2f}%, {r['ci_hi']*100:+.2f}%]")
    k2.metric("Hansen SPA p-value", f"{r['spa_p']:.3f}",
              help="H0: the best of N strategies has no edge. >= 0.05 => not significant.")
    k3.metric("Deflated Sharpe", f"{r['dsr']:.3f}",
              help=f"deflated for {r['n_strategies']} trials; SR*={r['sr_star']:.3f}")
    k4.metric("Survives BH FDR<0.05", f"{r['bh_rejected']} / {r['n_strategies']}")

    if r["spa_killed"]:
        st.error("### => PROJECT KILLED — best strategy is not significant (SPA p ≥ 0.05). "
                 "\n'But it was profitable in the backtest' is exactly what noise looks like.")
    else:
        st.success(f"### Best strategy is significant (SPA p = {r['spa_p']:.3f} < 0.05). "
                   "On synthetic data this only happens when a real edge was injected.")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Month-by-month ROI of the best strategy** — a real edge is stable; noise swings")
        stab = r["monthly"]
        bars = alt.Chart(stab).mark_bar().encode(
            x=alt.X("ts:N", title=None),
            y=alt.Y("roi:Q", title="ROI", axis=alt.Axis(format="%")),
            color=alt.condition("datum.roi >= 0", alt.value(GOOD), alt.value(CRIT)),
            tooltip=["ts", "n", alt.Tooltip("roi:Q", format=".3f")],
        ).properties(height=300)
        st.altair_chart(bars, use_container_width=True)
    with right:
        st.markdown("**Top strategies by ROI** — the seductive table. Read the p-values.")
        show = r["per_strategy"].head(10).copy()
        show["roi"] = (show["roi"] * 100).round(2)
        show["win_rate"] = (show["win_rate"] * 100).round(1)
        show["p_binom"] = show["p_binom"].round(3)
        st.dataframe(show, use_container_width=True, hide_index=True)

    st.caption(f"Breakeven at -110 is {r['breakeven']:.4f}. CLV on real bets — not this synthetic "
               "ROI — is the metric that would actually clear the project.")
