"""Rank |soft_book_line - fair_line|. If a soft book is 4 points off the sharp consensus, that's
an edge that requires no model at all.

We are not trying to beat the market consensus. We are trying to find the outlier *against* it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from eval.metrics import american_to_prob

from .fair import BookQuote, FairLine

# Rough SD of a 2H basketball total's realized points, used only to translate a points gap into a
# ballpark win-probability edge. Calibrate this from the collector once real data exists.
DEFAULT_TOTAL_SIGMA = 9.0


@dataclass
class Opportunity:
    book: str
    side: str                 # "over" or "under" — the side to bet at the soft book
    soft_line: float
    fair_line: float
    gap_points: float         # |soft_line - fair_line|, signed toward the recommended side
    soft_price: float         # American odds you'd take
    prob_edge: float          # est. P(win) - de-vigged implied P at the soft price
    ts: float | None = None


def find_outliers(
    quotes: list[BookQuote],
    fair: FairLine,
    min_gap: float = 1.0,
    sigma: float = DEFAULT_TOTAL_SIGMA,
) -> list[Opportunity]:
    """Rank soft-book quotes by how far their line sits from the fair line.

    For a total, a soft line *above* fair means its UNDER is generous (you get a higher number
    than fair); a soft line *below* fair means its OVER is generous. Opportunities are returned
    sorted by |gap| descending.
    """
    opps: list[Opportunity] = []
    for q in quotes:
        gap = q.line - fair.line  # signed: + means soft line is above fair
        if abs(gap) < min_gap:
            continue
        if gap > 0:
            side, price = "under", q.under_odds
        else:
            side, price = "over", q.over_odds

        prob_edge = _prob_edge(side, q.line, fair.line, price, sigma)
        opps.append(
            Opportunity(
                book=q.book,
                side=side,
                soft_line=q.line,
                fair_line=fair.line,
                gap_points=abs(gap),
                soft_price=price,
                prob_edge=prob_edge,
                ts=q.ts,
            )
        )
    opps.sort(key=lambda o: o.gap_points, reverse=True)
    return opps


def _prob_edge(side: str, soft_line: float, fair_line: float, price: float, sigma: float) -> float:
    """Estimated true win prob for the bet minus the de-vigged price of a fair two-way market.

    Model realized 2H points ~ Normal(fair_line, sigma). Our win prob for the *under at soft_line*
    is P(points < soft_line); for the *over at soft_line*, P(points > soft_line). Subtract the
    de-vigged implied probability at the soft price so soft juice is accounted for.
    """
    z = (soft_line - fair_line) / sigma
    if side == "under":
        p_win = float(stats.norm.cdf(z))
    else:
        p_win = float(1.0 - stats.norm.cdf(z))
    # Edge = our estimated win prob minus the (vigged) price we'd have to pay. This is exactly the
    # quantity fractional Kelly consumes; a positive value means the soft price is beatable even
    # after its juice.
    implied = american_to_prob(price)
    return p_win - implied
