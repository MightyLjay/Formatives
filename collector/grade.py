"""Grade a 2H-total snapshot against the settled game.

    TARGET = final_total - h1_total

Overtime settles into the 2nd-half bet (it's ~5.8% of games), so `final_total` MUST include OT.
The single most important rule in this file: **do not use the H2 box score.** A box-score "2H total"
excludes overtime and silently biases you UNDER. Always derive H2 as (final incl. OT) - (1st half).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GradeResult:
    h2_actual: float          # final_total (incl. OT) - h1_total
    result: str               # "win" | "loss" | "push"
    margin: float             # h2_actual - entry_line (signed toward the over)


def h2_actual_points(h1_total: float, final_total_incl_ot: float) -> float:
    """The quantity the 2H total settles on. `final_total_incl_ot` must include overtime points."""
    h2 = final_total_incl_ot - h1_total
    if h2 < 0:
        raise ValueError(
            f"negative 2H points ({h2}); final_total ({final_total_incl_ot}) < h1_total ({h1_total}) "
            "— check that final_total is the whole-game total, not a half."
        )
    return h2


def grade(bet_side: str, entry_line: float, h1_total: float, final_total_incl_ot: float) -> GradeResult:
    """Grade an over/under bet on the 2H total. Push on an exact landing."""
    side = bet_side.lower()
    if side not in ("over", "under"):
        raise ValueError(f"bet_side must be over/under, got {bet_side!r}")

    h2 = h2_actual_points(h1_total, final_total_incl_ot)
    margin = h2 - entry_line
    if margin == 0:
        result = "push"
    elif side == "over":
        result = "win" if h2 > entry_line else "loss"
    else:  # under
        result = "win" if h2 < entry_line else "loss"
    return GradeResult(h2_actual=h2, result=result, margin=margin)
