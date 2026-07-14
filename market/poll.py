"""Poll every book you can reach, continuously, timestamped. Not one book. All of them.

This is the intake for the whole market layer. A `Provider` returns a list of `BookQuote` for a
game's 2H total at a moment in time; `poll_once` fans out across providers and stamps every quote.

Ships with a `FixtureProvider` so `python -m market.poll --demo` runs fully offline. Real providers
(e.g. The Odds API) need a key and network — they import `requests` lazily and are intentionally
thin; wire them once the environment can reach them.
"""
from __future__ import annotations

import argparse
import time
from typing import Protocol

from .fair import BookQuote, fair_line
from .outliers import find_outliers


class Provider(Protocol):
    name: str

    def fetch(self, game_id: str) -> list[BookQuote]:
        ...


class FixtureProvider:
    """Deterministic synthetic quotes: a sharp anchor plus soft books, one of them badly off.

    Used for offline demos and tests. The soft book "lazybook" is deliberately 4 points high so the
    outlier ranker has something real to find.
    """

    name = "fixture"

    def fetch(self, game_id: str) -> list[BookQuote]:
        now = time.time()
        return [
            BookQuote("pinnacle", 104.5, -105, -105, ts=now, is_sharp=True),
            BookQuote("circa", 104.5, -108, -108, ts=now, is_sharp=True),
            BookQuote("draftkings", 105.0, -110, -110, ts=now),
            BookQuote("fanduel", 104.0, -112, -108, ts=now),
            BookQuote("lazybook", 108.5, -110, -110, ts=now),  # 4 pts off sharp consensus
        ]


def poll_once(game_id: str, providers: list[Provider]) -> list[BookQuote]:
    """Fetch from every provider, stamping any quote that arrived without a timestamp."""
    now = time.time()
    quotes: list[BookQuote] = []
    for p in providers:
        try:
            fetched = p.fetch(game_id)
        except Exception as e:  # a dead provider must not take the poll down
            print(f"[warn] provider {p.name} failed: {e}")
            continue
        for q in fetched:
            if q.ts is None:
                q.ts = now
            quotes.append(q)
    return quotes


def demo() -> None:
    game = "DEMO-2026-07-14-NCAAB-0001"
    quotes = poll_once(game, [FixtureProvider()])
    fair = fair_line(quotes)
    print(f"game={game}")
    print(f"fair line: {fair.line:.1f}  (anchor={fair.anchor}, P(over)={fair.p_over:.3f})\n")
    print("book quotes:")
    for q in quotes:
        tag = "sharp" if (q.is_sharp or q.book in ('pinnacle', 'circa')) else "soft "
        print(f"  {tag} {q.book:11s} line={q.line:6.1f}  o={q.over_odds:+.0f} u={q.under_odds:+.0f}")
    print("\noutliers (edges that need no model):")
    for o in find_outliers(quotes, fair, min_gap=1.0):
        print(
            f"  {o.book:11s} bet {o.side.upper():5s} @ {o.soft_line:6.1f} "
            f"(gap {o.gap_points:+.1f} pts, est. prob edge {o.prob_edge:+.3f})"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="poll books for 2H totals")
    ap.add_argument("--demo", action="store_true", help="run offline against the fixture provider")
    args = ap.parse_args()
    if args.demo:
        demo()
    else:
        print("Live polling needs a provider + network + key. Run with --demo for the offline demo.")
        print("Wire a real Provider (e.g. The Odds API) in market/providers.py and pass it to poll_once().")


if __name__ == "__main__":
    main()
