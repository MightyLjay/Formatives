"""Closing line value — did our pick beat the closing 2H number? THE PRIMARY METRIC.

Win rate needs ~2,000 bets to reach significance. CLV tells us in ~200. If our picks consistently
beat the closing number, we have an edge even before results come in. Two flavours:

- **Points CLV**: how many points better than the close we got on the total.
- **Probability CLV**: de-vigged win-probability we locked in vs. the de-vigged closing probability.
  This is the currency-agnostic version and the one the kill criterion consumes.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .fair import devig_two_way


@dataclass
class CLVRecord:
    side: str            # "over" | "under" — the side we took
    entry_line: float
    entry_odds: float
    closing_line: float
    closing_over_odds: float
    closing_under_odds: float
    points_clv: float
    prob_clv: float


def points_clv(side: str, entry_line: float, closing_line: float) -> float:
    """Points beaten vs the close. Positive = we got a better number than the close.

    For an OVER, a higher closing total is better (we bought the lower number): close - entry.
    For an UNDER, a lower closing total is better: entry - close.
    """
    if side == "over":
        return closing_line - entry_line
    if side == "under":
        return entry_line - closing_line
    raise ValueError(f"side must be over/under, got {side!r}")


def prob_clv(
    side: str,
    entry_odds: float,
    closing_over_odds: float,
    closing_under_odds: float,
    method: str = "multiplicative",
) -> float:
    """De-vigged probability we locked in, minus the de-vigged closing probability of our side.

    Positive means the market moved toward our side after we bet — the low-variance edge signal.
    We de-vig the closing two-way market; the entry side is de-vigged against a symmetric mirror
    of the price we took (a conservative proxy when only our side's entry price was recorded).
    """
    p_close_over, p_close_under = devig_two_way(closing_over_odds, closing_under_odds, method)
    p_close_side = p_close_over if side == "over" else p_close_under

    # Entry: de-vig our taken price against a symmetric mirror -> the "fair" prob our price implied.
    p_entry_side, _ = devig_two_way(entry_odds, entry_odds, method)  # = 0.5 by symmetry
    # Better: use the vigged implied of our entry price so a plus-money entry shows as < 0.5.
    p_entry_vig = 1.0 / _american_to_decimal(entry_odds)

    # CLV in probability terms = closing fair prob of our side - the prob our entry price implied.
    return float(p_close_side - p_entry_vig)


def grade_clv(records: list[CLVRecord]) -> dict:
    """Aggregate CLV over a set of graded bets."""
    if not records:
        return {"n": 0, "mean_points_clv": 0.0, "mean_prob_clv": 0.0, "beat_close_rate": 0.0}
    pc = np.array([r.points_clv for r in records], dtype=float)
    qc = np.array([r.prob_clv for r in records], dtype=float)
    return {
        "n": len(records),
        "mean_points_clv": float(pc.mean()),
        "mean_prob_clv": float(qc.mean()),
        "beat_close_rate": float(np.mean(qc > 0)),
    }


def make_record(
    side: str,
    entry_line: float,
    entry_odds: float,
    closing_line: float,
    closing_over_odds: float,
    closing_under_odds: float,
) -> CLVRecord:
    return CLVRecord(
        side=side,
        entry_line=entry_line,
        entry_odds=entry_odds,
        closing_line=closing_line,
        closing_over_odds=closing_over_odds,
        closing_under_odds=closing_under_odds,
        points_clv=points_clv(side, entry_line, closing_line),
        prob_clv=prob_clv(side, entry_odds, closing_over_odds, closing_under_odds),
    )


def _american_to_decimal(american: float) -> float:
    american = float(american)
    return 1.0 + american / 100.0 if american > 0 else 1.0 + 100.0 / abs(american)
