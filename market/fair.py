"""De-vig the sharp consensus into a "true" line.

Pinnacle (or the consensus of sharp books) is ground truth, not an opponent. If Pinnacle says the
2H total is 104.5 and a soft book says 108.5, you don't need a model — you need the under at 108.5.
This module removes the bookmaker's margin from a two-way price and builds a sharp-anchored fair line.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from eval.metrics import american_to_decimal

DEFAULT_SHARP_BOOKS = ("pinnacle", "circa", "bookmaker", "betcris")


@dataclass
class BookQuote:
    """One book's two-way price on a 2H total at a moment in time."""

    book: str
    line: float                 # the total (e.g. 104.5)
    over_odds: float = -110.0   # American
    under_odds: float = -110.0
    ts: float | None = None     # unix seconds; when we observed it
    is_sharp: bool = False


@dataclass
class FairLine:
    line: float                 # sharp-consensus fair total
    p_over: float               # de-vigged P(over) at `line` from the anchor
    p_under: float
    anchor: str
    n_sharp: int


def devig_two_way(over_odds: float, under_odds: float, method: str = "multiplicative"):
    """Remove vig from a two-way market. Returns (p_over_fair, p_under_fair), summing to 1.

    method:
      - "multiplicative": normalise implied probabilities proportionally (fast, standard).
      - "shin": Shin (1993) insider-adjusted de-vig; better on lopsided two-way markets.
    """
    q_over = 1.0 / american_to_decimal(over_odds)
    q_under = 1.0 / american_to_decimal(under_odds)
    booksum = q_over + q_under
    if booksum <= 0:
        raise ValueError("degenerate odds")

    if method == "multiplicative":
        return q_over / booksum, q_under / booksum

    if method == "shin":
        z = _shin_z(q_over, q_under)
        p_over = _shin_prob(q_over, booksum, z)
        p_under = _shin_prob(q_under, booksum, z)
        s = p_over + p_under
        return p_over / s, p_under / s

    raise ValueError(f"unknown method {method!r}")


def fair_line(
    quotes: list[BookQuote],
    anchor: str = "pinnacle",
    sharp_books: tuple[str, ...] = DEFAULT_SHARP_BOOKS,
    method: str = "multiplicative",
) -> FairLine:
    """Build the sharp-anchored fair line from a set of book quotes.

    The fair *point* is the anchor book's line if present, else the median of the sharp books'
    lines, else the median of all lines. The fair *probability* at that point is the de-vigged
    P(over) from the anchor (or the sharp median odds).
    """
    if not quotes:
        raise ValueError("no quotes")

    def _is_sharp(q: BookQuote) -> bool:
        return q.is_sharp or q.book.lower() in sharp_books

    sharp = [q for q in quotes if _is_sharp(q)]
    anchor_q = next((q for q in quotes if q.book.lower() == anchor.lower()), None)

    if anchor_q is not None:
        line = anchor_q.line
        p_over, p_under = devig_two_way(anchor_q.over_odds, anchor_q.under_odds, method)
        used_anchor = anchor_q.book
    elif sharp:
        line = float(np.median([q.line for q in sharp]))
        p_over, p_under = _median_devig(sharp, method)
        used_anchor = "sharp-consensus"
    else:
        line = float(np.median([q.line for q in quotes]))
        p_over, p_under = _median_devig(quotes, method)
        used_anchor = "all-books-consensus"

    return FairLine(line=line, p_over=p_over, p_under=p_under, anchor=used_anchor, n_sharp=len(sharp))


def _median_devig(quotes: list[BookQuote], method: str):
    ps = [devig_two_way(q.over_odds, q.under_odds, method) for q in quotes]
    p_over = float(np.median([p[0] for p in ps]))
    return p_over, 1.0 - p_over


def _shin_z(q_over: float, q_under: float, iters: int = 100) -> float:
    """Solve Shin's z (insider fraction) for a two-outcome book by fixed-point iteration."""
    booksum = q_over + q_under
    z = 0.0
    for _ in range(iters):
        num = np.sqrt(z**2 + 4.0 * (1.0 - z) * q_over**2 / booksum) + np.sqrt(
            z**2 + 4.0 * (1.0 - z) * q_under**2 / booksum
        )
        z_new = (num - 2.0) / (booksum - 2.0) if booksum != 2.0 else 0.0
        z_new = float(np.clip(z_new, 0.0, 0.2))
        if abs(z_new - z) < 1e-10:
            break
        z = z_new
    return z


def _shin_prob(q: float, booksum: float, z: float) -> float:
    return (np.sqrt(z**2 + 4.0 * (1.0 - z) * q**2 / booksum) - z) / (2.0 * (1.0 - z))
