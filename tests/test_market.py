"""Market layer: de-vig, fair line, outlier ranking, and CLV sign conventions."""
import numpy as np

from market.clv import grade_clv, make_record, points_clv
from market.fair import BookQuote, devig_two_way, fair_line
from market.outliers import find_outliers


def test_devig_sums_to_one_and_removes_margin():
    p_over, p_under = devig_two_way(-110, -110)
    assert abs(p_over + p_under - 1.0) < 1e-12
    assert abs(p_over - 0.5) < 1e-9  # symmetric price -> 50/50 after de-vig
    # A vigged book sums to > 1 before de-vig.
    q = 1 / (1 + 100 / 110) * 2
    assert q > 1.0


def test_devig_shin_runs_and_normalizes():
    p_over, p_under = devig_two_way(-150, +130, method="shin")
    assert abs(p_over + p_under - 1.0) < 1e-9
    assert p_over > p_under  # favourite side has higher prob


def test_fair_line_anchors_on_pinnacle():
    quotes = [
        BookQuote("pinnacle", 104.5, -105, -105, is_sharp=True),
        BookQuote("lazybook", 108.5, -110, -110),
    ]
    fl = fair_line(quotes)
    assert fl.line == 104.5
    assert fl.anchor.lower() == "pinnacle"


def test_outlier_recommends_under_on_high_soft_line():
    quotes = [
        BookQuote("pinnacle", 104.5, -105, -105, is_sharp=True),
        BookQuote("draftkings", 104.5, -110, -110),
        BookQuote("lazybook", 108.5, -110, -110),  # 4 pts high -> its UNDER is generous
    ]
    fl = fair_line(quotes)
    opps = find_outliers(quotes, fl, min_gap=1.0)
    assert opps  # at least one edge
    top = opps[0]
    assert top.book == "lazybook"
    assert top.side == "under"
    assert top.gap_points >= 3.9
    assert top.prob_edge > 0  # generous under is a positive-edge bet


def test_points_clv_signs():
    # Over bet: closing line higher than entry is good (we bought the low number).
    assert points_clv("over", 100.5, 102.5) == 2.0
    # Under bet: closing line lower than entry is good.
    assert points_clv("under", 102.5, 100.5) == 2.0
    assert points_clv("over", 102.5, 100.5) == -2.0


def test_grade_clv_aggregate():
    recs = [
        make_record("over", 100.5, -110, 102.5, -110, -110),
        make_record("under", 105.0, -110, 103.0, -110, -110),
    ]
    agg = grade_clv(recs)
    assert agg["n"] == 2
    assert agg["mean_points_clv"] == 2.0  # both beat the close by 2 points
